"""The verdict contract: what a Judge must return, and the anonymized Jury digest.

A model's reply is untrusted input. ``normalize`` turns it into a verdict dict that
NashBroker and the Voter can rely on, or raises VerdictError so the orchestrator can ask
again. Finding ids are assigned here, never by the model, so they are stable across the
Jury round and one Judge cannot overwrite another's finding.
"""

from __future__ import annotations

from jjv.nash import _key

SEVERITIES = ["nit", "minor", "major", "blocker"]
RECOMMENDATIONS = ["approve", "revise", "reject"]


class VerdictError(ValueError):
    """The reply cannot be used as a verdict."""


def schema(archetype: dict, *, deliberating: bool = False,
           negotiating: bool = False) -> dict:
    """JSON schema for one Judge's verdict, with that Judge's own rubric as required keys."""
    dims = [d["name"] for d in archetype["rubric"]]
    vetoes = list(archetype.get("veto_dimensions", []))
    finding = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Your existing id when keeping a "
                                                   "finding; omit for a new one."},
            "title": {"type": "string"},
            "severity": {"enum": SEVERITIES},
            "dimension": {"enum": dims + vetoes},
            "location": {"type": "string"},
            "detail": {"type": "string"},
        },
        "required": ["title", "severity", "dimension", "location", "detail"],
    }
    if deliberating:
        finding["properties"]["same_as"] = {
            "type": "string",
            "description": "Another Judge's finding id, when this is the same issue.",
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
    if negotiating:
        props |= {
            "fix_list": {"type": "array", "items": {"type": "string"},
                         "description": "Finding ids you would agree to fix now."},
            "message": {"type": "string",
                        "description": "Your argument, concession or offer to the others."},
        }
        required.append("fix_list")
    return {"type": "object", "properties": props, "required": required}


def overall(verdict: dict, archetype: dict) -> float:
    """Rubric-weighted mean of a Judge's dimension scores (1-5)."""
    weights = {d["name"]: d["weight"] for d in archetype["rubric"]}
    total = sum(weights.values())
    return round(sum(verdict["scores"][n] * w for n, w in weights.items()) / total, 3)


def canonical_dimension(dimension: object, archetype: dict) -> object:
    """Map "Physical correctness" to its veto word "physical-correctness".

    Live Judges write rubric names here. The broker and Voter match veto words exactly, so
    without this a real veto is downgraded to cheap talk and costs the Judge reputation.
    """
    for word in archetype.get("veto_dimensions", []):
        if _key({"id": dimension}) == word:
            return word
    return dimension


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

    for name, kind in (("scores", dict), ("findings", list), ("endorses", list),
                       ("fix_list", list)):
        if raw.get(name) is not None and not isinstance(raw[name], kind):
            raise VerdictError(f"{name} has the wrong type")

    scores = {}
    for d in archetype["rubric"]:
        value = (raw.get("scores") or {}).get(d["name"])
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise VerdictError(f"missing score for {d['name']!r}")
        if not 1 <= value <= 5:
            raise VerdictError(f"score for {d['name']!r} out of range: {value}")
        scores[d["name"]] = value

    earlier = (previous or {}).get("findings", [])
    mine = {f["id"] for f in earlier}
    by_title = {f["title"]: f["id"] for f in earlier}
    used = {int(i.rsplit("-", 1)[1]) for i in mine}
    findings = []
    for f in raw.get("findings") or []:
        if not isinstance(f, dict) or not str(f.get("title", "")).strip():
            raise VerdictError("finding without a title")
        if f.get("severity") not in SEVERITIES:
            raise VerdictError(f"bad severity: {f.get('severity')!r}")
        # One line only: titles are printed in the settlement, outside the digest's fence.
        title = " ".join(str(f["title"]).split())
        # A kept finding must keep its id, or endorsements of it would silently dangle.
        given = f.get("id")
        fid = given if isinstance(given, str) and given in mine else by_title.get(title)
        if fid is None or any(fid == x["id"] for x in findings):
            used.add(n := max(used, default=0) + 1)
            fid = f"{alias}-{n}"
        findings.append({
            "id": fid,
            "title": title,
            "severity": f["severity"],
            "dimension": canonical_dimension(f.get("dimension"), archetype),
            "location": f.get("location", ""),
            "detail": f.get("detail", ""),
        })
        link = f.get("same_as")
        if isinstance(link, str) and link.upper() in known_ids:
            findings[-1]["same_as"] = link.upper()

    own = {f["id"] for f in findings}
    for f in findings:
        if f.get("same_as") in own:     # a link joins two Judges, not one Judge's own list
            del f["same_as"]
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
        "endorses": sorted({e for e in (str(x).upper() for x in raw.get("endorses") or [])
                            if e in known_ids and e not in own}),
        "changed_mind": str(raw.get("changed_mind", "")),
    }
    if isinstance(raw.get("change_aversion"), (int, float)):
        verdict["change_aversion"] = min(1.0, max(0.0, float(raw["change_aversion"])))
    if raw.get("fix_list") is not None:
        verdict["fix_list"] = sorted({str(x).upper() for x in raw["fix_list"]})
        verdict["message"] = str(raw.get("message") or "")
    verdict["overall"] = overall(verdict, archetype)
    return verdict


