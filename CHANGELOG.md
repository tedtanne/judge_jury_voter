# Changelog

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
