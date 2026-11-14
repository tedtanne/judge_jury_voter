"""Generate the README hero: docs/hero-light.svg and docs/hero-dark.svg.

    python scripts/make_hero.py

The picture is computed, not drawn. A synthetic panel from jjv.eval_broker is enumerated
through the real NashBroker: every bundle of fixes is a particle placed by its revision cost
and its weighted Nash objective, the budget is the line the feasible swarm stops at, and the
path is the kernel's own add/drop/swap search climbing to the settlement. The five Judges
along the bottom are a real run (94f38f3fa5af, The Nash Table on docs/nash-agent.md):
each moves from its independent score to its score after the Jury round, and the consensus
lands where the Voter put it. The equations are the ones in jjv/nash.py.

The SVG animates with SMIL and uses only system fonts, so it plays inside an <img> on
GitHub, where scripts and web fonts do not load.
"""

from __future__ import annotations

import itertools
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jjv.eval_broker import make_panel          # noqa: E402
from jjv.nash import NashBroker                  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CYCLE = 16.0          # seconds per loop; every animation is keyed to this one clock
W, H = 1200, 560

# Judge scores from run 94f38f3fa5af: independent, then after the Jury round.
JUDGES = [("Simplifier", 3.0, 2.636), ("Security", 3.25, 3.25), ("Product", 3.286, 3.0),
          ("Staff Eng.", 3.182, 2.909), ("Nash_Agent", 2.731, 2.5)]
CONSENSUS = 2.857

THEMES = {
    "light": dict(paper="#f3f2ec", surface="#ffffff", line="#e4e1d7", ink="#1b1d24",
                  ink2="#4a4e5a", dim="#797f8c", accent="#3f57b8", accent_soft="#3f57b8",
                  approve="#2f8f66", revise="#c07f22", reject="#c1483f"),
    "dark": dict(paper="#111319", surface="#181b23", line="#2b303c", ink="#e8e9ef",
                 ink2="#b3b9c6", dim="#8b93a3", accent="#89a0f2", accent_soft="#89a0f2",
                 approve="#4cc78d", revise="#e0a545", reject="#ec6a60"),
}


# ---------------------------------------------------------------------------
# The bargaining game, enumerated through the kernel
# ---------------------------------------------------------------------------

def game(seed: int = 11, budget: float = 8.0):
    """All bundles of a synthetic panel, scored exactly as NashBroker.solve scores them."""
    rng = random.Random(seed)
    verdicts = make_panel(rng, n_judges=5)
    broker = NashBroker(budget=budget)
    players, findings, forced, _ = broker.build(verdicts)
    D = frozenset(forced)
    cost = lambda S: sum(findings[k].cost for k in S)
    d = {pid: broker._utility(p, D, findings) for pid, p in players.items()}
    vetoers = [p for p in players.values() if p.veto]
    area_d = {p.id: broker._area_utility(p, D, findings) for p in vetoers}

    def feasible(S):
        return cost(S) <= budget + 1e-9 and all(
            broker._area_utility(p, S, findings) >= area_d[p.id] - 1e-9 for p in vetoers)

    def objective(S):
        total = 0.0
        for pid, p in players.items():
            g = broker._utility(p, S, findings) - d[pid]
            total += p.weight * (math.log1p(g) if g > 0 else g)
        return total

    optional = sorted(k for k in findings if k not in D)
    bundles = []
    for r in range(len(optional) + 1):
        for combo in itertools.combinations(optional, r):
            S = D | frozenset(combo)
            bundles.append((S, cost(S), objective(S), feasible(S)))

    # The kernel's local search, traced step by step: add, drop or swap one finding while
    # the objective improves. The exact solver lands on the same bundle for this panel.
    best = D
    path = [best]
    improved = True
    while improved:
        improved = False
        moves = [best | {k} for k in optional if k not in best]
        moves += [best - {k} for k in best if k not in D]
        moves += [(best - {a}) | {b} for a in best if a not in D for b in optional
                  if b not in best]
        moves = [m for m in moves if feasible(m)]
        if moves:
            top = max(moves, key=lambda m: (round(objective(m), 9), -cost(m)))
            if objective(top) > objective(best) + 1e-9:
                best, improved = top, True
                path.append(best)
    exact = max((b for b in bundles if b[3]), key=lambda b: (round(b[2], 9), -b[1]))[0]
    gains = {pid: broker._utility(p, best, findings) - d[pid] for pid, p in players.items()}
    return dict(bundles=bundles, path=path, best=best, exact=exact, budget=budget,
                forced=len(D), cost=cost, objective=objective, gains=gains,
                n_optional=len(optional), weights={p.id: p.weight for p in players.values()})


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def t(seconds: float) -> str:
    """A keyTime on the shared clock."""
    return f"{max(0.0, min(1.0, seconds / CYCLE)):.4f}"


