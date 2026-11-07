"""Run a panel from the terminal.

    python -m jjv.cli review docs/design.md --panel "Physics of Compute"
    git diff | python -m jjv.cli review - --discipline code
    python -m jjv.cli review --url https://example.com/post --panel "Writers' Room"
    python -m jjv.cli generate brief.txt --panel "Docs Crit" --out draft.md
    python -m jjv.cli suggest --url https://example.com/post
    python -m jjv.cli explain RUN_ID

Live runs call Claude and spend money, up to --max-usd. Run records go to ~/.jjv/runs,
outside any repo, because Judges must not be able to read them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import threading
import time
from pathlib import Path

from jjv import voter
from jjv.backend import BackendError, ClaudeBackend
from jjv.explain import explain, step_label
from jjv.fetch import FetchError, fetch_page
from jjv.harness import consult, load_providers, make_backend, save_opinions, with_opinions
from jjv.orchestrator import AGGREGATORS, Config, Orchestrator, convene
from jjv.suggest import budget_warning, render, suggest_panel


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m jjv.cli", description=__doc__.split("\n\n")[0])
    ap.add_argument("mode", choices=["review", "generate", "suggest", "explain"])
    ap.add_argument("input", nargs="?", help="file holding the subject or brief; - reads "
                    "stdin. For explain, a run id")
    ap.add_argument("--url", help="review the text of this web page instead of a file")
    ap.add_argument("--allow-lost-math", action="store_true",
                    help="run even if formulas could not be read from the content")
    who = ap.add_mutually_exclusive_group()
    who.add_argument("--panel", help='a preset name, such as "Physics of Compute"')
    who.add_argument("--judges", help="comma-separated archetype ids")
    who.add_argument("--discipline", help="auto-convene the defaults for a discipline")
    ap.add_argument("--repo", help="let Judges read this directory")
    ap.add_argument("--no-jury", action="store_true", help="skip the deliberation round")
    ap.add_argument("--explain", action="store_true",
                    help="after the result, show how each section reached its output")
    ap.add_argument("--aggregator", choices=AGGREGATORS, default="nash_broker")
    ap.add_argument("--deliberation-rounds", type=int, default=1,
                    help="Jury rounds; above 1, Judges negotiate and cost rises with each round")
    ap.add_argument("--consult", help="review only: ask these models first and give the "
                    "Judges their answers, for example xai,openai,gemini,claude")
    ap.add_argument("--consult-usd", type=float, default=1.0,
                    help="spending limit for the --consult models, on top of --max-usd")
    ap.add_argument("--judge-provider", help="run the Judges on this provider's public API "
                    "instead of the local Claude Agent SDK")
    ap.add_argument("--providers-file", default="~/.jjv/providers.json",
                    help="model names and prices for --consult and --judge-provider")
    ap.add_argument("--model", help="use this model for every archetype")
    ap.add_argument("--max-usd", type=float, default=5.0, help="spending limit for the run")
    ap.add_argument("--revision-budget", type=float, default=8.0)
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--threshold", type=float, default=4.0)
    ap.add_argument("--store", default=str(Path.home() / ".jjv" / "runs"))
    ap.add_argument("--out", help="generate: write the final draft here")
    return ap


class Progress:
    """One status line per event, with elapsed time and money spent so far.

    Used as a context manager, it also prints a line when nothing has happened for a while,
    because a Judge can think for a minute and a silent terminal looks frozen.
    """

    def __init__(self, heartbeat_s: float = 15.0):
        self.start = time.monotonic()
        self.expected = 0
        self.reported = 0
        self.waiting: list[str] = []
        self.heartbeat_s = heartbeat_s
        self.quiet_since = self.start
        self.spent = 0.0
        self.phase = "starting"
        self.finished = threading.Event()
        self.ticker = threading.Thread(target=self._tick, daemon=True)

    def __enter__(self):
        self.ticker.start()
        return self

    def __exit__(self, *exc):
        self.finished.set()
        self.ticker.join()

    def _tick(self) -> None:
        while not self.finished.wait(self.heartbeat_s / 3):
            if time.monotonic() - self.quiet_since >= self.heartbeat_s:
                self.line({"cost_usd": self.spent},
                          f"  still working on {self.phase}{self.pending()}")

    def line(self, event: dict, text: str) -> None:
        self.quiet_since = time.monotonic()
        seconds = int(self.quiet_since - self.start)
        print(f"{seconds // 60:02d}:{seconds % 60:02d}  ${event.get('cost_usd', 0):5.2f}  {text}",
              file=sys.stderr, flush=True)

    def pending(self) -> str:
        if not self.waiting:
            return ""
        names = ", ".join(self.waiting[:3]) + (", ..." if len(self.waiting) > 3 else "")
        return f", {self.reported}/{self.expected} reported, waiting on {names}"

    def done(self, archetype_id: str) -> None:
        self.reported += 1
        if archetype_id in self.waiting:
            self.waiting.remove(archetype_id)

    def count(self) -> str:
        return f"{self.reported}/{self.expected} " if self.expected else ""

    def __call__(self, event: dict) -> None:
        kind = event["type"]
        self.spent = event.get("cost_usd", self.spent)
        self.phase = event.get("phase", self.phase)
        if kind == "phase":
            self.line(event, f"[{step_label(event['phase'])}]")
        elif kind == "verdict":
            self.done(event["archetype_id"])
            self.line(event, f"  {self.count()}{event['archetype_id']}: "
                             f"{event['recommendation']} ({event['overall']:g}/5)")
        elif kind == "note":
            if "expected" in event:
                self.expected, self.reported = event["expected"], 0
                self.waiting = list(event.get("waiting", []))
            self.line(event, f"  {event['text']}")
        elif kind == "failure":
            self.done(event["archetype_id"])
            self.line(event, f"  {self.count()}{event['archetype_id']} FAILED: {event['error']}")
        elif kind == "convergence":
            self.line(event, f"  convergence: {event['text']}")
        elif kind == "links":
            self.line(event, f"  linked {len(event['groups'])} groups of matching findings")
        elif kind == "restored":
            self.line(event, f"  put back {len(event['finding_ids'])} dropped findings")
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


def judge_backend(args):
    if not args.judge_provider:
        return ClaudeBackend()
    if args.repo:
        raise ValueError("--repo needs the Claude Agent SDK backend, which guards file tools")
    return make_backend(load_providers(args.providers_file, [args.judge_provider])[0])


def gather_opinions(args, text: str) -> tuple[list, str, dict]:
    """Ask the chosen models, report each one, and build the subject for the panel."""
    names = [n.strip() for n in args.consult.split(",") if n.strip()]
    providers = load_providers(args.providers_file, names)
    print(f"asking {len(providers)} models, limit ${args.consult_usd:.2f}", file=sys.stderr,
          flush=True)
    with Progress() as progress:
        progress.phase = "the model answers"
        opinions = asyncio.run(consult(text, providers, max_usd=args.consult_usd))
    for o in opinions:
        status = f"FAILED: {o.error}" if o.error else f"answered (${o.cost:.2f})"
        print(f"  {o.provider}: {status}", file=sys.stderr)
    subject, labels = with_opinions(text, opinions)
    return opinions, subject, labels


def explain_saved(args) -> int:
    run_id = args.input or ""
    if not re.fullmatch(r"[0-9a-f]{12}", run_id):
        print("error: explain needs a run id", file=sys.stderr)
        return 2
    try:
        run = json.loads((Path(args.store) / f"{run_id}.json").read_text())
    except (OSError, ValueError) as e:
        print(f"error: cannot read run {run_id}: {e}", file=sys.stderr)
        return 2
    print(explain(run), end="")
    return 0


def run_suggest(args, text: str) -> int:
    if not text.strip():
        print("error: nothing to read: the content is blank", file=sys.stderr)
        return 2
    try:
        backend = judge_backend(args)
        print("reading a sample of the content", file=sys.stderr, flush=True)
        with Progress() as progress:
            progress.phase = "the recommendation"
            result, cost = asyncio.run(suggest_panel(text, backend))
    except (ValueError, BackendError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if args.url:
        source = ["--url", args.url]
    else:
        source = [] if args.input == "-" else [args.input]
    print(render(result, text, source, cost=cost, store=args.store), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.mode == "explain":
        return explain_saved(args)
    if (args.input is None) == (args.url is None):
        print("error: give exactly one of a file or --url", file=sys.stderr)
        return 2
    try:
        if args.url:
            print(f"fetching {args.url}", file=sys.stderr, flush=True)
            page = fetch_page(args.url)
            text = page.text
            print(f"  read {len(text.split()):,} words, {page.formulas} formulas",
                  file=sys.stderr, flush=True)
            if warning := page.math_warning():
                if not args.allow_lost_math:
                    print(f"error: {warning} Nothing was spent. Use --allow-lost-math to run "
                          "anyway.", file=sys.stderr)
                    return 2
                print(f"WARNING: {warning}", file=sys.stderr)
        else:
            text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text()
    except FetchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (OSError, UnicodeDecodeError) as e:
        print(f"error: cannot read {args.input}: {e}", file=sys.stderr)
        return 2
    if args.mode == "suggest":
        return run_suggest(args, text)
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
        progress = Progress()
        orchestrator = Orchestrator(judge_backend(args), config, progress)
        entry = orchestrator.review if args.mode == "review" else orchestrator.generate
        opinions, labels = [], {}
        if args.consult:
            if args.mode != "review":
                raise ValueError("--consult works with review only")
            opinions, text, labels = gather_opinions(args, text)
        if not args.repo and args.mode == "review":
            # With --repo, Judges read more than the subject, so length says too little.
            warning = budget_warning(len(text), len(panel), args.max_usd, jury=not args.no_jury,
                                     rounds=args.deliberation_rounds, store=args.store)
            if warning:
                print(warning, file=sys.stderr)
        with progress:
            run = asyncio.run(entry(text, panel))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if opinions:
        save_opinions(args.store, run, opinions, labels)
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
    if args.explain:
        print("\n" + explain(run), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
