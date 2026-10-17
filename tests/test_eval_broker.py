"""Tests for the broker-vs-voting evaluation harness. No API key needed."""

import random

from jjv import eval_broker as E


def test_panels_are_reproducible():
    assert E.make_panel(random.Random(3)) == E.make_panel(random.Random(3))


def test_both_aggregators_respect_budget_and_vetoes():
    rng = random.Random(11)
    for _ in range(25):
        panel = E.make_panel(rng)
        _, findings, forced, _ = E.NashBroker().build(panel)
        floor = sum(findings[k].cost for k in forced)
        for select in E.AGGREGATORS.values():
            chosen = select(panel, 8.0)
            assert sum(findings[k].cost for k in chosen) <= max(8.0, floor) + 1e-9
            assert E.vetoes_satisfied(panel, chosen)


def test_loud_judge_only_inflates_a_judge_without_veto():
    rng = random.Random(5)
    panel = E.make_panel(rng)
    loud = E.make_loud(panel, rng)
    changed = [i for i, (a, b) in enumerate(zip(panel, loud)) if a != b]
    assert len(changed) == 1 and not panel[changed[0]]["veto"]
    assert loud[changed[0]]["recommendation"] == "reject"


def test_metrics_are_bounded():
    r = E.run_offline(trials=20, seed=2)
    for res in r.values():
        for m in ("loud_judge_displacement", "noise_stability",
                  "veto_satisfaction", "utilitarian_efficiency"):
            assert 0.0 <= getattr(res, m) <= 1.0
        assert res.judges_shut_out >= 0


def test_broker_resists_a_loud_judge_better_than_voting():
    # The headline claim, checked on a fixed seed so CI catches regressions.
    r = E.run_offline(trials=60, seed=7)
    assert r["nash_broker"].loud_judge_displacement < r["weighted_vote"].loud_judge_displacement
    assert r["nash_broker"].judges_shut_out <= r["weighted_vote"].judges_shut_out


def test_report_and_cli(tmp_path):
    out = tmp_path / "eval.md"
    assert E.main(["--trials", "5", "--seed", "1", "--out", str(out)]) == 0
    text = out.read_text()
    assert "| Metric |" in text and "Nash broker" in text


def test_live_comparison_with_stub_runner():
    def run_fn(subject, aggregator):
        return {"rounds": 2 if aggregator == "nash_broker" else 3, "score": 4.0}
    s = E.run_live_comparison(["a", "b"], run_fn)
    assert s["nash_broker"]["mean_rounds"] == 2 and s["weighted_vote"]["subjects"] == 2
