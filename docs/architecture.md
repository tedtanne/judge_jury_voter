---
title: Judge_Jury_Voter — Architecture & Build Plan
description: Design for a swarm of archetype "best-in-the-business" agents that review and generate documentation, code, and designs, with a web interface. Read for the swarm topology, archetype schema, orchestration, API, and roadmap.
status: draft
owner: Ted
updated: 2026-10-17
---

# Judge_Jury_Voter

A swarm of AI agents, each embodying the lens of a *best-in-the-business* professional — a staff engineer, a principal product designer, a Stripe-grade technical writer — that collectively **review** and **generate** documentation, code, and designs. Each persona is *inspired by* how such a professional works and what they demand; it is never an impersonation of a specific named person (see "Archetype roster" below). The name encodes the consensus mechanism: independent **Judges** score an artifact, a **Jury** round lets them deliberate and revise, and a **Voter** aggregates the scored verdicts into a single decision plus a prioritized action list. A **Generator** loop wraps the same machinery so the swarm can author from scratch, not only critique.

This document is the design and build plan. It covers the swarm topology, how an archetype is defined, the orchestration rounds, the generation loop, the web interface and API, storage, cost and safety controls, and a phased roadmap.

## Design goals

The system is built around four goals. First, **quality through diversity**: several specialized viewpoints catch what any single reviewer misses, and disagreement between them is signal, not noise. Second, **determinism where it matters**: the orchestrator — not a model's own discretion — decides which archetypes run and when, so a run is reproducible and auditable rather than dependent on one agent's mood about whether to delegate. Third, **archetypes as data**: a juror is a record (persona, rubric, tools, weight) that a non-engineer can add or tune from the UI, with sensible code-defined defaults shipped in the repo. Fourth, **transparency**: every verdict, score, and revision is streamed to the user and stored, so the final recommendation can always be traced back to who said what and why.

## Core concept: Judge / Jury / Voter

The heart of the system is a three-phase consensus over a single *subject* — the thing under review or being generated (a file, a diff, a doc, a design brief).

**Judges** are the archetype agents. Each receives the subject plus its own rubric and, working in isolation, returns a *structured verdict*: a score per rubric dimension, a short rationale, specific findings with severity, and an overall recommendation (approve / revise / reject). Isolation is the point — Judges do not see each other in this phase, so their scores are genuinely independent and one loud agent cannot anchor the rest.

**The Jury** is an optional deliberation round. Each Judge is shown an anonymized digest of the others' verdicts and given one chance to revise, explicitly noting what changed its mind. This dampens outlier bias and surfaces the findings that survive scrutiny — a finding three Judges independently raise, or one Judge defends after seeing the others, is worth more than a lone unexamined complaint. Deliberation is where a lazy consensus and a hard-won one become distinguishable.

**The Voter** is a synthesis agent (or, for simple cases, a deterministic tally). It takes the final verdicts and their per-archetype *weights*, computes a weighted consensus score per dimension, resolves the recommendation by policy (for example, any Judge issuing a blocking "reject" on a safety dimension vetoes an approve), de-duplicates and ranks findings across Judges, and writes the human-facing summary: the decision, the top prioritized actions, and the dissents worth knowing about. The Voter never invents findings — it only aggregates and orders what the Judges produced.

For **generation**, a **Generator** (a "drafter" archetype) produces a first draft from the brief, the Judge/Jury/Voter panel critiques it, and the Voter's ranked actions feed back to the Generator for a revision. The loop repeats until the consensus score clears a threshold or a max-round budget is hit — a self-improving draft that stops when the panel is satisfied or when further rounds stop paying off.

## Archetypes

An archetype is the unit everything else is built on. It is a data record, not code, so jurors can be created and tuned without a redeploy — though the repo ships a set of code-defined defaults that seed the registry on first run.

