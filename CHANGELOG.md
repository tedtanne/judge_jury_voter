# Changelog

## 2026-11-07

### Added
- **`suggest`** recommends one to three panels, or says none fits, with rough costs and a command built by code. One small model call, with no tools. Revised after a JJV review of the proposal: `--panel auto` and an MCP tool are left for later.
- **`--explain` and `explain RUN_ID`** show how each section reached its result, with the sums written out. Free on a saved run. MCP clients get `explain_run`.
- **`--json`** returns the result as data for an app, with a content `fingerprint`, on `review`, `generate`, `suggest` and `explain`.
- **Results are reused** when the same content is reviewed with the same panel and settings, so asking twice costs nothing. Failed runs, runs that lost a Judge and `--repo` runs are never reused. `--no-cache` runs again.
- **PDF, Word, PowerPoint and Excel** through optional Docling (`jjv/parse.py`, `requirements-parse.txt`), from a file or, for PDFs, a link. MegaParse was tried first and returned empty text.
- **More math survives.** Web pages keep formulas from MathJax scripts, MathML, KaTeX and Wikipedia. A run stops before spending if formulas cannot be read, unless `--allow-lost-math` is set, and Judges are told broken text may be an extraction fault.
- **Budget warning.** `review` warns before spending when `--max-usd` looks too small. Estimates ignore runs that failed or hit their limit.
- **Status lines** now show the step and how many Judges have reported, a heartbeat line names who is being waited on, and convergence lines show how the panel moved. These also appear in `--explain`, in the run record and in MCP `get_run`.
- **`docs/reading-a-run.md`** explains the status lines, convergence lines, result and `--explain` output, using a real run.

### Fixed
- A negotiating Judge that named no fix list crashed the run. It now counts as not agreeing.

## 2026-11-06

### Added
- **Twelve archetypes and six presets** (`jjv/thinkers.py`), bringing the roster to 58 archetypes and 25 presets. Seven Thinkers are methods of reasoning inspired by historical thinkers: Paradox Hunter, Formalizer, Back-of-Envelope Estimator, Thought Experimenter, Gap Finder, Shadow Reader and Human Consequences Reader. Five gap roles cover areas nobody did: Assumption Tester, Regulatory Reader, Model Evaluator, Distribution Realist and Developmental Editor. None holds a veto, and none has run live.
- **Negotiation rounds** (`--deliberation-rounds`, default 1). Judges exchange positions, arguments and offers over several Jury rounds. An agreed list replaces the formula if it fits the budget and keeps every credible veto; otherwise the formula decides. Not yet run live.
- **Next step:** decide what Judges are held to when there is no single truth to check a finding against.

- **`--url`** reviews a web page. Equations drawn as images keep their LaTeX, and reader comments are left out (`jjv/fetch.py`).
- **Status lines** show elapsed time and money spent, and a run warns when Judges failed.
- **Provider harness** (`jjv/harness.py`, `docs/providers.md`). `--consult` asks several models through their public APIs and sends their anonymous answers through the panel. `--judge-provider` runs the Judges on a provider. Any OpenAI-format service can be added in settings. Not yet run against a live provider.

- **MCP server** (`jjv/mcp_server.py`). Free tools read the registry and saved runs, and `settle` replays a bargain at a new budget with no model calls. Paid `review` and `generate` are off by default, and limits are set by the server owner, including a total allowance. Links from a client must be public addresses.

### Changed
- **Every panel bargains.** The Nash kernel no longer needs Nash_Agent on the panel, so the 13 presets without it stop falling back to a weighted vote. Their fix lists may change, and those runs now count toward reputation. `--aggregator weighted_vote` still selects a plain vote.

### Removed
- The list of non-research and personal records from `docs/domain-agents.md`.
- Knowledge base grounding from 2026-11-04 (`--knowledge`, finding citations), reverted in PR #8.

## 2026-11-04

### Added
- **Orchestrator** (`jjv/orchestrator.py`): review and generate runs, retries, quorum, per-run spending limit, saved run records, reputation across runs, and `live_run_fn` for `run_live_comparison`.
- **Claude backend** (`jjv/backend.py`) and **CLI** (`jjv/cli.py`). The SDK is in `requirements-live.txt`; tests and CI do not need it.
- **Voter** (`jjv/voter.py`) and **verdict contract** (`jjv/verdicts.py`).
- **Tests**: 164 new, bringing the total to 197.

