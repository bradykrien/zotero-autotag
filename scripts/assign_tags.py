"""
assign_tags.py — assign controlled vocabulary tags to your Zotero library.

Uses sentence-transformers to compute semantic similarity between each item's
content and the approved vocabulary tags, then applies the date-horizon and
protected-tag business logic before writing back to Zotero.

TWO-STEP PROCESS (safe by default):

  Step 1 — Dry run (default, no Zotero writes):
      python scripts/assign_tags.py

  This computes tag assignments for all items and saves a preview file at
  data/cache/tag_assignments.json. Open it to inspect what would be written.
  Use --limit to test on a small sample first:
      python scripts/assign_tags.py --limit 20

  Step 2 — Apply (writes to Zotero):
      python scripts/assign_tags.py --apply

  Reads the saved preview and writes tags to Zotero. You will be asked to
  confirm before any writes happen. Run the dry run first.
"""

import sys
from collections import Counter
from pathlib import Path

# ── Path fix ──────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from zotero_autotag.config import load_config
from zotero_autotag.tag_assigner import TagAssigner, save_assignments, load_assignments
from zotero_autotag.vocab_generator import load_proposals_with_descriptions
from zotero_autotag.zotero_connector import ZoteroConnector, load_cache

PROJECT_ROOT = Path(__file__).parent.parent
ITEMS_WITH_TEXT = PROJECT_ROOT / "data" / "cache" / "items_with_text.json"
ITEMS_CACHE     = PROJECT_ROOT / "data" / "cache" / "items.json"
VOCAB_FILE      = PROJECT_ROOT / "data" / "vocab_proposals.yaml"
ASSIGNMENTS_OUT = PROJECT_ROOT / "data" / "cache" / "tag_assignments.json"


def main(apply: bool = False, limit: int | None = None) -> None:
    print("Zotero Autotag — Assign Tags")
    print("=" * 52)

    # ── Load config ───────────────────────────────────────────────────────────
    try:
        config = load_config()
        print(f"[OK] Config loaded")
        print(f"     threshold={config['pipeline']['similarity_threshold']}  "
              f"max_tags={config['pipeline']['max_tags_per_item']}  "
              f"horizon={config['pipeline']['date_horizon_days']}d")
    except FileNotFoundError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    # ── Apply mode: read saved assignments and write to Zotero ────────────────
    if apply:
        _run_apply(config)
        return

    # ── Dry-run mode: compute assignments and save preview ────────────────────
    _run_dry_run(config, limit)


def _run_dry_run(config: dict, limit: int | None) -> None:
    """Compute tag assignments and save to data/cache/tag_assignments.json."""

    # ── Load items ────────────────────────────────────────────────────────────
    cache_path = ITEMS_WITH_TEXT if ITEMS_WITH_TEXT.exists() else ITEMS_CACHE
    try:
        items = load_cache(cache_path)
    except FileNotFoundError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    if limit:
        items = items[:limit]
        print(f"  [--limit] Processing first {limit} items only")

    # ── Load vocabulary ───────────────────────────────────────────────────────
    try:
        vocabulary, descriptions = load_proposals_with_descriptions(VOCAB_FILE)
        n_desc = sum(1 for t in vocabulary if t in descriptions)
        print(f"[OK] Vocabulary loaded ({len(vocabulary)} tags, "
              f"{n_desc} with descriptions)")
    except FileNotFoundError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    # ── Library snapshot ──────────────────────────────────────────────────────
    print(f"\n── Library snapshot ─────────────────────────────────")
    print(f"  Items to process : {len(items)}")
    print(f"  With PDF text    : {sum(1 for i in items if i.get('pdf_text'))}")
    protected = set(config["pipeline"].get("protected_tags", []))
    n_protected = sum(
        1 for i in items if any(t in protected for t in i.get("tags", []))
    )
    print(f"  Have protected tag : {n_protected}  "
          f"({', '.join(sorted(protected))} preserved but not added/removed)")

    # ── Run tag assignment ────────────────────────────────────────────────────
    print(f"\n── Computing tag assignments ─────────────────────────")
    assigner = TagAssigner(config)
    assignments = assigner.assign(items, vocabulary, descriptions=descriptions)

    # ── Save preview ──────────────────────────────────────────────────────────
    print(f"\n── Saving preview ───────────────────────────────────")
    save_assignments(assignments, ASSIGNMENTS_OUT)

    # ── Summary ───────────────────────────────────────────────────────────────
    _print_summary(assignments, vocabulary)

    print("\n" + "=" * 52)
    print("Dry run complete. Next steps:")
    print(f"  1. Inspect data/cache/tag_assignments.json")
    print(f"     Check a few items — do the proposed tags look right?")
    print(f"     If the threshold is too low/high, adjust 'similarity_threshold'")
    print(f"     in config/settings.yaml and re-run.")
    print(f"  2. When satisfied: python scripts/assign_tags.py --apply")


