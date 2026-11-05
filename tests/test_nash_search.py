"""Scoped vetoes, shared rework cost, linked findings, and the broker's local search."""

import random

from jjv.eval_broker import make_panel
from jjv.nash import NashBroker


def V(pid, findings, **kw):
    return {"archetype_id": pid, "findings": findings, **kw}


def F(title, dimension="docs", severity="major"):
    return {"title": title, "severity": severity, "dimension": dimension}


def veto(pid, dimension, findings=()):
    return V(pid, list(findings), veto=True, veto_dimensions=[dimension])


def test_a_clean_veto_holder_does_not_block_fixes_outside_its_area():
    """Found by the panel: a clean security review left a code panel with no fixes."""
    s = NashBroker().solve([veto("sec", "security"), V("writer", [F("Fix the example")])])
    assert s.address_now == ["fix-the-example"]
    assert s.gains["sec"] < 0 and s.individually_rational and s.is_equilibrium


def test_a_lone_blocker_no_longer_loses_to_its_own_rework_cost():
    """Found by the panel: with 4 Judges a lone major was chosen and a lone blocker dropped."""
    others = [V(n, []) for n in "bcd"]
    for severity in ("minor", "major", "blocker"):
        s = NashBroker(budget=8).solve([V("a", [F("t", "x", severity)]), *others])
        assert s.address_now == ["t"], severity


def test_a_blocker_that_is_not_a_veto_can_still_be_cheap_talk():
    s = NashBroker(budget=8).solve([V("a", [F("t", "x", "blocker")]), V("b", [])])
    assert s.forced == [] and s.cheap_talk


def test_a_veto_holds_inside_a_linked_group_whoever_comes_first():
    plain = {"id": "G", "title": "t", "severity": "major", "dimension": "style"}
    held = {"id": "G", "title": "t", "severity": "blocker", "dimension": "security"}
    for order in ([V("eng", [plain]), veto("sec", "security", [held])],
                  [veto("sec", "security", [held]), V("eng", [plain])]):
        s = NashBroker(budget=8).solve(order)
        assert s.forced == ["g"] and s.findings["g"].dimension == "security"
        assert s.findings["g"].raised_by and not s.cheap_talk


def test_a_linked_member_is_not_blamed_for_anothers_blocker():
    other = {"id": "G", "title": "t", "severity": "minor", "dimension": "x"}
    loud = {"id": "G", "title": "t", "severity": "blocker", "dimension": "x"}
    s = NashBroker(budget=8).solve([V("quiet", [other]), V("loud", [loud])])
    assert {c["by"] for c in s.cheap_talk} == {"loud"}


def test_linked_findings_cost_the_budget_once():
    a = {"id": "G", "title": "t", "severity": "major", "dimension": "x"}
    s = NashBroker(budget=2).solve([V("a", [a]), V("b", [a]), V("c", [F("other", "x", "major")])])
    assert s.address_now == ["g"] and s.cost == 2


def test_a_veto_still_blocks_inside_its_own_area():
    s = NashBroker().solve([veto("sec", "security"),
                            V("eng", [F("Rework the auth flow", "security")])])
    assert s.address_now == []
    assert any("veto-holder" in n for n in s.notes)


def test_blocking_never_pays_for_any_veto_holder():
    """The equilibrium claim, checked directly: a block strips the holder's area."""
    rng = random.Random(11)
    for _ in range(100):
        panel = make_panel(rng)
        broker = NashBroker(budget=8)
        s = broker.solve(panel)
        players, findings, forced, _ = broker.build(panel)
        S = frozenset(s.address_now)
        for p in players.values():
            if p.veto:
                stripped = frozenset(k for k in S if k in forced
                                     or not p.can_veto(findings[k].dimension))
                assert (broker._utility(p, S, findings)
                        >= broker._utility(p, stripped, findings) - 1e-9)


def test_local_search_steps_over_veto_holders_sharing_an_area():
    """Found in a live run: many findings, two veto-holders, and an empty settlement."""
    panel = [veto(n, "security", [F(f"{n} {i}", "security") for i in range(10)]) for n in "ab"]
    s = NashBroker(budget=8).solve(panel)
    assert not s.exact and s.address_now
    assert s.individually_rational and s.cost <= 8
