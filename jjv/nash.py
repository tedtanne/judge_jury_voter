"""Nash_Agent — the swarm's equilibrium broker.

Nash_Agent is a role archetype (not modeled on a person) for Judge_Jury_Voter. It has
two faces:

1. As a **Judge**, it scores a subject — a platform strategy, a partner contract, an API
   pricing tier, an operating concept — on how it behaves when every party acts in its own
   interest: incentive compatibility, equilibrium stability, commitment credibility,
   Pareto efficiency, and robustness to strategic/colluding actors.

2. As a **Broker** in the Jury round, it treats the other Judges as players in a
   bargaining game over *which findings the revision must address*, computes the
   weighted Nash bargaining settlement deterministically (``NashBroker``), and hands the
   Jury a single proposal every veto-holder is individually better off accepting.

The "extreme" is in rigor, never in manipulation. The broker bargains over *priorities*,
never over *facts*: it cannot add, drop, reword, or re-score another Judge's finding, it
holds no veto and no stake (a mediator with a threat point is a player, not a broker),
and it reports its own scores sincerely. Deception would be a dominant strategy for one
round and a ruinous one in the repeated game this swarm actually plays.

The kernel is pure Python with no dependencies so it runs (and tests) without an API key.
"""

from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass, field
from typing import Iterable

# ---------------------------------------------------------------------------
# Archetype record
# ---------------------------------------------------------------------------

NASH_PERSONA = """\
You are Nash_Agent, the equilibrium broker of a review swarm. You are best-in-the-business
at strategic negotiation in the tradition of game theory: Nash equilibrium and the Nash
bargaining solution, subgame-perfect reasoning, mechanism design, Rubinstein alternating
offers, and repeated games. You are a role archetype, not an impersonation of anyone.

HOW YOU THINK — apply these in order, every time:
1. Disagreement point first. Before any proposal, establish what each party gets if talks
   fail (their BATNA). No offer is evaluated in the absolute, only as surplus over that point.
2. Only credible threats count. A threat is credible only if carrying it out is in the
   threatener's interest when the moment comes (subgame perfection). A blocker from a
   veto-holder on its veto dimension is credible; "reject" from a party with no veto is
   cheap talk — record it, do not price it.
3. Delete dominated strategies. Any position every party would abandon given the others'
   positions is removed before bargaining starts.
4. Pareto before split. Never argue over how to divide value while value is still on the
   table; first move to the frontier.
5. Split by the weighted Nash product. On the frontier, choose the outcome maximizing the
   product of each party's surplus raised to its weight. It is the unique split that is
   efficient, symmetric under relabeling, independent of irrelevant alternatives, and
   invariant to how each party scales its own utility.
6. Publish the selection rule. Equilibria are often non-unique; coordination fails when
   parties pick different ones. State your tie-break rule to everyone so it becomes
   common knowledge and a focal point.
7. Delay has a price. Every extra revision round costs budget; the less patient party
   concedes more (Rubinstein). Say who pays for delay.
8. The game repeats. Track which parties' threats were cheap talk across runs; a party's
   credibility is its reputation. Cooperation is sustained by the shadow of the future.
9. Rules over rhetoric. Prefer proposing a mechanism (a rule, a commitment device, an
   escrow, a sunset clause) to persuading anyone of anything.
10. Assume coalitions. Truthfulness for individuals is not truthfulness for colluding
   groups; even a Vickrey auction loses efficiency to two colluders with wrong beliefs.
   Ask who could coordinate, and prefer mechanisms that make declaring the coalition a
   dominant strategy over ones that merely forbid it.
11. Know what is computable. Finding a Nash equilibrium is PPAD-hard in general, and the
   specific equilibrium a homotopy or Lemke-Howson path reaches is PSPACE-complete to
   predict. Never promise "the" equilibrium of a large game; state the solution concept,
   the algorithm, and whether the answer is exact, approximate, or local.
12. Know when to stop. Every further offer has an expected value and a cost; stop when
   the expected gain from another round falls below the cost of delay, and say so.
   Reciprocity that is nice, retaliatory, forgiving and clear sustains cooperation in
   repeated play; use it, don't just preach it.

WHEN YOU JUDGE A SUBJECT, ask of every party it touches: what is their payoff, what is
their best response, who can defect profitably, which promises are unenforceable, and what
coalition could form against the designer. Name the equilibrium the design will actually
settle into, not the one its author hopes for.

HARD CONSTRAINTS — these are not negotiable, including with yourself:
- Bargain over priorities, never over facts. You never invent, drop, reword, merge, or
  re-score another Judge's findings. You only propose which findings the revision
  addresses now and which it defers, with the math shown.
- You hold no veto and no stake. You do not threaten.
- Your own scores are sincere. You never shade them to move the Voter's tally.
- Show your work: disagreement point, credible vs cheap-talk threats, the settlement,
  each party's surplus, and your tie-break rule.
"""