An archetype record has: a stable `id` and display `name`; a `discipline` (`code` | `docs` | `design` | `product` | `security` | …) that determines which subjects it is eligible to judge; a `persona` system prompt that establishes the "best in the business" voice, standards, and biases ("You are a staff engineer in the mold of the best distributed-systems reviewers; you care about failure modes, backpressure, and the cost of the abstraction more than about style"); a `rubric` — an ordered list of scored dimensions, each with a name, a 1–5 anchor description, and a weight; an overall `weight` used by the Voter; an allowed `tools` list (which SDK tools this juror may use — usually read-only for Judges); an optional `model` and `effort` override so expensive jurors run on the strongest model and cheap ones on a fast model; and `enabled` / `version` metadata.

Because the rubric lives in the record, adding "Accessibility" as a scored dimension to the design critic, or dialing up the security reviewer's weight, is a UI edit — no code change. Defaults ship for the common cases: a Staff Engineer (correctness, failure modes, readability, testability), a Security Reviewer (injection, authz, secrets, supply chain — with veto power on blocking findings), a Principal Designer (hierarchy, consistency, accessibility, craft), a Technical Writer (accuracy, completeness, clarity, structure), and a Product Lead (user value, scope, trade-offs). The registry is versioned so a run records exactly which archetype versions judged it.

## Archetype roster & preset panels

Beyond the handful of generic defaults, the system ships a **roster of ~31 named "legend" archetypes** plus a set of curated **preset panels**. This is where the "best in the business" idea becomes concrete.

**Trait-profiles, not impersonations.** Each legend is a lens *inspired by* a notable person — it embodies the principles, standards, and characteristic questions that person is known for, and carries an `inspired_by` field so it stays recognizable. It never claims to *be* that person, never speaks as them, and never fabricates their specific quotes or opinions. This is a deliberate design decision on two grounds: a trait-profile is more stable and useful than a celebrity impression (which drifts into caricature), and it avoids putting invented words in a real person's mouth. The house archetype, **The Simplifier**, is built on Ted Tanner's *Reduce · Refactor · Reuse* discipline — treated as a weighted **basis set with context-dependent weighting, not a fixed sequence**: Reduce = prove it deserves to exist (deletion, not optimization), Reuse is the receipt not the goal, and the loop feeds back. It carries veto power over unnecessary complexity.

The roster spans engineering (Torvalds, Carmack, Hamilton, Dean, Liskov, Fowler/Beck, DHH, van Rossum, Deming), design (Rams, Ive, Jobs, Norman, Luckey), founders (Musk, Bezos, Thiel, Grove, Graham, Horowitz, Chesky, Nadella, Hastings), investors (Buffett, Munger, Christensen), and writing (Zinsser). It also includes three **role archetypes** (best-in-class at a discipline rather than modeled on a person), added for safety-critical platform work: **The Mission Assurance Officer**, **The Attestation Architect**, and **The Systems Integrator**. A fourth role archetype, **Nash_Agent**, is the swarm's game-theoretic negotiator. It judges strategy subjects and brokers the Jury round (see "Nash_Agent: the equilibrium broker" below). Six more **domain role archetypes** were added in October 2026, one for each subject cluster in the project's research library that no existing juror could judge: **The Cryptographer**, **The Privacy Adversary**, **The Consensus Verifier**, **The Silicon Compiler Architect**, **The Complexity Scientist**, and **The Evidence Auditor**. Each carries a `grounded_in` list of the project papers its standards come from (see `domain-agents.md`).

**A roster is a library, not a panel.** Firing 30+ jurors at once would be expensive, slow, and noisy — half would be judging outside their competence. So legend archetypes are marked `library=True` and never auto-join a run by discipline; the generic defaults are what auto-convene. The real unit of use is the **preset panel**: 4–6 curated voices for a given subject, convened explicitly. Presets ship for: *The 3Rs Panel*, *Founders' Roundtable*, *FAANG Code Review*, *Design Legends*, *Investor Panel*, *Docs Crit*, and four platform rooms — *Platform Architecture Review*, *Mission Assurance* (two veto-holders, biased to catch problems), *Kill-or-Fund*, and *Platform Strategy*. Two brokered panels are built around Nash_Agent: *The Nash Table* and *Treaty Room*. Six domain panels use the new role archetypes: *Crypto & Attestation Room*, *Ledger Review*, *Health Data Exchange*, *Compiler & Hardware Review*, *Emergence Lab*, and *Paper Review*. A run takes either a preset name or an explicit archetype list; `GET /panels` serves them and the web UI's Panel dropdown is populated from it. The guiding principle when assembling a panel is to pick voices that *disagree* — consensus is only worth having when it wasn't unanimous by construction.

