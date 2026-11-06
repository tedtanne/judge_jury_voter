"""Fetch a web page as plain text, so a link can be reviewed like a file.

Standard library only. The text is untrusted: it reaches Judges as the subject, inside the
same fence as any other subject.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlparse

MAX_BYTES = 5_000_000
TIMEOUT_S = 30
_SKIP = {"script", "style", "noscript", "template", "svg", "nav", "footer", "form", "aside"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
         "source", "track", "wbr"}
_BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
          "pre", "section", "article", "header", "table", "ul", "ol"}


_REPLIES = {"comments", "comment-list", "comments-area", "respond", "comment-respond", "disqus_thread"}


class FetchError(RuntimeError):
    """The link could not be turned into text to review."""


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            if self.skipping:
                return
            if tag == "br":
                self.parts.append("\n")
            elif tag == "img" and dict(attrs).get("alt"):
                # Equations are often images, with the LaTeX in alt. Dropping it garbles
                # the sentence, and Judges then report the gap as a fault in the writing.
                self.parts.append(f" {dict(attrs)['alt']} ")
            return
        marks = {dict(attrs).get("id") or ""} | set((dict(attrs).get("class") or "").split())
        if tag in _SKIP or self.skipping or marks & _REPLIES:   # readers' replies are not the post
            self.skipping += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if self.skipping:
            self.skipping -= 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    """The readable text of a page, without scripts, styles, navigation or reader comments."""
    body = re.search(r"<(article|main)\b.*?</\1\s*>", html, re.S | re.I)
    parser = _Text()
    parser.feed(body.group(0) if body else html)
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def fetch_text(url: str) -> str:
    """The text at ``url``, or FetchError. Only http and https links are allowed."""
    if urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc:
        raise FetchError(f"not a web link: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "judge-jury-voter"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
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
    text = html_to_text(text) if "html" in kind else text.strip()
    if not text:
        raise FetchError(f"no readable text at {url}; it may need JavaScript or a login")
    return text
