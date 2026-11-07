"""Show how each section of a run reached its result, from the saved record.

    python -m jjv.cli explain RUN_ID

Free: this reads the record and calls no model. The sums are recomputed here from the same
inputs the run used, so a reader can check them by hand.
"""

from __future__ import annotations

from collections import Counter

from jjv import registry, voter

STEPS = ("SELECT", "JUDGE", "JURY", "VOTE")


def step_label(phase: str) -> str:
    """Where a phase sits in the process, such as "2/4 JUDGE"."""
    return f"{STEPS.index(phase) + 1}/{len(STEPS)} {phase}" if phase in STEPS else phase


def spread(verdicts: list[dict]) -> float:
    """The gap between the highest and lowest Judge: zero means full agreement on the score."""
    scores = [v["overall"] for v in verdicts]
    return round(max(scores) - min(scores), 3) if scores else 0.0


def first_view(verdicts: list[dict]) -> dict:
    """Where the Judges stand before they have read each other."""
    tally = Counter(v["recommendation"] for v in verdicts)
    votes = ", ".join(f"{n} {r}" for r, n in sorted(tally.items()))
    count = sum(len(v["findings"]) for v in verdicts)
    return {"stage": "judge", "spread": spread(verdicts), "findings": count,
            "text": f"scores differ by {spread(verdicts):g}, votes: {votes}, {count} findings"}


def jury_view(before: list[dict], after: list[dict], number: int, links: int) -> dict:
    """How far one Jury round moved the panel."""
    moved = sum(a["overall"] != b["overall"] or a["recommendation"] != b["recommendation"]
                for a, b in zip(before, after))
    gap_before, gap_after = spread(before), spread(after)
    trend = ("closer" if gap_after < gap_before else
             "further apart" if gap_after > gap_before else "no closer")
    return {"stage": "jury", "round": number, "moved": moved, "of": len(after),
            "spread_before": gap_before, "spread": gap_after, "links": links,
            "text": f"round {number}: {moved} of {len(after)} Judges moved, score gap "
                    f"{gap_before:g} to {gap_after:g} ({trend}), {links} issues linked"}


def position_view(positions: dict[str, frozenset], number: int) -> dict:
    """How close negotiating Judges are to naming the same fix list."""
    biggest = max(Counter(positions.values()).values(), default=0)
    return {"stage": "negotiation", "round": number, "agree": biggest, "of": len(positions),
            "text": f"round {number}: {biggest} of {len(positions)} Judges name the same fix list"}


def fix_list_view(proposed: list[str], final: list[str]) -> dict:
    """How much the fix list changed between the first proposal and the final bargain."""
    kept = len(set(proposed) & set(final))
    return {"stage": "fix_list", "kept": kept, "proposed": len(proposed), "final": len(final),
            "text": f"{kept} of {len(proposed)} proposed fixes survived to the final "
                    f"{len(final)}"}


def round_view(number: int, score: float, previous: float | None, target: float) -> dict:
    """How a generate round moved the score toward its target."""
    change = "" if previous is None else f" ({score - previous:+.2f})"
    return {"stage": "generate", "round": number, "score": score, "target": target,
            "text": f"draft {number} scored {score:g}{change}, target {target:g}"}


def _weights(archetype_id: str) -> dict[str, float]:
    return {d["name"]: d["weight"] for d in registry.get(archetype_id)["rubric"]}


def judge_sum(verdict: dict) -> str:
    """One Judge's score, written out: each rubric score times its weight, over the weights."""
    weights = _weights(verdict["archetype_id"])
    terms = " + ".join(f"{verdict['scores'][n]:g}x{w:g}" for n, w in weights.items())
    return f"({terms}) / {sum(weights.values()):g} = {verdict['overall']:g}"


def _select(run: dict, rec: dict) -> list[str]:
    names = [registry.get(p["id"])["name"] for p in run["panel"]]
    return [f"[{step_label('SELECT')}] who reviews, and how it will be settled",
            f"  {len(names)} Judges: {', '.join(names)}",
            f"  Settled by: {rec.get('aggregator', 'unknown')}",
            f"  Spending limit ${run['config']['max_usd']:g}, "
            f"revision budget {run['config']['revision_budget']:g} cost units"]


def _judge(rec: dict) -> list[str]:
    out = [f"[{step_label('JUDGE')}] each Judge scores alone, without seeing the others",
           "  Score = each rubric score x its weight, divided by the total weight"]
    for v in rec.get("judge", []):
        out.append(f"  {v['archetype_id']}: {judge_sum(v)}, "
                   f"{len(v['findings'])} findings, recommends {v['recommendation']}")
    return out


