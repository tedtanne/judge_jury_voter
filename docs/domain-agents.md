---
title: Domain agents and the research library
description: How the papers in the Judge_Jury_Voter project map to subject clusters, which archetype covers each cluster, the eight domain role archetypes added in October 2026, and library housekeeping. Read before adding papers or archetypes.
status: draft
owner: Ted
updated: 2026-10-30
---

# Domain agents and the research library

The project's standing instruction is to create agents for the subject matter of the documents added to it. The October 17 upload added about 140 papers. Most of them fall into clusters that no existing juror could judge competently, so six **domain role archetypes** were added in `jjv/domain_roles.py`. Nash_Agent was also updated to version 2 using the new negotiation and mechanism-design papers.

Every new archetype is a role, not a person. Each one carries a `grounded_in` list naming the project papers its standards come from, so its findings can cite them.

## Library map

| Cluster | Representative papers | Covered by |
|---|---|---|
| Negotiation, mechanism design, equilibrium computation | Algorithmic / Classic Mechanism Design; Collusive Dominant-Strategy Truthfulness; Complexity of the Homotopy Method & Lemke-Howson; automated negotiator papers; iterated prisoner's dilemma; Contract Net; BitTorrent incentives | **Nash_Agent v2** |
| Cryptography, signatures, attestation, TEEs | Shannon's secrecy systems; Gentry's FHE; Schnorr exact security & multi-signatures; proxy re-encryption; DAA formal analysis; linkable ring signatures; *SGX Remote Attestation is not sufficient*; JITGuard; Macaroons | **The Cryptographer**, alongside The Attestation Architect |
| Privacy, identity, health data | Sweeney's *Simple Demographics*; *Building a Dossier on the Cheap*; data broker papers; privacy-preserving HIE audit; GeCo synthetic data; *Laws of Identity*; trusted evidence of identity; HIMSS survey | **The Privacy Adversary** |
| Consensus, ledgers, formal methods | Raft & network-assisted Raft; PBFT; *Making Consensus Tractable*; Plasma; Tezos; permissioned DLT; smart-contract verification; termination & consistency proofs | **The Consensus Verifier** |
| Compilers, IR, FPGA, hardware acceleration | Retargetable compilation for reconfigurable computing; IR survey; LLVM metamorphic codegen & JIT; FPGA soft vector & self-aware adaptation; SIMD vectorization | **The Silicon Compiler Architect** |
| Complex adaptive systems, ABM, autonomic computing | Complexity Economics; Santa Fe artificial market; coordination-mechanism catalogue; Kauffman / random Boolean networks; autonomic blueprint; self-adaptive agent organizations; NetLogo | **The Complexity Scientist** |
| Evidence, generalization, research ethics | *Rethinking Generalization*; *Illusion of Thinking*; *Feeling the Future*; Facebook emotional contagion; faces-to-orientation classifier; *Learnability can be undecidable* | **The Evidence Auditor** |
| Blockchain economics & business process | *Some Simple Economics of the Blockchain*; BPM on blockchains; blockchain ontology; healthcare blockchain case study; 0x, æternity | Nash_Agent + Consensus Verifier (no new agent needed) |
| ML methods & data integration | GANs; RL algorithms; schema matching; LSH clustering; streaming PMI; churn detection | Staff Engineer + Evidence Auditor (no new agent needed) |

The Evidence Auditor's papers include deliberately contested work. *Feeling the Future* failed independent replication. The emotional-contagion study drew an editorial expression of concern over consent. The faces-to-orientation classifier is a standing example of a dual-use inference about a protected trait. These papers are in the agent's grounding as cautionary cases, not as standards to emulate.

## The eight domain role archetypes

| Archetype | Judges | Veto dimension | Weight |
|---|---|---|---|
| The Cryptographer | Threat model and definitions, proofs and assumptions, composition, key lifecycle, primitive hygiene | `crypto` | 1.2 |
| The Privacy Adversary | Re-identification risk, linkage exposure, minimization, auditability, disclosure minimality | `privacy` | 1.1 |
| The Consensus Verifier | Fault model, safety argument, liveness and termination, understandability, adversarial execution | `consensus-safety` | 1.1 |
| The Silicon Compiler Architect | IR and lowering design, retargetability, equivalence evidence, performance honesty, determinism and hardening | none | 1.0 |
| The Complexity Scientist | Adaptivity awareness, coordination-mechanism fit, regime and scale behavior, feedback and control, trust dynamics | none | 0.9 |
| The Evidence Auditor | Claim support, evidence quality, generalization, research ethics, calibration | `evidence` | 1.0 |
| The Thermodynamicist | Physical correctness, quantitative precision, level-of-stack honesty, honest caveats, substrate fairness | `physical-correctness` | 1.2 |
| The Metering Economist | Cost recovery, incentive design, meterability, Goodhart resistance, savings allocation | `cost-recovery` | 1.1 |