NASH_RUBRIC = [
    {
        "name": "Incentive compatibility",
        "weight": 1.2,
        "anchors": {
            1: "Parties profit by misreporting, free-riding, or gaming the rules.",
            3: "Honest participation is usually best, with exploitable gaps named.",
            5: "Truthful, compliant behavior is each party's dominant strategy.",
        },
    },
    {
        "name": "Equilibrium stability",
        "weight": 1.2,
        "anchors": {
            1: "At least one party gains by defecting from the intended outcome.",
            3: "Intended outcome is an equilibrium but not unique or not robust.",
            5: "Intended outcome is the unique, stable equilibrium.",
        },
    },
    {
        "name": "Commitment credibility",
        "weight": 1.0,
        "anchors": {
            1: "Key promises or threats are not in the promiser's interest to keep.",
            3: "Most commitments are enforceable; some rely on goodwill.",
            5: "Every commitment is backed by a mechanism (escrow, attestation, contract).",
        },
    },
    {
        "name": "Pareto efficiency",
        "weight": 0.8,
        "anchors": {
            1: "Obvious gains left on the table that would hurt no one to capture.",
            3: "Near the frontier; minor improvements available.",
            5: "No party can be made better off without making another worse off.",
        },
    },
    {
        "name": "Strategic robustness",
        "weight": 1.0,
        "anchors": {
            1: "Breaks under a single adversarial or colluding actor.",
            3: "Survives individual adversaries; vulnerable to coalitions.",
            5: "Holds under adversarial actors and plausible coalitions.",
        },
    },
]

# Mirrors the archetype record in architecture.md. If the scaffold's Archetype is a
# dataclass, construct it with Archetype(**NASH_AGENT); unknown keys can be dropped.
NASH_AGENT = {
    "id": "nash_agent",
    "name": "Nash_Agent",
    "discipline": "strategy",
    "persona": NASH_PERSONA,
    "rubric": NASH_RUBRIC,
    "weight": 1.0,
    "veto": False,            # a broker with a threat point is a player
    "tools": ["Read", "Grep", "Glob"],
    "model": None,            # inherit; set to the strongest tier for brokered runs
    "effort": "high",
    "library": True,          # joins by panel only, never auto-convenes
    "inspired_by": "Game theory: Nash (1950, 1951), Rubinstein (1982), mechanism design",
    "role": "broker",         # tells the orchestrator to run NashBroker in the Jury round
    "enabled": True,
    "version": 2,
    "grounded_in": [
        "Nash Q-Learning for General-Sum Stochastic Games.pdf",
        "Algorithmic Mechanism Design .pdf",
        "Classic Mechanism Design.pdf",
        "Collusive Dominant-Strategy Truthfulness.pdf",
        "Computationally Efficient Techniques for Economic Mechanisms.pdf",
        "The Complexity of the Homotopy Method Equilibrium Selection and Lemke-Howson Solutions.pdf",
        "A Game Tree Strategy for Automated Negotiation.pdf",
        "A Negotiation Protocol for Optimal Decision Making by Collaborating Agents .pdf",
        "A Review of Strategy Design and Evaluation of Software Negotiation Agents.pdf",
        "Designing an Automated Negotiator- Learning What to Bid and When to Stop.pdf",
        "An open framework for the reproducible study of the iterated prisoner’s dilemma..pdf",
        "Incentives Build Robustness in BitTorrent.pdf",
        "HISTORY BASED COALITION FORMATION IN HEDONIC CONTEXT USING TRUST.pdf",
        "AutonomousAgents_And_GameTheory.pdf",
    ],
}

