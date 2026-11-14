"""One saved run as a single HTML page, so a reader can watch the panel change its mind.

    jjv render RUN_ID --out run.html

Free: this reads the record and calls no model. Everything on the page comes from the run
record, and the sums are the same ones ``jjv explain`` prints. The page is one file with
no scripts, images or fonts to fetch, so it can be opened from disk, attached or committed.

The page names who is behind each anonymous Judge and shows an excerpt of the subject, as
the run record does. Findings are model output and can quote the subject; the page escapes
them, and a reader should treat them as data, not instructions.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

from jjv import registry, voter
from jjv.explain import judge_sum
from jjv.report import DATA_NOTE

SEVERITY_ORDER = {"blocker": 0, "major": 1, "minor": 2, "nit": 3}
EXCERPT_CHARS = 1500


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def name_of(archetype_id: str) -> str:
    try:
        return registry.get(archetype_id)["name"]
    except KeyError:
        return archetype_id


def title_of(subject: str) -> str:
    """A title for the page: the front-matter title if there is one, else the first line."""
    lines = [l.strip() for l in subject.splitlines() if l.strip()]
    for line in lines[:12]:
        if line.lower().startswith("title:"):
            return line.split(":", 1)[1].strip().strip("'\"") or "Untitled"
    first = lines[0].lstrip("#").strip() if lines else "Untitled"
    return first if len(first) <= 90 else first[:87].rstrip() + "..."


def pct(score: float) -> float:
    """Where a 1 to 5 score sits across a track, as a percentage."""
    return max(0.0, min(100.0, (score - 1) / 4 * 100))


def fmt(number: float, digits: int = 2) -> str:
    """A number without trailing zeros: 2.0 is 2, 2.857 stays 2.857."""
    return f"{number:.{digits}f}".rstrip("0").rstrip(".") or "0"


# ---------------------------------------------------------------------------
# Pieces of the page
# ---------------------------------------------------------------------------

def _head(run: dict, rec: dict, result: dict) -> str:
    title = title_of(run.get("subject", ""))
    when = datetime.fromtimestamp(run["created"], timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    models = sorted({c["model"] for c in run.get("calls", []) if c.get("model")})
    settled = rec.get("settled_by") or rec.get("aggregator") or "unknown"
    meta = [("Run", run["id"]), ("Mode", run["mode"]), ("When", when),
            ("Judges", str(len(run.get("panel", [])))), ("Cost", f"${run['cost_usd']:.2f}"),
            ("Settled by", settled)]
    if models:
        meta.append(("Models", ", ".join(models)))
    decision = (result or {}).get("decision") or run.get("status", "unknown")
    score = (result or {}).get("score")
    verdict = (f'<div class="verdict"><span class="badge {esc(decision)}">{esc(decision)}</span>'
               + (f'<span class="score"><b>{fmt(score, 3)}</b> / 5</span>' if score is not None else "")
               + (f'<span class="reason">{esc(result["reason"])}</span>' if result else "")
               + "</div>")
    error = f'<p class="error">Stopped: {esc(run["error"])}</p>' if run.get("error") else ""
    return (f'<header><p class="kicker">Judge · Jury · Voter</p><h1>{esc(title)}</h1>'
            f'<dl class="meta">' + "".join(f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in meta)
            + f"</dl>{verdict}{error}</header>")


def _convergence_lines(run: dict) -> str:
    lines = [e["text"] for e in run.get("events", []) if e["type"] == "convergence"]
    if not lines:
        return ""
    return '<ul class="plain">' + "".join(f"<li>{esc(l)}</li>" for l in lines) + "</ul>"


def _room(run: dict, rec: dict) -> str:
    """One card per Judge: who it is, what it scored alone, what it scored after reading."""
    before = {v["archetype_id"]: v for v in rec.get("judge", [])}
    after = {v["archetype_id"]: v for v in rec.get("jury", [])}
    lost = {f["archetype_id"]: f.get("error", "") for f in run.get("failures", [])
            if str(f.get("phase", "")).upper() == "JURY"}
    cards = []
    for aid, first in before.items():
        last = after.get(aid)
        veto = ", ".join(first.get("veto_dimensions") or []) if first.get("veto") else ""
        head = (f'<div class="who"><span class="alias">{esc(first["alias"])}</span>'
                f'<div><b>{esc(name_of(aid))}</b><small>weight {fmt(first["weight"])}'
                + (f' · veto on {esc(veto)}' if veto else "") + "</small></div></div>")
        if last:
            delta = last["overall"] - first["overall"]
            arrow = ("stayed" if abs(delta) < 1e-9 else f"{delta:+.3f}")
            move = (f'<div class="move"><span>{fmt(first["overall"], 3)}</span>'
                    f'<span class="arrow">→</span><span><b>{fmt(last["overall"], 3)}</b></span>'
                    f'<span class="delta">{esc(arrow)}</span></div>'
                    f'<div class="recs"><span class="rec {esc(first["recommendation"])}">'
                    f'{esc(first["recommendation"])}</span><span class="arrow">→</span>'
                    f'<span class="rec {esc(last["recommendation"])}">{esc(last["recommendation"])}'
                    f'</span><span class="dim">findings {len(first["findings"])} → '
                    f'{len(last["findings"])}, endorses {len(last.get("endorses") or [])}</span></div>')
            mind = last.get("changed_mind") or ""
            if aid in lost:
                quote = (f'<p class="dim"><b>Its Jury call failed</b>, so its first verdict stands. '
                         f'{esc(lost[aid])}</p>')
            elif mind and mind.lower() != "nothing":
                quote = f'<blockquote><span class="dim">What changed its mind</span>{esc(mind)}</blockquote>'
            else:
                quote = '<p class="dim">Did not change its mind.</p>'
            aversion = last.get("change_aversion")
            foot = (f'<p class="dim">Change aversion {fmt(aversion)}: how much of the rework cost '
                    'it says it would bear.</p>' if aversion is not None else "")
        else:
            move = (f'<div class="move"><span><b>{fmt(first["overall"], 3)}</b></span>'
                    f'<span class="dim">no Jury verdict</span></div>'
                    f'<div class="recs"><span class="rec {esc(first["recommendation"])}">'
                    f'{esc(first["recommendation"])}</span><span class="dim">'
                    f'{len(first["findings"])} findings</span></div>')
            quote, foot = "", ""
        rationale = (last or first).get("rationale") or ""
        detail = (f'<details><summary>Rationale and rubric</summary><p>{esc(rationale)}</p>'
                  '<table class="rubric">' + "".join(
                      f"<tr><td>{esc(k)}</td><td>{fmt(v)}</td></tr>"
                      for k, v in (last or first).get("scores", {}).items())
                  + f'</table><p class="sum">{esc(judge_sum(last or first))}</p></details>')
        cards.append(f'<article class="judge">{head}{move}{quote}{foot}{detail}</article>')
    return '<div class="judges">' + "".join(cards) + "</div>"


def _tracks(rec: dict, result: dict | None) -> str:
    """Each Judge's score before and after the Jury on one 1 to 5 track, and the consensus."""
    before = {v["archetype_id"]: v for v in rec.get("judge", [])}
    after = {v["archetype_id"]: v for v in rec.get("jury", [])}
    if not before:
        return ""
    rows = []
    for aid, first in before.items():
        last = after.get(aid)
        a, b = first["overall"], (last or first)["overall"]
        lo, hi = min(a, b), max(a, b)
        rows.append(
            f'<div class="row"><span class="label">{esc(name_of(aid))}</span><div class="track">'
            f'<span class="span" style="left:{pct(lo):.1f}%;width:{pct(hi) - pct(lo):.1f}%"></span>'
            f'<span class="dot first" style="left:{pct(a):.1f}%" title="alone {fmt(a, 3)}"></span>'
            + (f'<span class="dot last" style="left:{pct(b):.1f}%" title="after the Jury {fmt(b, 3)}"></span>'
               if last else "") + "</div></div>")
    guides = f'<span class="guide approve" style="left:{pct(voter.APPROVE_SCORE):.1f}%"></span>'
    if result and result.get("score") is not None:
        guides += f'<span class="guide consensus" style="left:{pct(result["score"]):.1f}%"></span>'
    legend = ('<p class="legend"><span class="dot first"></span> alone '
              '<span class="dot last"></span> after the Jury '
              '<span class="key consensus"></span> consensus '
              f'<span class="key approve"></span> approve needs {fmt(voter.APPROVE_SCORE)}</p>')
    axis = '<div class="row axis"><span class="label"></span><div class="track">' + "".join(
        f'<span class="tick" style="left:{pct(n):.1f}%">{n}</span>' for n in range(1, 6)) + "</div></div>"
    return f'<div class="tracks"><div class="guides">{guides}</div>{"".join(rows)}{axis}</div>{legend}'