def _run_apply(config: dict) -> None:
    """Read saved assignments and write to Zotero after user confirmation."""

    # ── Load saved assignments ────────────────────────────────────────────────
    try:
        assignments = load_assignments(ASSIGNMENTS_OUT)
    except FileNotFoundError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    # ── Show summary before confirming ────────────────────────────────────────
    _print_summary(assignments, vocabulary=None)

    to_write = [a for a in assignments if a["status"] != "skipped"]
    print(f"\n  This will write to Zotero for {len(to_write)} items.")
    print(f"  Estimated time: ~{len(to_write) // 2} seconds (0.5s/item rate limit)")

    # ── Confirmation prompt ───────────────────────────────────────────────────
    print()
    answer = input('  Type "yes" to proceed, anything else to abort: ').strip().lower()
    if answer != "yes":
        print("  Aborted. No changes made.")
        sys.exit(0)

    # ── Write to Zotero ───────────────────────────────────────────────────────
    print(f"\n── Writing to Zotero ────────────────────────────────")
    try:
        connector = ZoteroConnector(config)
    except Exception as e:
        print(f"[FAIL] Could not connect to Zotero: {e}")
        sys.exit(1)

    counts = connector.write_assignments(assignments)

    # ── Final summary ─────────────────────────────────────────────────────────
    print(f"\n── Summary ──────────────────────────────────────────")
    print(f"  Written OK : {counts['success']}")
    print(f"  Failed     : {counts['failed']}")
    print(f"  Skipped    : {counts['skipped']}")
    print("\n" + "=" * 52)
    if counts["failed"] == 0:
        print("Done. Check your Zotero library to verify the tags.")
    else:
        print(f"Done with {counts['failed']} failures — check output above for details.")


def _print_summary(assignments: list[dict], vocabulary: list[str] | None) -> None:
    """Print a human-readable summary of the assignment results."""
    statuses = Counter(a["status"] for a in assignments)
    total_tags = sum(len(a["proposed_tags"]) for a in assignments)
    n_assigned = sum(1 for a in assignments if a["proposed_tags"])
    avg = total_tags / n_assigned if n_assigned else 0

    print(f"\n── Assignment summary ───────────────────────────────")
    print(f"  Skipped             : {statuses.get('skipped', 0)}")
    print(f"  Overwrite (old)     : {statuses.get('overwrite', 0)}")
    print(f"  Add-only (recent)   : {statuses.get('add_only', 0)}")
    print(f"  Avg tags assigned   : {avg:.1f}")
    print(f"  Items with no tags  : "
          f"{sum(1 for a in assignments if not a['proposed_tags'] and a['status'] != 'skipped')}")

    # Per-tag counts (how many items each tag would be assigned to)
    if vocabulary is not None:
        tag_counts = Counter(
            tag
            for a in assignments
            for tag in a["proposed_tags"]
        )
        print(f"\n── Tag coverage (proposed) ──────────────────────────")
        for tag in vocabulary:
            count = tag_counts.get(tag, 0)
            bar = "█" * min(count // 10, 30)
            print(f"  {tag:<30} {count:>4}  {bar}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Assign controlled vocabulary tags to your Zotero library."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write assignments to Zotero (default: dry run only)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Process only the first N items (useful for testing)",
    )
    args = parser.parse_args()
    main(apply=args.apply, limit=args.limit)