def carry_forward(first: list[dict], final: list[dict]) -> tuple[list[dict], list[str]]:
    """Restore what the Jury round must not lose; returns (verdicts, restored ids).

    Judges revise concurrently from one digest, so prompts alone cannot protect a finding:
    two Judges can each drop theirs and endorse the other's, and a veto blocker can be
    talked away by text quoted from the subject. So code keeps both. A veto holds until a
    new subject is reviewed, and a finding someone endorsed stays on the table.
    """
    present = {f["id"] for v in final for f in v["findings"]}
    endorsed = {e for v in final for e in v.get("endorses", [])}
    endorsed |= {f["same_as"] for v in final for f in v["findings"] if "same_as" in f}
    restored, out = [], []
    for old, new in zip(first, final):
        now = {f["id"]: f for f in new["findings"]}
        for f in old["findings"]:
            veto = f["severity"] == "blocker" and f["dimension"] in old["veto_dimensions"]
            kept = now.get(f["id"])
            if kept and "same_as" in f and "same_as" not in kept:
                now[f["id"]] = kept = {**kept, "same_as": f["same_as"]}   # links last all rounds
            if veto and (not kept or (kept["severity"], kept["dimension"])
                         != (f["severity"], f["dimension"])):
                now[f["id"]] = f
                restored.append(f["id"])
            elif f["id"] in endorsed and f["id"] not in present:
                now[f["id"]] = f
                restored.append(f["id"])
        out.append({**new, "findings": list(now.values())})
    return out, restored


def link_findings(verdicts: list[dict]) -> tuple[list[dict], list[list[str]]]:
    """Join findings Judges marked ``same_as``; returns (verdicts, the groups joined).

    Each Judge's words stay as written. Linked findings only share one id, so agreement
    counts and the issue costs budget once. Links are made by Judges about their own
    findings: neither the broker nor this code decides that two findings match. The
    original id stays in ``own_id`` for the audit trail.
    """
    parent: dict[str, str] = {}

    def root(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    present = {f["id"] for v in verdicts for f in v["findings"]}
    for v in verdicts:
        for f in v["findings"]:
            if f.get("same_as") in present:
                a, b = sorted((root(f["id"]), root(f["same_as"])))
                parent[b] = a

    members: dict[str, list[str]] = {}
    for x in parent:
        members.setdefault(root(x), []).append(x)
    groups = [sorted(m) for m in members.values() if len(m) > 1]

    def canon(x: str) -> str:
        return root(x) if x in parent else x

    linked = []
    for v in verdicts:
        findings = [{**f, "id": canon(f["id"]), "own_id": f["id"]} if f["id"] in parent else f
                    for f in v["findings"]]
        own = {f["id"] for f in findings}
        endorses = sorted({canon(e) for e in v.get("endorses", [])} - own)
        linked.append({**v, "findings": findings, "endorses": endorses})
    return linked, sorted(groups)


def digest(verdicts: list[dict], viewer: str, fence: str,
           settlement_text: str | None = None) -> str:
    """The anonymized digest one Judge reads: everyone else's verdicts, by alias only.

    Judges' words can quote the subject, so they sit inside ``fence``, a tag they cannot
    guess. The settlement sits outside. It still prints finding titles, but ``normalize``
    keeps each to one line, so a title cannot add lines to the settlement.
    """
    out = ["ANONYMIZED DIGEST OF THE OTHER JUDGES", f"<{fence}>", ""]
    for v in sorted(verdicts, key=lambda v: v["alias"]):
        if v["alias"] == viewer:
            continue
        out.append(f"Judge {v['alias']}: {v['recommendation']}, overall {v['overall']:g}/5")
        out.append(f"  Rationale: {v['rationale']}")
        if "fix_list" in v:
            out.append(f"  Would fix now: {', '.join(v['fix_list']) or 'nothing'}")
        if v.get("message"):
            out.append(f"  Says: {v['message']}")
        for f in v["findings"]:
            out.append(f"  - {f['id']} [{f['severity']}] {f['title']} "
                       f"({f['location']}): {f['detail']}")
        out.append("")
    out += [f"</{fence}>", ""]
    if settlement_text:
        out += [settlement_text, ""]
    return "\n".join(out).rstrip() + "\n"
