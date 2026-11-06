"""The Thinkers and gap roles: no vetoes, no impersonation, and panels that run."""

import asyncio

import pytest

from jjv import registry
from jjv.orchestrator import Config, Orchestrator, convene
from jjv.thinkers import GAP_ROLES, THINKER_PRESETS, THINKERS
from tests.test_orchestrator import Fake, finding, reply_for

NEW = [*THINKERS, *GAP_ROLES]


def test_counts():
    assert len(THINKERS) == 7
    assert len(GAP_ROLES) == 5
    assert len(THINKER_PRESETS) == 6
    assert len(registry.ALL_ARCHETYPES) == 58


@pytest.mark.parametrize("a", NEW, ids=lambda a: a["id"])
def test_new_archetypes_earn_power_before_they_get_it(a):
    assert a["veto"] is False and a["veto_dimensions"] == []
    assert a["library"] is True and a["role"] == "judge"
    assert 0 < a["weight"] <= 1.0


@pytest.mark.parametrize("a", NEW, ids=lambda a: a["id"])
def test_every_rubric_line_says_what_each_score_means(a):
    assert len(a["rubric"]) >= 3
    for d in a["rubric"]:
        assert set(d["anchors"]) == {1, 3, 5} and all(d["anchors"].values()), d["name"]


@pytest.mark.parametrize("a", THINKERS, ids=lambda a: a["id"])
def test_thinkers_are_methods_not_impersonations(a):
    persona = " ".join(a["persona"].split())
    assert a["category"] == "Thinkers" and a["inspired_by"]
    assert a["inspired_by"] in persona
    assert "You are not any of them" in persona
    assert "never quote or paraphrase them" in persona
    assert "never claim their endorsement" in persona


def test_shadow_reader_offers_readings_not_facts():
    persona = " ".join(registry.get("shadow_reader")["persona"].split())
    assert "judgment only" in persona
    assert "state of mind of a real person" in persona


def test_assumption_tester_sorts_objections_into_three_kinds():
    persona = registry.get("assumption_tester")["persona"]
    assert all(k in persona for k in ("[impossible]", "[unproven]", "[disliked]"))


@pytest.mark.parametrize("name", THINKER_PRESETS)
def test_new_presets_convene(name):
    judges = convene(name)
    assert 3 <= len(judges) <= 6


def test_every_new_preset_bargains():
    assert all("nash_agent" in m for m in THINKER_PRESETS.values())


def test_every_new_archetype_sits_on_a_preset():
    seated = {m for members in THINKER_PRESETS.values() for m in members}
    assert {a["id"] for a in NEW} <= seated


def test_a_blocker_from_a_thinker_is_cheap_talk_and_forces_nothing():
    def script(kind, aid, req):
        if aid == "paradox_hunter":
            return reply_for(aid, 2, "reject", [finding("loud", "blocker", "Stable definitions")])
        return reply_for(aid)
    panel = convene("Thinkers Panel")
    run = asyncio.run(Orchestrator(Fake(script), Config()).review("the subject", panel))
    settlement = run["rounds"][-1]["settlement"]
    assert settlement["cheap_talk"]
    assert settlement["forced"] == []
