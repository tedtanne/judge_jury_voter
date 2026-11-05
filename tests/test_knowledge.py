"""Grounded runs, driven by a scripted backend and a stand-in knowledge base."""

import asyncio
import json
import subprocess

import pytest

from jjv import cli, voter
from jjv.backend import knowledge_server
from jjv.knowledge import (MAX_LOOKUPS, KnowledgeSession, KnowledgeUnavailable, km_sessions,
                           summarize)
from jjv.orchestrator import Config, Orchestrator, convene
from jjv.registry import get
from jjv import verdicts as V
from tests.test_orchestrator import PHYSICS, Fake, finding, reply_for

TOOLS = [{"name": "search_knowledge_base", "description": "d", "input_schema": {"type": "object"}},
         {"name": "read_knowledge_record", "description": "d", "input_schema": {"type": "object"}}]


def handler(name, args):
    if name == "read_knowledge_record":
        if args["id"].startswith("gone"):
            return json.dumps({"error": "no record"})
        return json.dumps({"id": args["id"], "body": "private note text", "content_hash": f"h-{args['id']}"})
    return json.dumps({"results": []})


def session():
    return KnowledgeSession(TOOLS, handler, lambda: 2)


def run_review(fake, panel=PHYSICS, **config):
    made = []

    def factory():
        made.append(session())
        return made[-1]

    orchestrator = Orchestrator(fake, Config(knowledge=True, **config), knowledge=factory)
    return asyncio.run(orchestrator.review("the subject", panel)), made


def cited_finding(*ids, title="t"):
    return {**finding(title), "citations": list(ids)}


# The session

def test_session_records_reads_only():
    s = session()
    s.call("search_knowledge_base", {"query": "x"})
    assert s.reads == {}
    s.call("read_knowledge_record", {"id": "n1"})
    s.call("read_knowledge_record", {"id": "gone"})
    assert s.reads == {"n1": "h-n1"}


def test_session_stops_at_the_lookup_limit():
    s = session()
    for _ in range(MAX_LOOKUPS):
        assert "limit" not in s.call("search_knowledge_base", {"query": "x"})
    assert "limit" in s.call("read_knowledge_record", {"id": "n1"})
    assert s.reads == {}


def test_a_failing_lookup_is_returned_without_its_details():
    def broken(name, args):
        raise KeyError("/Users/someone/private/path")
    out = json.loads(KnowledgeSession(TOOLS, broken).call("search_knowledge_base", {}))
    assert out == {"error": "lookup failed: KeyError"}


def test_missing_km_is_a_clear_error(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "km.jjv_bridge", None)
    with pytest.raises(KnowledgeUnavailable):
        km_sessions()


# Off by default

def test_an_ordinary_run_has_no_trace_of_knowledge():
    fake = Fake()
    run = asyncio.run(Orchestrator(fake, Config()).review("the subject", PHYSICS))
    assert "knowledge" not in run
    assert all(r.knowledge is None for r in fake.requests)
    assert all("knowledge base" not in r.prompt for r in fake.requests)
    assert all("citations" not in json.dumps(r.schema) for r in fake.requests)


def test_an_ordinary_run_drops_citations_a_model_invents():
    def script(kind, aid, req):
        return reply_for(aid, findings=[cited_finding("n1")])
    run = asyncio.run(Orchestrator(Fake(script), Config(jury=False)).review("s", PHYSICS))
    assert all("citations" not in f for v in run["rounds"][0]["judge"] for f in v["findings"])


# Grounded runs

def test_judges_are_told_and_each_gets_its_own_session():
    fake = Fake()
    run, made = run_review(fake, jury=False)
    judges = [r for r in fake.requests if r.label.startswith("judge")]
    assert len({id(r.knowledge) for r in judges}) == len(PHYSICS) == len(made)
    assert all("knowledge base" in r.prompt and "citations" in json.dumps(r.schema) for r in judges)
    assert run["knowledge"]["enabled"] is True


def test_session_lasts_from_judge_to_jury():
    fake = Fake()
    run_review(fake)
    by_judge = {}
    for r in fake.requests:
        by_judge.setdefault(r.label.split(":")[1], set()).add(id(r.knowledge))
    assert all(len(ids) == 1 for ids in by_judge.values())


def test_drafter_gets_no_knowledge():
    fake = Fake()
    orchestrator = Orchestrator(fake, Config(knowledge=True, jury=False, max_rounds=1), knowledge=session)
    asyncio.run(orchestrator.generate("brief", PHYSICS))
    assert [r.knowledge for r in fake.requests if r.label.startswith("draft")] == [None]


def _reads_then_cites(read, cite):
    def script(kind, aid, req):
        if kind == "judge":
            for record_id in read:
                req.knowledge.call("read_knowledge_record", {"id": record_id})
            return reply_for(aid, findings=[cited_finding(*cite, title=f"t-{aid}")])
        return reply_for(aid, findings=[])
    return script


def test_citation_of_a_read_record_is_kept_with_its_version():
    run, _ = run_review(Fake(_reads_then_cites(["n1"], ["n1"])), jury=False)
    k = run["knowledge"]
    assert {c["id"] for c in k["cited"]} == {"n1"} and k["cited"][0]["content_hash"] == "h-n1"
    assert k["rejected_citations"] == []


def test_citation_of_an_unread_record_is_rejected_but_the_finding_stays():
    run, _ = run_review(Fake(_reads_then_cites([], ["n9"])), jury=False)
    findings = [f for v in run["rounds"][0]["judge"] for f in v["findings"]]
    assert findings and all(f["citations"] == [] for f in findings)
    assert run["knowledge"]["cited"] == []
    assert {r["id"] for r in run["knowledge"]["rejected_citations"]} == {"n9"}