# Suggested presets for PRESET_PANELS in jjv/legends.py.
NASH_PRESETS = {
    "The Nash Table": [
        "nash_agent", "security_reviewer", "simplifier", "staff_engineer", "product_lead",
    ],
    "Treaty Room": [  # partner and alliance deals: every party has an exit option
        "nash_agent", "attestation_architect", "systems_integrator",
        "mission_assurance_officer", "product_lead",
    ],
}

# ---------------------------------------------------------------------------
# Bargaining kernel
# ---------------------------------------------------------------------------

SEVERITY_VALUE = {"blocker": 8.0, "major": 4.0, "minor": 2.0, "nit": 1.0}
DEFAULT_COST = {"blocker": 3.0, "major": 2.0, "minor": 1.0, "nit": 1.0}
SEVERITY_RANK = {"nit": 0, "minor": 1, "major": 2, "blocker": 3}
ENDORSE_SHARE = 0.5
EXACT_LIMIT = 16  # enumerate all bundles up to 2**16 optional findings; else local search

TIE_BREAK_RULE = (
    "Maximize the weighted Nash product; ties go to higher total utility, then lower "
    "revision cost, then the lexicographically first set of finding keys."
)


def _key(finding: dict) -> str:
    raw = finding.get("id") or finding.get("title") or ""
    return re.sub(r"[^a-z0-9]+", "-", str(raw).lower()).strip("-")


@dataclass
class Player:
    id: str
    weight: float = 1.0
    veto: bool = False
    veto_dimensions: tuple[str, ...] = ()   # empty + veto=True means any dimension
    change_aversion: float = 0.25           # utility lost per unit of revision cost
    values: dict[str, float] = field(default_factory=dict)

    def can_veto(self, dimension: str | None) -> bool:
        if not self.veto:
            return False
        return not self.veto_dimensions or dimension in self.veto_dimensions


@dataclass
class Finding:
    key: str
    title: str
    severity: str
    dimension: str | None
    cost: float
    raised_by: list[str] = field(default_factory=list)
    endorsed_by: list[str] = field(default_factory=list)


@dataclass
class Settlement:
    address_now: list[str]
    deferred: list[str]
    forced: list[str]
    cheap_talk: list[dict]
    gains: dict[str, float]
    utilities: dict[str, float]
    disagreement: dict[str, float]
    budget: float
    cost: float
    objective: float
    individually_rational: bool
    pareto_optimal: bool | None      # None when search was heuristic
    exact: bool
    notes: list[str]
    findings: dict[str, Finding]
    tie_break_rule: str = TIE_BREAK_RULE

    @property
    def is_equilibrium(self) -> bool:
        """Accept-by-all is a Nash equilibrium of the ratification game.

        Only veto-holders can move the outcome by rejecting, and each weakly prefers the
        settlement to the disagreement point, so no player gains by deviating alone.
        """
        return self.individually_rational

    def to_digest(self) -> str:
        """Plain-text proposal for the anonymized Jury-round digest."""
        f = self.findings
        line = lambda k: f"  - [{f[k].severity}] {f[k].title}"
        out = ["NASH_AGENT SETTLEMENT PROPOSAL", ""]
        out.append("Credible vetoes (included; not negotiable):")
        out += [line(k) for k in self.forced] or ["  - none"]
        out.append("Address in this revision:")
        out += [line(k) for k in self.address_now if k not in self.forced] or ["  - none"]
        out.append("Defer (conceded this round, stays on record):")
        out += [line(k) for k in self.deferred] or ["  - none"]
        if self.cheap_talk:
            out.append("Unpriced threats (no veto behind them):")
            out += [f"  - {c['by']}: {c['what']}" for c in self.cheap_talk]
        out.append("")
        out.append(f"Revision cost {self.cost:g} of budget {self.budget:g}.")
        out.append("Surplus over disagreement, by party:")
        out += [f"  - {p}: {g:+.2f}" for p, g in sorted(self.gains.items())]
        out.append(
            "Every veto-holder is at least as well off accepting as blocking, so "
            "acceptance is an equilibrium." if self.individually_rational else
            "WARNING: a veto-holder is worse off than disagreement; expect a block."
        )
        out.append(f"Selection rule: {self.tie_break_rule}")
        out.append("To object, cite a finding and a credible veto; other objections are "
                   "recorded but not priced.")
        out += [f"Note: {n}" for n in self.notes]
        return "\n".join(out)


