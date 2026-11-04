"""Scoped vetoes and the broker's local search (panels over EXACT_LIMIT optional findings)."""

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
