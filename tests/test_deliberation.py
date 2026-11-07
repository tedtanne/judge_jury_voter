"""Negotiation rounds: Judges talk, agreement can replace the formula, and limits hold."""

import json
import re

import pytest

from jjv import cli, verdicts as V
from jjv.backend import BackendError
from jjv.orchestrator import Config, Orchestrator, convene
from tests.test_orchestrator import Fake, finding, reply_for, review

DOCS = convene("Docs Crit")         # four Judges, no Nash_Agent, no veto
PHYSICS = convene("Physics of Compute")


def raised_by_all(titles=("one", "two")):
    return lambda aid: [finding(f"{aid}-{t}") for t in titles]


def script(fix_list, *, message="", judge_findings=None):
    """Every Judge raises findings, then answers each Jury round with ``fix_list``."""
    judge_findings = judge_findings or raised_by_all()

    def play(kind, aid, req):
        found = judge_findings(aid)
        reply = reply_for(aid, findings=found)
        if kind == "jury":
            reply["fix_list"] = fix_list(aid, req) if callable(fix_list) else list(fix_list)
            reply["message"] = message
        return reply
    return play


def alias_in(prompt):
    return re.search(r"You are Judge (\w+)", prompt).group(1)


def another(prompt):
    """A finding id belonging to some other Judge; aliases are assigned at random."""
    return "B-1" if alias_in(prompt) == "A" else "A-1"


def proposed(prompt):
    line = re.search(r"Proposed fix list by id: (.*)", prompt).group(1)
    return [] if line == "none" else line.split(", ")


def own_ids(prompt):
    mine = json.loads(prompt.split("was:\n\n", 1)[1].split("\n\nANONYMIZED", 1)[0])
    return [f["id"] for f in mine["findings"]]


def jury_calls(fake):
    return sum(r.label.startswith("jury") for r in fake.requests)


def ids_of(run):
    return [f["id"] for v in run["rounds"][0]["judge"] for f in v["findings"]]


def test_the_default_is_one_round_with_no_negotiation():
    fake = Fake(script([]))
    rec = review(fake, DOCS)["rounds"][0]
    assert jury_calls(fake) == len(DOCS)
    assert "deliberation" not in rec and "agreed" not in rec
    assert rec["settled_by"] == "formula"
    jury = [r for r in fake.requests if r.label.startswith("jury")]
    assert all("fix_list" not in r.schema["properties"] for r in jury)
    assert all("negotiation round" not in r.prompt for r in jury)


def test_agreement_ends_the_talks_and_replaces_the_formula():
    fake = Fake(script(["A-1"]))
    rec = review(fake, DOCS, deliberation_rounds=3)["rounds"][0]
    assert jury_calls(fake) == len(DOCS)            # settled in the first round
    assert rec["agreed"] == ["a-1"] and rec["settled_by"] == "agreement"
    assert [f["id"] for f in rec["vote"]["fixes"]] == ["A-1"]
    assert "settlement" in rec                      # the formula stays on record


def test_judges_can_converge_over_rounds():
    def position(aid, req):
        return ["A-1"] if "negotiation round 2 of" in req.prompt else [aid]
    fake = Fake(script(position))
    rec = review(fake, DOCS, deliberation_rounds=3)["rounds"][0]
    assert jury_calls(fake) == 2 * len(DOCS)
    assert [d["agreed"] for d in rec["deliberation"]] == [None, ["a-1"]]


def test_no_agreement_runs_every_round_then_the_formula_decides():
    fake = Fake(script(lambda aid, req: [aid]))
    rec = review(fake, DOCS, deliberation_rounds=3)["rounds"][0]
    assert jury_calls(fake) == 3 * len(DOCS)
    assert "agreed" not in rec and rec["settled_by"] == "formula"
    want = set(rec["settlement"]["address_now"])
    assert {f["id"].lower() for f in rec["vote"]["fixes"]} == want


def test_agreement_cannot_talk_away_a_credible_veto():
    def found(aid):
        if aid == "thermodynamicist":
            return [finding("violates physics", "blocker", "physical-correctness")]
        return [finding(f"{aid}-note", "minor")]
    fake = Fake(script([], judge_findings=found))
    rec = review(fake, PHYSICS, deliberation_rounds=2)["rounds"][0]
    assert "agreed" not in rec and rec["settled_by"] == "formula"
    assert any(f["title"] == "violates physics" for f in rec["vote"]["fixes"])


def test_agreement_cannot_spend_past_the_budget():
    fake = Fake(script(lambda aid, req: ["A-1", "A-2", "B-1", "B-2"]))
    rec = review(fake, DOCS, deliberation_rounds=2, revision_budget=1.0)["rounds"][0]
    assert "agreed" not in rec and rec["settled_by"] == "formula"


def test_agreement_on_a_finding_that_does_not_exist_is_refused():
    rec = review(Fake(script(["Z-9"])), DOCS, deliberation_rounds=2)["rounds"][0]
    assert "agreed" not in rec