def test_one_judges_read_does_not_cover_another_judge():
    first = PHYSICS[0]["id"]

    def script(kind, aid, req):
        if aid == first:
            req.knowledge.call("read_knowledge_record", {"id": "n1"})
        return reply_for(aid, findings=[cited_finding("n1", title=f"t-{aid}")])

    run, _ = run_review(Fake(script), jury=False)
    assert len(run["knowledge"]["cited"]) == 1
    assert len(run["knowledge"]["rejected_citations"]) == len(PHYSICS) - 1


def test_citation_survives_the_jury_round_without_being_restated():
    a = get(PHYSICS[0]["id"])
    first = V.normalize(reply_for(a["id"], findings=[cited_finding("n1")]), a, "A", citable={"n1"})
    fid = first["findings"][0]["id"]
    kept = {**finding(), "id": fid}
    second = V.normalize(reply_for(a["id"], findings=[kept]), a, "A", previous=first, citable={"n1"})
    assert second["findings"][0]["citations"] == ["n1"]


@pytest.mark.parametrize("bad", ["n1", 7, None, {"id": "n1"}, [7, None, ["n1"]]])
def test_malformed_citations_are_ignored(bad):
    a = get(PHYSICS[0]["id"])
    raw = reply_for(a["id"], findings=[{**finding(), "citations": bad}])
    assert V.normalize(raw, a, "A", citable={"n1"})["findings"][0]["citations"] == []


def test_digest_shows_what_a_finding_cites():
    a = get(PHYSICS[0]["id"])
    v = V.normalize(reply_for(a["id"], findings=[cited_finding("n1")]), a, "A", citable={"n1"})
    assert "[cites n1]" in V.digest([v], "B", "fence")


def test_duplicate_findings_merge_their_citations_without_changing_them():
    a = get(PHYSICS[0]["id"])
    one = V.normalize(reply_for(a["id"], findings=[cited_finding("n1")]), a, "A", citable={"n1"})
    two = V.normalize(reply_for(a["id"], findings=[cited_finding("n2")]), a, "B", citable={"n2"})
    two["findings"][0]["id"] = one["findings"][0]["id"]
    merged = voter.merge_findings([one, two])
    assert merged[0]["citations"] == ["n1", "n2"]
    assert one["findings"][0]["citations"] == ["n1"]


def test_run_record_holds_no_note_text(tmp_path):
    run, _ = run_review(Fake(_reads_then_cites(["n1"], ["n1"])), jury=False, store=str(tmp_path / "runs"))
    saved = (tmp_path / "runs" / f"{run['id']}.json").read_text()
    assert "private note text" not in saved and '"content_hash": "h-n1"' in saved


def test_withheld_counts_reach_the_run_record():
    run, made = run_review(Fake(), jury=False)
    assert run["knowledge"]["withheld"] == 2 * len(made)


def test_a_failed_run_still_records_what_was_read():
    def script(kind, aid, req):
        req.knowledge.call("read_knowledge_record", {"id": "n1"})
        raise RuntimeError("model down")
    run, _ = run_review(Fake(script), jury=False, retries=0)
    assert run["status"] == "failed" and run["knowledge"]["reads"]


def test_git_cannot_pick_up_a_grounded_runs_records(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    run, _ = run_review(Fake(), jury=False, store=str(tmp_path / "runs"))
    assert (tmp_path / "runs" / f"{run['id']}.json").exists()
    status = subprocess.run(["git", "-C", str(tmp_path), "status", "--porcelain"],
                            capture_output=True, text=True, check=True)
    assert status.stdout == ""


def test_an_ordinary_run_writes_no_gitignore(tmp_path):
    asyncio.run(Orchestrator(Fake(), Config(jury=False, store=str(tmp_path))).review("s", PHYSICS))
    assert not (tmp_path / ".gitignore").exists()


def test_summarize_with_nothing():
    assert summarize("t", {}, [])["scope"] == {"tag": "t"}


# The server and the CLI

def test_server_exposes_only_the_session(monkeypatch):
    made = {}

    def tool(name, description, schema):
        return lambda fn: (name, fn)

    def create(name, tools):
        made.update(name=name, tools=dict(tools))
        return "server"

    s = session()
    assert knowledge_server(s, create, tool) == "server"
    assert made["name"] == "km" and set(made["tools"]) == {t["name"] for t in TOOLS}
    reply = asyncio.run(made["tools"]["read_knowledge_record"]({"id": "n1"}))
    assert json.loads(reply["content"][0]["text"])["id"] == "n1" and s.reads


def test_real_sdk_accepts_the_server():
    sdk = pytest.importorskip("claude_agent_sdk")
    assert knowledge_server(session(), sdk.create_sdk_mcp_server, sdk.tool)["name"] == "km"


def test_cli_tag_turns_knowledge_on_and_missing_km_stops_before_any_call(monkeypatch, tmp_path, capsys):
    import sys
    monkeypatch.setitem(sys.modules, "km.jjv_bridge", None)
    subject = tmp_path / "s.txt"
    subject.write_text("x")
    code = cli.main(["review", str(subject), "--panel", "Physics of Compute",
                     "--knowledge-tag", "jjv_test", "--store", str(tmp_path / "runs")])
    assert code == 2 and "km package" in capsys.readouterr().err


def test_cli_summary_lists_citations():
    text = cli.knowledge_summary({"reads": [{}], "withheld": 1, "rejected_citations": [{}],
                                  "cited": [{"finding": "A-1", "id": "n1"}]})
    assert "A-1: n1" in text and "1 sensitive" in text and "Rejected 1" in text