def _findings(run: dict, rec: dict, result: dict | None) -> str:
    if not result or not result.get("findings"):
        return "<p class=\"dim\">No findings.</p>"
    fixed = {f["id"] for f in result.get("fixes", [])}
    groups = {}
    for group in rec.get("links") or []:
        for fid in group:
            groups[fid] = group
    rows = []
    for i, f in enumerate(result["findings"], 1):
        who = ", ".join(name_of(a) for a in f.get("raised_by", []))
        backed = ", ".join(name_of(a) for a in f.get("endorsed_by", []))
        linked = groups.get(f["id"]) or groups.get(f.get("own_id", ""))
        tags = (f'<span class="tag {esc(f["severity"])}">{esc(f["severity"])}</span>'
                + ('<span class="tag fix">fix now</span>' if f["id"] in fixed else "")
                + (f'<span class="tag link" title="{esc(", ".join(linked))}">linked ×{len(linked)}</span>'
                   if linked else ""))
        rows.append(
            f'<details class="finding"><summary><span class="n">{i}</span>{tags}'
            f'<span class="title">{esc(f["title"])}</span>'
            f'<span class="support" title="weighted support">{fmt(f.get("support", 0))}</span></summary>'
            f'<div class="body"><p class="dim">{esc(f.get("dimension", ""))}'
            + (f' · {esc(f["location"])}' if f.get("location") else "") + "</p>"
            f'<p>{esc(f.get("detail", ""))}</p><p class="dim">Raised by {esc(who) or "—"}'
            + (f"; backed by {esc(backed)}" if backed else "") + "</p></div></details>")
    return "".join(rows)


