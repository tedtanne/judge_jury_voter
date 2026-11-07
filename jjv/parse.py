"""Turn a PDF, Word or PowerPoint file into text for review.

Optional, because the parser is large: ``pip install -r requirements-parse.txt``. Docling is
used for its MIT license and because it reads equations into LaTeX. It runs on this machine,
and a long paper can take a few minutes.

Formulas are read from the page image by a model, so they can contain small errors, and
inline math stays as plain text. Judges are told that broken text may be an extraction fault.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from jjv.fetch import FetchError, Page

SUFFIXES = {".pdf", ".docx", ".pptx", ".xlsx"}
UNDECODED = "<!-- formula-not-decoded -->"
NOTE = ("Formulas were read from the page image and may contain small errors. "
        "Check any formula a finding depends on.")


def can_parse(path: str) -> bool:
    return Path(path).suffix.lower() in SUFFIXES


def _convert(path: str) -> str:
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as e:
        raise FetchError("reading this file needs Docling; run "
                         "`pip install -r requirements-parse.txt`") from e
    options = PdfPipelineOptions(do_formula_enrichment=True)
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    try:
        return converter.convert(path).document.export_to_markdown()
    except Exception as e:      # the parser raises many types on a bad file
        raise FetchError(f"cannot read {Path(path).name}: {type(e).__name__}") from e


def to_page(markdown: str, name: str) -> Page:
    """Count formulas, and refuse an empty result: a blank review would look like a pass."""
    lost = markdown.count(UNDECODED)
    decoded = len(re.findall(r"\$\$.+?\$\$", markdown, re.S))
    text = markdown.replace(UNDECODED, "[formula not readable]").strip()
    if not text:
        raise FetchError(f"no readable text in {name}; it may be scanned or damaged")
    return Page(text, decoded + lost, lost, note=NOTE if decoded + lost else None)


def parse_file(path: str, convert=_convert) -> Page:
    return to_page(convert(path), Path(path).name)


def parse_bytes(data: bytes, suffix: str, name: str, convert=_convert) -> Page:
    """For a document that came from a link."""
    with tempfile.TemporaryDirectory(prefix="jjv-") as folder:
        path = Path(folder) / f"document{suffix}"
        path.write_bytes(data)
        return to_page(convert(str(path)), name)
