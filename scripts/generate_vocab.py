"""
generate_vocab.py — propose a controlled vocabulary for your Zotero library.

Uses a local LLM (Ollama) to analyze a sample of your library items and propose
50-80 controlled vocabulary tags for your review. The output is a YAML file you
can edit before Phase 5 applies any tags.

Ollama must be running before you run this script:
    ollama serve        (in a separate terminal, if not already running)

Then run:
    python scripts/generate_vocab.py

The output will be saved to data/vocab_proposals.yaml. Open it, review the
proposed tags, make any edits, and save. Phase 5 reads this file directly.
"""

import sys
from pathlib import Path

# ── Path fix ──────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from zotero_autotag.config import load_config
from zotero_autotag.zotero_connector import load_cache
from zotero_autotag.vocab_generator import VocabGenerator, save_proposals

PROJECT_ROOT = Path(__file__).parent.parent
ITEMS_WITH_TEXT = PROJECT_ROOT / "data" / "cache" / "items_with_text.json"
ITEMS_CACHE = PROJECT_ROOT / "data" / "cache" / "items.json"
VOCAB_OUTPUT = PROJECT_ROOT / "data" / "vocab_proposals.yaml"


def main() -> None:
    print("Zotero Autotag — Generate Vocabulary")
    print("=" * 52)

    # ── Load config ───────────────────────────────────────────────────────────
    try:
        config = load_config()
        model = config["model"]["name"]
        print(f"[OK] Config loaded (model: {model})")
    except FileNotFoundError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    # ── Load items — prefer enriched cache (has PDF text) ─────────────────────
    cache_path = ITEMS_WITH_TEXT if ITEMS_WITH_TEXT.exists() else ITEMS_CACHE
    try:
        items = load_cache(cache_path)
    except FileNotFoundError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    # ── Extract existing tags from the library ────────────────────────────────
    # These become the seed vocabulary — they guide the LLM's style and ensure
    # the proposed vocabulary is consistent with what already exists.
    protected_tags = set(config.get("pipeline", {}).get("protected_tags", []))
    tag_counts: dict[str, int] = {}
    for item in items:
        for tag in item.get("tags", []):
            if tag not in protected_tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # Only seed with tags that appear on at least 2 items — single-use tags
    # are likely noise or very specific labels, not controlled vocabulary
    existing_tags = sorted(t for t, count in tag_counts.items() if count >= 2)

    print(f"\n── Library snapshot ─────────────────────────────────")
    print(f"  Total items      : {len(items)}")
    print(f"  With PDF text    : {sum(1 for i in items if i.get('pdf_text'))}")
    print(f"  Existing tags    : {len(existing_tags)} (appearing on 2+ items)")
    print(f"  Seed tags        : {', '.join(existing_tags[:10])}"
          f"{'...' if len(existing_tags) > 10 else ''}")

    # ── Check Ollama is reachable ─────────────────────────────────────────────
    print(f"\n── Checking Ollama ──────────────────────────────────")
    import ollama
    try:
        client = ollama.Client(host=config["model"]["base_url"])
        client.list()  # lightweight check — lists available models
        print(f"  [OK] Ollama is running at {config['model']['base_url']}")
    except Exception as e:
        print(f"  [FAIL] Cannot reach Ollama: {e}")
        print(f"         Is Ollama running? Try: ollama serve")
        sys.exit(1)

    # ── Generate vocabulary ───────────────────────────────────────────────────
    print(f"\n── Generating vocabulary ────────────────────────────")
    generator = VocabGenerator(config)
    proposed_tags = generator.generate(items, existing_tags)

    # ── Save output ───────────────────────────────────────────────────────────
    print(f"\n── Saving proposals ─────────────────────────────────")
    save_proposals(
        proposed_tags,
        VOCAB_OUTPUT,
        metadata={
            "items_analyzed": len(items),
            "batches": VocabGenerator.NUM_BATCHES,
            "model": model,
        },
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n── Summary ──────────────────────────────────────────")
    print(f"  Proposed tags    : {len(proposed_tags)}")
    print(f"  Output file      : {VOCAB_OUTPUT}")

    print("\n" + "=" * 52)
    print("Done. Next steps:")
    print(f"  1. Open data/vocab_proposals.yaml")
    print(f"  2. Review the proposed tags — add, remove, or rename as you see fit")
    print(f"  3. Save the file when done")
    print(f"  4. Run Phase 5 to apply the vocabulary to your library")


if __name__ == "__main__":
    main()