def _bargain(run: dict, rec: dict, result: dict | None) -> str:
    s = rec.get("settlement")
    if not s:
        fixes = len((result or {}).get("fixes", []))
        return (f"<p>A plain weighted vote, no bargaining: credible vetoes first, then findings by "
                f"weighted severity, taken within the budget. Fixes chosen: {fixes}.</p>")
    names = {alias: name_of(a) for a, alias in run.get("aliases", {}).items()}
    gains = s.get("gains") or {}
    top = max((abs(g) for g in gains.values()), default=1) or 1
    bars = "".join(
        f'<div class="row"><span class="label">{esc(names.get(k, k))}</span><div class="bar">'
        f'<span class="{"neg" if g < 0 else "pos"}" style="width:{abs(g) / top * 100:.1f}%"></span>'
        f'</div><span class="val">{g:+.2f}</span></div>' for k, g in sorted(gains.items()))
    found = s.get("findings") or {}

    def items(keys, label):
        if not keys:
            return f'<p class="dim">{label}: none</p>'
        lis = "".join(
            f'<li><span class="tag {esc(found.get(k, {}).get("severity", ""))}">'
            f'{esc(found.get(k, {}).get("severity", "?"))}</span> {esc(found.get(k, {}).get("title", k))}'
            f' <span class="dim">cost {fmt(found.get(k, {}).get("cost", 0))}, '
            f'{esc(", ".join(names.get(a, a) for a in found.get(k, {}).get("raised_by", [])))}</span></li>'
            for k in keys)
        return f"<p><b>{label}</b> ({len(keys)})</p><ol class=\"fixes\">{lis}</ol>"

    proposal = rec.get("proposal") or {}
    survived = ""
    if proposal:
        # Keys can change between the proposal and the settlement when findings are linked,
        # so titles come from whichever record knows the key.
        titles = {k: f.get("title", k) for k, f in (proposal.get("findings") or {}).items()}
        titles.update({k: f.get("title", k) for k, f in found.items()})
        kept = set(proposal.get("address_now", [])) & set(s.get("address_now", []))
        dropped = [titles.get(k, k) for k in proposal.get("address_now", []) if k not in kept]
        added = [titles.get(k, k) for k in s.get("address_now", []) if k not in kept]
        survived = (f"<p>Before the Jury the broker proposed {len(proposal.get('address_now', []))} "
                    f"fixes; {len(kept)} survived to the final list of {len(s['address_now'])}."
                    + (f" Dropped: {esc('; '.join(dropped))}." if dropped else "")
                    + (f" Added: {esc('; '.join(added))}." if added else "")
                    + "</p>")
    agreed = ""
    if rec.get("settled_by") == "agreement":
        agreed = (f"<p><b>The Judges agreed their own list</b> of {len(rec.get('agreed', []))} fixes, "
                  "which replaced the formula's choice.</p>")
    stats = [("Budget", fmt(s["budget"])), ("Spent", fmt(s["cost"])),
             ("Forced by a veto", str(len(s["forced"]))), ("Chosen", str(len(s["address_now"]))),
             ("Deferred", str(len(s["deferred"]))), ("Empty threats", str(len(s["cheap_talk"]))),
             ("Search", "every combination" if s.get("exact") else "add, drop, swap"),
             ("Equilibrium holds", "yes" if s.get("individually_rational") else "NO")]
    return ('<p>The broker chooses the fixes that maximize the weighted product of each Judge\'s '
            'gain over having no deal, within the revision budget. A Judge\'s threat counts only '
            'where it holds a veto.</p><dl class="meta">'
            + "".join(f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in stats) + "</dl>"
            + f'<h3>Gain per Judge over no deal</h3><div class="bars">{bars}</div>'
            + items(s["forced"], "Forced by a credible veto") + items(s["address_now"], "Fix now")
            + items(s["cheap_talk"], "Empty threats, not priced") + survived + agreed
            + f'<details><summary>Deferred ({len(s["deferred"])}) and the rule</summary>'
            + items(s["deferred"], "Deferred")
            + f'<p class="dim">{esc(s.get("tie_break_rule", ""))}</p>'
            + "".join(f'<p class="dim">{esc(n)}</p>' for n in s.get("notes", [])) + "</details>")