class NashBroker:
    """Computes the weighted Nash bargaining settlement over Judges' findings.

    The game: players are Judges; the joint decision is the set S of findings the next
    revision addresses. Player i's utility is

        u_i(S) = sum(v_i(f) for f in S) - change_aversion_i * cost(S)

    where v_i(f) is the finding's severity value if i raised it, half that if i endorsed
    it in deliberation, else 0. Findings that are credible vetoes are forced into every
    outcome, including the disagreement outcome D (a subgame-perfect veto-holder would
    carry the threat out). Feasible S contain D, fit the revision budget, and leave every
    veto-holder at least as well off as D. Among feasible S we maximize

        sum_i w_i * phi(u_i(S) - u_i(D)),  phi(g) = log(1+g) if g > 0 else g

    a smoothed weighted Nash product: strictly increasing in each surplus, so the
    maximizer is Pareto-optimal, and concave on gains, so surplus is spread rather than
    piled on one party.
    """

    def __init__(self, budget: float = 8.0, history: dict | None = None):
        self.budget = budget
        # history[archetype_id] = {"rounds": int, "cheap_talk": int}; lowers weight of
        # parties whose past threats were empty (reputation in the repeated game).
        self.history = history or {}

    # -- building the game --------------------------------------------------

    def _credibility(self, pid: str) -> float:
        h = self.history.get(pid)
        if not h or not h.get("rounds"):
            return 1.0
        return max(0.5, 1.0 - 0.5 * h.get("cheap_talk", 0) / h["rounds"])

    def build(self, verdicts: Iterable[dict]):
        players: dict[str, Player] = {}
        findings: dict[str, Finding] = {}
        cheap_talk: list[dict] = []

        verdicts = list(verdicts)
        for v in verdicts:
            pid = v["archetype_id"]
            players[pid] = Player(
                id=pid,
                weight=float(v.get("weight", 1.0)) * self._credibility(pid),
                veto=bool(v.get("veto", False)),
                veto_dimensions=tuple(v.get("veto_dimensions", ())),
                change_aversion=float(v.get("change_aversion", 0.25)),
            )
            for raw in v.get("findings", []):
                k = _key(raw)
                if not k:
                    continue
                sev = raw.get("severity", "minor")
                sev = sev if sev in SEVERITY_VALUE else "minor"
                cost = float(raw.get("cost", DEFAULT_COST[sev]))
                if k not in findings:
                    findings[k] = Finding(k, raw.get("title", k), sev,
                                          raw.get("dimension"), cost)
                f = findings[k]
                if SEVERITY_RANK[sev] > SEVERITY_RANK[f.severity]:
                    f.severity = sev
                f.cost = max(f.cost, cost)
                if pid not in f.raised_by:
                    f.raised_by.append(pid)
                players[pid].values[k] = max(players[pid].values.get(k, 0.0),
                                             SEVERITY_VALUE[sev])

        # Endorsements and cheap talk need the full finding set.
        for v in verdicts:
            p = players[v["archetype_id"]]
            for raw_key in v.get("endorses", []):
                k = _key({"id": raw_key})
                if k in findings and k not in p.values:
                    findings[k].endorsed_by.append(p.id)
                    p.values[k] = ENDORSE_SHARE * SEVERITY_VALUE[findings[k].severity]
            if v.get("recommendation") == "reject" and not p.veto:
                cheap_talk.append({"by": p.id, "what": "recommended reject without a veto"})

        forced = []
        for k, f in findings.items():
            if f.severity != "blocker":
                continue
            if any(players[pid].can_veto(f.dimension) for pid in f.raised_by):
                forced.append(k)
            else:
                for pid in f.raised_by:
                    cheap_talk.append({"by": pid, "what": f"blocker without veto: {f.title}"})
        # Deliberately NOT capping the value of a no-veto blocker. Severity values are
        # geometric (1/2/4/8), so a Judge inflating every finding by one level just
        # rescales its own utility, and the Nash product is (nearly) invariant to that.
        # A cap breaks the symmetry and lets inflation reorder the Judge's findings;
        # jjv.eval_broker measured displacement rising from 0.03 to 0.09 with a cap.
        return players, findings, sorted(forced), cheap_talk

    # -- solving ------------------------------------------------------------

    @staticmethod
    def _utility(p: Player, S: frozenset, findings: dict) -> float:
        return (sum(p.values.get(k, 0.0) for k in S)
                - p.change_aversion * sum(findings[k].cost for k in S))

    def solve(self, verdicts: Iterable[dict]) -> Settlement:
        players, findings, forced, cheap_talk = self.build(verdicts)
        notes: list[str] = []
        D = frozenset(forced)
        cost = lambda S: sum(findings[k].cost for k in S)
        budget = self.budget
        if cost(D) > budget:
            budget = cost(D)
            notes.append(f"Credible vetoes alone cost {budget:g}; budget raised to fit them.")

        d = {pid: self._utility(p, D, findings) for pid, p in players.items()}
        vetoers = [p for p in players.values() if p.veto]

        def feasible(S):
            if cost(S) > budget + 1e-9:
                return False
            return all(self._utility(p, S, findings) >= d[p.id] - 1e-9 for p in vetoers)

        def score(S):
            obj = 0.0
            for pid, p in players.items():
                g = self._utility(p, S, findings) - d[pid]
                obj += p.weight * (math.log1p(g) if g > 0 else g)
            total = sum(self._utility(p, S, findings) for p in players.values())
            # Deterministic, published tie-break (see TIE_BREAK_RULE).
            return (round(obj, 9), round(total, 9), -cost(S),
                    tuple(-ord(c) for c in ",".join(sorted(S))))

        optional = sorted(k for k in findings if k not in D)
        exact = len(optional) <= EXACT_LIMIT
        candidates: list[frozenset] = []

        if exact:
            for r in range(len(optional) + 1):
                for combo in itertools.combinations(optional, r):
                    S = D | frozenset(combo)
                    if feasible(S):
                        candidates.append(S)
            best = max(candidates, key=score)
        else:
            notes.append(f"{len(optional)} optional findings; used local search "
                         "(add/drop/swap). Settlement is a local optimum.")
            best = D
            improved = True
            while improved:
                improved = False
                moves = [best | {k} for k in optional if k not in best]
                moves += [best - {k} for k in best if k not in D]
                moves += [(best - {a}) | {b} for a in best if a not in D
                          for b in optional if b not in best]
                moves = [m for m in moves if feasible(m)]
                if moves:
                    top = max(moves, key=score)
                    if score(top) > score(best):
                        best, improved = top, True

        u = {pid: self._utility(p, best, findings) for pid, p in players.items()}
        gains = {pid: round(u[pid] - d[pid], 4) for pid in players}

        pareto = None
        if exact:
            pareto = not any(
                all(self._utility(p, S, findings) >= u[pid] - 1e-9
                    for pid, p in players.items())
                and any(self._utility(p, S, findings) > u[pid] + 1e-9
                        for pid, p in players.items())
                for S in candidates
            )

        return Settlement(
            address_now=sorted(best),
            deferred=[k for k in optional if k not in best],
            forced=forced,
            cheap_talk=cheap_talk,
            gains=gains,
            utilities={k: round(v, 4) for k, v in u.items()},
            disagreement={k: round(v, 4) for k, v in d.items()},
            budget=budget,
            cost=cost(best),
            objective=score(best)[0],
            individually_rational=all(gains[p.id] >= -1e-9 for p in vetoers),
            pareto_optimal=pareto,
            exact=exact,
            notes=notes,
            findings=findings,
        )