def fade(begin: float, end: float, hold_until: float = CYCLE - 0.6, lo=0.0, hi=1.0) -> str:
    """Opacity that rises between begin and end, holds, and falls out before the loop ends."""
    return (f'<animate attributeName="opacity" dur="{CYCLE}s" repeatCount="indefinite" '
            f'values="{lo};{lo};{hi};{hi};{lo}" '
            f'keyTimes="0;{t(begin)};{t(end)};{t(hold_until)};1"/>')


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(theme: str, g: dict) -> str:
    c = THEMES[theme]
    serif = "Georgia, 'Times New Roman', Times, serif"
    mono = "ui-monospace, 'SF Mono', Menlo, Consolas, monospace"
    sans = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

    # Plot frame for the bargaining plane.
    px0, px1, py0, py1 = 70, 640, 70, 390
    costs = [b[1] for b in g["bundles"]]
    objs = [b[2] for b in g["bundles"]]
    cmax = max(costs) * 1.04
    omin, omax = min(objs), max(objs)
    pad = (omax - omin) * 0.08
    sx = lambda v: px0 + (v / cmax) * (px1 - px0)
    sy = lambda v: py1 - ((v - (omin - pad)) / ((omax + pad) - (omin - pad))) * (py1 - py0)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
           f'height="{H}" role="img" aria-labelledby="title desc">',
           '<title id="title">Judge · Jury · Voter: Nash bargaining over what to fix</title>',
           '<desc id="desc">Every bundle of fixes a panel could choose, placed by its revision '
           'cost and weighted Nash objective. The broker searches within the budget to the '
           'settlement. Below, five Judges move from independent scores to deliberated ones '
           'and the Voter finds the consensus.</desc>',
           '<defs>',
           f'<radialGradient id="glow"><stop offset="0" stop-color="{c["accent"]}" '
           f'stop-opacity=".55"/><stop offset="1" stop-color="{c["accent"]}" stop-opacity="0"/>'
           '</radialGradient>',
           f'<radialGradient id="wash" cx="0.3" cy="0"><stop offset="0" stop-color="{c["accent"]}" '
           f'stop-opacity=".10"/><stop offset="1" stop-color="{c["accent"]}" stop-opacity="0"/>'
           '</radialGradient>',
           '</defs>',
           f'<rect width="{W}" height="{H}" fill="{c["paper"]}"/>',
           f'<rect width="{W}" height="{H}" fill="url(#wash)"/>']

    # --- bargaining plane -----------------------------------------------------------
    out.append(f'<g font-family="{mono}" font-size="11" fill="{c["dim"]}">')
    out.append(f'<line x1="{px0}" y1="{py1}" x2="{px1}" y2="{py1}" stroke="{c["line"]}"/>')
    out.append(f'<line x1="{px0}" y1="{py0}" x2="{px0}" y2="{py1}" stroke="{c["line"]}"/>')
    out.append(f'<text x="{px1}" y="{py1 + 22}" text-anchor="end">revision cost of the bundle, c(S)</text>')
    out.append(f'<text x="{px0 - 8}" y="{py0 - 10}" text-anchor="start">Σ wᵢ φ(gainᵢ)</text>')
    out.append('</g>')

    # Particles: every bundle, infeasible ones hollow. They arrive in order of cost.
    rng = random.Random(3)
    for S, cost, obj, ok in g["bundles"]:
        x, y = sx(cost) + rng.uniform(-3, 3), sy(obj) + rng.uniform(-2, 2)
        arrive = 0.4 + (cost / cmax) * 2.4
        if ok:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{c["accent"]}" opacity="0">'
                       f'{fade(arrive, arrive + 0.5, hi=0.55)}</circle>')
        else:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.4" fill="none" '
                       f'stroke="{c["dim"]}" stroke-width=".8" opacity="0">'
                       f'{fade(arrive, arrive + 0.5, hi=0.35)}</circle>')

    # Budget line: drawn at 3s, after the swarm has arrived.
    bx = sx(g["budget"])
    out.append(f'<g opacity="0">{fade(3.0, 3.6)}'
               f'<line x1="{bx:.1f}" y1="{py0}" x2="{bx:.1f}" y2="{py1}" stroke="{c["reject"]}" '
               f'stroke-width="1.2" stroke-dasharray="4 4"/>'
               f'<text x="{bx + 6:.1f}" y="{py0 + 14}" font-family="{mono}" font-size="11" '
               f'fill="{c["reject"]}">budget B = {g["budget"]:g}</text>'
               f'<text x="{bx + 6:.1f}" y="{py0 + 28}" font-family="{mono}" font-size="10" '
               f'fill="{c["dim"]}">beyond it, no deal</text></g>')

    # Disagreement point D: where the search starts.
    pts = [(sx(g["cost"](S)), sy(g["objective"](S))) for S in g["path"]]
    dx, dy = pts[0]
    out.append(f'<g opacity="0">{fade(3.8, 4.3)}'
               f'<circle cx="{dx:.1f}" cy="{dy:.1f}" r="5" fill="none" stroke="{c["ink2"]}" stroke-width="1.4"/>'
               f'<text x="{dx + 10:.1f}" y="{dy + 4:.1f}" font-family="{mono}" font-size="11" '
               f'fill="{c["ink2"]}">D: the credible vetoes alone</text></g>')

    # The search path: one segment lights per step, then the marker rides the whole path.
    step0, step_dt = 4.6, 0.9
    for i in range(1, len(pts)):
        (x0, y0), (x1, y1) = pts[i - 1], pts[i]
        length = math.hypot(x1 - x0, y1 - y0)
        a = step0 + (i - 1) * step_dt
        out.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                   f'stroke="{c["accent"]}" stroke-width="2" stroke-linecap="round" '
                   f'stroke-dasharray="{length:.1f}" stroke-dashoffset="{length:.1f}" opacity="0.9">'
                   f'<animate attributeName="stroke-dashoffset" dur="{CYCLE}s" repeatCount="indefinite" '
                   f'values="{length:.1f};{length:.1f};0;0;{length:.1f}" '
                   f'keyTimes="0;{t(a)};{t(a + step_dt * 0.8)};{t(CYCLE - 0.6)};1"/>'
                   f'{fade(a, a + 0.05, hi=0.9)}</line>')
        out.append(f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="3.6" fill="{c["accent"]}" opacity="0">'
                   f'{fade(a + step_dt * 0.8, a + step_dt * 0.9)}</circle>')
    land = step0 + (len(pts) - 1) * step_dt

    # The settlement: a glow and a label, once the search lands.
    fx, fy = pts[-1]
    out.append(f'<g opacity="0">{fade(land, land + 0.5)}'
               f'<circle cx="{fx:.1f}" cy="{fy:.1f}" r="26" fill="url(#glow)">'
               f'<animate attributeName="r" dur="2.4s" repeatCount="indefinite" values="20;30;20"/></circle>'
               f'<circle cx="{fx:.1f}" cy="{fy:.1f}" r="5.5" fill="{c["accent"]}" stroke="{c["paper"]}" stroke-width="2"/>'
               f'<text x="{fx - 12:.1f}" y="{fy - 14:.1f}" text-anchor="end" font-family="{serif}" '
               f'font-size="15" font-style="italic" fill="{c["ink"]}">S*, the settlement</text>'
               f'<text x="{fx - 12:.1f}" y="{fy + 2:.1f}" text-anchor="end" font-family="{mono}" '
               f'font-size="10.5" fill="{c["dim"]}">cost {g["cost"](g["best"]):g} of {g["budget"]:g} · '
               f'{len(g["best"]) - g["forced"]} fixes + {g["forced"]} forced</text></g>')

    # Caption under the plane.
    n = len(g["bundles"])
    out.append(f'<text x="{px0}" y="{py1 + 44}" font-family="{sans}" font-size="12.5" fill="{c["ink2"]}">'
               f'{n} bundles a five-Judge panel could choose, drawn from the kernel. '
               f'Solid: fits the budget and keeps every veto. Hollow: no deal.</text>')

    # --- equations -------------------------------------------------------------------
    ex = 700
    out.append(f'<text x="{ex}" y="{py0 + 2}" font-family="{serif}" font-size="30" font-weight="700" '
               f'fill="{c["ink"]}" letter-spacing="-.5">Judge <tspan fill="{c["accent"]}">·</tspan> Jury '
               f'<tspan fill="{c["accent"]}">·</tspan> Voter</text>')
    out.append(f'<text x="{ex}" y="{py0 + 24}" font-family="{sans}" font-size="13" fill="{c["ink2"]}">'
               'A swarm of review agents, settled by Nash bargaining instead of a vote.</text>')

    eqs = [
        (1.0, "uᵢ(S) = Σ<tspan baseline-shift='sub' font-size='11'>f∈S</tspan> vᵢ(f) − aᵢ · c(S) / n",
         "each Judge's utility: the findings it values, less its share of the rework"),
        (2.2, "D = the credible vetoes  ·  feasible S ⊇ D,  c(S) ≤ B",
         "a blocker counts only when a veto stands behind it; the rest is cheap talk"),
        (3.4, "max<tspan baseline-shift='sub' font-size='11'>S</tspan> Π<tspan baseline-shift='sub' font-size='11'>i</tspan> (uᵢ(S) − uᵢ(D))<tspan baseline-shift='super' font-size='11'>wᵢ</tspan>",
         "Nash (1950): the weighted product of each party's gain over no deal"),
        (4.6, "= max<tspan baseline-shift='sub' font-size='11'>S</tspan> Σ<tspan baseline-shift='sub' font-size='11'>i</tspan> wᵢ φ(gᵢ),   φ(g) = ln(1+g) if g > 0, else g",
         "the kernel's smoothed form: concave on gains, so surplus is spread, not piled"),
        (5.8, "uᵢ<tspan baseline-shift='super' font-size='11'>area</tspan>(S*) ≥ uᵢ<tspan baseline-shift='super' font-size='11'>area</tspan>(D)  ∀ veto-holders  ⇒  accept is an equilibrium",
         "no holder gains by blocking in its own area, so ratifying S* is a Nash equilibrium"),
    ]
    y = py0 + 64
    for at, formula, note in eqs:
        out.append(f'<g opacity="0">{fade(at, at + 0.7)}'
                   f'<text x="{ex}" y="{y}" font-family="{serif}" font-size="17" font-style="italic" '
                   f'fill="{c["ink"]}">{formula}</text>'
                   f'<text x="{ex}" y="{y + 18}" font-family="{sans}" font-size="11.5" fill="{c["dim"]}">'
                   f'{esc(note)}</text></g>')
        y += 50

    # Gains per Judge, once the settlement lands.
    gx = ex
    out.append(f'<g opacity="0">{fade(land + 0.3, land + 0.9)}'
               f'<text x="{gx}" y="{y + 2}" font-family="{mono}" font-size="10.5" fill="{c["dim"]}" '
               f'letter-spacing="1.5">SURPLUS OVER NO DEAL, BY JUDGE</text></g>')
    gy = y + 22
    for i, (pid, gain) in enumerate(sorted(g["gains"].items())):
        col = c["approve"] if gain > 0 else c["reject"]
        out.append(f'<g opacity="0">{fade(land + 0.4 + i * 0.12, land + 0.9 + i * 0.12)}'
                   f'<text x="{gx + i * 96}" y="{gy}" font-family="{mono}" font-size="12" fill="{c["ink2"]}">'
                   f'{esc(pid)}</text>'
                   f'<text x="{gx + i * 96}" y="{gy + 16}" font-family="{mono}" font-size="13" '
                   f'font-weight="700" fill="{col}">{gain:+.2f}</text></g>')

    # --- the Judges' convergence strip ------------------------------------------------
    sy0 = 470
    ax0, ax1 = px0, W - 70
    sc = lambda v: ax0 + ((v - 1) / 4) * (ax1 - ax0)
    out.append(f'<line x1="{ax0}" y1="{sy0}" x2="{ax1}" y2="{sy0}" stroke="{c["line"]}"/>')
    for v in (1, 2, 3, 4, 5):
        out.append(f'<line x1="{sc(v):.1f}" y1="{sy0 - 4}" x2="{sc(v):.1f}" y2="{sy0 + 4}" stroke="{c["line"]}"/>'
                   f'<text x="{sc(v):.1f}" y="{sy0 + 20}" text-anchor="middle" font-family="{mono}" '
                   f'font-size="10.5" fill="{c["dim"]}">{v}</text>')
    out.append(f'<text x="{ax0}" y="{sy0 - 44}" font-family="{mono}" font-size="10.5" fill="{c["dim"]}" '
               f'letter-spacing="1.5">A LIVE PANEL, SCORES OUT OF 5 · INDEPENDENT → AFTER THE JURY → CONSENSUS</text>')
    # Approve threshold and the decision bands.
    out.append(f'<line x1="{sc(4):.1f}" y1="{sy0 - 30}" x2="{sc(4):.1f}" y2="{sy0 + 6}" '
               f'stroke="{c["approve"]}" stroke-dasharray="3 3" opacity=".7"/>'
               f'<text x="{sc(4) + 5:.1f}" y="{sy0 - 20}" font-family="{mono}" font-size="10" '
               f'fill="{c["approve"]}">approve ≥ 4</text>'
               f'<line x1="{sc(2):.1f}" y1="{sy0 - 30}" x2="{sc(2):.1f}" y2="{sy0 + 6}" '
               f'stroke="{c["reject"]}" stroke-dasharray="3 3" opacity=".7"/>'
               f'<text x="{sc(2) - 5:.1f}" y="{sy0 - 20}" text-anchor="end" font-family="{mono}" '
               f'font-size="10" fill="{c["reject"]}">reject &lt; 2</text>')
    move0, move1 = 6.0, 8.4
    for i, (name, before, after) in enumerate(JUDGES):
        yy = sy0 - 8 - (i % 2) * 11          # two rows, so labels do not collide
        out.append(f'<g>'
                   f'<line x1="{sc(before):.1f}" y1="{yy}" x2="{sc(before):.1f}" y2="{yy}" '
                   f'stroke="{c["revise"]}" stroke-width="1.2" opacity=".6">'
                   f'<animate attributeName="x2" dur="{CYCLE}s" repeatCount="indefinite" '
                   f'values="{sc(before):.1f};{sc(before):.1f};{sc(after):.1f};{sc(after):.1f};{sc(before):.1f}" '
                   f'keyTimes="0;{t(move0)};{t(move1)};{t(CYCLE - 0.6)};1"/></line>'
                   f'<circle cy="{yy}" r="4.5" fill="{c["revise"]}" stroke="{c["paper"]}" stroke-width="1.5">'
                   f'<animate attributeName="cx" dur="{CYCLE}s" repeatCount="indefinite" '
                   f'values="{sc(before):.1f};{sc(before):.1f};{sc(after):.1f};{sc(after):.1f};{sc(before):.1f}" '
                   f'keyTimes="0;{t(move0)};{t(move1)};{t(CYCLE - 0.6)};1" calcMode="spline" '
                   f'keySplines="0 0 1 1;.2 .8 .2 1;0 0 1 1;0 0 1 1"/>'
                   f'{fade(0.6 + i * 0.15, 1.0 + i * 0.15)}</circle>'
                   f'<text y="{yy - 8}" text-anchor="middle" font-family="{mono}" font-size="9.5" fill="{c["ink2"]}">'
                   f'<animate attributeName="x" dur="{CYCLE}s" repeatCount="indefinite" '
                   f'values="{sc(before):.1f};{sc(before):.1f};{sc(after):.1f};{sc(after):.1f};{sc(before):.1f}" '
                   f'keyTimes="0;{t(move0)};{t(move1)};{t(CYCLE - 0.6)};1" calcMode="spline" '
                   f'keySplines="0 0 1 1;.2 .8 .2 1;0 0 1 1;0 0 1 1"/>'
                   f'{fade(0.6 + i * 0.15, 1.0 + i * 0.15)}{esc(name)}</text></g>')
    # Consensus marker.
    cx = sc(CONSENSUS)
    out.append(f'<g opacity="0">{fade(move1 + 0.4, move1 + 1.0)}'
               f'<line x1="{cx:.1f}" y1="{sy0 - 34}" x2="{cx:.1f}" y2="{sy0 + 8}" stroke="{c["accent"]}" stroke-width="2"/>'
               f'<text x="{cx:.1f}" y="{sy0 + 38}" text-anchor="middle" font-family="{serif}" font-size="14" '
               f'font-style="italic" fill="{c["ink"]}">consensus {CONSENSUS} · REVISE</text></g>')
    out.append(f'<text x="{ax1}" y="{sy0 + 38}" text-anchor="end" font-family="{mono}" font-size="10" '
               f'fill="{c["dim"]}">run 94f38f3fa5af · The Nash Table · {len(JUDGES)} Judges</text>')

    out.append('</svg>')
    return "\n".join(out) + "\n"


def main() -> int:
    g = game()
    assert g["best"] == g["exact"], "the traced search did not reach the exact optimum"
    for theme in THEMES:
        path = ROOT / "docs" / f"hero-{theme}.svg"
        path.write_text(render(theme, g), encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB, "
              f"{len(g['bundles'])} bundles, {len(g['path']) - 1} search steps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
