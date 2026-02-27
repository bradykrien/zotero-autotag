"""
pdf_extractor.py — extract text from PDFs and enrich the items cache.

Two public functions:

  extract_text(pdf_path, max_pages)
      Opens a single PDF and returns cleaned text from its first N pages.

  enrich_items(items, attachment_map, storage_path, webdav_path, max_pages)
      Walks the items list, finds each item's PDF on disk, extracts text,
      and adds 'pdf_text' and 'pdf_text_source' fields to each item dict.

Items without a PDF get pdf_text = None, pdf_text_source = None.
Later pipeline stages treat None as a signal to fall back to title + creators.
"""

import io
import logging
import re
from pathlib import Path

from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams

# pdfminer emits a lot of low-level warnings about malformed fonts, missing
# MediaBox entries, and DRM flags. These don't affect extraction quality —
# they're quirks in how PDFs were generated. Silencing them keeps the output
# readable. Change to logging.WARNING to see them again if debugging.
logging.getLogger("pdfminer").setLevel(logging.ERROR)

# Minimum number of characters for extracted text to be considered usable.
# Below this threshold we treat the result as None — this catches scanned
# image-only PDFs that technically "parse" but return near-nothing.
MIN_TEXT_CHARS = 200


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text(pdf_path: Path, max_pages: int = 20) -> str | None:
    """
    Extract and clean text from the first max_pages pages of a PDF.

    Returns a cleaned string, or None if extraction fails or yields too
    little text to be useful (likely a scanned image-only PDF).
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return None

    try:
        output = io.StringIO()
        with open(pdf_path, "rb") as f:
            extract_text_to_fp(
                f,
                output,
                laparams=LAParams(),
                maxpages=max_pages,
            )
        raw = output.getvalue()
        text = clean_text(raw)
        # Treat near-empty extractions as failures — these are usually
        # scanned PDFs where pdfminer found no selectable text layer.
        return text if len(text) >= MIN_TEXT_CHARS else None
    except Exception:
        # PDFs can fail to parse for many reasons (encrypted, corrupted).
        # Return None and let the pipeline fall back to metadata.
        return None


def enrich_items(
    items: list[dict],
    attachment_map: dict[str, str],
    storage_path: Path | None,
    webdav_path: Path | None,
    max_pages: int = 20,
) -> list[dict]:
    """
    Add 'pdf_text' and 'pdf_text_source' fields to each item dict.

    For each item:
    1. Look up its attachment key in attachment_map
    2. Search for a PDF at storage_path/<attachment_key>/*.pdf  (source: "local")
    3. If not found locally, try webdav_path/<attachment_key>/*.pdf  (source: "webdav")
    4. Extract and clean text from the first max_pages pages
    5. Set pdf_text = text (or None), pdf_text_source = "local"/"webdav"/None

    Returns the same list with both fields added in place.
    """
    storage_path = Path(storage_path) if storage_path else None
    webdav_path = Path(webdav_path) if webdav_path else None

    counts = {"local": 0, "webdav": 0, "none": 0}

    for i, item in enumerate(items):
        key = item["key"]
        attachment_key = attachment_map.get(key)

        pdf_path, source = None, None
        if attachment_key:
            pdf_path, source = _find_pdf(attachment_key, storage_path, webdav_path)

        if pdf_path:
            item["pdf_text"] = extract_text(pdf_path, max_pages)
            item["pdf_text_source"] = source
            counts[source] += 1
        else:
            item["pdf_text"] = None
            item["pdf_text_source"] = None
            counts["none"] += 1

        # Progress report every 100 items so the user knows it's still running
        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{len(items)} items...")

    print(f"  PDF found (local)  : {counts['local']}")
    print(f"  PDF found (webdav) : {counts['webdav']}")
    print(f"  No PDF found       : {counts['none']}")
    return items


def clean_text(text: str) -> str:
    """
    Normalize raw pdfminer output for downstream use.

    pdfminer output commonly has two problems:
    1. Hyphenated line-breaks: "pub-\\nlishing" should be "publishing"
    2. Excessive whitespace from column layouts and page margins

    We fix these while preserving paragraph structure (double newlines).
    """
    # Rejoin words broken with a hyphen at the end of a line
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
    # Collapse runs of spaces/tabs to a single space
    text = re.sub(r'[ \t]+', ' ', text)
    # Collapse more than two consecutive newlines to two (preserve paragraphs)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _find_pdf(
    attachment_key: str,
    storage_path: Path | None,
    webdav_path: Path | None,
) -> tuple[Path | None, str | None]:
    """
    Search for a PDF in the attachment's storage folder.

    Zotero stores attachments in a flat directory structure:
        <storage_root>/<attachment_key>/<filename>.pdf

    Checks local storage first (faster), then WebDAV.
    Returns (pdf_path, source) where source is "local" or "webdav",
    or (None, None) if not found in either location.
    """
    sources = []
    if storage_path:
        sources.append((storage_path, "local"))
    if webdav_path:
        sources.append((webdav_path, "webdav"))

    for base, source in sources:
        folder = base / attachment_key
        if not folder.exists():
            continue
        pdfs = list(folder.glob("*.pdf"))
        if pdfs:
            return pdfs[0], source

    return None, None
