"""Every phase of a run, driven by a scripted backend. No API key, no SDK."""

import asyncio
import json
import re

import pytest

from jjv import cli, orchestrator
from jjv.backend import BackendError, Reply
from jjv.eval_broker import run_live_comparison
from jjv.orchestrator import Config, Orchestrator, convene, live_run_fn
from jjv.registry import ALL_ARCHETYPES, PRESET_PANELS, get


def reply_for(archetype_id, score=4, rec="approve", findings=()):
    a = get(archetype_id)
    return {"scores": {d["name"]: score for d in a["rubric"]}, "rationale": "r",
            "recommendation": rec, "findings": list(findings), "changed_mind": "nothing"}


def finding(title="t", sev="major", dim="x"):
    return {"title": title, "severity": sev, "dimension": dim, "location": "l", "detail": "d"}


class Fake:
    """``script(kind, archetype_id, request)`` returns a reply dict, or raises."""

    def __init__(self, script=None, cost=0.01):
        self.script = script or (lambda kind, aid, req: reply_for(aid))
        self.cost = cost
        self.requests = []
        self.drafts = 0

    async def ask(self, request):
        self.requests.append(request)
        kind, aid = request.label.split(":")
        self.drafts += kind == "draft"
        if kind == "draft":
            return Reply(f"draft {self.drafts}", self.cost)
        request.draft_number = self.drafts
        return Reply(self.script(kind, aid, request), self.cost)

    def prompts(self, kind):
        return {r.label.split(":")[1]: r.prompt for r in self.requests
                if r.label.startswith(kind)}


def review(fake, panel, **config):
    return asyncio.run(Orchestrator(fake, Config(**config)).review("the subject", panel))


def generate(fake, panel, **config):
    return asyncio.run(Orchestrator(fake, Config(**config)).generate("the brief", panel))


PHYSICS = convene("Physics of Compute")


def test_every_preset_convenes_and_auto_convene_skips_library_and_generator():
    for name in PRESET_PANELS:
        assert convene(name)
    ids = {a["id"] for a in convene(discipline="code")}
    assert ids == {"staff_engineer", "security_reviewer"}
    with pytest.raises(ValueError):
        convene("Docs Crit", discipline="code")
    with pytest.raises(ValueError):
        convene(discipline="astrology")


def test_review_walks_the_state_machine_and_approves():
    run = review(Fake(), PHYSICS)
    phases = [e["phase"] for e in run["events"] if e["type"] == "phase"]
    assert phases == ["SELECT", "JUDGE", "JURY", "VOTE"]
    assert run["status"] == "done" and run["phase"] == "DONE"
    assert run["result"]["decision"] == "approve"
    assert len(run["rounds"][0]["jury"]) == len(PHYSICS)


def test_physics_panel_veto_is_forced_through_the_broker_and_blocks_approval():
    def script(kind, aid, req):
        if aid == "thermodynamicist":
            return reply_for(aid, 5, "reject", [finding("Beats Landauer", "blocker",
                                                        "physical-correctness")])
        return reply_for(aid, 5)
    run = review(Fake(script), PHYSICS)
    assert run["result"]["decision"] == "reject"
    assert [f["title"] for f in run["result"]["fixes"]] == ["Beats Landauer"]
    assert run["rounds"][0]["settlement"]["forced"]


def test_a_veto_written_as_its_rubric_name_stays_credible():
    """Found in a live run: Judges wrote "Physical correctness", not the veto word."""
    def script(kind, aid, req):
        if aid == "thermodynamicist":
            return reply_for(aid, 5, "reject", [finding("Heat", "blocker", "Physical correctness")])
        if aid == "metering_economist":
            return reply_for(aid, 5, "reject", [finding("Price", "blocker", "Cost recovery")])
        return reply_for(aid, 5)
    run = review(Fake(script), PHYSICS)
    assert len(run["result"]["vetoes"]) == 2
    assert len(run["rounds"][0]["settlement"]["forced"]) == 2
    assert run["rounds"][0]["settlement"]["cheap_talk"] == []


