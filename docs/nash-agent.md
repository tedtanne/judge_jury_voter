---
title: Nash_Agent — equilibrium broker archetype
description: Spec for Nash_Agent, the game-theoretic negotiation archetype in Judge_Jury_Voter — persona, rubric, the bargaining kernel it runs in the Jury round, and how to wire it into the swarm.
status: draft
owner: Ted
updated: 2026-10-17
---

# Nash_Agent

Nash_Agent is a **role archetype** (not modeled on a person) built on hard-line game-theoretic negotiation: Nash equilibrium, the Nash bargaining solution, subgame-perfect credibility, Rubinstein alternating offers, mechanism design, and repeated games. It lives in `jjv/nash.py`; tests are in `tests/test_nash.py` (all passing, no API key needed).

It does two jobs in the swarm.

**As a Judge**, it scores a subject on how it behaves when every party acts in its own interest. That makes it useful for platform strategy, partner and enterprise terms, API pricing, and operating concepts. Its rubric has five dimensions: Incentive compatibility (1.2), Equilibrium stability (1.2), Commitment credibility (1.0), Pareto efficiency (0.8), and Strategic robustness (1.0).

**As a Broker**, it acts during the Jury round. It treats the other Judges as players bargaining over *which findings the next revision addresses*. It computes a weighted Nash bargaining settlement and puts one proposal into the Jury digest. Every veto-holder is at least as well off accepting that proposal as blocking it.

## The negotiation doctrine

The persona applies nine rules, in this order:

1. Set the disagreement point first.
2. Price only credible threats.
3. Delete dominated strategies.
4. Reach the Pareto frontier before splitting anything.
5. Split by the weighted Nash product.
6. Publish the rule used to pick between tied outcomes.
7. Price delay.
8. Treat the game as repeated, so reputation counts.
9. Prefer rules and mechanisms to rhetoric.

"Extreme" here means strict rigor. It does not mean manipulation. Nash_Agent bargains over priorities, **never over facts**. It never adds, drops, rewords, or re-scores another Judge's findings. It holds no veto and no stake, because a mediator with a threat point is really another player. Its own scores are sincere.

**Version 2 (October 2026)** adds three rules to the persona, drawn from the mechanism-design and negotiation papers in the project library:

10. Assume coalitions, and prefer mechanisms that make declaring a coalition dominant.
11. Know what is computable. Equilibrium finding is PPAD-hard, so always state whether an answer is exact, approximate, or local.
12. Know when to stop, and use reciprocity in repeated play.

The archetype record now carries a `grounded_in` list of those papers. The kernel itself is unchanged. See `domain-agents.md`.

## The kernel (`NashBroker`)

- **Players**: the Judges. Each player's weight is its archetype weight multiplied by a credibility factor drawn from past runs. The factor bottoms out at 0.5 for parties whose threats were always cheap talk.
- **Utility**: `u_i(S) = Σ v_i(f) − change_aversion_i · cost(S)`.
  - Severity values: blocker 8, major 4, minor 2, nit 1.
  - A Judge that endorses another Judge's finding gets half that finding's value.
- **Disagreement outcome D**: the credible vetoes. A credible veto is a blocker raised by a veto-holder on one of its own veto dimensions. D is forced into every outcome.
- **Cheap talk**:
  - A blocker from a Judge with no veto, or a veto-holder's blocker outside its veto dimension, is recorded but not priced.
  - A "reject" from a non-veto Judge is treated the same way.
- **Feasible outcomes**: they contain D, fit the revision budget, and leave every veto-holder at or above its disagreement utility.
- **Objective**: maximize `Σ w_i · φ(gain_i)`, where φ = log(1+g) for gains and linear for losses. This yields a Pareto-optimal outcome and spreads surplus across parties.
- **Search**: exhaustive for up to 16 optional findings. Above that it uses local search (add/drop/swap) and flags the result as a local optimum.
- **Output**: a `Settlement` with
  - the findings to address now, those deferred, and the forced vetoes
  - the list of cheap-talk threats
  - each party's surplus
  - `is_equilibrium` and `pareto_optimal` flags
  - `to_digest()`, which writes the plain-text proposal for the Jury round.

### Worked example (budget 7)

