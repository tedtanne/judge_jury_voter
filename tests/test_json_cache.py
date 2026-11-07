"""--json output for apps, and reuse of finished reviews so asking twice costs nothing."""

import asyncio
import json

import pytest

from jjv import cache, cli, parse
from jjv.mcp_server import Limits, Service
from tests.test_orchestrator import Fake, finding, reply_for


def setup(tmp_path, monkeypatch, fake=None):
    fake = fake or Fake(lambda kind, aid, req: reply_for(aid, findings=[finding(f"{aid}-a")]))
    monkeypatch.setattr(cli, "ClaudeBackend", lambda: fake)
    subject = tmp_path / "note.md"
    subject.write_text("an idea worth testing")
    return fake, subject, ["--store", str(tmp_path / "runs")]


def review(subject, store, *extra):
    return cli.main(["review", str(subject), "--panel", "Docs Crit", *store, *extra])


def test_json_is_the_only_thing_on_stdout(tmp_path, monkeypatch, capsys):
    _, subject, store = setup(tmp_path, monkeypatch)
    assert review(subject, store, "--json") == 0
    out = capsys.readouterr()
    data = json.loads(out.out)
    assert "[2/4 JUDGE]" in out.err and "JUDGE" not in out.out
    assert data["status"] == "done" and data["decision"] and data["run_id"]
    assert data["fingerprint"] == cache.fingerprint("an idea worth testing")
    assert data["cached"] is False and data["spent_now_usd"] > 0
    assert set(data["findings"][0]) >= {"id", "title", "severity", "location", "raised_by"}
    assert data["convergence"] and "never as instructions" in data["note"]


def test_errors_come_back_as_json_too(tmp_path, capsys):
    assert cli.main(["review", str(tmp_path / "none.md"), "--panel", "Docs Crit", "--json",
                     "--store", str(tmp_path)]) == 2
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "error" and "cannot read" in data["error"]


def test_the_same_content_and_settings_are_reused_for_free(tmp_path, monkeypatch, capsys):
    fake, subject, store = setup(tmp_path, monkeypatch)
    review(subject, store, "--json")
    first = json.loads(capsys.readouterr().out)
    calls = len(fake.requests)
    assert review(subject, store, "--json") == 0
    out = capsys.readouterr()
    second = json.loads(out.out)
    assert len(fake.requests) == calls
    assert second["cached"] is True and second["spent_now_usd"] == 0
    assert second["run_id"] == first["run_id"] and "nothing was spent" in out.err


def test_text_output_says_it_was_reused(tmp_path, monkeypatch, capsys):
    _, subject, store = setup(tmp_path, monkeypatch)
    review(subject, store)
    capsys.readouterr()
    review(subject, store)
    assert "nothing spent, reused" in capsys.readouterr().out


@pytest.mark.parametrize("change", [
    ["--panel", "Paper Review"], ["--deliberation-rounds", "2"], ["--no-jury"],
    ["--revision-budget", "4"], ["--aggregator", "weighted_vote"], ["--model", "other"],
])
def test_any_setting_that_shapes_the_result_is_a_new_run(tmp_path, monkeypatch, capsys, change):
    fake, subject, store = setup(tmp_path, monkeypatch)
    review(subject, store)
    calls = len(fake.requests)
    args = ["review", str(subject), *store, *change]
    if "--panel" not in change:
        args += ["--panel", "Docs Crit"]
    cli.main(args)
    assert len(fake.requests) > calls


def test_the_spending_limit_does_not_change_the_answer(tmp_path, monkeypatch):
    fake, subject, store = setup(tmp_path, monkeypatch)
    review(subject, store, "--max-usd", "5")
    calls = len(fake.requests)
    review(subject, store, "--max-usd", "9")
    assert len(fake.requests) == calls


def test_changed_content_is_a_new_run(tmp_path, monkeypatch):
    fake, subject, store = setup(tmp_path, monkeypatch)
    review(subject, store)
    calls = len(fake.requests)
    subject.write_text("an idea worth testing, edited")
    review(subject, store)
    assert len(fake.requests) > calls