def _negotiation(run: dict, rec: dict) -> str:
    talks = rec.get("deliberation") or []
    if not talks:
        return ""
    names = {alias: name_of(a) for a, alias in run.get("aliases", {}).items()}
    out = []
    for talk in talks:
        positions = talk.get("positions") or {}
        messages = talk.get("messages") or {}
        agreed = talk.get("agreed")
        verdict = (f"agreed on {len(agreed)} fixes" if agreed is not None else "no agreement")
        rows = "".join(
            f'<article class="offer"><b>{esc(names.get(a, a))}</b> '
            f'<span class="dim">offers {esc(", ".join(positions.get(a, [])) or "nothing")}</span>'
            f'<p>{esc(messages.get(a, ""))}</p></article>' for a in sorted(positions))
        out.append(f'<h3>Round {talk.get("round")}: {esc(verdict)}</h3><div class="offers">{rows}</div>')
    return ('<p>Judges exchange positions and offers. An agreed list replaces the formula if it '
            'fits the budget and keeps every credible veto.</p>' + "".join(out))


def _decision(rec: dict, result: dict | None) -> str:
    final = rec.get("jury") or rec.get("judge") or []
    if not result or not final:
        return '<p class="dim">Not reached.</p>'
    terms = " + ".join(f"{fmt(v['overall'], 3)}×{fmt(v['weight'])}" for v in final)
    total = sum(v["weight"] for v in final)
    share = sum(v["weight"] for v in final if v["recommendation"] == "approve") / total
    rules = [
        (f"A credible veto blocks approval", f"{len(result['vetoes'])} found"),
        ("A veto-holder that did not report blocks approval", f"{len(result['missing_vetoes'])}"),
        (f"Approve needs score ≥ {fmt(voter.APPROVE_SCORE)} and approval share ≥ 0.50",
         f"score {fmt(result['score'], 3)}, share {share:.2f}"),
        (f"Reject if score < {fmt(voter.REJECT_SCORE)}; anything else is revise", ""),
    ]
    lis = "".join(f"<li>{esc(r)}" + (f' <span class="dim">{esc(v)}</span>' if v else "") + "</li>"
                  for r, v in rules)
    dissents = "".join(
        f'<p><b>Dissent, {esc(name_of(d.get("by", "")))}</b> ({esc(d.get("recommendation", ""))}): '
        f'{esc(d.get("rationale", ""))}</p>' for d in result.get("dissents", []))
    return (f'<p class="sum">Consensus = ({esc(terms)}) / {fmt(total)} = <b>{fmt(result["score"], 3)}</b></p>'
            f'<p>A fixed rule, with no model involved:</p><ol>{lis}</ol>'
            f'<p class="result"><span class="badge {esc(result["decision"])}">{esc(result["decision"])}</span> '
            f'{esc(result["reason"])}</p>{dissents}')


