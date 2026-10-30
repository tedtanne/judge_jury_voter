"""Registry integrity: every preset resolves, every veto is scoped, docs match code."""

from pathlib import Path

import pytest

from jjv import registry
from jjv.archetypes import DEFAULT_ARCHETYPES
from jjv.legends import LEGEND_PRESETS, LEGENDS, PRESET_PANELS

ROOT = Path(__file__).resolve().parents[1]


def test_registry_is_consistent():
    assert registry.validate() == []


def test_roster_counts():
    assert len(LEGENDS) == 31
    assert len(DEFAULT_ARCHETYPES) == 6
    assert len(PRESET_PANELS) == 19
    assert len(LEGEND_PRESETS) == 10


def test_every_preset_member_resolves():
    for name in PRESET_PANELS:
        records = registry.panel(name)
        assert all(r["enabled"] for r in records), name


def test_unknown_ids_raise():
    with pytest.raises(KeyError):
        registry.get("no_such_juror")
    with pytest.raises(KeyError):
        registry.panel("No Such Room")


def test_every_veto_is_scoped():
    # A veto with no dimensions would make NashBroker force that Judge's blockers on any
    # dimension. The prototype roster had exactly that bug; it must not come back.
    for a in registry.ALL_ARCHETYPES:
        if a["veto"]:
            assert a["veto_dimensions"], a["id"]
            assert set(a["veto_dimensions"]) <= set(registry.VETO_DIMENSIONS), a["id"]


def test_defaults_auto_convene_and_legends_do_not():
    assert not any(a["library"] for a in DEFAULT_ARCHETYPES)
    assert all(a["library"] for a in LEGENDS)


def test_legends_are_trait_profiles_not_impersonations():
    for a in LEGENDS:
        if a["inspired_by"]:
            assert "You are not\n  that person" in a["persona"], a["id"]
            assert "never quote" in a["persona"], a["id"]
        else:
            assert a["category"] == "Mission"
            assert "not an impersonation" in a["persona"], a["id"]


def test_drafter_is_unscored_generator():
    d = registry.get("drafter")
    assert d["role"] == "generator" and d["rubric"] == [] and d["weight"] == 0


def test_preset_name_drift_resolved():
    assert "Mission Platform Review" in PRESET_PANELS
    assert "Platform Architecture Review" not in PRESET_PANELS


def test_physics_of_compute_is_fully_defined():
    ids = {a["id"] for a in registry.panel("Physics of Compute")}
    assert {"thermodynamicist", "metering_economist", "nash_agent"} <= ids


def test_catalog_is_current():
    on_disk = (ROOT / "docs" / "archetypes.md").read_text(encoding="utf-8")
    assert on_disk == registry.catalog(), (
        "docs/archetypes.md is stale; run: python -m jjv.registry > docs/archetypes.md")
