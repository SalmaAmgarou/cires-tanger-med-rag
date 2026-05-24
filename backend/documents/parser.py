"""PDF text extraction with page tracking, using PyMuPDF (fitz)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF


@dataclass
class PageText:
    page_number: int
    text: str


def extract_pages(pdf_path: Path) -> tuple[list[PageText], dict]:
    """Extract per-page text from a PDF.

    Returns:
        (pages, metadata) where metadata has title, author, subject, total_pages.
    """
    pages: list[PageText] = []
    metadata: dict = {"title": "", "author": "", "subject": "", "total_pages": 0}

    with fitz.open(pdf_path) as doc:
        md = doc.metadata or {}
        metadata = {
            "title": (md.get("title") or "").strip(),
            "author": (md.get("author") or "").strip(),
            "subject": (md.get("subject") or "").strip(),
            "total_pages": doc.page_count,
        }
        for i, page in enumerate(doc, 1):
            text = (page.get_text("text") or "").strip()
            if text:
                pages.append(PageText(page_number=i, text=text))

    return pages, metadata


_FR_MARKERS = (
    "é", "è", "ê", "à", "ô", "ç",
    " le ", " la ", " les ", " des ", " du ", " et ",
    " qui ", " que ", " pour ", " dans ", " avec ",
)
_EN_MARKERS = (
    " the ", " of ", " and ", " to ", " in ", " is ",
    " for ", " on ", " with ", " by ", " that ",
)


def detect_language(text: str) -> str:
    """Quick FR vs EN detection via marker counts."""
    sample = (text or "")[:3000].lower()
    fr_score = sum(1 for m in _FR_MARKERS if m in sample)
    en_score = sum(1 for m in _EN_MARKERS if m in sample)
    return "fr" if fr_score >= en_score else "en"