Each persona also carries shared house rules:
- It is a role archetype, not an impersonation.
- Findings must name a location in the subject.
- Blockers are raised only on the archetype's own veto dimensions. Anywhere else, Nash_Agent records a blocker as cheap talk, so jurors use "major" there.
- Papers from the library are named when used.

## The physics-of-compute archetypes

Two role archetypes cover subjects about the physics and the pricing of computation. These are subjects no other juror on the roster can rule on.

**The Thermodynamicist** judges whether claims about energy, information and physical limits are true at the level of the stack where they are made. It checks three things:
- each bound is named for what it actually bounds;
- figures for a gate, a chip and a whole system are kept apart;
- caveats are stated wherever an argument leans on them.

Its veto is on `physical-correctness`.

**The Metering Economist** judges whether a price recovers the full cost of the asset, what behavior its billing unit rewards, and who captures the savings. That covers cost recovery, meterability, Goodhart resistance, savings sharing and the ratchet effect. Its veto is on `cost-recovery`, so a price that cannot pay for the plant is a credible blocker rather than cheap talk.

Both records carry a `canon` list alongside `grounded_in`. It names standard references from outside the project library: Landauer, Bennett, Horowitz, Koomey and Weitzman.

## Nash_Agent v2

Three new rules, drawn from the new papers:

- **Assume coalitions.** A mechanism that is truthful for individuals isn't necessarily truthful for colluding groups. Prefer mechanisms that make declaring the coalition a dominant strategy.
- **Know what is computable.** Finding an equilibrium is PPAD-hard. Predicting which equilibrium Lemke-Howson reaches is PSPACE-complete. So Nash_Agent states its solution concept and whether its answer is exact, approximate, or local. The kernel already does this when it switches to local search.
- **Know when to stop.** Stop bargaining when the expected gain from another round is less than the cost of delay. Use reciprocity in repeated play.

The kernel is unchanged; only the persona and its grounding changed.

## New presets

| Preset | Members | Use for |
|---|---|---|
| Crypto & Attestation Room | Cryptographer, Attestation Architect, Privacy Adversary, Security Reviewer, Simplifier | Protocols, enclaves, key management |
| Ledger Review | Consensus Verifier, Cryptographer, Nash_Agent, Systems Integrator, Staff Engineer | DLT designs, smart contracts, token mechanics |
| Health Data Exchange | Privacy Adversary, Cryptographer, Attestation Architect, Nash_Agent, Product Lead | HIE, clinical data sharing, consent flows |
| Compiler & Hardware Review | Silicon Compiler Architect, Attestation Architect, Systems Integrator, Consensus Verifier, Simplifier | High-level code to hardware, accelerators, heterogeneous targets |
| Emergence Lab | Complexity Scientist, Nash_Agent, Evidence Auditor, Staff Engineer, Product Lead | Swarms, markets, multi-agent platforms (including this one) |
| Paper Review | Evidence Auditor, Technical Writer, Complexity Scientist, Simplifier | Reviewing papers, whitepapers and research-heavy docs |
| Physics of Compute | Thermodynamicist, Metering Economist, Silicon Compiler Architect, Evidence Auditor, Nash_Agent | Energy, physical limits and pricing of computation; usage-based pricing models |

Every member id resolves in `jjv/registry.py`; the base and legend ids (`security_reviewer`, `attestation_architect`, `systems_integrator`, `staff_engineer`, `product_lead`, `technical_writer`, `simplifier`) are defined in `jjv/archetypes.py` and `jjv/legends.py`.

## Library housekeeping

- **The library is over the project's knowledge limit** (about 5.3 MB against 2 MB). Search still returns hits from the new papers, but retrieval is selective, so some documents will rarely surface. Removing the items below is the cheapest way to bring it down.
- **Duplicates uploaded twice:**
  - *Nash Q-Learning*
  - *Practical Byzantine Fault Tolerance*
  - *TOPOLOGY AND ECONOMICS*
  - *A Retargetable Compilation Framework*
  - *The Complexity of the Homotopy Method* (two copies)
  - *Computational lambda-calculus and monads* (two copies)
  - *Feeling the Future* (two versions)
  - *Poisoning Language Models During Instruction Tuning* (from the first upload)
- **Not research material:**
  - LaTeX guides (three)
  - the fingerstyle guitar lesson
  - a saved dermavir.com page
  - a Python-libraries listicle
- **Personal and business records:** consulting agreements and SOWs, the LLC operating agreement, an ACH authorization, AR aging reports, a release form, and a résumé. These are searchable by any agent given library access. Consider moving them out before Phase 5c gives jurors a search tool.
