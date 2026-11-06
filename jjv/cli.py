"""Run a panel from the terminal.

    python -m jjv.cli review docs/design.md --panel "Physics of Compute"
    git diff | python -m jjv.cli review - --discipline code
    python -m jjv.cli review --url https://example.com/post --panel "Writers' Room"
    python -m jjv.cli generate brief.txt --panel "Docs Crit" --out draft.md

Live runs call Claude and spend money, up to --max-usd. Run records go to ~/.jjv/runs,
outside any repo, because Judges must not be able to read them.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from jjv import voter
from jjv.backend import ClaudeBackend
from jjv.fetch import FetchError, fetch_text
from jjv.orchestrator import AGGREGATORS, Config, Orchestrator, convene


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m jjv.cli", description=__doc__.split("\n\n")[0])
    ap.add_argument("mode", choices=["review", "generate"])
    ap.add_argument("input", nargs="?", help="file holding the subject or brief; - reads stdin")
    ap.add_argument("--url", help="review the text of this web page instead of a file")
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--panel", help='a preset name, such as "Physics of Compute"')
    who.add_argument("--judges", help="comma-separated archetype ids")
    who.add_argument("--discipline", help="auto-convene the defaults for a discipline")
    ap.add_argument("--repo", help="let Judges read this directory")
    ap.add_argument("--no-jury", action="store_true", help="skip the deliberation round")
    ap.add_argument("--aggregator", choices=AGGREGATORS, default="nash_broker")
    ap.add_argument("--deliberation-rounds", type=int, default=1,
                    help="Jury rounds; above 1, Judges negotiate and cost rises with each round")
    ap.add_argument("--model", help="use this model for every archetype")
    ap.add_argument("--max-usd", type=float, default=5.0, help="spending limit for the run")
    ap.add_argument("--revision-budget", type=float, default=8.0)
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--threshold", type=float, default=4.0)
    ap.add_argument("--store", default=str(Path.home() / ".jjv" / "runs"))
    ap.add_argument("--out", help="generate: write the final draft here")
    return ap


class Progress:
    """One status line per event, with elapsed time and money spent so far."""

    def __init__(self):
        self.start = time.monotonic()

    def line(self, event: dict, text: str) -> None:
        seconds = int(time.monotonic() - self.start)
        print(f"{seconds // 60:02d}:{seconds % 60:02d}  ${event.get('cost_usd', 0):5.2f}  {text}",
              file=sys.stderr, flush=True)

    def __call__(self, event: dict) -> None:
        kind = event["type"]
        if kind == "phase":
            self.line(event, f"[{event['phase']}]")
        elif kind == "verdict":
            self.line(event, f"  {event['archetype_id']}: {event['recommendation']} "
                             f"({event['overall']:g}/5)")
        elif kind == "note":
            self.line(event, f"  {event['text']}")
        elif kind == "failure":
            self.line(event, f"  {event['archetype_id']} FAILED: {event['error']}")
        elif kind == "settlement":
            self.line(event, f"  settlement proposes {len(event['address_now'])} fixes")
        elif kind == "vote":
            self.line(event, f"  decision: {event['decision']} ({event['score']:g}/5)")


def failure_warning(run: dict) -> str | None:
    """Say plainly when Judges dropped out, because the result then means less."""
    failures = run.get("failures") or []
    if not failures:
        return None
    phases = sorted({f["phase"] for f in failures})
    return (f"WARNING: {len(failures)} Judge call(s) failed ({', '.join(phases)}). Judges that "
            "failed the Jury kept their first verdict, so this result is less deliberated "
            "than it looks. Raise --max-usd if the errors mention budget.")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if (args.input is None) == (args.url is None):
        print("error: give exactly one of a file or --url", file=sys.stderr)
        return 2
    try:
        if args.url:
            text = fetch_text(args.url)
        else:
            text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text()
    except FetchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
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
                    deliberation_rounds=args.deliberation_rounds,
                    threshold=args.threshold)
    try:
        orchestrator = Orchestrator(ClaudeBackend(), config, Progress())
        entry = orchestrator.review if args.mode == "review" else orchestrator.generate
        run = asyncio.run(entry(text, panel))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if run["status"] != "done":
        print(f"run failed: {run['error']}", file=sys.stderr)
        print(failure_warning(run) or "", file=sys.stderr)
        return 1
    if warning := failure_warning(run):
        print(warning, file=sys.stderr)
    print(voter.summary(run["result"]))
    if run["result"]["fixes"]:
        print("\nFix in the next revision:")
        print("\n".join(f"  - {f['title']}" for f in run["result"]["fixes"]))
    if args.mode == "generate":
        print(f"\nStopped: {run['stop_reason']}; kept round {run['best_round']} "
              f"of {len(run['rounds'])}.")
        if args.out:
            Path(args.out).write_text(run["draft"])
    print(f"\nRun {run['id']}: ${run['cost_usd']:.2f}, saved in {args.store}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
