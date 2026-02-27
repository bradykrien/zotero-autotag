"""
generate_descriptions.py — use Mistral to generate tag descriptions for human review.

Reads the approved vocabulary from data/vocab_proposals.yaml, generates a
1-2 sentence description for each tag (grounded in your actual library items),
and writes the descriptions back to vocab_proposals.yaml for review.

Why: the tag assigner embeds descriptions rather than bare tag names, which
significantly improves discrimination between tags that share words (e.g.
"digital humanities" vs "environmental humanities"). This script automates
the work of writing those descriptions.

WORKFLOW:
  1. Run this script to generate/update descriptions
  2. Open data/vocab_proposals.yaml and review the descriptions — edit any
     that don't match how you use the tag in your library
  3. Re-run the dry run: python scripts/assign_tags.py
  4. Apply when satisfied: python scripts/assign_tags.py --apply

Run:
    python scripts/generate_descriptions.py              # skip tags with existing descriptions
    python scripts/generate_descriptions.py --refresh    # regenerate all descriptions

Requires Ollama to be running locally (same as generate_vocab.py).
"""

import sys
from pathlib import Path

# ── Path fix ──────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from zotero_autotag.config import load_config
from zotero_autotag.description_generator import DescriptionGenerator, update_descriptions_in_yaml
from zotero_autotag.vocab_generator import load_proposals_with_descriptions
from zotero_autotag.zotero_connector import load_cache

PROJECT_ROOT = Path(__file__).parent.parent
VOCAB_FILE   = PROJECT_ROOT / "data" / "vocab_proposals.yaml"
ITEMS_CACHE  = PROJECT_ROOT / "data" / "cache" / "items_with_text.json"
ITEMS_FALLBACK = PROJECT_ROOT / "data" / "cache" / "items.json"


def main(refresh: bool = False) -> None:
    print("Zotero Autotag — Generate Tag Descriptions")
    print("=" * 52)

    # ── Load config ───────────────────────────────────────────────────────────
    try:
        config = load_config()
        print(f"[OK] Config loaded (model: {config['model']['name']})")
    except FileNotFoundError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    # ── Load vocabulary ───────────────────────────────────────────────────────
    try:
        vocabulary, existing_descriptions = load_proposals_with_descriptions(VOCAB_FILE)
        print(f"[OK] Vocabulary loaded ({len(vocabulary)} tags, "
              f"{len(existing_descriptions)} with existing descriptions)")
    except FileNotFoundError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    # ── Load library items (for grounding context) ────────────────────────────
    items_path = ITEMS_CACHE if ITEMS_CACHE.exists() else ITEMS_FALLBACK
    try:
        items = load_cache(items_path)
        print(f"[OK] Items loaded ({len(items)} from {items_path.name})")
    except FileNotFoundError as e:
        print(f"[FAIL] Could not load items cache: {e}")
        print("       Run 'python scripts/fetch_items.py' first.")
        sys.exit(1)

    # ── Generate descriptions ─────────────────────────────────────────────────
    print(f"\n── Generating descriptions ──────────────────────────")
    if refresh:
        print("  --refresh: regenerating all descriptions from scratch")

    try:
        generator = DescriptionGenerator(config)
        descriptions = generator.generate(
            vocabulary=vocabulary,
            items=items,
            existing_descriptions=existing_descriptions,
            refresh=refresh,
        )
    except Exception as e:
        print(f"\n[FAIL] Generation failed: {e}")
        sys.exit(1)

    # ── Save back to vocab_proposals.yaml ─────────────────────────────────────
    print(f"\n── Saving to {VOCAB_FILE.name} ──────────────────────")
    update_descriptions_in_yaml(VOCAB_FILE, descriptions)

    n_new = len(descriptions) - len(existing_descriptions) if not refresh else len(descriptions)
    print(f"  [OK] {len(descriptions)} descriptions saved "
          f"({n_new} new, {len(descriptions) - n_new} unchanged)")

    # ── Print generated descriptions for immediate review ─────────────────────
    new_keys = set(descriptions) - set(existing_descriptions) if not refresh else set(descriptions)
    if new_keys:
        print(f"\n── Generated descriptions (review before using) ─────")
        for tag in sorted(new_keys):
            print(f"  {tag}:")
            print(f"    {descriptions[tag]}")

    print("\n" + "=" * 52)
    print("Done. Next steps:")
    print("  1. Review/edit descriptions in data/vocab_proposals.yaml")
    print("  2. Re-run the dry run: python scripts/assign_tags.py")
    print("  3. Apply when satisfied: python scripts/assign_tags.py --apply")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate tag descriptions using a local LLM."
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Regenerate all descriptions, even those that already exist.",
    )
    args = parser.parse_args()
    main(refresh=args.refresh)