def _jury(rec: dict) -> list[str]:
    if "jury" not in rec:
        return [f"[{step_label('JURY')}] skipped: the Judges' first verdicts stand"]
    out = [f"[{step_label('JURY')}] each Judge reads the others anonymously, then may revise"]
    before = {v["archetype_id"]: v for v in rec.get("judge", [])}
    for v in rec["jury"]:
        old = before.get(v["archetype_id"], v)
        moved = (f"{old['overall']:g} to {v['overall']:g}" if old["overall"] != v["overall"]
                 else f"stayed at {v['overall']:g}")
        out.append(f"  {v['archetype_id']}: score {moved}, "
                   f"findings {len(old['findings'])} to {len(v['findings'])}")
    out.append(f"  Linked as the same issue: {len(rec.get('links') or [])} groups")
    if rec.get("restored"):
        out.append(f"  Put back after being dropped: {len(rec['restored'])} findings "
                   "(a veto, or a finding another Judge backed, cannot be dropped)")
    for talk in rec.get("deliberation", []):
        result = f"agreed on {len(talk['agreed'])} fixes" if talk["agreed"] is not None \
            else "no agreement"
        out.append(f"  Negotiation round {talk['round']}: {result}")
    return out


def _settlement(run: dict, rec: dict) -> list[str]:
    s = rec.get("settlement")
    if not s:
        fixes = len(rec.get("vote", {}).get("fixes", []))
        return [f"[{step_label('VOTE')}: fix list] plain weighted vote, no bargaining",
                f"  Fixes chosen: {fixes}, within budget "
                f"{rec.get('revision_budget', 'as configured')}"]
    settled_by = rec.get("settled_by", "formula")
    names = {alias: archetype for archetype, alias in run.get("aliases", {}).items()}
    out = [f"[{step_label('VOTE')}: fix list] Nash bargaining over what to fix now",
           "  Chooses the fixes that maximize the weighted product of each Judge's gain over "
           "having no deal",
           f"  Budget {s['budget']:g}, spent {s['cost']:g}. Forced by a credible veto: "
           f"{len(s['forced'])}. Chosen: {len(s['address_now'])}. Deferred: {len(s['deferred'])}",
           "  Gain per Judge: " + (", ".join(f"{names.get(k, k)} {g:+.2f}"
                                             for k, g in sorted(s["gains"].items())) or "none"),
           f"  Empty threats recorded: {len(s['cheap_talk'])}",
           f"  Search: {'every combination checked' if s['exact'] else 'heuristic'}. "
           f"Equilibrium holds: {'yes' if s['individually_rational'] else 'NO'}"]
    if settled_by == "agreement":
        out.append(f"  Judges agreed their own list of {len(rec['agreed'])} fixes, which "
                   "replaced the formula's choice above")
    return out


def _vote(rec: dict) -> list[str]:
    final = rec.get("jury") or rec.get("judge") or []
    result = rec.get("vote")
    if not result or not final:
        return [f"[{step_label('VOTE')}: decision] not reached"]
    terms = " + ".join(f"{v['overall']:g}x{v['weight']:g}" for v in final)
    total = sum(v["weight"] for v in final)
    share = sum(v["weight"] for v in final if v["recommendation"] == "approve") / total
    vetoes, missing = len(result["vetoes"]), result["missing_vetoes"]
    return [
        f"[{step_label('VOTE')}: decision] a fixed rule, with no model involved",
        f"  Consensus = ({terms}) / {total:g} = {result['score']:g}",
        f"  Approval share = {share:.2f} of the panel's weight",
        "  Rules, in order:",
        f"    1. A credible veto blocks approval: {vetoes} found",
        f"    2. A veto-holder that did not report blocks approval: {len(missing)}",
        f"    3. Approve needs score >= {voter.APPROVE_SCORE:g} and approval share >= 0.50",
        f"    4. Reject if score < {voter.REJECT_SCORE:g}. Anything else is revise",
        f"  Result: {result['decision'].upper()} ({result['reason']})",
    ]


def _convergence(run: dict) -> list[str]:
    lines = [e["text"] for e in run.get("events", []) if e["type"] == "convergence"]
    return ["[Convergence] how the panel moved", *(f"  {line}" for line in lines)] if lines else []


def explain(run: dict) -> str:
    out = [f"HOW RUN {run['id']} REACHED ITS RESULT ({run['status']}, "
           f"${run['cost_usd']:.2f})", ""]
    if run.get("error"):
        out += [f"Stopped: {run['error']}", ""]
    for rec in run.get("rounds", []):
        if len(run["rounds"]) > 1:
            out += [f"=== Generate round {rec.get('round')} ===", ""]
        for section in (_select(run, rec), _judge(rec), _jury(rec), _settlement(run, rec),
                        _vote(rec)):
            out += [*section, ""]
    if lines := _convergence(run):
        out += [*lines, ""]
    if run.get("failures"):
        out.append(f"Judge calls that failed: {len(run['failures'])}, and any Judge that failed "
                   "the Jury kept its last verdict.")
    return "\n".join(out).rstrip() + "\n"
