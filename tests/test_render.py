"""The run viewer: one static page from a saved record, with the same sums as --explain."""

import json

import pytest

from jjv import cli
from jjv.render import render, title_of
from jjv.orchestrator import convene
from tests.test_orchestrator import Fake, finding, reply_for, review

PANEL = convene(None, ["staff_engineer", "security_reviewer", "product_lead"], None)


def changing_mind(kind, aid, req):
    if kind == "judge":
        return reply_for(aid, score=4, rec="approve",
                         findings=[finding("Secrets in the <b>log</b>", "major", "AuthZ & secrets")])
    return {**reply_for(aid, score=3, rec="revise",
                        findings=[finding("Secrets in the <b>log</b>", "major", "AuthZ & secrets")]),
            "changed_mind": "Judge B's finding showed the log line leaks the token.",
            "change_aversion": 0.4}


@pytest.fixture
def run():
    return review(Fake(changing_mind), PANEL)


def test_page_is_one_self_contained_document(run):
    page = render(run)
    assert page.startswith("<!doctype html>") and page.count("<html") == 1
    # Nothing to fetch: no scripts, stylesheets, fonts or images.
    assert "<script" not in page and "<link" not in page and "<img" not in page
    assert 'src="' not in page and "@import" not in page
    assert f"JJV run {run['id']}" in page


def test_page_shows_each_judge_moving_and_why(run):
    page = render(run)
    for name in ("Staff Engineer", "Security Reviewer", "Product Lead"):
        assert name in page
    assert "What changed its mind" in page
    assert "showed the log line leaks the token" in page
    assert 'class="rec approve"' in page and 'class="rec revise"' in page
    assert "Change aversion 0.4" in page


def test_model_text_is_escaped(run):
    page = render(run)
    assert "<b>log</b>" not in page and "&lt;b&gt;log&lt;/b&gt;" in page


def test_page_carries_the_decision_rule_and_the_consensus_sum(run):
    page = render(run)
    score = run["result"]["score"]
    assert f"= <b>{score:g}</b>" in page
    assert "A credible veto blocks approval" in page
    assert f'class="badge {run["result"]["decision"]}"' in page


def test_bargain_section_matches_the_settlement(run):
    rec = run["rounds"][-1]
    s = rec["settlement"]
    page = render(run)
    assert "The bargain" in page
    assert f"<dt>Chosen</dt><dd>{len(s['address_now'])}</dd>" in page
    assert f"<dt>Deferred</dt><dd>{len(s['deferred'])}</dd>" in page
    assert "Gain per Judge over no deal" in page


def test_a_plain_vote_says_there_was_no_bargaining():
    run = review(Fake(), PANEL, aggregator="weighted_vote")
    assert "no bargaining" in render(run)


def test_a_failed_run_still_renders():
    def bad(kind, aid, req):
        raise RuntimeError("boom")
    run = review(Fake(bad), PANEL)
    page = render(run)
    assert run["status"] == "failed" and "Stopped:" in page


def test_title_prefers_front_matter_then_first_line():
    assert title_of("---\ntitle: A plan\n---\nbody") == "A plan"
    assert title_of("# Heading\n\nbody") == "Heading"
    assert title_of("x" * 120).endswith("...")
    assert title_of("") == "Untitled"


def test_cli_renders_a_saved_run_to_a_file_or_stdout(tmp_path, capsys, run):
    store = tmp_path / "runs"
    store.mkdir()
    (store / f"{run['id']}.json").write_text(json.dumps(run))
    out = tmp_path / "run.html"
    assert cli.main(["render", run["id"], "--store", str(store), "--out", str(out)]) == 0
    assert out.read_text().startswith("<!doctype html>")
    assert cli.main(["render", run["id"], "--store", str(store)]) == 0
    assert capsys.readouterr().out.startswith("<!doctype html>")
    assert cli.main(["render", "nope", "--store", str(store)]) == 2


def test_a_judge_whose_jury_call_failed_is_marked_on_its_card():
    def jury_fails_for_one(kind, aid, req):
        if kind == "jury" and aid == "product_lead":
            raise RuntimeError("out of budget")
        return reply_for(aid)
    run = review(Fake(jury_fails_for_one), PANEL, retries=0)
    page = render(run)
    assert run["failures"] and "Its Jury call failed" in page
    assert page.count("Its Jury call failed") == 1
