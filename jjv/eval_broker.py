"""Evaluation harness: Nash_Agent broker vs plain weighted voting.

The question this answers is the one a skeptical reviewer would ask of the broker: does
deciding *which findings a revision addresses* by Nash bargaining beat ranking them by
weighted vote? Two modes:

**Offline simulation (no API key).** Generates synthetic review panels — Judges with
weights, veto rights, overlapping findings, severities and costs — and runs both
aggregators on each under a fixed revision budget. It measures:

- ``loud_judge_displacement``: how much the chosen set moves when one Judge without a
  veto inflates every severity by a level and recommends reject (0 = unmoved, 1 = fully
  replaced). This is the "one overconfident Judge" test.
- ``noise_stability``: mean pairwise overlap (Jaccard) of the chosen set across reruns
  in which each severity is jittered by one level with some probability (1 = identical).
- ``veto_satisfaction``: share of panels in which every credible veto was addressed.
- ``judges_shut_out``: average number of Judges who raised findings but got none
  addressed (lower is fairer).
- ``utilitarian_efficiency``: weighted value addressed, as a share of the best value any
  budget-feasible set could address (1 = maximal total value). The broker optimizes the
  Nash product, not the sum, so it is *expected* to trail voting slightly here; the
  metric is reported so the trade is visible, not hidden.

**Live comparison (needs the scaffold and an API key).** ``run_live_comparison`` takes
real subjects and a ``run_fn(subject, aggregator) -> {"rounds": int, "score": float}``
that drives the orchestrator's generate loop with either aggregator, and reports rounds
to reach the quality threshold and final scores. Wire ``run_fn`` to the orchestrator once
Nash_Agent is in the Jury phase (roadmap Phase 5b).

CLI::

    python -m jjv.eval_broker --trials 300 --seed 7 --out reports/broker_eval.md
"""

from __future__ import annotations

import argparse
import itertools
import random
import statistics
from dataclasses import dataclass
from typing import Callable, Iterable

from jjv.nash import DEFAULT_COST, SEVERITY_VALUE, NashBroker, _key

SEVERITIES = ["nit", "minor", "major", "blocker"]
DIMENSIONS = ["authz", "privacy", "crypto", "complexity", "correctness", "docs", "ux"]


# ---------------------------------------------------------------------------
# Baseline aggregator: weighted voting with veto
# ---------------------------------------------------------------------------

def weighted_vote_select(verdicts: list[dict], budget: float) -> list[str]:
    """What a conventional Voter does: credible vetoes first, then findings ranked by
    the weighted sum of severity votes, taken greedily while they fit the budget.

    Uses the broker's own parser so both aggregators see identical findings, keys,
    costs and veto rules; only the selection rule differs.
    """
    players, findings, forced, _ = NashBroker(budget).build(verdicts)
    raw = {}  # weighted votes use the severities as stated, inflated or not
    for v in verdicts:
        w = float(v.get("weight", 1.0))
        for f in v.get("findings", []):
            k = _key(f)
            raw[k] = raw.get(k, 0.0) + w * SEVERITY_VALUE.get(f.get("severity"), 2.0)
    chosen = list(forced)
    spent = sum(findings[k].cost for k in chosen)
    for k in sorted((k for k in findings if k not in chosen),
                    key=lambda k: (-raw.get(k, 0.0), k)):
        if spent + findings[k].cost <= max(budget, spent) + 1e-9:
            chosen.append(k)
            spent += findings[k].cost
    return sorted(chosen)


def nash_select(verdicts: list[dict], budget: float) -> list[str]:
    return NashBroker(budget=budget).solve(verdicts).address_now


AGGREGATORS: dict[str, Callable[[list[dict], float], list[str]]] = {
    "nash_broker": nash_select,
    "weighted_vote": weighted_vote_select,
}


# ---------------------------------------------------------------------------
# Synthetic panels
# ---------------------------------------------------------------------------

