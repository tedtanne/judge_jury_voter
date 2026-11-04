"""The broker's local search, used on panels with more than EXACT_LIMIT optional findings."""

from jjv.nash import NashBroker


def test_local_search_steps_over_two_veto_holders_who_each_lose_alone():
    """Found in a live run: 46 findings, two veto-holders, and an empty settlement."""
    def judge(name, dimension):
        return {"archetype_id": name, "veto": True, "veto_dimensions": [dimension],
                "findings": [{"title": f"{name} {i}", "severity": "major", "dimension": "x"}
                             for i in range(10)]}
    settlement = NashBroker(budget=8).solve([judge("a", "security"), judge("b", "complexity")])
    assert not settlement.exact and settlement.address_now
    assert settlement.individually_rational and settlement.cost <= 8


def test_an_empty_settlement_says_why():
    clean = {"archetype_id": "v", "veto": True, "veto_dimensions": ["security"], "findings": []}
    other = {"archetype_id": "o", "findings": [{"title": "t", "severity": "major"}]}
    settlement = NashBroker().solve([clean, other])
    assert settlement.address_now == [] and any("veto-holder" in n for n in settlement.notes)
