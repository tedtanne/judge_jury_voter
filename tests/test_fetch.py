"""Turning a link into text. No network: urlopen is replaced."""

import io
import urllib.error
from email.message import Message

import pytest

from jjv import cli, fetch
from jjv.fetch import FetchError, fetch_text, html_to_text


class Page(io.BytesIO):
    def __init__(self, body, kind="text/html; charset=utf-8", url="https://x.test/a"):
        super().__init__(body)
        self.headers = Message()
        self.headers["Content-Type"] = kind
        self.url = url

    def geturl(self):
        return self.url


def serve(monkeypatch, page):
    seen = []

    def urlopen(request, timeout):
        seen.append(request)
        if isinstance(page, Exception):
            raise page
        return page
    monkeypatch.setattr(fetch.urllib.request, "urlopen", urlopen)
    return seen


def test_html_keeps_the_writing_and_drops_the_machinery():
    text = html_to_text("""<html><head><title>t</title><style>x{}</style></head><body>
        <nav>Home</nav><script>evil()</script><h1>Joules</h1><p>One &amp; two.</p>
        <footer>Copyright</footer></body></html>""")
    assert "Joules" in text and "One & two." in text
    assert not any(w in text for w in ("Home", "evil", "Copyright", "x{}"))


def test_the_article_is_preferred_over_the_rest_of_the_page():
    text = html_to_text("<div>Sidebar</div><article><p>The post</p></article>")
    assert text == "The post"


def test_void_tags_inside_skipped_blocks_do_not_leak_text():
    assert html_to_text("<nav><img src=a><br>Menu</nav><p>Body</p>") == "Body"


def test_equations_drawn_as_images_keep_their_text():
    text = html_to_text('<p>dissipates at least <img src="f.png" alt="k_{B}T\\ln 2"> of energy</p>')
    assert text == "dissipates at least k_{B}T\\ln 2 of energy"


def test_reader_comments_are_not_part_of_the_post():
    text = html_to_text("""<article><p>The post</p><div id="comments"><div><p>A reader</p></div>
        </div></article><div class="comment-respond">Reply</div>""")
    assert text == "The post"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x.test/a", "x.test", "https://"])
def test_only_web_links_are_allowed(url):
    with pytest.raises(FetchError, match="not a web link"):
        fetch_text(url)


def test_a_page_is_fetched_with_a_generic_client_name(monkeypatch):
    seen = serve(monkeypatch, Page(b"<p>hello</p>"))
    assert fetch_text("https://x.test/a") == "hello"
    assert seen[0].get_header("User-agent") == "judge-jury-voter"


def test_plain_text_is_left_alone(monkeypatch):
    serve(monkeypatch, Page(b"<p> stays\n", "text/plain"))
    assert fetch_text("https://x.test/a") == "<p> stays"


def test_a_redirect_off_the_web_is_refused(monkeypatch):
    serve(monkeypatch, Page(b"hi", url="ftp://x.test/a"))
    with pytest.raises(FetchError, match="redirected"):
        fetch_text("https://x.test/a")


def test_a_pdf_is_refused_with_a_clear_message(monkeypatch):
    serve(monkeypatch, Page(b"%PDF", "application/pdf"))
    with pytest.raises(FetchError, match="application/pdf"):
        fetch_text("https://x.test/a")


def test_a_huge_page_is_refused(monkeypatch):
    serve(monkeypatch, Page(b"x" * (fetch.MAX_BYTES + 1)))
    with pytest.raises(FetchError, match="larger"):
        fetch_text("https://x.test/a")


def test_a_page_with_no_text_says_why(monkeypatch):
    serve(monkeypatch, Page(b"<div id=app></div><script>app()</script>"))
    with pytest.raises(FetchError, match="JavaScript"):
        fetch_text("https://x.test/a")


def test_a_network_failure_is_reported(monkeypatch):
    serve(monkeypatch, urllib.error.URLError("no route"))
    with pytest.raises(FetchError, match="cannot fetch"):
        fetch_text("https://x.test/a")


def test_cli_needs_exactly_one_source(capsys):
    assert cli.main(["review", "--panel", "Docs Crit"]) == 2
    assert cli.main(["review", "a.md", "--url", "https://x.test", "--panel", "Docs Crit"]) == 2
    assert "exactly one" in capsys.readouterr().err


def test_cli_reports_a_bad_link_before_spending(monkeypatch, capsys):
    serve(monkeypatch, urllib.error.URLError("no route"))
    assert cli.main(["review", "--url", "https://x.test/a", "--panel", "Docs Crit"]) == 2
    assert "cannot fetch" in capsys.readouterr().err


def test_status_lines_show_time_and_money(capsys):
    cli.Progress()({"type": "phase", "phase": "JURY", "cost_usd": 1.5})
    err = capsys.readouterr().err
    assert "$ 1.50" in err and "[3/4 JURY]" in err and err.startswith("00:00")


def test_failed_judges_produce_a_plain_warning():
    assert cli.failure_warning({"failures": []}) is None
    text = cli.failure_warning({"failures": [{"phase": "JURY"}, {"phase": "JURY"}]})
    assert "2 Judge call(s)" in text and "JURY" in text and "--max-usd" in text
