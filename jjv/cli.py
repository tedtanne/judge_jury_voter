"""Run a panel from the terminal.

    python -m jjv.cli review docs/design.md --panel "Physics of Compute"
    git diff | python -m jjv.cli review - --discipline code
    python -m jjv.cli generate brief.txt --panel "Docs Crit" --out draft.md

Live runs call Claude and spend money, up to --max-usd. Run records go to ~/.jjv/runs,
outside any repo, because Judges must not be able to read them.

--knowledge lets Judges look up and cite a personal knowledge base, which sends the text they
read to Claude. It is off by default and needs the optional km package.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from jjv import voter
from jjv.backend import ClaudeBackend
from jjv.knowledge import KnowledgeUnavailable
from jjv.orchestrator import AGGREGATORS, Config, Orchestrator, convene


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m jjv.cli", description=__doc__.split("\n\n")[0])
    ap.add_argument("mode", choices=["review", "generate"])
    ap.add_argument("input", help="file holding the subject or brief; - reads stdin")
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--panel", help='a preset name, such as "Physics of Compute"')
    who.add_argument("--judges", help="comma-separated archetype ids")
    who.add_argument("--discipline", help="auto-convene the defaults for a discipline")
    ap.add_argument("--repo", help="let Judges read this directory")
    ap.add_argument("--no-jury", action="store_true", help="skip the deliberation round")
    ap.add_argument("--aggregator", choices=AGGREGATORS, default="nash_broker")
    ap.add_argument("--model", help="use this model for every archetype")
    ap.add_argument("--max-usd", type=float, default=5.0, help="spending limit for the run")
    ap.add_argument("--revision-budget", type=float, default=8.0)
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--threshold", type=float, default=4.0)
    ap.add_argument("--store", default=str(Path.home() / ".jjv" / "runs"))
    ap.add_argument("--out", help="generate: write the final draft here")
    ap.add_argument("--knowledge", action="store_true",
                    help="let Judges look up and cite the knowledge base; sends what they read to Claude")
    ap.add_argument("--knowledge-tag", help="limit --knowledge to records with this tag")
    return ap


def progress(event: dict) -> None:
    if event["type"] == "phase":
        print(f"[{event['phase']}]", file=sys.stderr)
    elif event["type"] == "verdict":
        print(f"  {event['archetype_id']}: {event['recommendation']} "
              f"({event['overall']:g}/5)", file=sys.stderr)
    elif event["type"] == "note":
        print(f"  note: {event['text']}", file=sys.stderr)
    elif event["type"] == "failure":
        print(f"  {event['archetype_id']} FAILED: {event['error']}", file=sys.stderr)


def knowledge_summary(section: dict) -> str:
    lines = [f"\nKnowledge base: {len(section['reads'])} reads, "
             f"{section['withheld']} sensitive results withheld."]
    if section["cited"]:
        lines.append("Cited by findings (check these yourself):")
        lines += [f"  {c['finding']}: {c['id']}" for c in section["cited"]]
    if section["rejected_citations"]:
        lines.append(f"Rejected {len(section['rejected_citations'])} citations of records "
                     "the Judge had not read.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text()
    except (OSError, UnicodeDecodeError) as e:
        print(f"error: cannot read {args.input}: {e}", file=sys.stderr)
        return 2
    try:
        panel = convene(args.panel, args.judges.split(",") if args.judges else None,
                        args.discipline)
    except (KeyError, ValueError) as e:
        print(f"error: {e.args[0]}", file=sys.stderr)
        return 2

    config = Config(jury=not args.no_jury, aggregator=args.aggregator, model=args.model,
                    repo=args.repo, max_usd=args.max_usd, store=args.store,
                    revision_budget=args.revision_budget, max_rounds=args.max_rounds,
                    threshold=args.threshold,
                    knowledge=args.knowledge or bool(args.knowledge_tag),
                    knowledge_tag=args.knowledge_tag)
    try:
        orchestrator = Orchestrator(ClaudeBackend(), config, progress)
        entry = orchestrator.review if args.mode == "review" else orchestrator.generate
        run = asyncio.run(entry(text, panel))
    except (ValueError, KnowledgeUnavailable) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if run["status"] != "done":
        print(f"run failed: {run['error']}", file=sys.stderr)
        return 1
    print(voter.summary(run["result"]))
    if run["result"]["fixes"]:
        print("\nFix in the next revision:")
        print("\n".join(f"  - {f['title']}" for f in run["result"]["fixes"]))
    if args.mode == "generate":
        print(f"\nStopped: {run['stop_reason']}; kept round {run['best_round']} "
              f"of {len(run['rounds'])}.")
        if args.out:
            Path(args.out).write_text(run["draft"])
    if "knowledge" in run:
        print(knowledge_summary(run["knowledge"]))
    print(f"\nRun {run['id']}: ${run['cost_usd']:.2f}, saved in {args.store}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