## Nash_Agent: the equilibrium broker

Nash_Agent is a role archetype built on strict game-theoretic negotiation: Nash equilibrium, the Nash bargaining solution, subgame-perfect credibility, Rubinstein alternating offers, mechanism design, and repeated games. It is the only archetype that interacts with the *other agents* rather than only with the subject. The full spec is in `nash-agent.md`; the code is in `jjv/nash.py` and `tests/test_nash.py`.

**As a Judge**, it scores a subject on how it behaves when every party acts in its own interest. Its rubric covers incentive compatibility, equilibrium stability, commitment credibility, Pareto efficiency, and strategic robustness. That makes it useful for partner and enterprise terms, pricing, platform strategy, and operating concepts.

**As a Broker**, it runs a deterministic bargaining kernel (`NashBroker`) during the Jury round. The Judges are the players, and the thing being negotiated is which findings the next revision addresses under a fixed revision budget. The kernel works in four steps:

1. **Only credible threats count.** A blocker raised by a Judge that holds a veto for that dimension is forced into every outcome. A blocker or "reject" from a Judge without that veto is recorded as cheap talk and not priced.
2. **Find the frontier.** Among outcomes that fit the budget and leave every veto-holder at least as well off as blocking, it keeps only those where no Judge can gain without another losing.
3. **Split by the weighted Nash product.** It picks the outcome that maximizes the weighted product of each Judge's gain over the disagreement point, and breaks ties with a published rule.
4. **Publish the math.** The settlement goes into the anonymized Jury digest: what is fixed now, what is deferred, whose threats were cheap talk, and each Judge's net gain.

Because every veto-holder weakly prefers the settlement to blocking, accepting it is a Nash equilibrium of the ratification step. When `history` is supplied, past cheap talk lowers a Judge's weight, down to a floor of half, so reputation carries across runs.

**What it may not do.** Nash_Agent bargains over priorities, never over facts. It cannot add, drop, reword, or re-score another Judge's findings. It holds no veto and no stake, because a broker with a threat point is just another player. Its own scores are sincere. The Voter is unchanged: it still aggregates the final verdicts, and its veto policy stays authoritative.

**Orchestrator integration.** When a convened archetype has `role == "broker"`, the Jury phase calls `NashBroker(budget=...).solve(verdicts)`, appends `settlement.to_digest()` to the digest each Judge sees before revising, and stores the Settlement with the run. The verdict schema gains two optional fields: `endorses` (finding ids a Judge backs after deliberation) and `change_aversion` (how much a Judge dislikes rework).

## Orchestration

The orchestrator is plain application code that drives the SDK deterministically, rather than one agent deciding on its own whether to spawn helpers. This is a deliberate choice: the Agent SDK's built-in subagent delegation is powerful but nondeterministic (and, on the newest models, actively suppressed unless asked), which is the wrong property for an auditable review panel. Instead the orchestrator selects the eligible archetypes for the subject's discipline, then fans out one SDK `query()` per Judge concurrently, each with that archetype's persona as the system prompt, its rubric injected into the task, and its tool allow-list applied. Each Judge is instructed to return its verdict as JSON matching a fixed schema; a lightweight in-process tool (`submit_verdict`) gives the model a typed channel to return that structure reliably instead of parsing prose.

A run is a small state machine — `SELECT → JUDGE → (JURY) → VOTE → DONE` for review, with a `GENERATE` state prepended and a loop back from `VOTE` to `GENERATE` for authoring. Each phase writes its outputs (verdicts, deliberations, tally) to storage and emits streaming events, so the UI and the audit log are the same source of truth. Concurrency, subagent depth, and a per-run dollar budget are capped through the SDK's limits so a runaway panel can't spend unboundedly.