def test_judges_are_independent_and_the_digest_is_anonymous():
    fake = Fake(lambda k, aid, r: reply_for(aid, findings=[finding("by-" + aid)]))
    run = review(fake, PHYSICS)
    assert all("by-" not in p for p in fake.prompts("judge").values())
    alias = run["aliases"]["thermodynamicist"]
    text = fake.prompts("jury")["metering_economist"]
    assert f"Judge {alias}:" in text and "NASH_AGENT SETTLEMENT PROPOSAL" in text
    # Titles are the Judges' own words; the machinery must add no archetype id.
    stripped = text.replace("by-thermodynamicist", "")
    assert "thermodynamicist" not in stripped


def test_broker_is_not_a_player_and_no_broker_means_no_settlement():
    run = review(Fake(), PHYSICS)
    settlement = run["rounds"][0]["settlement"]
    assert run["aliases"]["nash_agent"] not in settlement["gains"]
    assert len(settlement["gains"]) == len(PHYSICS) - 1

    fake = Fake()
    run = review(fake, convene("Docs Crit"))
    assert "settlement" not in run["rounds"][0]
    assert "SETTLEMENT" not in " ".join(fake.prompts("jury").values())


def test_endorsements_from_the_jury_reach_the_voter():
    def script(kind, aid, req):
        if aid == "staff_engineer":
            return reply_for(aid, findings=[finding()])
        if kind == "jury":
            seen = re.search(r"- (\w-1) \[", req.prompt).group(1)
            return reply_for(aid) | {"endorses": [seen, "Z-9"]}
        return reply_for(aid)

    run = review(Fake(script), convene(ids=["staff_engineer", "product_lead"]))
    assert run["result"]["findings"][0]["endorsed_by"] == ["product_lead"]


def test_no_jury_flag_and_single_judge_skip_deliberation():
    assert "jury" not in review(Fake(), PHYSICS, jury=False)["rounds"][0]
    assert "jury" not in review(Fake(), convene(ids=["staff_engineer"]))["rounds"][0]


def test_a_bad_reply_is_retried_then_recorded_and_the_panel_carries_on():
    calls = []

    def script(kind, aid, req):
        if aid == "evidence_auditor" and kind == "judge":
            calls.append(1)
            return {"recommendation": "nonsense"}
        return reply_for(aid)

    run = review(Fake(script), PHYSICS)
    assert len(calls) == 2 and run["status"] == "done"
    assert run["failures"][0]["archetype_id"] == "evidence_auditor"
    assert len(run["rounds"][0]["judge"]) == len(PHYSICS) - 1


def test_a_retry_can_succeed():
    calls = []

    def script(kind, aid, req):
        calls.append(aid)
        if calls.count(aid) == 1:
            raise BackendError("overloaded", cost=0.5)
        return reply_for(aid)

    run = review(Fake(script, cost=0), convene(ids=["staff_engineer"]))
    assert run["status"] == "done" and not run["failures"] and run["cost_usd"] == 0.5


def test_a_silent_veto_holder_blocks_approve():
    def script(kind, aid, req):
        if aid == "thermodynamicist":
            raise BackendError("down")
        return reply_for(aid, 5)
    run = review(Fake(script), PHYSICS)
    assert run["result"]["decision"] == "revise"
    assert run["result"]["missing_vetoes"] == ["thermodynamicist"]


def test_no_quorum_fails_without_a_decision():
    def script(kind, aid, req):
        raise BackendError("down")
    run = review(Fake(script), PHYSICS)
    assert run["status"] == "failed" and run["result"] is None and "of 5" in run["error"]


def test_jury_failure_keeps_the_independent_verdict():
    def script(kind, aid, req):
        if kind == "jury" and aid == "evidence_auditor":
            raise BackendError("down")
        return reply_for(aid, 5)
    run = review(Fake(script), PHYSICS)
    assert len(run["rounds"][0]["jury"]) == len(PHYSICS)
    assert run["result"]["decision"] == "approve"


def test_an_unexpected_exception_is_one_judges_failure_not_the_runs():
    def script(kind, aid, req):
        if aid == "evidence_auditor":
            raise RuntimeError("surprise")
        return reply_for(aid)
    run = review(Fake(script), PHYSICS)
    assert run["status"] == "done" and "surprise" in run["failures"][0]["error"]


def test_a_call_that_hit_its_budget_is_not_retried_and_its_spend_is_counted():
    calls = []

    def script(kind, aid, req):
        calls.append(aid)
        raise BackendError("Reached maximum budget", cost=0.3, retry=False)
    run = review(Fake(script, cost=0), convene(ids=["staff_engineer"]))
    assert len(calls) == 1 and run["cost_usd"] == 0.3 and run["status"] == "failed"