def make_panel(rng: random.Random, n_judges: int | None = None) -> list[dict]:
    """A plausible review panel: 4–6 Judges, one or two veto-holders, overlapping
    findings drawn from a shared pool so agreement happens naturally."""
    n = n_judges or rng.randint(4, 6)
    pool = [f"finding-{i}" for i in range(rng.randint(7, 11))]
    pool_dim = {f: rng.choice(DIMENSIONS) for f in pool}
    vetoers = rng.sample(range(n), k=rng.choice([1, 2]))
    verdicts = []
    for j in range(n):
        veto_dims = [rng.choice(DIMENSIONS[:4])] if j in vetoers else []
        findings = []
        for title in rng.sample(pool, k=rng.randint(2, 4)):
            dim = pool_dim[title]
            if veto_dims and dim in veto_dims and rng.random() < 0.6:
                sev = "blocker"
            else:
                sev = rng.choices(SEVERITIES[:3], weights=[1, 3, 3])[0]
            findings.append({"title": title, "severity": sev, "dimension": dim,
                             "cost": DEFAULT_COST[sev]})
        verdicts.append({
            "archetype_id": f"judge-{j}",
            "weight": rng.choice([0.8, 1.0, 1.0, 1.2]),
            "veto": bool(veto_dims),
            "veto_dimensions": veto_dims,
            "findings": findings,
            "recommendation": "revise",
        })
    return verdicts


def _shift(sev: str, delta: int) -> str:
    i = max(0, min(len(SEVERITIES) - 1, SEVERITIES.index(sev) + delta))
    return SEVERITIES[i]


def make_loud(verdicts: list[dict], rng: random.Random) -> list[dict]:
    """One Judge without a veto inflates every severity a level and recommends reject.
    Costs stay as originally estimated: the work did not change, only the rhetoric."""
    candidates = [i for i, v in enumerate(verdicts) if not v["veto"]]
    if not candidates:
        return verdicts
    i = rng.choice(candidates)
    out = [dict(v, findings=[dict(f) for f in v["findings"]]) for v in verdicts]
    out[i]["recommendation"] = "reject"
    for f in out[i]["findings"]:
        f["severity"] = _shift(f["severity"], +1)
    return out


def jitter(verdicts: list[dict], rng: random.Random, p: float = 0.25) -> list[dict]:
    out = [dict(v, findings=[dict(f) for f in v["findings"]]) for v in verdicts]
    for v in out:
        for f in v["findings"]:
            if f["severity"] != "blocker" and rng.random() < p:
                f["severity"] = _shift(f["severity"], rng.choice([-1, 1]))
                if f["severity"] == "blocker":
                    f["severity"] = "major"
    return out


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    a, b = set(a), set(b)
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def _weighted_values(verdicts: list[dict]):
    players, findings, forced, _ = NashBroker().build(verdicts)
    value = {k: sum(p.weight * p.values.get(k, 0.0) for p in players.values())
             for k in findings}
    return players, findings, forced, value


def utilitarian_efficiency(verdicts: list[dict], chosen: list[str], budget: float) -> float:
    """Value addressed / best feasible value, by exact 0-1 knapsack over integer costs."""
    _, findings, forced, value = _weighted_values(verdicts)
    cap = int(round(max(budget, sum(findings[k].cost for k in forced))))
    base = sum(value[k] for k in forced)
    used = int(round(sum(findings[k].cost for k in forced)))
    best = [0.0] * (cap - used + 1)
    for k, f in findings.items():
        if k in forced:
            continue
        c = int(round(f.cost))
        for r in range(len(best) - 1, c - 1, -1):
            best[r] = max(best[r], best[r - c] + value[k])
    optimum = base + best[-1]
    got = sum(value[k] for k in chosen)
    return 1.0 if optimum <= 0 else min(1.0, got / optimum)


def judges_shut_out(verdicts: list[dict], chosen: list[str]) -> int:
    players, *_ = NashBroker().build(verdicts)
    chosen = set(chosen)
    return sum(1 for p in players.values() if p.values and not (set(p.values) & chosen))


def vetoes_satisfied(verdicts: list[dict], chosen: list[str]) -> bool:
    _, _, forced, _ = NashBroker().build(verdicts)
    return set(forced) <= set(chosen)