def _subject(run: dict) -> str:
    text = run.get("subject") or ""
    words = len(text.split())
    excerpt = text[:EXCERPT_CHARS] + (" …" if len(text) > EXCERPT_CHARS else "")
    repo = run.get("config", {}).get("repo")
    note = " Judges could also read files in a repository, with read-only tools." if repo else ""
    return (f'<details><summary>The subject, {words:,} words{" (excerpt)" if len(text) > EXCERPT_CHARS else ""}'
            f'</summary><pre>{esc(excerpt)}</pre></details><p class="dim">What the panel read.{note}</p>')


def _round(run: dict, rec: dict, many: bool) -> str:
    result = rec.get("vote")
    head = ""
    if many:
        best = " · kept as the result" if rec.get("round") == run.get("best_round") else ""
        head = f'<h2 class="round">Round {rec.get("round")}{esc(best)}</h2>'
        if rec.get("draft"):
            head += (f'<details><summary>Draft {rec.get("round")}</summary>'
                     f'<pre>{esc(rec["draft"])}</pre></details>')
    sections = [
        ("room", "The room", "Each Judge scored alone, then read the others anonymously and "
                 "could revise. The arrow is what reading the room did.", _room(run, rec)),
        ("convergence", "Convergence", "",
         _tracks(rec, result) + ("" if many else _convergence_lines(run))),
        ("findings", "What the panel found", "Every finding after the Jury, ranked by weighted "
                     "support. Linked findings are one issue raised by several Judges.", _findings(run, rec, result)),
        ("negotiation", "Negotiation", "", _negotiation(run, rec)),
        ("bargain", "The bargain", "", _bargain(run, rec, result)),
        ("decision", "The decision", "", _decision(rec, result)),
    ]
    out = [head]
    for sid, title, lede, body in sections:
        if not body:
            continue
        suffix = f"-{rec.get('round')}" if many else ""
        out.append(f'<section id="{sid}{suffix}"><h2>{esc(title)}</h2>'
                   + (f'<p class="lede">{esc(lede)}</p>' if lede else "") + body + "</section>")
    return "".join(out)


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

