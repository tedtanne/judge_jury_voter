"""Shape tests for the domain role archetypes. No API key needed."""

from jjv import registry
from jjv.domain_roles import DOMAIN_PRESETS, DOMAIN_ROLES
from jjv.nash import NASH_AGENT


def test_ids_unique_and_library_only():
    ids = [r["id"] for r in DOMAIN_ROLES]
    assert len(ids) == len(set(ids))
    assert NASH_AGENT["id"] not in ids
    assert all(r["library"] for r in DOMAIN_ROLES)


def test_rubrics_are_complete():
    for r in DOMAIN_ROLES:
        assert len(r["rubric"]) == 5, r["id"]
        for dim in r["rubric"]:
            assert set(dim["anchors"]) == {1, 3, 5}
            assert dim["weight"] > 0


def test_veto_flag_matches_dimensions():
    for r in DOMAIN_ROLES:
        assert r["veto"] == bool(r["veto_dimensions"]), r["id"]


def test_personas_carry_house_rules_and_grounding():
    for r in DOMAIN_ROLES:
        assert "not an impersonation" in r["persona"]
        assert "cheap talk" in r["persona"]
        assert len(r["grounded_in"]) >= 5


def test_presets_reference_known_archetypes():
    for name, members in DOMAIN_PRESETS.items():
        assert 4 <= len(members) <= 6, name
        assert set(members) <= set(registry.BY_ID), (name, set(members) - set(registry.BY_ID))


def test_nash_agent_v2_covers_coalitions_and_computability():
    p = NASH_AGENT["persona"]
    assert NASH_AGENT["version"] == 2
    assert "coalitions" in p.lower() and "PPAD" in p and "stop" in p
