# Changelog

## 2026-11-04

### Added
- **Orchestrator** (`jjv/orchestrator.py`): review and generate runs, retries, quorum, per-run spending limit, saved run records, reputation across runs, and `live_run_fn` for `run_live_comparison`.
- **Claude backend** (`jjv/backend.py`) and **CLI** (`jjv/cli.py`). The SDK is in `requirements-live.txt`; tests and CI do not need it.
- **Voter** (`jjv/voter.py`) and **verdict contract** (`jjv/verdicts.py`).
- **Tests**: 102 new, bringing the total to 135.

### Changed
- **Docs** record the first full review, including limits on earlier claims: live fix lists follow list order, the scoped veto check rarely binds, and the evaluation does not yet describe live panels.
- **Docs** now carry a prioritized next-steps list (`docs/architecture.md`, summarized in the README), and no longer describe finished wiring as a to-do.
- **Vetoes are scoped in the broker.** A veto-holder's feasibility check now counts only findings in its veto area. Before, a holder with nothing to gain blocked every optional fix on the panel. Published results moved at seed 7: displacement 0.029 to 0.036, stability 0.809 to 0.824, judges shut out 0.077 to 0.057, efficiency 0.962 to 0.938. Acceptance is still an equilibrium, and `tests/test_nash_search.py` checks that blocking never pays.

### Fixed
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