CSS = """
:root{--paper:#f3f2ec;--surface:#fff;--line:#e4e1d7;--ink:#1b1d24;--ink2:#4a4e5a;--dim:#797f8c;
--accent:#3f57b8;--approve:#2f8f66;--revise:#c07f22;--reject:#c1483f;--soft:#eceaf8;
--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
--serif:Georgia,"Times New Roman",Times,serif;--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--paper:#111319;--surface:#181b23;
--line:#2b303c;--ink:#e8e9ef;--ink2:#b3b9c6;--dim:#8b93a3;--accent:#89a0f2;--approve:#4cc78d;
--revise:#e0a545;--reject:#ec6a60;--soft:#232840;color-scheme:dark}}
:root[data-theme=dark]{--paper:#111319;--surface:#181b23;--line:#2b303c;--ink:#e8e9ef;--ink2:#b3b9c6;
--dim:#8b93a3;--accent:#89a0f2;--approve:#4cc78d;--revise:#e0a545;--reject:#ec6a60;--soft:#232840;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 var(--sans);
padding-block:28px 48px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
main{max-width:1040px;margin:0 auto;display:grid;gap:22px}
h1{font:600 30px/1.2 var(--serif);margin:4px 0 14px;text-wrap:balance}
h2{font:600 20px/1.3 var(--serif);margin:0 0 6px}
h3{font:600 15px/1.3 var(--sans);margin:18px 0 6px}
p{margin:6px 0;max-width:72ch}
.kicker{font:600 12px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--dim);margin:0}
.lede{color:var(--ink2);margin-bottom:12px}
.dim{color:var(--dim);font-size:13px}
header,section{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:20px 22px}
.meta{display:flex;flex-wrap:wrap;gap:6px 22px;margin:0 0 10px}
.meta div{display:flex;flex-direction:column;min-width:0}
.meta dt{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--dim)}
.meta dd{margin:0;font-weight:500;font-family:var(--mono);font-size:13px}
.verdict{display:flex;flex-wrap:wrap;align-items:center;gap:14px;margin-top:10px}
.badge{display:inline-block;padding:4px 12px;border-radius:999px;font:600 13px var(--sans);
letter-spacing:.04em;text-transform:uppercase;color:#fff;background:var(--dim)}
.badge.approve{background:var(--approve)}.badge.revise{background:var(--revise)}.badge.reject{background:var(--reject)}
.score{font:400 18px var(--serif)}.score b{font-size:30px}
.reason{color:var(--ink2)}
.error{color:var(--reject);font-weight:600}
.plain{list-style:none;padding:0;margin:12px 0 0;color:var(--ink2);font-size:14px}
.judges{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:14px}
.judge{border:1px solid var(--line);border-radius:10px;padding:14px;background:var(--paper);min-width:0}
.who{display:flex;gap:10px;align-items:center;margin-bottom:10px}.who small{display:block;color:var(--dim);font-size:12px}
.alias{width:32px;height:32px;border-radius:50%;background:var(--accent);color:#fff;font:600 14px var(--mono);
display:inline-flex;align-items:center;justify-content:center;flex:none}
.move{display:flex;align-items:baseline;gap:8px;font:400 22px var(--serif)}
.move .delta{font:500 13px var(--mono);color:var(--accent)}
.arrow{color:var(--dim)}
.recs{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:6px 0 10px;font-size:13px}
.rec{font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.05em}
.rec.approve{color:var(--approve)}.rec.revise{color:var(--revise)}.rec.reject{color:var(--reject)}
blockquote{margin:8px 0;padding:8px 12px;border-left:3px solid var(--accent);background:var(--surface);
font-size:13.5px;color:var(--ink2);border-radius:0 8px 8px 0}
blockquote .dim{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px}
details{margin-top:8px}summary{cursor:pointer;color:var(--accent);font-size:13.5px}
details p{font-size:13.5px}
.rubric{border-collapse:collapse;font-size:13px;margin:6px 0}.rubric td{padding:2px 10px 2px 0;border-bottom:1px solid var(--line)}
.sum{font-family:var(--mono);font-size:12.5px;color:var(--ink2);word-break:break-word}
.tracks{position:relative;display:grid;gap:10px;margin:14px 0 4px}
.row{display:grid;grid-template-columns:minmax(90px,180px) 1fr;align-items:center;gap:12px}
.row .label{font-size:13px;color:var(--ink2);text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.track{position:relative;height:18px;border-bottom:1px solid var(--line)}
.axis .track{border:0;height:16px}.tick{position:absolute;transform:translateX(-50%);font-size:11px;color:var(--dim);font-family:var(--mono)}
.span{position:absolute;top:8px;height:2px;background:var(--accent);opacity:.45}
.dot{position:absolute;top:4px;width:10px;height:10px;border-radius:50%;transform:translateX(-50%);border:2px solid var(--accent);background:var(--surface)}
.dot.last{background:var(--accent)}
.legend .dot,.legend .key{position:static;display:inline-block;transform:none;vertical-align:middle;margin:0 4px 0 10px}
.key{width:2px;height:14px;background:var(--accent)}.key.approve{background:var(--approve)}
.guides{position:absolute;left:calc(min(180px,100% * .22) + 12px);right:0;top:0;bottom:26px;pointer-events:none}
.guide{position:absolute;top:0;bottom:0;width:2px;transform:translateX(-50%)}
.guide.consensus{background:var(--accent)}.guide.approve{background:var(--approve);opacity:.6}
.legend{font-size:12.5px;color:var(--dim);margin-top:4px}
@media (max-width:560px){.row{grid-template-columns:minmax(70px,110px) 1fr}.guides{left:calc(min(110px,100% * .3) + 12px)}}
.finding{margin:0;border-top:1px solid var(--line);padding:8px 0}
.finding summary{display:flex;flex-wrap:wrap;align-items:center;gap:8px;color:var(--ink);font-size:14px;list-style:none}
.finding summary::-webkit-details-marker{display:none}
.finding .n{font-family:var(--mono);color:var(--dim);font-size:12px;min-width:22px}
.finding .title{flex:1 1 320px;min-width:0}
.finding .support{font-family:var(--mono);font-size:12px;color:var(--dim)}
.finding .body{padding:4px 0 2px 30px}
.tag{display:inline-block;font:600 10.5px var(--sans);letter-spacing:.05em;text-transform:uppercase;padding:2px 7px;border-radius:999px;
background:var(--soft);color:var(--ink2)}
.tag.blocker{background:var(--reject);color:#fff}.tag.major{background:var(--revise);color:#fff}
.tag.fix{background:var(--approve);color:#fff}.tag.link{border:1px solid var(--accent);color:var(--accent);background:transparent}
.bars{display:grid;gap:6px;max-width:560px}.bar{position:relative;height:14px;background:var(--soft);border-radius:4px;overflow:hidden}
.bar span{position:absolute;left:0;top:0;bottom:0;background:var(--accent);border-radius:4px}.bar .neg{background:var(--reject)}
.bars .row{grid-template-columns:minmax(90px,180px) 1fr 60px}.val{font-family:var(--mono);font-size:12.5px;color:var(--ink2)}
.fixes{padding-left:22px;margin:4px 0 10px}.fixes li{margin:3px 0;font-size:14px}
.offers{display:grid;gap:10px}.offer{border-left:3px solid var(--line);padding:2px 12px;font-size:13.5px}
.offer p{margin:4px 0 0;color:var(--ink2)}
ol{padding-left:22px}
.result{margin-top:10px}
pre{white-space:pre-wrap;word-break:break-word;font:12.5px/1.5 var(--mono);background:var(--paper);border:1px solid var(--line);
border-radius:8px;padding:12px;max-height:420px;overflow:auto}
code{font-family:var(--mono);font-size:.92em}
footer{color:var(--dim);font-size:12.5px;text-align:center}
h2.round{font-size:17px;color:var(--dim);margin:8px 0 -8px;text-transform:uppercase;letter-spacing:.06em;font-family:var(--sans)}
"""


def render(run: dict) -> str:
    """The whole page as one HTML string."""
    rounds = run.get("rounds") or []
    last = rounds[-1] if rounds else {}
    result = run.get("result") or last.get("vote")
    many = run.get("mode") == "generate" and len(rounds) > 1
    body = [_head(run, last, result)]
    if many:
        body.append(f'<section><h2>Convergence</h2>{_convergence_lines(run)}</section>')
    for rec in rounds:
        body.append(_round(run, rec, many))
    if run.get("failures"):
        body.append(f'<section><h2>Failures</h2><p>Judge calls that failed: {len(run["failures"])}. '
                    'A Judge that failed the Jury kept its last verdict.</p></section>')
    body.append(f'<section><h2>The subject</h2>{_subject(run)}</section>')
    body.append(f'<footer><p>Rendered from run record {esc(run["id"])} by <code>jjv render</code>, '
                f'with no model call. {esc(DATA_NOTE)}</p></footer>')
    title = title_of(run.get("subject", ""))
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">"
            f"<title>{esc(title)} · JJV run {esc(run['id'])}</title><style>{CSS}</style></head>"
            f"<body><main>{''.join(body)}</main></body></html>\n")