def test_verdicts_are_saved_before_the_jury_can_lose_them(tmp_path):
    def script(kind, aid, req):
        if kind == "jury":
            record = json.loads(next(tmp_path.glob("*.json")).read_text())
            assert len(record["rounds"][0]["judge"]) == len(PHYSICS)
            assert "proposal" in record["rounds"][0]
        return reply_for(aid)
    assert review(Fake(script), PHYSICS, store=str(tmp_path))["failures"] == []


def test_a_jury_cannot_talk_a_veto_away():
    def script(kind, aid, req):
        if aid == "thermodynamicist" and kind == "judge":
            return reply_for(aid, 5, findings=[finding("Heat", "blocker", "physical-correctness")])
        return reply_for(aid, 5)
    run = review(Fake(script), PHYSICS)
    assert run["result"]["decision"] == "revise" and len(run["rounds"][0]["restored"]) == 1


def test_a_store_inside_the_repo_is_refused(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        Orchestrator(Fake(), Config(repo=str(tmp_path), store=str(tmp_path / "data")))


def test_fallback_to_weighted_vote_is_recorded():
    run = review(Fake(), convene("Docs Crit"))
    assert run["rounds"][0]["aggregator"] == "weighted_vote"
    assert any(e["type"] == "note" for e in run["events"])
    assert review(Fake(), PHYSICS)["rounds"][0]["aggregator"] == "nash_broker"


def test_digest_fence_is_fresh_and_settlement_sits_outside_it():
    fake = Fake(lambda k, aid, r: reply_for(aid, findings=[finding("by-" + aid)]))
    review(fake, PHYSICS)
    text = fake.prompts("jury")["metering_economist"]
    fence = re.search(r"</(digest-\w+)>", text).group(1)
    assert text.index(f"</{fence}>") < text.index("NASH_AGENT SETTLEMENT PROPOSAL")
    assert fence not in fake.prompts("jury")["thermodynamicist"]


@pytest.mark.parametrize("content", ["{broken", "[1, 2]", '{"x": 3}', '{"x": {"rounds": "a"}}'])
def test_a_damaged_reputation_file_cannot_kill_a_paid_run(tmp_path, content):
    path = tmp_path / "reputation.json"
    path.write_text(content)
    run = review(Fake(), PHYSICS, store=str(tmp_path))
    assert run["status"] == "done"
    assert path.read_text() == content          # kept for a person to look at
    assert any("reputation not updated" in e.get("text", "") for e in run["events"])


def test_an_unwritable_store_is_refused_before_any_spending(tmp_path):
    (tmp_path / "file").write_text("x")
    with pytest.raises(ValueError, match="cannot write"):
        Orchestrator(Fake(), Config(store=str(tmp_path / "file" / "runs")))


def test_a_store_lost_mid_run_keeps_the_result(tmp_path):
    store = tmp_path / "runs"
    fake = Fake()
    orch = Orchestrator(fake, Config(store=str(store)))
    store.rmdir()
    (tmp_path / "runs").write_text("now a file")
    run = asyncio.run(orch.review("s", PHYSICS))
    assert run["status"] == "done" and run["result"] and run["save_error"]


def test_an_unexpected_drafter_error_fails_the_run_cleanly():
    class Broken(Fake):
        async def ask(self, request):
            raise RuntimeError("bare SDK error")

    run = generate(Broken(), DOCS)
    assert run["status"] == "failed" and "bare SDK error" in run["error"]


@pytest.mark.parametrize("subject", ["", "   ", "\n\t"])
def test_a_blank_subject_is_refused_before_any_spending(subject):
    fake = Fake()
    with pytest.raises(ValueError, match="blank"):
        asyncio.run(Orchestrator(fake).review(subject, PHYSICS))
    assert fake.requests == []


def test_a_repeated_judge_is_refused_before_any_spending():
    fake = Fake()
    panel = convene(ids=["staff_engineer", "staff_engineer", "product_lead"])
    with pytest.raises(ValueError, match="twice"):
        asyncio.run(Orchestrator(fake).review("s", panel))
    assert fake.requests == []


def test_a_very_large_panel_keeps_every_finding_distinct():
    judges = [a for a in ALL_ARCHETYPES if a["role"] != "generator"]
    run = review(Fake(lambda k, aid, r: reply_for(aid, findings=[finding(aid)])), judges)
    ids = [f["id"] for v in run["rounds"][0]["jury"] for f in v["findings"]]
    assert len(ids) == len(judges) == len({i.lower() for i in ids})
    assert all(alias.isalpha() and alias.isupper() for alias in run["aliases"].values())


def test_cli_explains_a_missing_file_and_a_blank_subject(tmp_path, capsys):
    assert cli.main(["review", str(tmp_path / "nope.md"), "--panel", "Docs Crit"]) == 2
    assert "cannot read" in capsys.readouterr().err
    blank = tmp_path / "blank.md"
    blank.write_text("  ")
    assert cli.main(["review", str(blank), "--panel", "Docs Crit",
                     "--store", str(tmp_path / "runs")]) == 2
    assert "blank" in capsys.readouterr().err


def test_timeouts_count_as_failures():
    class Slow(Fake):
        async def ask(self, request):
            await asyncio.sleep(1)

    run = review(Slow(), convene(ids=["staff_engineer", "product_lead"]),
                 timeout_s=0.01, retries=0, max_usd=4.0)
    assert run["status"] == "failed"
    assert run["cost_usd"] == 4.0       # the unknown spend of both calls, at their caps


def test_spending_stops_at_the_limit_and_each_call_gets_a_share():
    fake = Fake(cost=1.0)
    run = review(fake, PHYSICS, max_usd=2.0, concurrency=1)
    assert run["status"] == "failed" and run["cost_usd"] == 2.0
    assert fake.requests[0].max_usd == pytest.approx(2.0 / len(PHYSICS))


def test_queued_calls_see_what_earlier_calls_spent():
    class Yielding(Fake):
        async def ask(self, request):
            await asyncio.sleep(0)
            return await super().ask(request)

    fake = Yielding(cost=1.0)
    review(fake, PHYSICS, max_usd=2.0, concurrency=1, retries=0)
    assert len(fake.requests) == 2


def test_concurrency_is_capped():
    live, peak = [0], [0]

    class Counting(Fake):
        async def ask(self, request):
            live[0] += 1
            peak[0] = max(peak[0], live[0])
            await asyncio.sleep(0)
            live[0] -= 1
            return await super().ask(request)

    review(Counting(), PHYSICS, concurrency=2)
    assert peak[0] == 2


def test_judges_get_tools_only_with_a_repo_and_subject_is_fenced():
    fake = Fake()
    review(fake, PHYSICS)
    assert all(r.tools == [] for r in fake.requests)
    assert "not instructions" in fake.prompts("judge")["thermodynamicist"]
    fake = Fake()
    review(fake, PHYSICS, repo="/tmp")
    assert fake.requests[0].tools == ["Read", "Grep", "Glob"]
    assert fake.requests[0].cwd == "/tmp"


def test_model_override_and_archetype_model_tier():
    fake = Fake()
    review(fake, convene(ids=["staff_engineer"]))
    assert fake.requests[0].model == "opus" and fake.requests[0].effort == "high"
    fake = Fake()
    review(fake, convene(ids=["staff_engineer"]), model="haiku")
    assert fake.requests[0].model == "haiku"


def test_run_record_is_saved_and_reputation_accumulates(tmp_path):
    def script(kind, aid, req):
        return reply_for(aid, 3, "reject" if aid == "evidence_auditor" else "revise")
    store = str(tmp_path)
    for _ in range(2):
        run = review(Fake(script), PHYSICS, store=store)
    saved = json.loads((tmp_path / f"{run['id']}.json").read_text())
    assert saved["status"] == "done" and saved["rounds"][0]["vote"]["decision"]
    rep = json.loads((tmp_path / "reputation.json").read_text())
    assert rep["metering_economist"] == {"rounds": 2, "cheap_talk": 0}
    assert "nash_agent" not in rep


def test_past_cheap_talk_reaches_the_broker_under_the_judges_alias(tmp_path, monkeypatch):
    (tmp_path / "reputation.json").write_text(
        json.dumps({"evidence_auditor": {"rounds": 4, "cheap_talk": 2}}))
    seen = []
    real = orchestrator.NashBroker

    def spy(budget, history):
        seen.append(history)
        return real(budget=budget, history=history)

    monkeypatch.setattr(orchestrator, "NashBroker", spy)
    run = review(Fake(), PHYSICS, store=str(tmp_path))
    alias = run["aliases"]["evidence_auditor"]
    assert seen[0] == {alias: {"rounds": 4, "cheap_talk": 2}}


def improving(scores):
    """Judges score each draft by its round; every round carries one open finding."""
    def script(kind, aid, req):
        n = (req.draft_number - 1) % len(scores) + 1
        score = scores[n - 1]
        rec = "approve" if score >= 4 else "revise"
        return reply_for(aid, score, rec, [] if score >= 4 else [finding(f"fix {n}")])
    return script


DOCS = convene(ids=["technical_writer", "product_lead", "nash_agent"])


def test_generate_loops_until_approved_and_feeds_fixes_back():
    fake = Fake(improving([2, 3, 5]))
    run = generate(fake, DOCS)
    assert run["stop_reason"] == "approved" and len(run["rounds"]) == 3
    assert run["draft"] == "draft 3" and run["result"]["decision"] == "approve"
    drafts = [r.prompt for r in fake.requests if r.label.startswith("draft")]
    assert "fix 1" in drafts[1] and "draft 1" in drafts[1] and "Revise" not in drafts[0]
    assert fake.requests[0].label == "draft:drafter"


def test_generate_stops_at_the_round_limit_and_on_a_plateau():
    assert generate(Fake(improving([2, 3, 3.5])), DOCS, max_rounds=2)["stop_reason"] == "round limit"
    run = generate(Fake(improving([3, 3, 5])), DOCS)
    assert run["stop_reason"] == "no further improvement" and len(run["rounds"]) == 2


def test_generate_keeps_the_best_round_when_a_later_one_regresses():
    run = generate(Fake(improving([3, 2, 5])), DOCS)
    assert run["best_round"] == 1 and run["draft"] == "draft 1" and run["result"]["score"] == 3


def test_generate_with_no_finished_round_fails_but_keeps_finished_work_otherwise():
    fake = Fake(improving([2, 3, 5]), cost=1.0)
    assert generate(fake, DOCS, max_usd=0.5)["status"] == "failed"
    run = generate(Fake(improving([2, 3, 5]), cost=1.0), DOCS, max_usd=7.0, concurrency=1)
    assert run["status"] == "done" and run["stop_reason"].startswith("stopped early")


def test_best_round_prefers_approved_and_fully_reviewed_rounds():
    def script(kind, aid, req):
        if req.draft_number == 1:                       # high score, no approval
            return reply_for(aid, 5, "revise", [finding("polish")])
        return reply_for(aid, 4)                        # lower score, approved
    run = generate(Fake(script), DOCS)
    assert run["stop_reason"] == "approved" and run["best_round"] == 2

    sec = convene(ids=["security_reviewer", "technical_writer", "product_lead"])

    def silent(kind, aid, req):
        if req.draft_number == 1:
            return reply_for(aid, 3, "revise", [finding("x")])
        if aid == "security_reviewer":
            raise BackendError("down")
        return reply_for(aid, 5, "revise", [finding("y")])
    assert generate(Fake(silent), sec, max_rounds=2)["best_round"] == 1


def test_weighted_vote_arm_runs_without_the_broker():
    run = generate(Fake(improving([2, 5])), DOCS, aggregator="weighted_vote")
    assert "settlement" not in run["rounds"][0] and run["rounds"][0]["vote"]["fixes"]


def test_live_comparison_hook_drives_both_arms_with_a_blind_panel():
    blind = convene(ids=["staff_engineer", "security_reviewer"])

    def script(kind, aid, req):
        if aid in ("staff_engineer", "security_reviewer"):
            return reply_for(aid, 5)
        return improving([3, 5])(kind, aid, req)

    run_fn = live_run_fn(Fake(script), DOCS, blind)
    summary = run_live_comparison(["brief"], run_fn)
    assert summary["nash_broker"]["mean_rounds"] == 2
    assert summary["weighted_vote"]["mean_score"] == 5


def test_live_comparison_refuses_a_rigged_setup():
    with pytest.raises(ValueError, match="overlaps"):
        live_run_fn(Fake(), DOCS, convene(ids=["product_lead"]))
    with pytest.raises(ValueError, match="Nash_Agent"):
        live_run_fn(Fake(), convene(ids=["product_lead"]), convene(ids=["staff_engineer"]))
