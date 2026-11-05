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

**As a Broker**, it acts during the Jury round. It treats the other Judges as players bargaining over *which findings the next revision addresses*. It computes a weighted Nash bargaining settlement and puts one proposal into the Jury digest. Every veto-holder is at least as well off in its own veto area accepting that proposal as blocking it.

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
| Loud-judge displacement | lower | **0.012** | 0.194 |
| Noise stability | higher | **0.848** | 0.801 |
| Veto satisfaction | higher | 1.0 | 1.0 |
| Judges shut out (avg) | lower | **0.057** | 0.133 |
| Utilitarian efficiency | higher | 0.957 | **0.988** |

Seeds 1–3 agree. In these simulated panels the broker is about 6–16× more resistant to a Judge who inflates every severity, and it shuts out 2–3× fewer Judges. It trails by 3–4 points on total value. On panels built to imitate live ones the two rules were nearly tied, so none of this is a live claim yet.

**Why cheap talk is "not priced."** An uncredible blocker is never forced and confers no veto. Its value in the Judge's utility is left at the blocker level on purpose. Severity values are geometric (1/2/4/8), so a Judge that inflates everything has only rescaled its own utility, and the Nash product is nearly invariant to that. An earlier variant capped such blockers at the major value. The evaluation showed the cap *raised* displacement from 0.03 to 0.09, because it let inflation reorder the Judge's own findings, so it was removed.

**Limits.** Synthetic panels test the selection rule, not LLM verdict quality, and payoffs come from severity points rather than elicitation. `run_live_comparison` is the hook for the real test: rounds to threshold and blind final scores on live subjects.

## How it is wired into the swarm

- **Registry.** `NASH_AGENT` and its presets are in `jjv/registry.py`. It is `library=True`, so it joins only through a panel.
- **Jury phase.** When a panel includes an archetype with `role == "broker"`, the orchestrator solves the settlement and shows it to each Judge after the fenced digest. It solves under anonymous aliases, so the printed math names no archetype.
- **Vote phase.** The broker solves again on the final verdicts to pick the fix list. Both settlements are stored with the run.
- **Verdict fields.** `endorses` and `change_aversion` are collected in the Jury round. Without a Jury, `change_aversion` falls back to 0.25.
- **Not a player.** Nash_Agent's own findings reach the Voter but are not bargained over, unless a Judge links its finding to one of them.
- **Linked findings.** In the Jury round a Judge can mark its own finding `same_as` another Judge's. `link_findings` gives them one id, so agreement counts and the issue costs budget once. Judges make the link; the broker changes nothing. A joined group stays forced if any member is a credible veto.
- **Rework cost.** A fix is done once, so each Judge bears a 1/n share of its cost. Charging everyone the whole cost let a lone blocker lose to a lone major.
- **The Voter is separate.** The broker sets priorities. The Voter still makes the decision, and its veto policy stays authoritative.
- **No broker on the panel.** The run uses weighted vote, and says so in the round's `aggregator` field.

## Decisions to confirm

- **A veto reaches only its own area (decided 2026-11-04).** A veto-holder's feasibility check counts only findings on its veto dimensions, so a clean security review no longer blocks a documentation fix. A block removes the optional fixes in that area, and utility adds up across findings, so blocking never pays and acceptance stays an equilibrium. A holder can now show a negative total gain, because its rework cost elsewhere still counts in the Nash product. The cost is about 2 points of utilitarian efficiency in the simulation (96% to 94%). On live panels this check rarely binds, because each veto word has one holder and a Judge can tag only its own words. Vetoes act through forced blockers.

- **An unvetoed blocker can be deferred.** This is the purist position: without a credible threat behind it, a blocker is cheap talk. If some disciplines should never defer a blocker, give that archetype a veto on the relevant dimension; don't soften the kernel.
- **Default budget is 8 cost units per revision**, about four majors. Tune it per panel.
- **Reputation needs a store.** The orchestrator saves cheap-talk counts to `reputation.json` beside the run records. Reputation changes later settlements, and a run record does not yet snapshot the history it used.

## Next steps

Broker work still open, from [the full list](architecture.md#next-steps):
- Confirm links on the full models. Findings no Judge linked still tie within a severity, and the first id wins.
- Make the weighted-vote baseline fair on live panels, then run the live comparison. Offline results are simulations only.
- Decide whether veto-holders may keep choosing their own finding's dimension, and whether `change_aversion` should stay self-reported.
