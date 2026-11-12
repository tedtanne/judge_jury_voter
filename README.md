# Judge_Jury_Voter

![tests](https://github.com/tedtanne/judge_jury_voter/actions/workflows/tests.yml/badge.svg)

A swarm of AI review agents. Each agent is an *archetype* of a best-in-the-business professional. Together they **review** and **generate** code, documentation and designs.

- **Judges** score a subject independently.
- **The Jury** lets them see an anonymized digest of each other's verdicts and revise.
- **The Voter** aggregates the final verdicts into a decision and a ranked action list.
- **A Generator loop** reuses the same panel to draft, critique and revise from a brief.

The distinctive piece is **Nash_Agent**, a game-theoretic broker that runs during the Jury round. It treats the Judges as players bargaining over which findings the next revision fixes, under a fixed revision budget. It settles that bargaining with the Nash bargaining solution, not a vote. A Judge's threat counts only when it holds a veto for that area. In simulation this resists one overconfident Judge far better than weighted voting, but that has not been shown on live panels (see [Evaluation](#evaluation)).

## What's new

- **PDF, Word, PowerPoint and Excel** files, read on your machine by optional Docling, with formulas kept as LaTeX.
- **`--json` and a cache** for apps: results come back as data, and reviewing the same content again costs nothing.
- **`suggest`** recommends a panel and a budget, and `review` warns when a limit looks too small.
- **Live status and convergence**: where a run is, who it is waiting on, and how the panel is moving. `--explain` shows the sums behind every result. See [`docs/reading-a-run.md`](docs/reading-a-run.md).
- **More math survives** from web pages, and a run stops before spending if formulas are lost.
- **Other models and AI clients**: ask OpenAI, xAI and Gemini alongside Claude, or call JJV from an MCP client. See [`docs/providers.md`](docs/providers.md).

Every change is in [`CHANGELOG.md`](CHANGELOG.md).

## Quick start

Install only what you need. Each line includes the ones above it.

| You want to | Install | Size |
|---|---|---|
| Run the tests and the broker evaluation | `pip install -r requirements.txt` | Small |
| Review code, text and web pages with real models | `pip install -r requirements-live.txt` | Small |
| Also review PDF, Word, PowerPoint and Excel files | `pip install -r requirements-parse.txt` | About 1.5 GB, plus about 1 GB of models on first use |

Without the last one, everything else still works, and a document file stops with a message saying what to install. If you set up JJV on another computer, or delete the `.venv` folder, install again.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                                          # 403 unit tests, no API key needed
python -m jjv.registry > docs/archetypes.md        # regenerate the archetype catalog
python -m jjv.registry --readme                    # regenerate the roster in this README
python -m jjv.eval_broker --trials 300 --seed 7    # Nash broker vs weighted vote
```

Everything except live runs uses the Python standard library alone. `requirements.txt` only adds the test tooling.

To run a real panel, install the Claude Agent SDK. Live runs call Claude and spend money, up to `--max-usd` (default $5, a soft limit checked between calls). Run records go to `~/.jjv/runs`, outside any repo, because they name who is behind each anonymous Judge and Judges can read the repo they review. Keep secrets gitignored too: Judges cannot read files named like secrets, but a `Grep` can search one that git does not ignore. A store inside `--repo` is refused.

```bash
pip install -r requirements-live.txt
python -m jjv.cli review design.md --panel "Physics of Compute"
git diff | python -m jjv.cli review - --discipline code --repo .
python -m jjv.cli generate brief.txt --panel "Docs Crit" --out draft.md
python -m jjv.cli review plan.md --panel "Thinkers Panel" --deliberation-rounds 3
python -m jjv.cli suggest --url https://example.com/post   # recommend a panel and a budget
python -m jjv.cli review --url https://example.com/post --panel "Paper Review"
python -m jjv.cli explain RUN_ID                           # how a saved run reached its result, free
python -m jjv.cli review plan.md --panel "Thinkers Panel" --consult claude,openai,xai,gemini
```

While a run works, status lines show elapsed time, money spent, the step (`2/4 JUDGE`) and how many Judges have reported. When nothing has happened for 15 seconds, a line says it is still working and who it is waiting on. Convergence lines show how far apart the Judges are, how many moved in each round, how many name the same fix list, how much of the proposed fix list survived, and how each draft scored against its target. `review` warns first if `--max-usd` looks too small. Add `--explain` to see how each section reached its output, with the sums written out.

`suggest` makes one small model call with no tools, and only prints a recommendation. Its costs are rough, based on a few runs, and improve as clean runs are saved. It has been tried on only four samples.

[`docs/reading-a-run.md`](docs/reading-a-run.md) explains every line, with a real example.

### Documents and formulas

Text files, code and web pages work with no extra install. Web pages keep formulas as LaTeX, whether they are images with alt text, MathML, KaTeX, MathJax scripts or Wikipedia math. If a page's formulas cannot be read, the run stops before spending anything, unless you pass `--allow-lost-math`.

PDF, Word, PowerPoint and Excel files need [Docling](https://github.com/docling-project/docling), which is large (about 1.5 GB, plus about 1 GB of models on first use) and runs on your machine:

```bash
pip install -r requirements-parse.txt
python -m jjv.cli review paper.pdf --panel "Paper Review" --max-usd 8
python -m jjv.cli review --url https://arxiv.org/pdf/1706.03762 --panel "Paper Review" --max-usd 8
```

A paper can take a few minutes to read, and `suggest` followed by `review` reads it twice. Displayed formulas become LaTeX, read from the page image, so they can contain small errors. Inline math stays as plain text. Check any formula a finding depends on. Scanned documents are untested.

### Ways to run JJV

The native way needs no harness, no MCP server and no settings file. The others are optional, and only apply when you ask for them.

| Way | How | What you need |
|---|---|---|
| **Native** | `python -m jjv.cli review ...` | The Claude Agent SDK, signed in through Claude Code or with `ANTHROPIC_API_KEY` |
| **Several models first** | Add `--consult claude,openai,xai,gemini` | Native setup, plus provider keys and `~/.jjv/providers.json` |
| **Judges on a public API** | Add `--judge-provider openai` | Provider key and `~/.jjv/providers.json`. No Claude Code needed |
| **From an AI client** | `python -m jjv.mcp_server` | Nothing extra for free tools. Paid tools also need `JJV_MCP_PAID=1` and the setup for the backend they use |

### From an app

Add `--json` to `review`, `generate`, `suggest` or `explain`, and the result comes back as JSON on stdout: the decision, score, fix list, every finding, convergence, the run id and a `fingerprint` of the content. Status lines stay on stderr, and errors come back as `{"status": "error", "error": "..."}`.

```bash
python -m jjv.cli review note.md --panel "Thinkers Panel" --json > result.json
```

A finished review is reused when the same content is reviewed again with the same panel and settings, so asking twice costs nothing, and a cached PDF is not read again. The JSON says `"cached": true`. Use `--no-cache` to run again. Changing the content, panel, an archetype's version or any setting that shapes the result starts a new run; changing `--max-usd` does not. Runs that failed or lost a Judge are never reused, and neither are `--repo` runs. The MCP server reuses results the same way.

`--repo`, which lets Judges read a codebase, works only the native way. Setup for the optional ways is in [`docs/providers.md`](docs/providers.md).

## What's in this repository

| Piece | What it does | Where |
|---|---|---|
| Default archetypes | Six generic jurors that auto-convene by discipline, including the Drafter (the Generator) | `jjv/archetypes.py` |
| Legend roster | 31 trait-profile and mission archetypes, plus the ten original preset rooms; `PRESET_PANELS` merges all 25 presets | `jjv/legends.py` |
| Domain archetypes | Eight role archetypes with rubrics, veto dimensions, presets, and the papers their standards come from | `jjv/domain_roles.py` |
| Thinkers and gap roles | Seven thinking methods and five roles for areas nobody else covered, with six presets. None holds a veto, and none has run live yet | `jjv/thinkers.py` |
| Provider harness | Asks several models through their public APIs with your own keys, then sends their answers through the panel. See [`docs/providers.md`](docs/providers.md). Not yet run against a live provider | `jjv/harness.py` |
| MCP server | Lets MCP clients list panels, read runs and replay a bargain for free. Paid `review` and `generate` are off unless the owner enables them, with limits the client cannot raise. See [`docs/providers.md`](docs/providers.md#mcp-server) | `jjv/mcp_server.py` |
| Nash_Agent | Archetype record, plus the deterministic bargaining kernel that brokers the Jury round | `jjv/nash.py` |
| Registry | One lookup for all 58 archetypes and 25 presets, the veto-dimension vocabulary, `validate()`, and the generated catalog | `jjv/registry.py`, `docs/archetypes.md` |
| Orchestrator | Runs SELECT, JUDGE, JURY, VOTE and the generate loop in fixed order, with retries, quorum, spending limit, saved run records and reputation | `jjv/orchestrator.py`, `jjv/backend.py`, `jjv/cli.py` |
| Voter | Deterministic tally: consensus score, decision by veto policy, ranked findings, dissents | `jjv/voter.py`, `jjv/verdicts.py` |
| Evaluation | Nash broker vs weighted voting: offline simulation plus a live-comparison hook | `jjv/eval_broker.py` |
| Tests and CI | 403 unit tests; GitHub Actions runs them on Python 3.10–3.12 along with the evaluation | `tests/`, `.github/workflows/tests.yml` |
| Design docs | The full swarm architecture and roadmap, the broker spec, the domain-agent library map, and the catalog | `docs/` |

**Status.** This repository holds the full archetype registry (58 archetypes, 25 presets, every preset member defined), the negotiation layer and its evaluation, the orchestrator, the Voter, and a CLI. Still to come: the FastAPI backend and web UI, and the live broker comparison on real subjects.

**Next steps**, in recommended order (details in [`docs/architecture.md`](docs/architecture.md#next-steps)):
1. Confirm finding links on the full models. So far they have been checked on two cheap-model runs.
2. Show Judges the brief in generate mode, and carry findings across rounds.
3. Make the weighted-vote baseline fair on live panels, then run the live broker comparison.
4. Decide the open incentive questions in the Voter and the broker.
5. Decide what Judges are held to when there is no single truth to check a finding against, which also sets the basis for adding or removing agents.
6. Test the Thinkers and gap roles on real subjects, starting with the Thinkers Panel on a bold idea. They are built but have never run live.
7. Test negotiation rounds live, to see whether the extra cost buys better fix lists.
8. Try the MCP server from a real client, including its paid tools.
9. Build the web interface.

Design rationale is in [`docs/architecture.md`](docs/architecture.md). The broker spec is in [`docs/nash-agent.md`](docs/nash-agent.md), the domain archetypes are in [`docs/domain-agents.md`](docs/domain-agents.md), and every archetype and preset is listed in [`docs/archetypes.md`](docs/archetypes.md).

## The archetypes

An archetype is one reviewer lens: a persona, a scoring rubric, a weight, and sometimes a veto. There are 58, in six groups:

| Group | Count | Who they are | Examples |
|---|---|---|---|
| Defaults | 6 | Generic reviewers that convene automatically by discipline. The Drafter writes drafts and never votes. | Staff Engineer, Security Reviewer, Technical Writer |
| Legends | 31 | Trait profiles across engineering (9), founders (9), design (5), investors (3), mission roles (3), plus The Simplifier and The Clarity Editor. They join through presets. | The Reliability Engineer, The Reductionist, The Value Investor |
| Thinkers | 7 | Methods of reasoning inspired by historical thinkers, one record per method, not per person. They join through presets. | The Paradox Hunter, The Back-of-Envelope Estimator, The Shadow Reader |
| Domain roles | 8 | Specialists modeled on a discipline, each with standards drawn from published papers. | The Cryptographer, The Evidence Auditor, The Thermodynamicist |
| Gap roles | 5 | Roles for areas no other juror covered. | The Assumption Tester, The Regulatory Reader, The Model Evaluator |
| Broker | 1 | Nash_Agent, a Judge who scores a subject's incentives. It holds no veto. Bargaining runs on every panel, with or without it. | Nash_Agent |

Twelve archetypes hold a veto, each on one area. For example, the Security Reviewer holds `security` and The Thermodynamicist holds `physical-correctness`.

A **preset** is a ready-made panel of 3–6 archetypes, and there are 25. For example, *Physics of Compute* convenes The Thermodynamicist, The Metering Economist, The Silicon Compiler Architect, The Evidence Auditor and Nash_Agent.

"Legend" archetypes are trait profiles: lenses *inspired by* how notable people are publicly known to work. They are not impersonations. They never speak as those people, and no endorsement or affiliation is implied. Role archetypes, such as The Cryptographer and Nash_Agent, are modeled on a discipline, not on any person.

<!-- roster:start (generated by python -m jjv.registry --readme) -->
### Every archetype, by group

Click a group to open it. "Judges on" lists the archetype's rubric dimensions, and "Veto" is the one area where its blocker is forced into the fix list.

<details>
<summary><b>Defaults (6) — convene automatically by discipline</b></summary>

| Archetype | Judges on | Veto |
|---|---|---|
| Staff Engineer | Correctness; Failure modes; Readability; Testability | — |
| Security Reviewer | Injection & input; AuthZ & secrets; Supply chain | `security` |
| Technical Writer | Accuracy; Completeness; Clarity; Structure | — |
| Principal Designer | Hierarchy; Consistency; Accessibility; Craft | — |
| Product Lead | User value; Scope; Trade-offs | — |
| Drafter | Writes drafts; never votes | — |

</details>

<details>
<summary><b>Legends (31) — trait profiles that join through presets</b></summary>

**House (1)**

| Archetype | Inspired by | Judges on | Veto |
|---|---|---|---|
| The Simplifier | Ted Tanner (tedtanner.org) | Reduce — deserves to exist; Refactor — clean what survives; Reuse — earned; Measured, not asserted | `complexity` |

**Engineering (9)**

| Archetype | Inspired by | Judges on | Veto |
|---|---|---|---|
| The Maintainer | Linus Torvalds | Data structures & taste; No regressions; Correctness | — |
| The Optimizer | John Carmack | Hot-path efficiency; First-principles fit; Simplicity under load | — |
| The Reliability Engineer | Margaret Hamilton | Failure handling; Defensive design; Recoverability | `failure-handling` |
| The Abstractionist | Barbara Liskov | Interface cleanliness; Contract integrity; Information hiding | — |
| The Refactorer | Martin Fowler & Kent Beck | Test safety net; Simple design; Evolvability | — |
| The Scale Architect | Jeff Dean | Scales to target; Latency & tails; Cost at scale | — |
| The Pragmatist | David Heinemeier Hansson | Right-sized complexity; Developer ergonomics; Boring-tech bias | — |
| The Readability Purist | Guido van Rossum | Readability; Explicitness; Consistency | — |
| The Quality Systems Thinker | W. Edwards Deming | Quality built in; Systems over blame; Continuous improvement | — |

**Design (5)**

| Archetype | Inspired by | Judges on | Veto |
|---|---|---|---|
| The Reductionist | Dieter Rams | Less but better; Honest & understandable; Unobtrusive craft | — |
| The Craftsman | Jony Ive | Detail & finish; Coherence of the whole; Material honesty | — |
| The Taste Maker | Steve Jobs | End-to-end experience; Focus / courage to cut; Delight | `experience` |
| The Usability Scientist | Don Norman | Affordance & feedback; Error tolerance; Mental-model fit | — |
| The Hardware Contrarian | Palmer Luckey | Buildability; Cost realism; Contrarian merit | — |

**Founders (9)**

| Archetype | Inspired by | Judges on | Veto |
|---|---|---|---|
| The Deletionist | Elon Musk | Necessity; Simplicity; Velocity | — |
| The Customer-Backwards Operator | Jeff Bezos | Customer benefit; Works backwards; Long-term standard | — |
| The Zero-to-One Contrarian | Peter Thiel | Differentiation / moat; Zero-to-one novelty; Contrarian truth | — |
| The Operator | Andy Grove | Measurable objectives; Execution discipline; Inflection awareness | — |
| The Maker of Wanted Things | Paul Graham | Make something people want; Real vs. imagined problem; Willing to do the unscalable | — |
| The Wartime CEO | Ben Horowitz | Faces the hard thing; Honest under pressure; Plan for the downside | — |
| The Experience Maximalist | Brian Chesky | End-to-end journey; Emotional peak; Reach toward great | — |
| The Platform Steward | Satya Nadella | Platform leverage; Ecosystem / partnership; Growth mindset | — |
| The Culture Architect | Reed Hastings | Context over control; Talent density; Rule justification | — |

**Investors (3)**

| Archetype | Inspired by | Judges on | Veto |
|---|---|---|---|
| The Value Investor | Warren Buffett | Durable advantage; Margin of safety; Understandability | — |
| The Rationalist | Charlie Munger | Inversion / failure modes; Bias resistance; Avoids stupidity | — |
| The Disruption Theorist | Clayton Christensen | Job-to-be-done clarity; Disruptive vs. sustaining; Market insight | — |

**Writing (1)**

| Archetype | Inspired by | Judges on | Veto |
|---|---|---|---|
| The Clarity Editor | William Zinsser | Clutter removed; Plain language; One idea per sentence | — |

**Mission (3)**

| Archetype | Inspired by | Judges on | Veto |
|---|---|---|---|
| The Mission Assurance Officer | — | Mission fitness; Assurance case; Degradation under stress | `mission-assurance` |
| The Attestation Architect | — | Verifiable provenance; Identity & revocation; Supply-chain integrity | `attestation` |
| The Systems Integrator | — | Interface stability; Interoperability; Integration risk | — |

</details>

<details>
<summary><b>Thinkers (7) — methods of reasoning, no vetoes, not yet run live</b></summary>

| Archetype | Judges on | Veto |
|---|---|---|
| The Paradox Hunter | Stable definitions; Internal consistency; Stated premises; Self-application | — |
| The Formalizer | Formalizable claims; Valid steps; Boundary cases | — |
| The Back-of-Envelope Estimator | Deciding quantities; Order of magnitude; Sensitivity | — |
| The Thought Experimenter | End-to-end walkthrough; Holds under variation; Experiment available | — |
| The Gap Finder | Coverage of the pattern; Handling of anomalies; Predictive value | — |
| The Shadow Reader | Unasked questions; Candor about risk; Stated motives | — |
| The Human Consequences Reader | People in view; Realistic behavior; Second-order effects | — |

</details>

<details>
<summary><b>Domain roles (8) — specialists grounded in published papers</b></summary>

| Archetype | Judges on | Veto |
|---|---|---|
| The Cryptographer | Threat model & definitions; Proof & assumptions; Composition; Key & credential lifecycle; Primitive hygiene | `crypto` |
| The Privacy Adversary | Re-identification risk; Linkage exposure; Minimization & purpose; Auditability; Disclosure minimality | `privacy` |
| The Consensus Verifier | Fault model; Safety argument; Liveness & termination; Understandability; Adversarial execution | `consensus-safety` |
| The Silicon Compiler Architect | IR & lowering design; Retargetability; Equivalence evidence; Performance honesty; Determinism & hardening | — |
| The Complexity Scientist | Adaptivity awareness; Coordination mechanism fit; Regime & scale behavior; Feedback & control; Trust dynamics | — |
| The Evidence Auditor | Claim support; Evidence quality; Generalization; Research ethics; Calibration | `evidence` |
| The Thermodynamicist | Physical correctness; Quantitative precision; Level-of-stack honesty; Honest caveats; Substrate fairness | `physical-correctness` |
| The Metering Economist | Cost recovery; Incentive design; Meterability; Goodhart resistance; Savings allocation | `cost-recovery` |

</details>

<details>
<summary><b>Gap roles (5) — areas nobody else covers, no vetoes, not yet run live</b></summary>

| Archetype | Judges on | Veto |
|---|---|---|
| The Assumption Tester | Bets stated; Impossible ruled out; Cheap tests exist | — |
| The Regulatory Reader | Regulated activity identified; Duties addressed; Open questions flagged | — |
| The Model Evaluator | Eval validity; Data separation; Untrusted input; Drift and monitoring | — |
| The Distribution Realist | Buyer clarity; Channel fit; Acquisition economics; Switching reason | — |
| The Developmental Editor | Reader and purpose; Argument; Structure; Voice | — |

</details>

<details>
<summary><b>Broker (1) — Nash_Agent</b></summary>

| Archetype | Judges on | Veto |
|---|---|---|
| Nash_Agent | Incentive compatibility; Equilibrium stability; Commitment credibility; Pareto efficiency; Strategic robustness | — |

</details>

<details>
<summary><b>Presets (25) — ready-made panels for `--panel`</b></summary>

| Preset | Members |
|---|---|
| The 3Rs Panel | The Simplifier, The Deletionist, The Refactorer, The Reductionist, The Quality Systems Thinker |
| Founders' Roundtable | The Deletionist, The Customer-Backwards Operator, The Zero-to-One Contrarian, The Maker of Wanted Things, The Wartime CEO, The Simplifier |
| FAANG Code Review | The Maintainer, The Scale Architect, The Reliability Engineer, The Refactorer, Security Reviewer, The Simplifier |
| Design Legends | The Reductionist, The Craftsman, The Taste Maker, The Usability Scientist, The Hardware Contrarian |
| Investor Panel | The Value Investor, The Rationalist, The Zero-to-One Contrarian, The Disruption Theorist, The Operator |
| Docs Crit | The Clarity Editor, Technical Writer, The Customer-Backwards Operator, The Simplifier |
| Mission Platform Review | The Systems Integrator, The Reliability Engineer, The Scale Architect, The Attestation Architect, Security Reviewer, The Simplifier |
| Mission Assurance | The Mission Assurance Officer, The Reliability Engineer, The Attestation Architect, Security Reviewer, The Simplifier |
| Kill-or-Fund | The Deletionist, The Zero-to-One Contrarian, The Rationalist, The Wartime CEO, The Customer-Backwards Operator, The Simplifier |
| Platform Strategy | The Platform Steward, The Operator, The Disruption Theorist, The Value Investor, The Simplifier |
| The Nash Table | Nash_Agent, Security Reviewer, The Simplifier, Staff Engineer, Product Lead |
| Treaty Room | Nash_Agent, The Attestation Architect, The Systems Integrator, The Mission Assurance Officer, Product Lead |
| Crypto & Attestation Room | The Cryptographer, The Attestation Architect, The Privacy Adversary, Security Reviewer, The Simplifier |
| Ledger Review | The Consensus Verifier, The Cryptographer, Nash_Agent, The Systems Integrator, Staff Engineer |
| Health Data Exchange | The Privacy Adversary, The Cryptographer, The Attestation Architect, Nash_Agent, Product Lead |
| Compiler & Hardware Review | The Silicon Compiler Architect, The Attestation Architect, The Systems Integrator, The Consensus Verifier, The Simplifier |
| Emergence Lab | The Complexity Scientist, Nash_Agent, The Evidence Auditor, Staff Engineer, Product Lead |
| Paper Review | The Evidence Auditor, Technical Writer, The Complexity Scientist, The Simplifier |
| Physics of Compute | The Thermodynamicist, The Metering Economist, The Silicon Compiler Architect, The Evidence Auditor, Nash_Agent |
| Thinkers Panel | The Assumption Tester, The Paradox Hunter, The Back-of-Envelope Estimator, The Shadow Reader, Nash_Agent |
| Thought Lab | The Formalizer, The Thought Experimenter, The Gap Finder, The Human Consequences Reader, Nash_Agent |
| Regulated Launch | The Regulatory Reader, The Privacy Adversary, Security Reviewer, The Evidence Auditor, Nash_Agent |
| AI System Review | The Model Evaluator, Security Reviewer, The Evidence Auditor, The Privacy Adversary, The Reliability Engineer, Nash_Agent |
| Go-to-Market | The Distribution Realist, The Metering Economist, The Customer-Backwards Operator, The Value Investor, The Assumption Tester, Nash_Agent |
| Writers' Room | The Developmental Editor, The Clarity Editor, Technical Writer, The Human Consequences Reader, Nash_Agent |

</details>

<!-- roster:end -->

Weights, rubric weights and the thinkers who inspired each Thinker are in [`docs/archetypes.md`](docs/archetypes.md), which is generated from the code.

## The Nash_Agent broker in brief

Every panel bargains by default. Use `--aggregator weighted_vote` for a plain vote instead.

1. **Disagreement point.** A blocker raised by a Judge holding a veto for that area is a *credible* threat. It is forced into every outcome. Any other blocker or "reject" is recorded as cheap talk.
2. **Feasible set.** These are the outcomes that fit the revision budget and leave every veto-holder at least as well off *in its own veto area* as blocking.
3. **Settlement.** The broker maximizes a weighted Nash product of each Judge's gain over the disagreement point, then breaks ties by a published rule.
4. **Transparency.** The settlement goes into the Jury digest with the math shown: what is fixed now, what is deferred, whose threats were cheap talk, and each Judge's net gain.

A veto reaches only its holder's area, and each holder weakly prefers the settlement to blocking there, so accepting it is a Nash equilibrium of the ratification step. The broker bargains over *priorities*, never facts: it cannot add, drop, reword or re-score anyone's findings.

**Negotiation.** With `--deliberation-rounds` above 1, Judges talk over several rounds. Each names the fixes it would accept and can send the others an argument or offer. If every Judge names the same list, that list stands and the formula is not used, as long as it fits the budget and includes every credible veto. If they never agree, the formula decides. The default is one round, because each extra round costs about as much as the Jury round again, and whether it helps is unproven.

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
