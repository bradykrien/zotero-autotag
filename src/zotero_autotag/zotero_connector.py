"""
zotero_connector.py — fetch items and metadata from the Zotero Web API.

The main class is ZoteroConnector. It wraps pyzotero and returns clean,
pipeline-friendly dicts — stripping out the Zotero API noise we don't need.

Cache utilities (save_cache / load_cache) let downstream stages persist and
reload items without hitting the API again.
"""

import json
from pathlib import Path

from pyzotero import zotero


# ── Data shape ────────────────────────────────────────────────────────────────
# Each item returned by fetch_items() looks like this:
#
#   {
#     "key":              "ABCD1234",          # Zotero item key (used to write tags back)
#     "item_type":        "journalArticle",    # Zotero item type
#     "title":            "...",
#     "creators":         ["Last, First", ...],
#     "publication_date": "2021",
#     "date_added":       "2021-03-15T10:30:00Z",  # ISO 8601, used for date-horizon logic
#     "tags":             ["book history", "tbr"],  # existing tags, preserved as-is
#   }
#
# Attachment keys (for PDF lookup) are intentionally omitted here —
# that mapping is built in Phase 3 (pdf_extractor.py).


class ZoteroConnector:
    """
    Wraps the Zotero Web API and returns clean item dicts.

    Usage:
        from zotero_autotag.config import load_config
        from zotero_autotag.zotero_connector import ZoteroConnector

        config = load_config()
        connector = ZoteroConnector(config)
        items = connector.fetch_items()
    """

    def __init__(self, config: dict):
        zot_cfg = config["zotero"]
        self.zot = zotero.Zotero(
            library_id=zot_cfg["library_id"],
            library_type=zot_cfg["library_type"],
            api_key=zot_cfg["api_key"],
        )

    def fetch_items(self) -> list[dict]:
        """
        Fetch all top-level library items and return them as clean dicts.

        "Top-level" means we skip attachments and standalone notes —
        only the actual library items (articles, books, etc.) are returned.

        pyzotero's zot.everything() handles pagination automatically, so
        this works correctly even for large libraries.
        """
        print("Fetching items from Zotero API (this may take a moment)...")
        raw_items = self.zot.everything(self.zot.top())
        print(f"  Fetched {len(raw_items)} items.")

        return [self._clean_item(item) for item in raw_items]

    def fetch_attachment_map(self) -> dict[str, str]:
        """
        Return a mapping of {parent_item_key: attachment_item_key} for all
        PDF attachments in the library.

        We need this because Zotero's storage directory is keyed by attachment
        key, not parent key:
            storage/ABCD1234/paper.pdf   ← ABCD1234 is the attachment key

        This method fetches all attachment items from the API, filters to PDFs,
        and returns a dict so pdf_extractor.py can look up the right folder.
        If a parent has multiple PDF attachments, we take the first one.
        """
        print("Fetching attachment map from Zotero API...")
        raw_attachments = self.zot.everything(self.zot.items(itemType="attachment"))

        attachment_map = {}
        for att in raw_attachments:
            data = att["data"]
            if data.get("contentType") != "application/pdf":
                continue
            parent_key = data.get("parentItem")
            if not parent_key:
                continue
            # Keep only the first PDF attachment per parent
            if parent_key not in attachment_map:
                attachment_map[parent_key] = data["key"]

        print(f"  Found {len(attachment_map)} items with PDF attachments.")
        return attachment_map

    def _clean_item(self, raw: dict) -> dict:
        """
        Extract only the fields the pipeline needs from a raw pyzotero item.

        The raw pyzotero response is a deeply nested dict. All the useful
        content lives under the 'data' key — everything else (library, links,
        meta) is Zotero API bookkeeping we don't need.
        """
        data = raw["data"]
        return {
            "key": data["key"],
            "item_type": data.get("itemType", ""),
            "title": data.get("title", ""),
            "creators": _format_creators(data.get("creators", [])),
            "publication_date": data.get("date", ""),
            "date_added": data.get("dateAdded", ""),
            "tags": [t["tag"] for t in data.get("tags", [])],
        }


# ── Cache utilities ───────────────────────────────────────────────────────────
# These are module-level functions (not methods) because they don't need the
# API connection — they just read/write JSON on disk.

def save_cache(items: list[dict], path: Path) -> None:
    """
    Write items to a JSON cache file on disk.

    Creates parent directories if they don't exist.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    print(f"  Cache saved to {path} ({len(items)} items)")


def load_cache(path: Path) -> list[dict]:
    """
    Load items from a JSON cache file.

    Raises FileNotFoundError if the cache doesn't exist yet.
    Use this to skip the API fetch during development.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"\n\nCache file not found: {path}\n"
            f"Run 'python scripts/fetch_items.py' to populate it.\n"
        )
    with open(path) as f:
        items = json.load(f)
    print(f"  Loaded {len(items)} items from cache ({path})")
    return items


# ── Internal helpers ──────────────────────────────────────────────────────────

def _format_creators(creators: list[dict]) -> list[str]:
    """
    Convert Zotero creator dicts to plain strings.

    Zotero stores creators as dicts like:
        {"creatorType": "author", "firstName": "Jane", "lastName": "Smith"}
    or for single-field entries:
        {"creatorType": "author", "name": "World Health Organization"}

    We convert these to "Last, First" or just "Name" strings.
    """
    result = []
    for c in creators:
        if "lastName" in c:
            first = c.get("firstName", "")
            last = c["lastName"]
            result.append(f"{last}, {first}".strip(", "))
        elif "name" in c:
            result.append(c["name"])
    return result