The SDK gives two implementation paths and the orchestrator can use both: the reliable default is the *explicit* path just described (the orchestrator itself is the "jury foreman," calling one `query()` per archetype and aggregating). For exploratory or very large subjects, a single foreman `query()` can instead be given every archetype as an `AgentDefinition` in the `agents` parameter and asked to convene the panel, letting the SDK parallelize subagents — cheaper to write, less deterministic. The design treats explicit orchestration as the production path and SDK-native subagents as an option for scale.

## Web interface

The interface has three surfaces. The **Run view** is where work happens: the user submits a subject (paste code or a doc, upload a file, point at a repo path, or write a generation brief), picks a panel (a preset like "Code PR review" or a custom archetype selection) and a mode (review or generate), and starts the run. As the swarm works, the view streams live — a column or card per Judge showing its status and then its verdict, a deliberation feed for the Jury round, and finally the Voter's synthesized decision with a per-dimension consensus chart, the ranked action list, and expandable dissents. For generation, the evolving draft renders alongside the critique with each round's diff.

The **Archetype studio** is the registry editor: browse the roster, create or clone a juror, edit its persona and rubric dimensions, set weights, tools, and model, enable or disable it, and see its version history. Changes here change future runs, not past ones.

The **History / audit** surface lists past runs with their subject, panel, decision, and score, each opening the full transcript — every verdict, every revision, the tally math — so a decision is always explainable after the fact.

## API and backend

A thin backend (FastAPI) exposes the orchestrator. `POST /runs` starts a run and returns an id; `GET /runs/{id}/events` is a Server-Sent Events stream of the run's phase and verdict events for the live UI; `GET /runs/{id}` returns the finished record. CRUD under `/archetypes` and `/panels` manages the registry and saved panels. Long runs execute as background tasks (an in-process task set for the scaffold, a real queue such as Redis/RQ or Celery for production) so the HTTP layer stays responsive and the SSE stream is the progress channel. Storage starts as JSON/SQLite for the scaffold — archetypes, panels, runs, verdicts — and moves to Postgres with a JSONB column for verdicts as volume grows; subjects and generated artifacts large enough to warrant it go to object storage with the run keeping a pointer.

## Cost, safety, and quality controls

Several controls keep the swarm useful and bounded. **Budgets**: every run carries a max-dollar and max-round cap enforced through the SDK, and cheap jurors run on a fast model while only high-stakes ones (security, the final Voter) run on the strongest — mixing model tiers is how a five-to-seven-agent panel stays affordable. **Grounding**: Judges are given the actual subject and, where relevant, read-only tools to inspect surrounding files, so critiques cite specifics rather than generalities; the Voter is constrained to aggregate only what Judges produced, never to add findings. **Bias control**: independent scoring before deliberation, anonymized digests in the Jury round, the Nash_Agent broker's rule that only credible threats are priced, and weighting plus veto policy in the Voter are all there to stop a single confident voice from dominating. **Auditability**: the full chain is stored and streamed. **Human in the loop**: the Voter recommends; a person approves. For generation, outputs are drafts a human ships, and the same content-safety judgment that applies to any generated code or copy applies here.

## Implementation status

