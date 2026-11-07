"""Turning a link into text. No network: urlopen is replaced."""

import io
import urllib.error
from email.message import Message

import pytest

from jjv import cli, fetch, parse
from jjv.fetch import FetchError, fetch_text, html_to_text, read_html


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


def test_old_mathjax_scripts_keep_their_latex():
    page = read_html('<p>energy <script type="math/tex">E = mc^2</script> here</p>'
                     '<script>evil()</script>')
    assert page.text == "energy E = mc^2 here" and page.formulas == 1


def test_mathml_uses_its_tex_annotation_and_not_the_symbols():
    html = """<p>so <math><semantics><mrow><mi>x</mi></mrow>
        <annotation encoding="application/x-tex">x^2</annotation></semantics></math> holds</p>"""
    page = read_html(html)
    assert page.text == "so x^2 holds" and page.formulas == 1 and page.lost == 0


def test_mathml_falls_back_to_alttext():
    assert read_html('<p><math alttext="a+b"><mi>a</mi></math></p>').text == "a+b"


def test_wikipedia_keeps_tex_in_a_json_attribute():
    html = """<p>so <math data-mw='{"name":"math","body":{"extsrc":"E \\\\geq k T"}}'><mi>E</mi></math></p>"""
    assert read_html(html).text == "so E \\geq k T"


def test_katex_is_read_once():
    html = """<p>Let <span class="katex"><span class="katex-mathml"><math><semantics><mrow/>
        <annotation encoding="application/x-tex">\\pi r^2</annotation></semantics></math></span>
        <span class="katex-html" aria-hidden="true"><span>πr2</span></span></span> be area</p>"""
    page = read_html(html)
    assert "\\pi r^2" in page.text and "πr2" not in page.text and page.formulas == 1


def test_wikipedia_style_math_is_read_once():
    html = """<p><span class="mwe-math-element"><math alttext="{\\displaystyle x}"><mi>x</mi></math>
        <img class="mwe-math-fallback-image-inline" alt="{\\displaystyle x}" src="a.svg"></span></p>"""
    page = read_html(html)
    assert page.text.count("displaystyle") == 1 and page.formulas == 1


def test_formula_images_without_text_are_counted_as_lost():
    page = read_html('<p>at least <img class="ql-img-inline-formula" src="f.png"> of energy</p>')
    assert page.lost == 1 and "[formula not readable]" in page.text
    assert "1 of 1 formulas" in page.math_warning()


def test_mathml_with_no_tex_is_lost_not_garbled():
    page = read_html("<p><math><mi>x</mi><mo>+</mo></math></p>")
    assert page.lost == 1 and page.text == "[formula not readable]"


def test_ordinary_images_are_not_counted_as_formulas():
    page = read_html('<p><img src="cat.png" alt="a cat"></p>')
    assert page.text == "a cat" and page.formulas == 0 and page.math_warning() is None


def test_a_page_drawing_math_with_javascript_is_flagged():
    page = read_html('<script src="mathjax.js"></script><p>the sum of the terms</p>')
    assert "JavaScript" in page.math_warning()
    typed = read_html('<script src="mathjax.js"></script><p>so \\(x^2\\) holds</p>')
    assert typed.math_warning() is None


def test_cli_stops_before_spending_when_math_is_lost(monkeypatch, capsys):
    serve(monkeypatch, Page(b'<p>word <img class="latex" src="a.png"> word</p>'))
    assert cli.main(["review", "--url", "https://x.test/a", "--panel", "Docs Crit"]) == 2
    err = capsys.readouterr().err
    assert "Nothing was spent" in err and "--allow-lost-math" in err


def test_judges_are_told_broken_text_may_be_extraction():
    from jjv.orchestrator import judge_prompt
    from jjv.registry import get
    assert "fault\nin extraction" in judge_prompt(get("simplifier"), "s", "t", False)


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


def test_a_pdf_link_goes_to_the_parser(monkeypatch):
    serve(monkeypatch, Page(b"%PDF", "application/pdf"))
    seen = []

    def convert(data, suffix, name):
        seen.append((data, suffix))
        return parse.to_page("the text", name)
    monkeypatch.setattr(parse, "parse_bytes", convert)
    assert fetch_text("https://x.test/a") == "the text"
    assert seen == [(b"%PDF", ".pdf")]


def test_other_binary_links_are_refused(monkeypatch):
    serve(monkeypatch, Page(b"PK", "application/zip"))
    with pytest.raises(FetchError, match="application/zip"):
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


def test_a_parsed_document_reports_its_formulas():
    page = parse.to_page("Intro\n\n$$x^2$$\n\n<!-- formula-not-decoded -->", "a.pdf")
    assert page.formulas == 2 and page.lost == 1
    assert "[formula not readable]" in page.text and "may contain small errors" in page.note
    assert "1 of 2 formulas" in page.math_warning()


def test_a_document_with_no_math_has_no_warning():
    page = parse.to_page("Just words", "a.docx")
    assert page.note is None and page.math_warning() is None


def test_an_empty_parse_is_an_error_not_a_blank_review():
    with pytest.raises(FetchError, match="no readable text"):
        parse.parse_file("a.pdf", convert=lambda path: "   ")


def test_only_known_document_types_go_to_the_parser():
    assert parse.can_parse("a.PDF") and parse.can_parse("b.docx")
    assert not parse.can_parse("c.md") and not parse.can_parse("d.py")


def test_missing_parser_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "docling.document_converter", None)
    with pytest.raises(FetchError, match="requirements-parse.txt"):
        parse._convert("a.pdf")


def test_cli_stops_before_spending_on_a_document_with_lost_math(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "parse_file",
                        lambda path: parse.to_page("words <!-- formula-not-decoded -->", path))
    path = tmp_path / "a.pdf"
    path.write_bytes(b"x")
    assert cli.main(["review", str(path), "--panel", "Docs Crit"]) == 2
    assert "Nothing was spent" in capsys.readouterr().err