### Changed
- **Findings can be linked.** In the Jury round a Judge marks its own finding `same_as` another Judge's, and linked findings share one key. This replaces "drop yours and endorse theirs". On a cheap-model code review, 37 findings became 24 rows, where the old instruction took 60 to 58.
- **Rework cost is shared.** Each Judge bears a 1/n share of a fix's cost, so a lone blocker no longer loses to a lone major.
- **Veto credibility is judged per raiser.** A joined group stays forced if any member is a credible veto, and a Judge's inflated blocker no longer rides on a veto-holder's finding. At seed 7: displacement 0.036 to 0.012, stability 0.824 to 0.848, efficiency 0.938 to 0.957, Judges shut out unchanged.
- **README claim softened.** "5x harder to steer" is gone, because panels built to imitate live ones showed a near tie with weighted voting.
- **Docs** record the first full review, including limits on earlier claims: live fix lists follow list order, the scoped veto check rarely binds, and the evaluation does not yet describe live panels.
- **Docs** now carry a prioritized next-steps list (`docs/architecture.md`, summarized in the README), and no longer describe finished wiring as a to-do.
- **Vetoes are scoped in the broker.** A veto-holder's feasibility check now counts only findings in its veto area. Before, a holder with nothing to gain blocked every optional fix on the panel. Published results moved at seed 7: displacement 0.029 to 0.036, stability 0.809 to 0.824, judges shut out 0.077 to 0.057, efficiency 0.962 to 0.938. Acceptance is still an equilibrium, and `tests/test_nash_search.py` checks that blocking never pays.

### Fixed
- Found by stress tests:
  - **Secrets block** missed `.GIT` and other case variants, which macOS treats as the same folder.
  - **Crashes after spending** from a damaged `reputation.json`, a lost run folder, or an unexpected Drafter error. These now leave the result intact or fail the run cleanly.
  - **Refused before spending:** a blank subject, a repeated Judge, and a run folder that cannot be written.
  - **Labels** past 26 Judges collided and merged findings.
  - **CLI** now explains a missing input file.
- Found by the second full review:
  - **File guard** now denies when its own check fails. A crashed hook counted as no decision, so the tool ran.
  - **Secret files** inside the repo are blocked by name, and `.git`, `.ssh`, `.aws` and `.gnupg` by folder. A secret that git does not ignore can still be reached by `Grep` over a directory.
  - **Finding titles** are kept to one line, so they cannot forge lines in the settlement.
  - **Grep** patterns are no longer checked as paths, and brace expansion no longer hides `..` in Glob patterns.
- Bare `pytest` failed to import `jjv`; `pytest.ini` now sets the path.
- `docs/architecture.md` said the scaffold zip held these modules. It does not.
- Found by the first full panel review of this code:
  - **Empty settlements.** On panels over `EXACT_LIMIT` with two veto-holders, the broker's local search stalled and chose nothing. It now starts with one fix per veto-holder. The exact path and the published evaluation are unchanged.
  - **File access.** Judges' read tools could reach any path on the machine; a hook now confines them to the repository.
  - **Run records** defaulted to a folder inside the repo Judges read, which exposed their identities.
  - **Crashes.** SDK and malformed-reply errors escaped and killed the run; they now count as one Judge's failure, and work is saved after each phase.
  - **Lost findings.** A Jury round could erase a veto blocker or a finding two Judges endorsed to each other.
  - **Spending.** Timed-out calls were not counted, and queued calls checked the limit before earlier calls had spent.
  - **Best round** could prefer an unapproved draft or one a veto-holder never saw.
  - **Fences.** Digest and revision notes are now fenced with unguessable tags.

## 2026-10-30

### Added
- **Default archetypes** (`jjv/archetypes.py`): Staff Engineer, Security Reviewer, Technical Writer, Principal Designer, Product Lead, and the Drafter (the generate-mode author: unscored, `role="generator"`).
- **The legend roster** (`jjv/legends.py`). 31 archetypes: the Simplifier, 9 engineering, 5 design, 9 founders, 3 investors, the Clarity Editor, and 3 mission roles. Also the ten original presets.
  - Ported from the Deliberation Console prototype, which held them as display-name-keyed data.
  - Each record now has a stable `id`, the shared record shape, and house rules that keep legends as trait profiles rather than impersonations.
- **The Thermodynamicist and The Metering Economist** (`jjv/domain_roles.py`), with the **Physics of Compute** preset.
- **Registry** (`jjv/registry.py`):
  - one lookup for 46 archetypes and 19 presets;
  - the controlled vocabulary for veto dimensions;
  - `validate()`;
  - the generated catalog at `docs/archetypes.md`.
- **Tests**: 11 new, bringing the total to 33. They cover registry integrity, scoped vetoes, impersonation guards, and catalog freshness.

### Fixed
- **Unscoped vetoes.** The prototype roster had veto flags with no dimensions, which `NashBroker` reads as a veto on every dimension. Every veto-holder now names its dimensions:
  - Security Reviewer: `security`
  - Simplifier: `complexity`
  - Reliability Engineer: `failure-handling`
  - Taste Maker: `experience`
  - Mission Assurance Officer: `mission-assurance`
  - Attestation Architect: `attestation`
- **Dangling presets.** All eight presets in `jjv/nash.py` and `jjv/domain_roles.py` named archetype ids that did not exist in the repository. They all resolve now.
- **Preset name drift.** The canonical name is *Mission Platform Review*. *Platform Architecture Review* is retired.
- **Doc errors in `docs/architecture.md`.** It said *Mission Assurance* has two veto-holders; all five members hold one. Implementation status now separates what is in the repository from what remains in the original scaffold.

### Changed
- `tests/test_domain_roles.py` checks preset members against the registry instead of a hard-coded id list.

## 2026-10-17

- Nash_Agent v2, the six domain archetypes, the broker evaluation, CI.