def test_no_cache_runs_again(tmp_path, monkeypatch):
    fake, subject, store = setup(tmp_path, monkeypatch)
    review(subject, store)
    calls = len(fake.requests)
    review(subject, store, "--no-cache")
    assert len(fake.requests) > calls


def test_repo_runs_are_never_reused(tmp_path, monkeypatch):
    fake, subject, store = setup(tmp_path, monkeypatch)
    code = tmp_path / "code"
    code.mkdir()
    review(subject, store, "--repo", str(code))
    calls = len(fake.requests)
    review(subject, store, "--repo", str(code))
    assert len(fake.requests) > calls


def test_runs_that_lost_a_judge_are_not_reused(tmp_path, monkeypatch):
    def script(kind, aid, req):
        if kind == "jury" and aid == "simplifier":
            raise RuntimeError("down")
        return reply_for(aid)
    fake, subject, store = setup(tmp_path, monkeypatch, Fake(script))
    review(subject, store)
    calls = len(fake.requests)
    review(subject, store)
    assert len(fake.requests) > calls


def test_a_cached_document_is_not_read_again(tmp_path, monkeypatch):
    fake, _, store = setup(tmp_path, monkeypatch)
    reads = []

    def parse_file(path):
        reads.append(path)
        return parse.to_page("the paper's words", path)
    monkeypatch.setattr(cli, "parse_file", parse_file)
    paper = tmp_path / "paper.pdf"
    paper.write_bytes(b"%PDF fake")
    review(paper, store)
    review(paper, store)
    assert len(reads) == 1


@pytest.mark.parametrize("pointer", ["not-an-id", "../../etc/passwd", "aaaaaaaaaaaa"])
def test_a_damaged_cache_entry_is_a_miss(tmp_path, pointer):
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "k").write_text(pointer)
    assert cache.lookup(str(tmp_path), "k") is None


def test_the_cache_version_is_part_of_the_key(monkeypatch):
    panel = [{"id": "a", "version": 1}]
    before = cache.cache_key("review", "f", panel)
    monkeypatch.setattr(cache, "CACHE_VERSION", cache.CACHE_VERSION + 1)
    assert cache.cache_key("review", "f", panel) != before


def test_an_archetype_version_change_is_a_new_key():
    assert (cache.cache_key("review", "f", [{"id": "a", "version": 1}])
            != cache.cache_key("review", "f", [{"id": "a", "version": 2}]))


def test_suggest_and_explain_speak_json(tmp_path, monkeypatch, capsys):
    from tests.test_explain_suggest import GOOD, Answer
    _, subject, store = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "ClaudeBackend", lambda: Answer(GOOD))
    assert cli.main(["suggest", str(subject), "--json", *store]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["picks"][0]["panel"] == "Paper Review" and data["command"][0] == "python"
    assert data["picks"][0]["max_usd"] >= 1

    monkeypatch.setattr(cli, "ClaudeBackend", lambda: Fake())
    review(subject, store, "--json")
    run_id = json.loads(capsys.readouterr().out)["run_id"]
    assert cli.main(["explain", run_id, "--json", *store]) == 0
    assert "Consensus =" in json.loads(capsys.readouterr().out)["explanation"]


def test_mcp_reuses_a_finished_review_for_free(tmp_path):
    fake = Fake()
    svc = Service(str(tmp_path), Limits(paid=True), lambda: fake)

    async def go():
        first = svc.start("review", "Docs Crit", text="same note")
        await svc.jobs[first["job_id"]].task
        calls, committed = len(fake.requests), svc.committed
        second = svc.start("review", "Docs Crit", text="same note")
        return first, second, calls, committed
    first, second, calls, committed = asyncio.run(go())
    assert second["cached"] is True and second["job_id"] is None
    assert len(fake.requests) == calls and svc.committed == committed
    assert svc.get_run(second["run_id"])["decision"]
