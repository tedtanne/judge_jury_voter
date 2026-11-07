---
title: Reading a run
description: What the status lines, convergence lines and --explain output mean, with a real example.
status: draft
updated: 2026-11-07
---

# Reading a run

A run reports what it is doing while it works, then what it decided, then, if you ask, how it got there.

```bash
python -m jjv.cli suggest plan.md                       # which panel, and what budget
python -m jjv.cli review plan.md --panel "The Nash Table" --max-usd 5 --explain
python -m jjv.cli explain RUN_ID                        # the same explanation later, free
```

The example on this page is a real run: a short design for a rate limiter, reviewed by The Nash Table with `--deliberation-rounds 2`. It took 3 minutes 34 seconds and cost $2.62.

## Status lines

Status lines go to stderr as they happen.

```
00:43  $ 0.26    3/5 staff_engineer: revise (2.727/5)
```

| Part | Meaning |
|---|---|
| `00:43` | Time since the run started |
| `$ 0.26` | Money spent so far. It updates when a Judge finishes, so it lags work in progress |
| `3/5` | Judges that have reported in this step |
| `staff_engineer: revise (2.727/5)` | That Judge's recommendation and score |

A run has four steps:

| Step | What happens |
|---|---|
| `1/4 SELECT` | The panel is chosen |
| `2/4 JUDGE` | Each Judge scores alone, without seeing the others |
| `3/4 JURY` | Each Judge reads the others anonymously, sees the settlement proposal, and may revise |
| `4/4 VOTE` | Nash bargaining sets the fix list, and a fixed rule makes the decision |

In generate mode, a `GENERATE` step writes each draft, and the four steps repeat for it.

### Heartbeat

Judges can think for a minute or more. If nothing has happened for 15 seconds, a line says the run is alive and who it is waiting on:

```
01:10  $ 0.27    still working on JUDGE, 4/5 reported, waiting on nash_agent
```

### Warnings

Before spending, `review` warns if the limit looks too small, because Judges that run out of money drop out:

```
WARNING: this run may need $4.46 to $8.92, and the limit is $3.00. Judges that run out of money drop out. Consider --max-usd 9. This is a rough estimate.
```

The estimate comes from the length of the subject and the number of model calls, and is adjusted once three clean runs are saved. Runs that failed or lost a Judge are ignored, because they show what was spent, not what was needed. There is no warning with `--repo`, where Judges read more than the subject.

After a run, a warning says if any Judge calls failed. Treat that result with care: a Judge that failed the Jury kept its earlier verdict, so the result is less deliberated than it looks.

## Convergence lines

These show how the panel is moving. They are in the status output, in `--explain`, in the run record's events, and in MCP `get_run`.

| Line | What it tells you |
|---|---|
| `scores differ by 1, votes: 5 revise, 47 findings` | Where the Judges stand before reading each other. The score gap is the highest Judge minus the lowest, and zero means they agree |
| `round 1: 1 of 5 Judges moved, score gap 1 to 1 (no closer), 9 issues linked` | How one Jury round changed things. Moved means a score or recommendation changed. Linked issues are findings Judges marked as the same problem |
| `round 1: 2 of 4 Judges name the same fix list` | With negotiation on, the largest group naming one list. Nash_Agent does not count, because it holds no stake |
| `4 of 4 proposed fixes survived to the final 4` | How much of the first proposal stayed in the final fix list |
| `draft 2 scored 3.4 (+0.6), target 4` | In generate mode, how each draft moved toward the target |

The example run went from 2 of 4 to 3 of 4 on the fix list, while only one Judge changed a score. Judges moved on what to fix, not on how good the design was. One holdout remained, so the formula decided.

Convergence is not correctness. Judges can agree and still be wrong, especially when they run on the same model.

## The result

```
DECISION: REVISE  (score 2.544, approval share 0.00)
Consensus score: 2.544/5

Top actions:
  1. [major] Fail-open removes the limit under the conditions it is meant to handle
  ...

Fix in the next revision:
  - Fail-open removes the limit under the conditions it is meant to handle
  - Bucket identity does not match the tenant limit
```

**Top actions** ranks every finding by severity, then by how much support it has from the panel. **Fix in the next revision** is the list the bargain chose within the revision budget. The two can differ: a finding can rank high and still be deferred.

A low score does not mean bad work. Judges are built to find faults, and most rubrics measure soundness, not originality or importance. Read the findings, not just the number.

## What --explain shows

Each section shows how its output was computed.

**Judge scores.** Each rubric score is multiplied by its weight, then divided by the total weight:

```
simplifier: (3x2 + 3x1.3 + 3x1.2 + 1x1) / 5.5 = 2.636, 9 findings, recommends revise
```

**Jury.** Each Judge's score and finding count before and after, the issues linked, any findings put back, and the result of each negotiation round. A veto, or a finding another Judge backed, cannot be dropped, so code restores it.

**Fix list.** The broker chooses the fixes that maximize the weighted product of each Judge's gain over having no deal:

```
Budget 8, spent 8. Forced by a credible veto: 0. Chosen: 4. Deferred: 21
Gain per Judge: simplifier +13.60, staff_engineer +15.60, security_reviewer +13.40, product_lead +9.40
Empty threats recorded: 0
Search: heuristic. Equilibrium holds: yes
```

| Term | Meaning |
|---|---|
| Budget | Revision cost units available, 8 by default. A major finding costs about 2 |
| Forced by a credible veto | Blockers from a Judge holding a veto in that area. They are always included |
| Gain per Judge | How much better off each Judge is than with no deal, after its share of the rework |
| Empty threats | Blockers or rejections with no veto behind them. They lower a Judge's weight in later runs |
| Search | Every combination was checked, or a heuristic search was used because there were too many |
| Equilibrium holds | No veto-holder would do better by blocking |

If negotiating Judges all named one list, and it fits the budget and keeps every credible veto, a line says it replaced the formula's choice. The formula's answer is still saved, for comparison.

**Decision.** No model is involved. The consensus is each Judge's score times its weight, divided by the total weight:

```
Consensus = (2x1 + 2.625x1.2 + 2.4x1.4 + 2.727x1.3 + 3x0.9) / 5.8 = 2.544
```

The rules are applied in order:

1. A credible veto blocks approval.
2. A veto-holder that did not report blocks approval.
3. Approve needs a score of at least 4, and at least half the panel's weight recommending approve.
4. Reject if the score is below 2. Anything else is revise.

The decision is a recommendation. A person approves.

## Reused results

If the same content was already reviewed with the same panel and settings, the run is reused and nothing is spent:

```
reusing run 8d179356c0cf from 2026-11-07 14:02: the same content and settings, so nothing was spent. Use --no-cache to run again.
```

With `--json`, the result says `"cached": true` and `"spent_now_usd": 0`.

## Choosing a panel

```
This looks like: Python module: deterministic tally of review verdicts, with decision policy (573 words)

1. FAANG Code Review  (about $1.75 to $3.50)
   This is production Python code with a docstring, functions, and edge-case handling, so it fits a code review of a pull request.

Run the top pick with:
  python -m jjv.cli review jjv/voter.py --panel 'FAANG Code Review' --max-usd 4
```

`suggest` makes one small model call, with no tools, on a sample of the content. It gives one to three panels, or says none fits. It never starts a paid run. The reasons come from a model that read the content, so treat them as untrusted. The command is built by code from the preset name. Costs are rough, and it has been tried on only four samples.