def test_a_judge_that_fails_has_not_agreed():
    base = script(["A-1"])

    def play(kind, aid, req):
        if kind == "jury" and aid == "simplifier":
            raise BackendError("down")
        return base(kind, aid, req)
    rec = review(Fake(play), DOCS, deliberation_rounds=2)["rounds"][0]
    assert "agreed" not in rec and rec["settled_by"] == "formula"


def test_nash_agent_scores_but_does_not_get_a_say_in_the_agreement():
    def position(aid, req):
        return ["Z-9"] if aid == "nash_agent" else proposed(req.prompt)
    rec = review(Fake(script(position)), PHYSICS, deliberation_rounds=2)["rounds"][0]
    assert rec["settled_by"] == "agreement"
    assert "z-9" not in rec["agreed"]


def test_a_veto_blocker_cannot_be_dropped_in_a_later_round():
    def play(kind, aid, req):
        blocker = finding("hot", "blocker", "physical-correctness")
        if aid != "thermodynamicist":
            found = [finding(f"{aid}-note", "minor")]
        else:
            found = [blocker] if "negotiation round 2" not in req.prompt else []
        reply = reply_for(aid, findings=found)
        if kind == "jury":
            reply["fix_list"] = [aid]
        return reply
    rec = review(Fake(play), PHYSICS, deliberation_rounds=2)["rounds"][0]
    assert any(f["title"] == "hot" for f in rec["vote"]["findings"])
    assert rec["restored"]


def test_a_link_made_in_an_early_round_lasts_to_the_end():
    def play(kind, aid, req):
        found = finding(f"{aid}-issue")
        if kind == "jury" and aid == "simplifier" and "round 1 of" in req.prompt:
            found["same_as"] = another(req.prompt)
        reply = reply_for(aid, findings=[found])
        if kind == "jury":
            reply["fix_list"] = [aid]
        return reply
    rec = review(Fake(play), DOCS, deliberation_rounds=2)["rounds"][0]
    assert len(rec["links"]) == 1


def test_linked_findings_count_as_one_when_comparing_lists():
    def play(kind, aid, req):
        found = finding(f"{aid}-issue")
        reply = reply_for(aid, findings=[found])
        if kind == "jury":
            # B-1 is linked to A-1. Half the panel names one id, half names the other.
            if alias_in(req.prompt) == "B":
                found["same_as"] = "A-1"
            reply["fix_list"] = ["A-1"] if alias_in(req.prompt) in "AC" else ["B-1"]
        return reply
    rec = review(Fake(play), DOCS, deliberation_rounds=2)["rounds"][0]
    assert rec["settled_by"] == "agreement" and rec["agreed"] == ["a-1"]


def test_messages_reach_the_others_inside_the_fence_and_anonymously():
    fake = Fake(script(lambda aid, req: own_ids(req.prompt),
                       message="I will defer mine if yours is fixed",
                       judge_findings=lambda aid: [finding("an issue")]))
    review(fake, DOCS, deliberation_rounds=2)
    last = fake.prompts("jury")["simplifier"]
    start, end = last.index("<digest-"), last.index("</digest-")
    assert start < last.index("Says: I will defer mine") < end
    assert "negotiation round 2 of 2" in last
    assert "Proposed fix list by id:" in last
    assert not any(a["id"] in last[start:end] or a["name"] in last[start:end] for a in DOCS)


def test_each_round_shares_the_spending_limit():
    fake = Fake(script(lambda aid, req: [aid]))
    review(fake, DOCS, deliberation_rounds=3, max_usd=1.0)
    jury = [r for r in fake.requests if r.label.startswith("jury")]
    assert jury[0].max_usd < 1.0 / len(DOCS) / 2    # later rounds are left money


def test_going_over_budget_mid_talks_stops_the_run_cleanly():
    fake = Fake(script(lambda aid, req: [aid]), cost=0.3)
    run = review(fake, DOCS, deliberation_rounds=3, max_usd=1.5)
    assert run["cost_usd"] < 3.0


@pytest.mark.parametrize("config", [
    {"deliberation_rounds": 0},
    {"deliberation_rounds": 2, "jury": False},
    {"deliberation_rounds": 2, "aggregator": "weighted_vote"},
])
def test_settings_that_cannot_work_are_refused(config):
    with pytest.raises(ValueError):
        Orchestrator(Fake(), Config(**config))


def test_the_cli_passes_the_rounds_through():
    args = cli.parser().parse_args(
        ["review", "x", "--panel", "Docs Crit", "--deliberation-rounds", "3"])
    assert args.deliberation_rounds == 3


def test_fix_list_must_be_a_list():
    a = DOCS[0]
    bad = reply_for(a["id"]) | {"fix_list": "A-1"}
    with pytest.raises(V.VerdictError):
        V.normalize(bad, a, "A")


def test_a_judge_that_names_no_list_has_not_agreed_and_nothing_crashes():
    def play(kind, aid, req):
        reply = reply_for(aid, findings=[finding(f"{aid}-x")])
        if kind == "jury" and aid != "simplifier":
            reply["fix_list"] = ["A-1"]
        return reply
    rec = review(Fake(play), DOCS, deliberation_rounds=2)["rounds"][0]
    assert "agreed" not in rec and rec["settled_by"] == "formula"
