"""The verdict contract: what a Judge must return, and the anonymized Jury digest.

A model's reply is untrusted input. ``normalize`` turns it into a verdict dict that
NashBroker and the Voter can rely on, or raises VerdictError so the orchestrator can ask
again. Finding ids are assigned here, never by the model, so they are stable across the
Jury round and one Judge cannot overwrite another's finding.
"""

from __future__ import annotations

SEVERITIES = ["nit", "minor", "major", "blocker"]
RECOMMENDATIONS = ["approve", "revise", "reject"]


class VerdictError(ValueError):
    """The reply cannot be used as a verdict."""


def schema(archetype: dict, *, deliberating: bool = False) -> dict:
    """JSON schema for one Judge's verdict, with that Judge's own rubric as required keys."""
    dims = [d["name"] for d in archetype["rubric"]]
    finding = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Your existing id when keeping a "
                                                   "finding; omit for a new one."},
            "title": {"type": "string"},
            "severity": {"enum": SEVERITIES},
            "dimension": {"type": "string"},
            "location": {"type": "string"},
            "detail": {"type": "string"},
        },
        "required": ["title", "severity", "dimension", "location", "detail"],
    }
    props = {
        "scores": {
            "type": "object",
            "properties": {d: {"type": "integer", "minimum": 1, "maximum": 5} for d in dims},
            "required": dims,
        },
        "rationale": {"type": "string"},
        "recommendation": {"enum": RECOMMENDATIONS},
        "findings": {"type": "array", "items": finding},
    }
    required = ["scores", "rationale", "recommendation", "findings"]
    if deliberating:
        props |= {
            "endorses": {"type": "array", "items": {"type": "string"}},
            "change_aversion": {"type": "number", "minimum": 0, "maximum": 1},
            "changed_mind": {"type": "string"},
        }
        required.append("changed_mind")
    return {"type": "object", "properties": props, "required": required}


def overall(verdict: dict, archetype: dict) -> float:
    """Rubric-weighted mean of a Judge's dimension scores (1-5)."""
    weights = {d["name"]: d["weight"] for d in archetype["rubric"]}
    total = sum(weights.values())
    return round(sum(verdict["scores"][n] * w for n, w in weights.items()) / total, 3)


def normalize(raw: object, archetype: dict, alias: str, *,
              previous: dict | None = None, known_ids: set[str] = frozenset()) -> dict:
    """Validate ``raw`` and return a verdict dict.

    ``alias`` is the Judge's anonymous label. ``previous`` is its Judge-round verdict when
    this is a Jury revision. ``known_ids`` are every finding id on the table, used to drop
    endorsements of findings that do not exist.
    """
    if not isinstance(raw, dict):
        raise VerdictError("verdict is not an object")
    if raw.get("recommendation") not in RECOMMENDATIONS:
        raise VerdictError(f"bad recommendation: {raw.get('recommendation')!r}")

    scores = {}
    for d in archetype["rubric"]:
        value = (raw.get("scores") or {}).get(d["name"])
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise VerdictError(f"missing score for {d['name']!r}")
        if not 1 <= value <= 5:
            raise VerdictError(f"score for {d['name']!r} out of range: {value}")
        scores[d["name"]] = value

    mine = {f["id"] for f in (previous or {}).get("findings", [])}
    used = {int(i.rsplit("-", 1)[1]) for i in mine}
    findings = []
    for f in raw.get("findings") or []:
        if not isinstance(f, dict) or not str(f.get("title", "")).strip():
            raise VerdictError("finding without a title")
        if f.get("severity") not in SEVERITIES:
            raise VerdictError(f"bad severity: {f.get('severity')!r}")
        fid = f.get("id")
        if fid not in mine or any(fid == x["id"] for x in findings):
            used.add(n := max(used, default=0) + 1)
            fid = f"{alias}-{n}"
        findings.append({
            "id": fid,
            "title": str(f["title"]).strip(),
            "severity": f["severity"],
            "dimension": f.get("dimension"),
            "location": f.get("location", ""),
            "detail": f.get("detail", ""),
        })

    own = {f["id"] for f in findings}
    verdict = {
        "archetype_id": archetype["id"],
        "alias": alias,
        "weight": archetype["weight"],
        "veto": archetype["veto"],
        "veto_dimensions": list(archetype.get("veto_dimensions", [])),
        "scores": scores,
        "rationale": str(raw.get("rationale", "")),
        "recommendation": raw["recommendation"],
        "findings": findings,
        "endorses": sorted({e for e in raw.get("endorses") or []
                            if e in known_ids and e not in own}),
        "changed_mind": str(raw.get("changed_mind", "")),
    }
    if isinstance(raw.get("change_aversion"), (int, float)):
        verdict["change_aversion"] = min(1.0, max(0.0, float(raw["change_aversion"])))
    verdict["overall"] = overall(verdict, archetype)
    return verdict


def digest(verdicts: list[dict], viewer: str, settlement_text: str | None = None) -> str:
    """The anonymized digest one Judge reads: everyone else's verdicts, by alias only."""
    out = ["ANONYMIZED DIGEST OF THE OTHER JUDGES", ""]
    for v in sorted(verdicts, key=lambda v: v["alias"]):
        if v["alias"] == viewer:
            continue
        out.append(f"Judge {v['alias']}: {v['recommendation']}, overall {v['overall']:g}/5")
        out.append(f"  Rationale: {v['rationale']}")
        for f in v["findings"]:
            out.append(f"  - {f['id']} [{f['severity']}] {f['title']} "
                       f"({f['location']}): {f['detail']}")
        out.append("")
    if settlement_text:
        out += [settlement_text, ""]
    return "\n".join(out).rstrip() + "\n"
