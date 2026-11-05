# Judge_Jury_Voter

![tests](https://github.com/tedtanne/judge_jury_voter/actions/workflows/tests.yml/badge.svg)

A swarm of AI review agents. Each agent is an *archetype* of a best-in-the-business professional. Together they **review** and **generate** code, documentation and designs.

- **Judges** score a subject independently.
- **The Jury** lets them see an anonymized digest of each other's verdicts and revise.
- **The Voter** aggregates the final verdicts into a decision and a ranked action list.
- **A Generator loop** reuses the same panel to draft, critique and revise from a brief.

The distinctive piece is **Nash_Agent**, a game-theoretic broker that runs during the Jury round. It treats the Judges as players bargaining over which findings the next revision fixes, under a fixed revision budget. It settles that bargaining with the Nash bargaining solution, not a vote. A Judge's threat counts only when it holds a veto for that area. In simulation this resists one overconfident Judge far better than weighted voting, but that has not been shown on live panels (see [Evaluation](#evaluation)).

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                                          # 164 unit tests, no API key needed
python -m jjv.registry > docs/archetypes.md        # regenerate the archetype catalog
python -m jjv.eval_broker --trials 300 --seed 7    # Nash broker vs weighted vote
```

Everything except live runs uses the Python standard library alone. `requirements.txt` only adds the test tooling.

To run a real panel, install the Claude Agent SDK. Live runs call Claude and spend money, up to `--max-usd` (default $5, a soft limit checked between calls). Run records go to `~/.jjv/runs`, outside any repo, because they name who is behind each anonymous Judge and Judges can read the repo they review. Keep secrets gitignored too: Judges cannot read files named like secrets, but a `Grep` can search one that git does not ignore. A store inside `--repo` is refused.

```bash
pip install -r requirements-live.txt
python -m jjv.cli review design.md --panel "Physics of Compute"
git diff | python -m jjv.cli review - --discipline code --repo .
python -m jjv.cli generate brief.txt --panel "Docs Crit" --out draft.md
```

## What's in this repository

| Piece | What it does | Where |
|---|---|---|
| Default archetypes | Six generic jurors that auto-convene by discipline, including the Drafter (the Generator) | `jjv/archetypes.py` |
| Legend roster | 31 trait-profile and mission archetypes, plus the ten original preset rooms; `PRESET_PANELS` merges all 19 presets | `jjv/legends.py` |
| Domain archetypes | Eight role archetypes with rubrics, veto dimensions, presets, and the papers their standards come from | `jjv/domain_roles.py` |
| Nash_Agent | Archetype record, plus the deterministic bargaining kernel that brokers the Jury round | `jjv/nash.py` |
| Registry | One lookup for all 46 archetypes and 19 presets, the veto-dimension vocabulary, `validate()`, and the generated catalog | `jjv/registry.py`, `docs/archetypes.md` |
| Orchestrator | Runs SELECT, JUDGE, JURY, VOTE and the generate loop in fixed order, with retries, quorum, spending limit, saved run records and reputation | `jjv/orchestrator.py`, `jjv/backend.py`, `jjv/cli.py` |
| Voter | Deterministic tally: consensus score, decision by veto policy, ranked findings, dissents | `jjv/voter.py`, `jjv/verdicts.py` |
| Evaluation | Nash broker vs weighted voting: offline simulation plus a live-comparison hook | `jjv/eval_broker.py` |
| Tests and CI | 164 unit tests; GitHub Actions runs them on Python 3.10–3.12 along with the evaluation | `tests/`, `.github/workflows/tests.yml` |
| Design docs | The full swarm architecture and roadmap, the broker spec, the domain-agent library map, and the catalog | `docs/` |

**Status.** This repository holds the full archetype registry (46 archetypes, 19 presets, every preset member defined), the negotiation layer and its evaluation, the orchestrator, the Voter, and a CLI. Still to come: the FastAPI backend and web UI, and the live broker comparison on real subjects.

**Next steps**, in recommended order (details in [`docs/architecture.md`](docs/architecture.md#next-steps)):
1. Confirm finding links on the full models. So far they have been checked on two cheap-model runs.
2. Show Judges the brief in generate mode, and carry findings across rounds.
3. Make the weighted-vote baseline fair on live panels, then run the live broker comparison.
4. Decide the open incentive questions in the Voter and the broker.
5. Add an MCP server, so MCP clients can call the panels: free read-only tools first, then capped `review` and `generate`.
6. Build the web interface.

Design rationale is in [`docs/architecture.md`](docs/architecture.md). The broker spec is in [`docs/nash-agent.md`](docs/nash-agent.md), the domain archetypes are in [`docs/domain-agents.md`](docs/domain-agents.md), and every archetype and preset is listed in [`docs/archetypes.md`](docs/archetypes.md).

## The archetypes

An archetype is one reviewer lens: a persona, a scoring rubric, a weight, and sometimes a veto. There are 46, in four groups:

| Group | Count | Who they are | Examples |
|---|---|---|---|
| Defaults | 6 | Generic reviewers that convene automatically by discipline. The Drafter writes drafts and never votes. | Staff Engineer, Security Reviewer, Technical Writer |
| Legends | 31 | Trait profiles across engineering (9), founders (9), design (5), investors (3), mission roles (3), plus The Simplifier and The Clarity Editor. They join through presets. | The Reliability Engineer, The Reductionist, The Value Investor |
| Domain roles | 8 | Specialists modeled on a discipline, each with standards drawn from published papers. | The Cryptographer, The Evidence Auditor, The Thermodynamicist |
| Broker | 1 | Nash_Agent, which judges a subject and also brokers the Jury round. It holds no veto. | Nash_Agent |

Twelve archetypes hold a veto, each on one area. For example, the Security Reviewer holds `security` and The Thermodynamicist holds `physical-correctness`.

A **preset** is a ready-made panel of 3–6 archetypes, and there are 19. For example, *Physics of Compute* convenes The Thermodynamicist, The Metering Economist, The Silicon Compiler Architect, The Evidence Auditor and Nash_Agent.

"Legend" archetypes are trait profiles: lenses *inspired by* how notable people are publicly known to work. They are not impersonations. They never speak as those people, and no endorsement or affiliation is implied. Role archetypes, such as The Cryptographer and Nash_Agent, are modeled on a discipline, not on any person.

Every archetype, veto and preset is listed in [`docs/archetypes.md`](docs/archetypes.md).

## The Nash_Agent broker in brief

1. **Disagreement point.** A blocker raised by a Judge holding a veto for that area is a *credible* threat. It is forced into every outcome. Any other blocker or "reject" is recorded as cheap talk.
2. **Feasible set.** These are the outcomes that fit the revision budget and leave every veto-holder at least as well off *in its own veto area* as blocking.
3. **Settlement.** The broker maximizes a weighted Nash product of each Judge's gain over the disagreement point, then breaks ties by a published rule.
4. **Transparency.** The settlement goes into the Jury digest with the math shown: what is fixed now, what is deferred, whose threats were cheap talk, and each Judge's net gain.

A veto reaches only its holder's area, and each holder weakly prefers the settlement to blocking there, so accepting it is a Nash equilibrium of the ratification step. The broker bargains over *priorities*, never facts: it cannot add, drop, reword or re-score anyone's findings.

In the Jury round a Judge can mark its own finding `same_as` another Judge's. Linked findings are fixed as one, so agreement counts and an issue costs the budget once. Each Judge's words stay on record.

## Tests

```bash
bash scripts/run_tests.sh        # writes reports/: log, junit.xml, coverage, summary
```

CI (`.github/workflows/tests.yml`) runs the suite on Python 3.10–3.12 for every push and pull request. Results, per-module coverage, and the broker evaluation appear on each run's **Summary** page. No API key is used in CI.

## Evaluation

`python -m jjv.eval_broker --trials 300 --seed 7` generates synthetic review panels: 4–6 Judges, one or two veto-holders, and overlapping findings with severities and costs. It then compares the Nash broker against a conventional *weighted vote*: credible vetoes first, then findings ranked by weighted severity, taken greedily within the budget. Both aggregators parse findings identically; only the selection rule differs.

| Metric (300 panels, seed 7) | Better | Nash broker | Weighted vote |
|---|---|---|---|
| Loud-judge displacement | lower | **0.012** | 0.194 |
| Noise stability | higher | **0.848** | 0.801 |
| Veto satisfaction | higher | 1.0 | 1.0 |
| Judges shut out (avg) | lower | **0.057** | 0.133 |
| Utilitarian efficiency | higher | 0.957 | **0.988** |

What the metrics mean:
- **Loud-judge displacement:** how much the chosen fix list changes when one Judge without a veto inflates every severity by a level and recommends reject.
- **Noise stability:** how much the fix list overlaps across reruns with randomly jittered severities.
- **Judges shut out:** Judges who raised findings but got none addressed.
- **Utilitarian efficiency:** the total weighted value addressed, as a share of the best any budget-feasible list could address.

Seeds 1–3 give the same picture:
- displacement 0.01–0.03 vs 0.16–0.17;
- judges shut out 0.04–0.06 vs 0.12–0.19;
- stability higher, 0.84–0.86 vs 0.81–0.82;
- efficiency 95–96% vs 99%.

**Interpretation.**
- In these simulated panels the broker resists one overconfident voice about 6–16 times better, and it shuts fewer Judges out. In exchange it addresses about 3–4% less total value.
- That trade is deliberate. The Nash product favors spreading gains over maximizing their sum.
- The robustness comes from the Nash product's invariance to how a player scales its own utility. Severity values are geometric (1/2/4/8), so inflating every severity by one level is nearly a pure rescale.
- An early variant capped the value of no-veto blockers. The evaluation showed the cap made displacement *worse* (0.03 → 0.09), so it was removed.

**Limits.** These results do not carry over to live panels so far. On panels built to imitate live ones, with far more issues than the budget fits, the two rules were nearly tied: displacement 0.41–0.43 vs 0.42–0.44, and voting was slightly ahead on value and blockers. Only the live comparison can settle it. Synthetic panels test the aggregation rule, not the quality of LLM verdicts. Payoffs are assigned from severity points, not elicited from the Judges. The test that matters is the live comparison: `run_live_comparison(subjects, run_fn)` drives real generate-loop runs with each aggregator. It reports rounds to reach the quality threshold, and final scores from a separate, blind panel. That is roadmap Phase 5b.

## Related work

Judge_Jury_Voter combines established ideas. The bargaining broker is the part that does not appear to have direct precedent. A short search found no prior work that aggregates LLM critiques by Nash bargaining over a revision budget, with a credible-veto filter and reputation across runs. This is a search, not a systematic review.

**LLM juries, debate and refinement**
- Verga et al., *Replacing Judges with Juries: Evaluating LLM Generations with a Panel of Diverse Models* (2024). A panel of diverse smaller judges beats a single large judge. [arXiv:2404.18796](https://arxiv.org/abs/2404.18796)
- Du et al., *Improving Factuality and Reasoning in Language Models through Multiagent Debate* (2023). [arXiv:2305.14325](https://arxiv.org/abs/2305.14325)
- Chan et al., *ChatEval: Towards Better LLM-based Evaluators through Multi-Agent Debate* (2023). [arXiv:2308.07201](https://arxiv.org/abs/2308.07201)
- Madaan et al., *Self-Refine: Iterative Refinement with Self-Feedback* (2023). This is the draft–critique–revise pattern behind the Generator loop. [arXiv:2303.17651](https://arxiv.org/abs/2303.17651)
- *Literature Review of Multi-Agent Debate for Problem-Solving* (2025). [arXiv:2506.00066](https://arxiv.org/abs/2506.00066)
- Emergent Mind, *Multi-Agent Critique Aggregation*. An overview of voting, averaging and debate as aggregation methods. [link](https://www.emergentmind.com/topics/multi-agent-critique-aggregation)

**Deliberation**
- Dalkey & Helmer, *An Experimental Application of the Delphi Method to the Use of Experts*, Management Science (1963). The Jury round's anonymized digest-and-revise step is a Delphi round.

**LLMs and game theory**
- Hua et al., *Game-theoretic LLM: Agent Workflow for Negotiation Games* (2024). Here LLMs are the negotiators; in Judge_Jury_Voter, a deterministic kernel bargains on the Judges' behalf. [arXiv:2411.05990](https://arxiv.org/abs/2411.05990)
- Bhattacharya et al., *Evaluating Negotiation Capabilities of Large Language Models: From Ultimatum Games to Nash Bargaining* (2025). [Proc. HFES](https://journals.sagepub.com/doi/10.1177/10711813251372102)
- *LLM Agents for Bargaining with Utility-based Feedback* (2025). [arXiv:2505.22998](https://arxiv.org/abs/2505.22998)

**Game theory and mechanism design foundations**
- Nash, *The Bargaining Problem*, Econometrica (1950); *Non-Cooperative Games*, Annals of Mathematics (1951).
- Rubinstein, *Perfect Equilibrium in a Bargaining Model*, Econometrica (1982).
- Hu & Wellman, *Nash Q-Learning for General-Sum Stochastic Games*, JMLR (2003).
- Chen & Micali, *Collusive Dominant-Strategy Truthfulness* (2012). The source of Nash_Agent's assume-coalitions rule.
- Goldberg, Papadimitriou & Savani, *The Complexity of the Homotopy Method, Equilibrium Selection, and Lemke-Howson Solutions*, ACM TEAC (2013). The source of Nash_Agent's know-what-is-computable rule.

The domain archetypes cite their own grounding papers in each record's `grounded_in` field. See [`docs/domain-agents.md`](docs/domain-agents.md).

## License

See [`LICENSE`](LICENSE).
