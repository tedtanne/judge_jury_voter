"""The Voter: a deterministic tally of the final verdicts.

It computes the consensus score, resolves the decision by policy, merges findings, and
names the dissents. It never invents a finding, and it recommends: a person approves.

Decision policy, in order:

1. A blocker raised by a Judge holding a veto on that finding's dimension can never be
   approved. The decision is ``reject`` if that Judge recommended reject, else ``revise``.
2. A veto-holder that failed to report blocks ``approve`` as well: its silence is not
   consent. The decision is at best ``revise``.
3. Otherwise ``approve`` needs a consensus score of at least APPROVE_SCORE and at least
   half the panel's weight recommending approve.
4. A consensus score below REJECT_SCORE is ``reject``. Everything else is ``revise``.
"""

from __future__ import annotations

from jjv.nash import SEVERITY_RANK, _key

APPROVE_SCORE = 4.0
REJECT_SCORE = 2.0


def _weighted_mean(pairs: list[tuple[float, float]]) -> float:
    total = sum(w for _, w in pairs)
    return round(sum(x * w for x, w in pairs) / total, 3) if total else 0.0


def credible_vetoes(verdicts: list[dict]) -> list[dict]:
    """Blockers raised by a Judge holding a veto on the finding's own dimension."""
    return [
        {"finding": f, "by": v["archetype_id"], "recommendation": v["recommendation"]}
        for v in verdicts for f in v["findings"]
        if f["severity"] == "blocker" and f.get("dimension") in v["veto_dimensions"]
    ]


def merge_findings(verdicts: list[dict]) -> list[dict]:
    """One row per finding, most serious and best supported first."""
    merged: dict[str, dict] = {}
    for v in verdicts:
        for f in v["findings"]:
            row = merged.setdefault(_key(f), {**f, "raised_by": [], "endorsed_by": [],
                                              "support": 0.0})
            if SEVERITY_RANK[f["severity"]] > SEVERITY_RANK[row["severity"]]:
                row["severity"] = f["severity"]
            if f.get("citations"):
                # A new list: the row shares its first finding's, which must not change.
                row["citations"] = sorted({*row.get("citations", []), *f["citations"]})
            row["raised_by"].append(v["archetype_id"])
            row["support"] += v["weight"]
    for v in verdicts:
        for e in v.get("endorses", []):
            row = merged.get(_key({"id": e}))
            if row and v["archetype_id"] not in row["raised_by"]:
                row["endorsed_by"].append(v["archetype_id"])
                row["support"] += 0.5 * v["weight"]
    return sorted(merged.values(), key=lambda r: (-SEVERITY_RANK[r["severity"]],
                                                  -r["support"], r["id"]))


def tally(verdicts: list[dict], missing_vetoes: list[str] = ()) -> dict:
    """Aggregate final verdicts. ``missing_vetoes``: veto-holders that failed to report."""
    if not verdicts:
        raise ValueError("cannot tally zero verdicts")

    score = _weighted_mean([(v["overall"], v["weight"]) for v in verdicts])
    dimensions: dict[str, list] = {}
    for v in verdicts:
        for name, value in v["scores"].items():
            dimensions.setdefault(name, []).append((value, v["weight"]))

    total_weight = sum(v["weight"] for v in verdicts)
    approving = sum(v["weight"] for v in verdicts if v["recommendation"] == "approve")
    vetoes = credible_vetoes(verdicts)

    if vetoes:
        decision = "reject" if any(x["recommendation"] == "reject" for x in vetoes) else "revise"
        reason = f"{len(vetoes)} credible veto(es)"
    elif missing_vetoes:
        decision = "reject" if score < REJECT_SCORE else "revise"
        reason = "veto-holder did not report: " + ", ".join(missing_vetoes)
    elif score >= APPROVE_SCORE and approving * 2 >= total_weight:
        decision, reason = "approve", f"score {score:g} with majority approval"
    elif score < REJECT_SCORE:
        decision, reason = "reject", f"score {score:g} below {REJECT_SCORE:g}"
    else:
        decision, reason = "revise", f"score {score:g}, approval share {approving / total_weight:.2f}"

    return {
        "decision": decision,
        "reason": reason,
        "score": score,
        "dimensions": {k: _weighted_mean(p) for k, p in sorted(dimensions.items())},
        "vetoes": vetoes,
        "findings": merge_findings(verdicts),
        "dissents": [
            {"by": v["archetype_id"], "recommendation": v["recommendation"],
             "rationale": v["rationale"]}
            for v in verdicts if v["recommendation"] != decision
        ],
        "missing_vetoes": list(missing_vetoes),
    }


def summary(result: dict, limit: int = 10) -> str:
    """The human-facing report."""
    out = [f"DECISION: {result['decision'].upper()}  ({result['reason']})",
           f"Consensus score: {result['score']:g}/5", ""]
    if result["findings"]:
        out.append("Top actions:")
        for i, f in enumerate(result["findings"][:limit], 1):
            who = ", ".join(f["raised_by"] + [f"+{e}" for e in f["endorsed_by"]])
            out.append(f"{i:>3}. [{f['severity']}] {f['title']} ({f['location']}) - {who}")
        if len(result["findings"]) > limit:
            out.append(f"     ...and {len(result['findings']) - limit} more in the run record.")
        out.append("")
    if result["dissents"]:
        out.append("Dissents:")
        out += [f"  - {d['by']} ({d['recommendation']}): {d['rationale']}"
                for d in result["dissents"]]
    return "\n".join(out).rstrip()
