import pytest

from jjv.registry import get
from jjv.verdicts import VerdictError, digest, normalize, schema
from jjv.voter import credible_vetoes, merge_findings, summary, tally


def raw(archetype, score=4, rec="approve", findings=()):
    return {"scores": {d["name"]: score for d in archetype["rubric"]},
            "rationale": "because", "recommendation": rec, "findings": list(findings)}


def finding(sev="major", dim="x", **kw):
    return {"title": "t", "severity": sev, "dimension": dim, "location": "l", "detail": "d"} | kw


def verdict(id, alias="A", **kw):
    a = get(id)
    return normalize(raw(a, **kw), a, alias)


def test_schema_requires_every_rubric_dimension():
    a = get("thermodynamicist")
    assert schema(a)["properties"]["scores"]["required"] == [d["name"] for d in a["rubric"]]
    assert "endorses" in schema(a, deliberating=True)["properties"]


@pytest.mark.parametrize("bad", [
    None, {}, {"recommendation": "maybe"}, {"recommendation": "approve", "scores": {}},
])
def test_normalize_rejects_malformed_replies(bad):
    with pytest.raises(VerdictError):
        normalize(bad, get("staff_engineer"), "A")


def test_normalize_rejects_out_of_range_score_and_bad_severity():
    a = get("staff_engineer")
    with pytest.raises(VerdictError):
        normalize(raw(a, score=9), a, "A")
    with pytest.raises(VerdictError):
        normalize(raw(a, findings=[finding(sev="fatal")]), a, "A")


def test_ids_come_from_the_orchestrator_not_the_model():
    a = get("staff_engineer")
    v = normalize(raw(a, findings=[finding(id="B-1"), finding()]), a, "A")
    assert [f["id"] for f in v["findings"]] == ["A-1", "A-2"]


def test_revision_keeps_own_ids_and_cannot_claim_anothers():
    a = get("staff_engineer")
    first = normalize(raw(a, findings=[finding(), finding()]), a, "A")
    revised = normalize(raw(a, findings=[finding(id="A-2"), finding(id="B-1", title="u")]), a,
                        "A", previous=first)
    assert [f["id"] for f in revised["findings"]] == ["A-2", "A-3"]


def test_a_kept_finding_keeps_its_id_even_when_the_model_omits_it():
    a = get("staff_engineer")
    first = normalize(raw(a, findings=[finding(title="kept")]), a, "A")
    revised = normalize(raw(a, findings=[finding(title="kept"), finding(title="new")]), a, "A",
                        previous=first)
    assert [f["id"] for f in revised["findings"]] == ["A-1", "A-2"]


def test_endorsements_must_exist_and_belong_to_someone_else():
    a = get("staff_engineer")
    r = raw(a, findings=[finding()]) | {"endorses": ["b-1", "A-1", "Z-9"]}
    v = normalize(r, a, "A", known_ids={"A-1", "B-1"})
    assert v["endorses"] == ["B-1"]


def test_digest_hides_identity_and_the_viewers_own_verdict():
    a = verdict("thermodynamicist", "A", findings=[finding()])
    b = verdict("staff_engineer", "B")
    text = digest([a, b], viewer="B", settlement_text="SETTLED")
    assert "A-1" in text and "Judge B" not in text and "SETTLED" in text
    assert "thermodynamicist" not in text and "Thermodynamicist" not in text


def test_all_approving_high_score_is_approved():
    r = tally([verdict("staff_engineer", score=5), verdict("product_lead", "B", score=4)])
    assert r["decision"] == "approve" and not r["dissents"]


def test_credible_veto_blocks_approval_despite_top_scores():
    bad = finding("blocker", "security")
    sec = verdict("security_reviewer", score=5, rec="revise", findings=[bad])
    r = tally([sec, verdict("staff_engineer", "B", score=5)])
    assert r["decision"] == "revise" and len(r["vetoes"]) == 1


def test_veto_holder_recommending_reject_rejects():
    sec = verdict("security_reviewer", rec="reject", findings=[finding("blocker", "security")])
    assert tally([sec, verdict("staff_engineer", "B", score=5)])["decision"] == "reject"


def test_blocker_outside_the_veto_dimension_is_not_a_veto():
    sec = verdict("security_reviewer", score=5, findings=[finding("blocker", "complexity")])
    eng = verdict("staff_engineer", "B", score=5, findings=[finding("blocker", "security")])
    assert credible_vetoes([sec, eng]) == []
    assert tally([sec, eng])["decision"] == "approve"


def test_a_missing_veto_holder_blocks_approve():
    r = tally([verdict("staff_engineer", score=5)], missing_vetoes=["security_reviewer"])
    assert r["decision"] == "revise" and "security_reviewer" in r["reason"]


def test_low_score_rejects_and_weight_decides_the_consensus():
    assert tally([verdict("staff_engineer", score=1, rec="revise")])["decision"] == "reject"
    r = tally([verdict("staff_engineer", score=5), verdict("product_lead", "B", score=1)])
    assert r["score"] == pytest.approx((5 * 1.3 + 1 * 0.9) / 2.2, abs=1e-3)


def test_findings_rank_by_severity_then_support_and_are_never_invented():
    a = verdict("staff_engineer", findings=[finding("minor"), finding("blocker")])
    b = normalize(raw(get("product_lead")) | {"endorses": ["A-1"]}, get("product_lead"), "B",
                  known_ids={"A-1", "A-2"})
    rows = merge_findings([a, b])
    assert [r["id"] for r in rows] == ["A-2", "A-1"]
    assert rows[1]["endorsed_by"] == ["product_lead"]


def test_tally_refuses_an_empty_panel_and_summary_names_the_decision():
    with pytest.raises(ValueError):
        tally([])
    assert summary(tally([verdict("staff_engineer", score=5)])).startswith("DECISION: APPROVE")