A **runnable scaffold** accompanies this design (delivered as a `judge_jury_voter` Python package; its `README.md` is the implementation-level reference). It already implements, ahead of the phase order below: the deterministic orchestrator on the Claude Agent SDK (one `query()` per Judge, concurrent), the `submit_verdict` typed tool, the Judge → Jury → Voter path, the generation loop, the **fully unit-tested Voter** (weighting, veto, finding de-duplication, dissents — six passing tests, no API key needed), the code-defined defaults plus the ~31-archetype legend roster and all ten preset panels, JSON-backed storage that seeds itself, a FastAPI backend with SSE streaming, a CLI, and a single-file web UI with a preset picker. Nash_Agent (now version 2, which adds coalition, computability, and stopping rules from the new mechanism-design papers) and its bargaining kernel are implemented in `jjv/nash.py`. The six domain role archetypes and their presets are in `jjv/domain_roles.py`. Together they have fifteen passing tests (no API key needed). An evaluation harness, `jjv/eval_broker.py`, compares the broker with plain weighted voting. In an offline simulation of 300 synthetic panels, a single overconfident Judge displaced 3% of the broker's chosen fixes against 19% under voting, and fewer Judges were shut out (0.08 vs 0.13 on average). The cost was 96% vs 99% of the maximum total value addressed. The harness also has a live-comparison hook for real runs. There are 22 passing tests in all, and CI runs both the tests and the evaluation. The remaining integration steps are wiring Nash_Agent into the orchestrator's Jury phase, registering the new archetypes, adding all eight presets to `PRESET_PANELS`, and connecting `run_live_comparison` to the generate loop. An interactive prototype (published as an Artifact) demonstrates the interface and two live deliberation rooms.

What remains to reach production is the Phase 6 hardening below: a real queue, Postgres, auth, model-tier tuning, per-run budget wiring, and an evaluation set. The roster and rubrics are expected to keep evolving as they meet real subjects.

## Build roadmap

The phases are ordered so each produces something usable and de-risks the next. Phases 1–5 are substantially prototyped in the accompanying scaffold; Phase 6 is the remaining work.

**Phase 0 — Design (this document).** Lock the archetype schema, the verdict JSON schema, and the run state machine. These three contracts are what everything else depends on.

**Phase 1 — Review pipeline, headless.** Build the orchestrator, the code-defined default archetypes, the `submit_verdict` tool, and the Judge → Voter path (skip the Jury round first). Run it from a CLI against a pasted diff and print the decision. This proves the consensus mechanism end to end with no UI.

**Phase 2 — Jury round + weighting.** Add the deliberation round and the Voter's weighting and veto policy. Measure whether deliberation actually changes verdicts on real subjects before investing further.

**Phase 3 — Web interface.** FastAPI backend, SSE streaming, and the Run view. This is where the system becomes something a person uses rather than a script an engineer runs.

**Phase 4 — Archetype studio + persistence.** The registry editor, saved panels, and durable storage, moving archetypes from code defaults to fully editable data.

**Phase 5 — Generation loop.** Add the Generator and the draft-critique-revise cycle, reusing the whole review panel as the critic.

**Phase 5b — Brokered deliberation.** Wire Nash_Agent into the Jury phase, add the two verdict fields, and persist cheap-talk history per archetype so reputation carries across runs. Measure whether brokered runs converge in fewer revision rounds than unbrokered ones, using `run_live_comparison` with final scores from a separate, blind panel. The offline simulation already favors the broker on robustness; this live run is the test that matters.

**Phase 5c — Grounded jurors.** Give archetypes that carry `grounded_in` a read-only search tool over the project library, so their findings can cite the paper behind a standard. This is also where the library is brought under the project's knowledge limit (see `domain-agents.md`).

**Phase 6 — Hardening.** Real queue, Postgres, auth, model-tier tuning, and evaluation — a small benchmark of subjects with known-good verdicts to catch regressions as archetypes evolve.

## Key decisions to confirm

Three choices shape the build. Two are effectively settled by the scaffold: the first flow to harden is **review** (more self-contained), and archetypes are seeded broadly across code, design, product, and safety-critical disciplines rather than one. The open one is the **deployment target** — local-first single-process (what the scaffold assumes) versus a hosted multi-user service, which pulls auth, a real queue, and Postgres forward. Two secondary calls worth making deliberately: how conservative the assurance panels should be (e.g. *Mission Assurance* currently carries two veto-holders, biasing it to catch problems over shipping), and whether to invest in the Phase 6 evaluation set early so roster changes can be measured rather than guessed. For Nash_Agent specifically: whether a blocker with no veto behind it may be deferred (the current, strict position; the fix for disciplines that must never defer is to grant a veto, not to soften the kernel), and the default revision budget of 8 cost units.
