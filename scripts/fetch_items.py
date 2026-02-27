"""
fetch_items.py — fetch all Zotero library items and save to local cache.

Run this before the first pipeline run (or when you want fresh data):
    python scripts/fetch_items.py

By default it skips the API call if a cache already exists:
    python scripts/fetch_items.py           # use cache if it exists
    python scripts/fetch_items.py --refresh # force a fresh API fetch
"""

import argparse
import sys
from pathlib import Path

# ── Path fix ──────────────────────────────────────────────────────────────────
# Adds src/ to Python's module search path so we can import zotero_autotag.
# (Same pattern as verify_setup.py — see that file for a full explanation.)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from zotero_autotag.config import load_config
from zotero_autotag.zotero_connector import ZoteroConnector, load_cache, save_cache

# Cache lives in data/cache/ at the project root.
# This directory is git-ignored — the cache is local to each machine.
PROJECT_ROOT = Path(__file__).parent.parent
CACHE_PATH = PROJECT_ROOT / "data" / "cache" / "items.json"


def main(refresh: bool = False) -> None:
    print("Zotero Autotag — Fetch Items")
    print("=" * 52)

    # ── Load config ───────────────────────────────────────────────────────────
    try:
        config = load_config()
        print(f"[OK] Config loaded")
    except FileNotFoundError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    # ── Use cache if it exists and --refresh was not requested ────────────────
    if not refresh and CACHE_PATH.exists():
        print(f"\nCache found at {CACHE_PATH}")
        print("  Loading from cache (use --refresh to force a new API fetch)")
        try:
            items = load_cache(CACHE_PATH)
        except Exception as e:
            print(f"  [FAIL] Could not read cache: {e}")
            sys.exit(1)
    else:
        if refresh:
            print("\n--refresh flag set: fetching fresh data from Zotero API")
        else:
            print(f"\nNo cache found at {CACHE_PATH}")
            print("  Fetching from Zotero API...")

        try:
            connector = ZoteroConnector(config)
            items = connector.fetch_items()
            save_cache(items, CACHE_PATH)
        except Exception as e:
            print(f"  [FAIL] {e}")
            sys.exit(1)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n── Summary ──────────────────────────────────────────")
    print(f"  Total items : {len(items)}")

    item_types = {}
    for item in items:
        t = item.get("item_type", "unknown")
        item_types[t] = item_types.get(t, 0) + 1
    for item_type, count in sorted(item_types.items(), key=lambda x: -x[1]):
        print(f"  {item_type:<25} {count}")

    # ── Sample ────────────────────────────────────────────────────────────────
    print(f"\n── First 3 items ────────────────────────────────────")
    for item in items[:3]:
        title = item.get("title", "(no title)")[:60]
        tags = item.get("tags", [])
        date_added = item.get("date_added", "")[:10]  # just the date part
        print(f"  [{item['key']}] {title}")
        print(f"    Added: {date_added}  Tags: {tags}")

    print("\n" + "=" * 52)
    print("Done. items.json is ready for the next pipeline stage.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Zotero items to local cache.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force a fresh fetch from the Zotero API, even if cache exists.",
    )
    args = parser.parse_args()
    main(refresh=args.refresh)
