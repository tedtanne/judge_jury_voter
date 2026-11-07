"""Fetch a web page as plain text, so a link can be reviewed like a file.

Standard library only. The text is untrusted: it reaches Judges as the subject, inside the
same fence as any other subject.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

MAX_BYTES = 5_000_000
TIMEOUT_S = 30
_SKIP = {"script", "style", "noscript", "template", "svg", "nav", "footer", "form", "aside"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
         "source", "track", "wbr"}
_MATH_IMAGE = {"latex", "tex", "ql-img-inline-formula", "ql-img-displayed-equation", "wp-latex"}
_DUPLICATE = {"katex-html", "mwe-math-fallback-image-inline",
              "mwe-math-fallback-image-display", "MathJax_Preview"}
_BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
          "pre", "section", "article", "header", "table", "ul", "ol"}


_REPLIES = {"comments", "comment-list", "comments-area", "respond", "comment-respond", "disqus_thread"}


class FetchError(RuntimeError):
    """The link could not be turned into text to review."""


def _wiki_tex(values: dict) -> str:
    """Wikipedia keeps a formula's source in a JSON attribute on its <math> tag."""
    try:
        return str(json.loads(values.get("data-mw") or "{}")["body"]["extsrc"])
    except (ValueError, KeyError, TypeError):
        return ""


class _Text(HTMLParser):
    """Readable text, keeping each formula as LaTeX where the page provides it.

    Formulas arrive in several shapes: images with LaTeX in ``alt``, MathML with a TeX
    annotation or ``alttext``, and old MathJax ``math/tex`` scripts. KaTeX and Wikipedia add a
    visual copy beside the real one, which is skipped so a formula is not read twice.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0
        self.formulas = 0
        self.lost = 0
        self.math_alt: str | None = None     # set while inside <math>
        self.math_tex = ""
        self.in_tex = False
        self.tex_script = False

    def _formula(self, tex: str | None) -> None:
        self.formulas += 1
        if tex and tex.strip():
            self.parts.append(f" {tex.strip()} ")
        else:
            self.lost += 1
            self.parts.append(" [formula not readable] ")

    def _img(self, values: dict, classes: set) -> None:
        drawn = bool(classes & _MATH_IMAGE) or any(
            mark in (values.get("src") or "") for mark in ("quicklatex", "latex.php", "mathtex"))
        if classes & _DUPLICATE:
            return
        if drawn:
            self._formula(values.get("alt"))
        elif values.get("alt"):
            self.parts.append(f" {values['alt']} ")

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if self.math_alt is not None:
            if tag == "annotation" and "tex" in (values.get("encoding") or "").lower():
                self.in_tex = True
            return
        if tag in _VOID:
            if self.skipping:
                return
            if tag == "br":
                self.parts.append("\n")
            elif tag == "img":
                self._img(values, classes)
            return
        if not self.skipping and tag == "math":
            self.math_alt, self.math_tex = values.get("alttext") or _wiki_tex(values), ""
            return
        if not self.skipping and tag == "script" and (
                values.get("type") or "").startswith("math/tex"):
            self.tex_script = True
            return
        marks = {values.get("id") or ""} | classes
        if tag in _SKIP or self.skipping or marks & _REPLIES or classes & _DUPLICATE:
            self.skipping += 1                 # readers' replies are not the post
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.math_alt is not None:
            if tag == "annotation":
                self.in_tex = False
            elif tag == "math":
                self._formula(self.math_tex or self.math_alt)
                self.math_alt = None
            return
        if self.tex_script:
            self.tex_script = False
            return
        if tag in _VOID:
            return
        if self.skipping:
            self.skipping -= 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.math_alt is not None:
            if self.in_tex:
                self.math_tex += data
        elif self.tex_script:
            self._formula(data)
        elif not self.skipping:
            self.parts.append(data)


@dataclass
class Page:
    text: str
    formulas: int = 0
    lost: int = 0
    needs_scripts: bool = False

    def math_warning(self) -> str | None:
        if self.lost:
            return (f"{self.lost} of {self.formulas} formulas could not be read, so Judges "
                    "would see gaps in the math.")
        if self.needs_scripts and not self.formulas:
            return ("This page draws its math with JavaScript and no formulas were found, so "
                    "Judges may see gaps in the math.")
        return None


def read_html(html: str) -> Page:
    """The readable text of a page, without scripts, styles, navigation or reader comments."""
    body = re.search(r"<(article|main)\b.*?</\1\s*>", html, re.S | re.I)
    parser = _Text()
    parser.feed(body.group(0) if body else html)
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    typed = re.search(r"\\\(|\\\[|\$\$", text) is not None
    drawn = re.search(r"mathjax|katex", html, re.I) is not None
    return Page(text, parser.formulas, parser.lost, drawn and not typed)


def html_to_text(html: str) -> str:
    return read_html(html).text


def require_public(url: str) -> None:
    """Refuse a link that points at this machine or a private network."""
    host = urlparse(url).hostname or ""
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError as e:
        raise FetchError(f"cannot find {host}: {e}") from e
    for address in addresses:
        if not ipaddress.ip_address(address.split("%")[0]).is_global:
            raise FetchError(f"not a public address: {host}")


class _PublicRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_text(url: str, public_only: bool = False) -> str:
    return fetch_page(url, public_only).text


def fetch_page(url: str, public_only: bool = False) -> Page:
    """The page at ``url``, or FetchError. Only http and https links are allowed.

    ``public_only`` is for a link that came from an AI client rather than a person, so a
    steered client cannot read this machine's own services. A name that changes address
    between the check and the fetch can still get past it.
    """
    if urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc:
        raise FetchError(f"not a web link: {url}")
    if public_only:
        require_public(url)
    opener = (urllib.request.build_opener(_PublicRedirects).open if public_only
              else urllib.request.urlopen)
    request = urllib.request.Request(url, headers={"User-Agent": "judge-jury-voter"})
    try:
        with opener(request, timeout=TIMEOUT_S) as response:
            if urlparse(response.geturl()).scheme not in ("http", "https"):
                raise FetchError(f"link redirected away from the web: {response.geturl()}")
            kind = response.headers.get_content_type()
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read(MAX_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise FetchError(f"cannot fetch {url}: {e}") from e
    if len(raw) > MAX_BYTES:
        raise FetchError(f"page is larger than {MAX_BYTES:,} bytes: {url}")
    if kind not in ("text/html", "application/xhtml+xml") and not kind.startswith("text/"):
        raise FetchError(f"cannot review content of type {kind}: {url}")
    try:
        text = raw.decode(charset, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    page = read_html(text) if "html" in kind else Page(text.strip())
    if not page.text:
        raise FetchError(f"no readable text at {url}; it may need JavaScript or a login")
    return page