# ---------------------------------------------------------------------------
# Offline experiment
# ---------------------------------------------------------------------------

@dataclass
class Result:
    name: str
    loud_judge_displacement: float
    noise_stability: float
    veto_satisfaction: float
    judges_shut_out: float
    utilitarian_efficiency: float


def run_offline(trials: int = 300, seed: int = 7, budget: float = 8.0,
                reruns: int = 5) -> dict[str, Result]:
    rng = random.Random(seed)
    acc = {name: {"disp": [], "stab": [], "veto": [], "shut": [], "eff": []}
           for name in AGGREGATORS}
    for _ in range(trials):
        panel = make_panel(rng)
        loud = make_loud(panel, rng)
        noisy = [jitter(panel, rng) for _ in range(reruns)]
        for name, select in AGGREGATORS.items():
            base = select(panel, budget)
            a = acc[name]
            a["disp"].append(1.0 - jaccard(base, select(loud, budget)))
            picks = [select(v, budget) for v in noisy]
            a["stab"].append(statistics.mean(
                jaccard(x, y) for x, y in itertools.combinations(picks, 2)))
            a["veto"].append(1.0 if vetoes_satisfied(panel, base) else 0.0)
            a["shut"].append(judges_shut_out(panel, base))
            a["eff"].append(utilitarian_efficiency(panel, base, budget))
    return {
        name: Result(name, *(round(statistics.mean(a[m]), 3)
                             for m in ("disp", "stab", "veto", "shut", "eff")))
        for name, a in acc.items()
    }


def report_markdown(results: dict[str, Result], trials: int, seed: int,
                    budget: float) -> str:
    rows = [
        ("Loud-judge displacement", "loud_judge_displacement", "lower"),
        ("Noise stability", "noise_stability", "higher"),
        ("Veto satisfaction", "veto_satisfaction", "higher"),
        ("Judges shut out (avg)", "judges_shut_out", "lower"),
        ("Utilitarian efficiency", "utilitarian_efficiency", "higher"),
    ]
    nb, wv = results["nash_broker"], results["weighted_vote"]
    out = [
        "## Broker evaluation (offline simulation)",
        "",
        f"{trials} synthetic panels, seed {seed}, revision budget {budget:g}. "
        "Reproduce with `python -m jjv.eval_broker --trials "
        f"{trials} --seed {seed}`.",
        "",
        "| Metric | Better | Nash broker | Weighted vote |",
        "|---|---|---|---|",
    ]
    for label, attr, better in rows:
        out.append(f"| {label} | {better} | {getattr(nb, attr)} | {getattr(wv, attr)} |")
    out += [
        "",
        "Synthetic panels test the aggregation rule, not the quality of LLM verdicts. "
        "The live comparison (`run_live_comparison`) is the test that counts.",
    ]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Live comparison hook
# ---------------------------------------------------------------------------

def run_live_comparison(subjects: list, run_fn: Callable[[object, str], dict],
                        aggregators: Iterable[str] = ("nash_broker", "weighted_vote")):
    """Drive real generate-loop runs with each aggregator and summarize.

    ``run_fn(subject, aggregator_name)`` must return ``{"rounds": int, "score": float}``:
    revision rounds until the consensus threshold (or the round cap) and the final
    score from a *separate, blind* evaluation panel, not the panel that steered the run.
    """
    summary = {}
    for name in aggregators:
        runs = [run_fn(s, name) for s in subjects]
        summary[name] = {
            "subjects": len(runs),
            "mean_rounds": round(statistics.mean(r["rounds"] for r in runs), 3),
            "mean_score": round(statistics.mean(r["score"] for r in runs), 3),
        }
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--budget", type=float, default=8.0)
    ap.add_argument("--out", help="write the Markdown report here as well as stdout")
    args = ap.parse_args(argv)
    md = report_markdown(run_offline(args.trials, args.seed, args.budget),
                         args.trials, args.seed, args.budget)
    print(md)
    if args.out:
        import os
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as fh:
            fh.write(md + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
