"""
extract_text.py — enrich the items cache with PDF full text.

Reads items.json, fetches the attachment key map from the Zotero API,
extracts text from each item's PDF (up to max_pages), and writes the
result to data/cache/items_with_text.json.

Supports resuming interrupted runs: if items_with_text.json already exists,
already-processed items are skipped and new results are merged in. This means
if the run dies partway through, just re-run and it picks up where it left off.

Run after fetch_items.py:
    python scripts/extract_text.py

Options:
    --refresh    Re-fetch the attachment map from the API and reprocess all items
"""

import argparse
import json
import sys
from pathlib import Path

# ── Path fix ──────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from zotero_autotag.config import load_config
from zotero_autotag.zotero_connector import ZoteroConnector, load_cache, save_cache
from zotero_autotag.pdf_extractor import enrich_items

PROJECT_ROOT = Path(__file__).parent.parent
ITEMS_CACHE = PROJECT_ROOT / "data" / "cache" / "items.json"
ATTACHMENT_MAP_CACHE = PROJECT_ROOT / "data" / "cache" / "attachment_map.json"
OUTPUT_CACHE = PROJECT_ROOT / "data" / "cache" / "items_with_text.json"

# Save a checkpoint to disk every this many newly processed items.
CHECKPOINT_EVERY = 100


def main(refresh: bool = False) -> None:
    print("Zotero Autotag — Extract PDF Text")
    print("=" * 52)

    # ── Load config ───────────────────────────────────────────────────────────
    try:
        config = load_config()
        max_pages = config.get("pdf", {}).get("max_pages", 20)
        print(f"[OK] Config loaded (max_pages={max_pages})")
    except FileNotFoundError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    # ── Load items from Phase 2 cache ─────────────────────────────────────────
    try:
        all_items = load_cache(ITEMS_CACHE)
    except FileNotFoundError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    # ── Load any previously processed items (for resumability) ───────────────
    # We key the processed dict by item key so we can quickly look up whether
    # an item has already been enriched. Items are marked done if they have the
    # 'pdf_text' key, even when its value is None (None = no PDF, still done).
    processed: dict[str, dict] = {}
    if not refresh and OUTPUT_CACHE.exists():
        try:
            existing = load_cache(OUTPUT_CACHE)
            processed = {
                item["key"]: item
                for item in existing
                if "pdf_text" in item
            }
            print(f"  Resuming: {len(processed)} items already processed.")
        except Exception:
            print("  Could not read existing output — starting fresh.")

    todo = [item for item in all_items if item["key"] not in processed]
    print(f"  Items to process   : {len(todo)}")

    if not todo:
        print("\nAll items already processed. Use --refresh to reprocess.")
        _print_summary(list(processed.values()))
        return

    # ── Load or fetch the attachment map ──────────────────────────────────────
    if not refresh and ATTACHMENT_MAP_CACHE.exists():
        print(f"\nLoading attachment map from cache...")
        with open(ATTACHMENT_MAP_CACHE) as f:
            attachment_map = json.load(f)
        print(f"  {len(attachment_map)} PDF attachments loaded from cache.")
    else:
        label = "--refresh" if refresh else "No cache found"
        print(f"\n{label}: fetching attachment map from Zotero API...")
        try:
            connector = ZoteroConnector(config)
            attachment_map = connector.fetch_attachment_map()
            ATTACHMENT_MAP_CACHE.parent.mkdir(parents=True, exist_ok=True)
            with open(ATTACHMENT_MAP_CACHE, "w") as f:
                json.dump(attachment_map, f, indent=2)
            print(f"  Attachment map cached to {ATTACHMENT_MAP_CACHE}")
        except Exception as e:
            print(f"[FAIL] Could not fetch attachment map: {e}")
            sys.exit(1)

    # ── Resolve PDF storage paths ─────────────────────────────────────────────
    paths_cfg = config.get("paths", {})
    storage_path = paths_cfg.get("zotero_storage") or None
    webdav_path = paths_cfg.get("webdav_mount") or None

    print(f"\nPDF search paths:")
    print(f"  Local storage : {storage_path or '(not set)'}")
    print(f"  WebDAV mount  : {webdav_path or '(not set)'}")

    # ── Process in batches, saving a checkpoint after each batch ─────────────
    # This means if the run is interrupted, at most CHECKPOINT_EVERY items
    # need to be reprocessed when you resume.
    print(f"\nExtracting text (first {max_pages} pages each, "
          f"checkpoint every {CHECKPOINT_EVERY} items)...")

    for batch_start in range(0, len(todo), CHECKPOINT_EVERY):
        batch = todo[batch_start : batch_start + CHECKPOINT_EVERY]

        enriched_batch = enrich_items(
            batch,
            attachment_map=attachment_map,
            storage_path=storage_path,
            webdav_path=webdav_path,
            max_pages=max_pages,
        )

        for item in enriched_batch:
            processed[item["key"]] = item

        # Preserve original item order from all_items when saving
        ordered = [processed[item["key"]] for item in all_items if item["key"] in processed]
        save_cache(ordered, OUTPUT_CACHE)
        print(f"  Checkpoint: {len(processed)}/{len(all_items)} items saved.\n")

    # ── Final summary ─────────────────────────────────────────────────────────
    final = [processed[item["key"]] for item in all_items if item["key"] in processed]
    _print_summary(final)
    print("\n" + "=" * 52)
    print("Done. items_with_text.json is ready for the next pipeline stage.")


def _print_summary(items: list[dict]) -> None:
    local = sum(1 for i in items if i.get("pdf_text_source") == "local")
    webdav = sum(1 for i in items if i.get("pdf_text_source") == "webdav")
    no_pdf = sum(1 for i in items if i.get("pdf_text_source") is None)
    has_text = sum(1 for i in items if i.get("pdf_text"))

    print(f"\n── Summary ──────────────────────────────────────────")
    print(f"  PDF found (local)  : {local}")
    print(f"  PDF found (webdav) : {webdav}")
    print(f"  No PDF found       : {no_pdf}")
    print(f"  ─────────────────────────────")
    pdf_found = local + webdav
    scanned = max(0, pdf_found - has_text)  # PDFs opened but returned no usable text
    untracked = has_text - min(has_text, pdf_found)  # text exists but source not recorded
    note = f"scanned/image PDFs: {scanned}" if not untracked else f"source untracked (old cache): {untracked}"
    print(f"  Usable text        : {has_text}  ({note})")
    print(f"  Total              : {len(items)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich items cache with PDF text.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch the attachment map and reprocess all items from scratch.",
    )
    args = parser.parse_args()
    main(refresh=args.refresh)
