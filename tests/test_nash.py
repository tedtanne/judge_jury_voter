"""Tests for the Nash_Agent bargaining kernel. No API key needed."""

from jjv.nash import NASH_AGENT, NASH_RUBRIC, NashBroker


def V(pid, findings, **kw):
    return {"archetype_id": pid, "findings": findings, **kw}


def F(title, severity="major", dimension=None, cost=None):
    f = {"title": title, "severity": severity, "dimension": dimension}
    if cost is not None:
        f["cost"] = cost
    return f


def test_archetype_record_is_a_neutral_broker():
    assert NASH_AGENT["name"] == "Nash_Agent"
    assert NASH_AGENT["veto"] is False
    assert NASH_AGENT["library"] is True
    assert len(NASH_RUBRIC) == 5


def test_credible_veto_is_forced_and_cheap_talk_is_not():
    s = NashBroker(budget=3).solve([
        V("security", [F("SQL injection", "blocker", "injection")],
          veto=True, veto_dimensions=["injection"]),
        V("designer", [F("Kill the whole feature", "blocker", "craft")],
          recommendation="reject"),
    ])
    assert s.forced == ["sql-injection"]
    assert "sql-injection" in s.address_now
    whats = {c["what"] for c in s.cheap_talk}
    assert "recommended reject without a veto" in whats
    assert any("Kill the whole feature" in w for w in whats)


def test_veto_outside_its_dimension_is_cheap_talk():
    s = NashBroker().solve([
        V("security", [F("Rename variables", "blocker", "readability")],
          veto=True, veto_dimensions=["injection"]),
    ])
    assert s.forced == []
    assert s.cheap_talk


def test_budget_forces_a_split_and_every_raiser_gets_something():
    # Two parties, each with two majors (cost 2); budget 4 fits two findings.
    s = NashBroker(budget=4).solve([
        V("eng", [F("Retry storm"), F("No backpressure")]),
        V("writer", [F("Missing runbook"), F("Wrong API example")]),
    ])
    assert s.cost <= 4
    assert all(g > 0 for g in s.gains.values())  # Nash product spreads surplus
    assert s.pareto_optimal is True


def test_change_averse_veto_holder_blocks_nothing_it_cannot_accept():
    # Simplifier holds a veto over complexity and hates change; every veto-holder must
    # end up at least as well off as the disagreement point.
    s = NashBroker(budget=10).solve([
        V("simplifier", [F("Delete the plugin layer", "minor")],
          veto=True, veto_dimensions=["complexity"], change_aversion=2.0),
        V("eng", [F("Add caching tier", "major", cost=3), F("Add metrics", "minor")]),
    ])
    assert s.individually_rational and s.is_equilibrium
    assert s.gains["simplifier"] >= 0


def test_endorsement_merges_and_raises_value():
    s = NashBroker(budget=2).solve([
        V("eng", [F("Unbounded queue")]),
        V("pm", [F("Confusing onboarding")], endorses=["unbounded queue"]),
        V("writer", [F("Confusing onboarding")]),
    ])
    assert s.findings["unbounded-queue"].endorsed_by == ["pm"]
    assert len(s.address_now) == 1


def test_reputation_discounts_past_cheap_talk():
    b = NashBroker(history={"loud": {"rounds": 4, "cheap_talk": 4}})
    s = b.solve([V("loud", [F("x")]), V("quiet", [F("y")])])
    players, *_ = b.build([V("loud", [F("x")])])
    assert players["loud"].weight == 0.5
    assert s.exact


def test_digest_publishes_rule_and_math():
    s = NashBroker(budget=2).solve([V("eng", [F("Retry storm")])])
    text = s.to_digest()
    assert "Selection rule" in text and "Surplus over disagreement" in text


def test_large_panels_fall_back_to_local_search():
    findings = [F(f"issue {i}", "minor") for i in range(20)]
    s = NashBroker(budget=5).solve([V("eng", findings)])
    assert not s.exact and s.cost <= 5 and s.pareto_optimal is None