| Judge | Findings / behavior |
|---|---|
| Security (veto: authz) | Blocker: partner tokens not scoped per tenant |
| Simplifier (veto: complexity) | Major: drop the plugin marketplace |
| Product Lead | Blocker: enterprise tier has no pricing (no veto behind it); recommends reject |
| Staff Engineer | Major: no backpressure on event ingest |

Result:

- **Forced**: the tenant-scoping blocker.
- **Addressed now**: drop the marketplace and add key rotation. Key rotation was raised by Security and endorsed by Product Lead.
- **Deferred**: backpressure, onboarding, and enterprise pricing.
- The Product Lead's "blocker" and "reject" were recorded as cheap talk.

The settlement is Pareto-optimal, and accepting it is an equilibrium. The Staff Engineer ends at −1.00: it has no veto, and its finding lost the budget. The digest shows this number openly.

## Evaluation

`jjv/eval_broker.py` compares the broker with a conventional weighted vote. The vote takes credible vetoes first, then ranks findings by weighted severity and fills the budget greedily. Both run on the same synthetic panels. Results for 300 panels with seed 7:

| Metric | Better | Nash broker | Weighted vote |
|---|---|---|---|
| Loud-judge displacement | lower | **0.029** | 0.194 |
| Noise stability | higher | 0.809 | 0.801 |
| Veto satisfaction | higher | 1.0 | 1.0 |
| Judges shut out (avg) | lower | **0.077** | 0.133 |
| Utilitarian efficiency | higher | 0.962 | **0.988** |

Seeds 1–3 agree. The broker is about 5–7× more resistant to a Judge who inflates every severity, and it shuts out 2–3× fewer Judges. It trails by 2–3 points on total value addressed, which is the expected price of optimizing the Nash product rather than the sum.

**Why cheap talk is "not priced."** An uncredible blocker is never forced and confers no veto. Its value in the Judge's utility is left at the blocker level on purpose. Severity values are geometric (1/2/4/8), so a Judge that inflates everything has only rescaled its own utility, and the Nash product is nearly invariant to that. An earlier variant capped such blockers at the major value. The evaluation showed the cap *raised* displacement from 0.03 to 0.09, because it let inflation reorder the Judge's own findings, so it was removed.

**Limits.** Synthetic panels test the selection rule, not LLM verdict quality, and payoffs come from severity points rather than elicitation. `run_live_comparison` is the hook for the real test: rounds to threshold and blind final scores on live subjects.

## Wiring it into the swarm

1. **Register the archetype.** Add `NASH_AGENT` to the registry, via `Archetype(**NASH_AGENT)` or a studio import. It is `library=True`, so it joins only through a panel.
2. **Add the presets** from `NASH_PRESETS` to `PRESET_PANELS` in `jjv/legends.py`:
   - *The Nash Table*: Nash, Security, Simplifier, Staff Engineer, Product Lead.
   - *Treaty Room*, for partner and alliance deals: Nash, Attestation Architect, Systems Integrator, Mission Assurance Officer, Product Lead.
3. **Update the orchestrator.** In the Jury phase, when a convened archetype has `role == "broker"`:
   - Build verdict dicts that carry `archetype_id`, `weight`, `veto`, `veto_dimensions`, `findings`, `recommendation`, and `endorses`.
   - Call `NashBroker(budget=…).solve(verdicts)`.
   - Append `settlement.to_digest()` to the anonymized digest each Judge sees before it revises.
   - Store the Settlement with the run for audit.
4. **Add two optional verdict fields** to the schema: `endorses` (finding ids the Judge supports after deliberation) and `change_aversion` (how much the Judge dislikes churn).
5. **The Voter needs no change.** The broker proposes priorities, and the Voter still aggregates the final verdicts. Its veto policy stays authoritative.

## Decisions to confirm

- **An unvetoed blocker can be deferred.** This is the purist position: without a credible threat behind it, a blocker is cheap talk. If some disciplines should never defer a blocker, give that archetype a veto on the relevant dimension; don't soften the kernel.
- **Default budget is 8 cost units per revision**, about four majors. Tune it per panel.
- **Reputation is on only when `history` is passed.** Persisting cheap-talk counts across runs requires one new table.
