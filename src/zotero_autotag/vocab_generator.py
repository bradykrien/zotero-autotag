"""
vocab_generator.py — propose a controlled tag vocabulary using a local LLM.

The main class is VocabGenerator. It uses a seed-first, batch-sampling strategy:

  1. Sample the library in 8 batches of 30 items each (stratified by item type)
  2. Each batch is sent to Ollama with the existing tags as seed — asking the LLM
     to propose tags that are stylistically consistent with what already exists
  3. All candidate tags from all batches are aggregated and deduplicated
  4. A final consolidation pass asks the LLM to merge synonyms and reduce to the
     target vocabulary size (default 50–80 tags)

The output is a YAML file for human review. Nothing is written to Zotero until
the user approves the vocabulary and Phase 5 runs.

Module-level helpers:
  save_proposals(tags, path)   — write the reviewed YAML output
  load_proposals(path)         — read the approved vocabulary (used by Phase 5)
"""

import random
import re
from datetime import date
from pathlib import Path

import ollama
import yaml


# ── VocabGenerator ────────────────────────────────────────────────────────────

class VocabGenerator:
    """
    Proposes a controlled vocabulary by analyzing library items with a local LLM.

    Usage:
        from zotero_autotag.config import load_config
        from zotero_autotag.vocab_generator import VocabGenerator, save_proposals

        config = load_config()
        generator = VocabGenerator(config)
        tags = generator.generate(items, existing_tags)
        save_proposals(tags, Path("data/vocab_proposals.yaml"))
    """

    # How many items to send per LLM batch. 30 items is ~1,500 tokens of content,
    # well within Mistral's context window with room for the prompt and response.
    BATCH_SIZE = 30

    # How many batches to run. 12 × 30 = 360 item-slots, covering roughly 30% of
    # a 1,151-item library. Stratification (see _sample_batches) ensures we
    # sample proportionally across item types, not just the first 360 items.
    NUM_BATCHES = 12

    # Tags to request per batch. More than this and the LLM starts hallucinating
    # very specific tags that won't generalize across the library.
    CANDIDATES_PER_BATCH = 12

    def __init__(self, config: dict):
        self.model = config["model"]["name"]
        self.host = config["model"]["base_url"]

    def generate(
        self,
        items: list[dict],
        existing_tags: list[str],
        target_size: int = 65,
    ) -> list[str]:
        """
        Run the full vocabulary generation pipeline and return a list of tags.

        Steps:
          1. Sample items into batches (stratified by item type)
          2. Run each batch through the LLM to collect candidate tags
          3. Aggregate and deduplicate all candidates
          4. Run a consolidation pass to reach the target vocabulary size

        Returns a sorted list of proposed tags.
        """
        batches = self._sample_batches(items)
        print(f"  Running {len(batches)} batches × {self.BATCH_SIZE} items "
              f"(model: {self.model})")

        all_candidates: list[str] = list(existing_tags)  # seed with existing tags

        for i, batch in enumerate(batches):
            print(f"  Batch {i + 1}/{len(batches)}...", end=" ", flush=True)
            candidates = self._run_batch(batch, existing_tags)
            print(f"{len(candidates)} candidates")
            all_candidates.extend(candidates)

        # Deduplicate (case-insensitive) before sending to consolidation
        seen = set()
        unique_candidates = []
        for tag in all_candidates:
            key = tag.lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique_candidates.append(tag.lower().strip())

        print(f"\n  Raw candidates collected: {len(unique_candidates)}")
        print(f"  Running consolidation pass (target: {target_size} tags)...")

        final_tags = self._consolidate(unique_candidates, existing_tags, target_size)
        print(f"  Final vocabulary: {len(final_tags)} tags")
        return sorted(final_tags)

    def _sample_batches(self, items: list[dict]) -> list[list[dict]]:
        """
        Sample items into NUM_BATCHES batches of BATCH_SIZE items each.

        Stratification: we sample proportionally across item types so that
        journal articles, books, book sections, etc. are all represented in
        roughly the same ratio as they appear in the full library. This prevents
        the vocabulary from being dominated by whichever type has the most items.
        """
        # Group items by type
        by_type: dict[str, list[dict]] = {}
        for item in items:
            t = item.get("item_type", "unknown")
            by_type.setdefault(t, []).append(item)

        total_slots = self.BATCH_SIZE * self.NUM_BATCHES

        # Calculate how many slots each type gets (proportional to library share)
        type_counts = {t: len(items_of_type) for t, items_of_type in by_type.items()}
        total_items = len(items)
        type_slots = {
            t: max(1, round(count / total_items * total_slots))
            for t, count in type_counts.items()
        }

        # Sample from each type
        pool: list[dict] = []
        for t, slots in type_slots.items():
            available = by_type[t]
            sampled = random.sample(available, min(slots, len(available)))
            pool.extend(sampled)

        # Shuffle the pool and divide into batches
        random.shuffle(pool)
        batches = []
        for i in range(0, len(pool), self.BATCH_SIZE):
            batch = pool[i : i + self.BATCH_SIZE]
            if batch:
                batches.append(batch)

        return batches[: self.NUM_BATCHES]

    def _run_batch(self, batch: list[dict], existing_tags: list[str]) -> list[str]:
        """
        Send one batch of items to the LLM and return candidate tags.

        The prompt is designed to:
        - Ground the LLM in your specific domain
        - Show the existing tags as a style guide
        - Ask for a small number of specific, reusable tags
        - Return clean YAML so we can parse the response reliably
        """
        seed_tags_str = "\n".join(f"  - {t}" for t in sorted(existing_tags))
        items_str = "\n".join(_format_item(item) for item in batch)

        prompt = f"""You are a librarian building a controlled vocabulary for a humanities research library.

The library covers: digital humanities, print culture, American literature,
environmental humanities, and library/information science (~1,150 items total).

The library currently uses these tags as a style guide
(lowercase noun phrases, 1-4 words):
{seed_tags_str}

Here are {len(batch)} items from the library:
{items_str}

Propose {self.CANDIDATES_PER_BATCH} to {self.CANDIDATES_PER_BATCH + 3} controlled vocabulary tags
that would be useful for categorizing items in this library.
Rules:
- Lowercase noun phrases only (e.g. "book history", not "historical" or "about books")
- Broad enough to apply to multiple items, specific enough to be meaningful
- No author names, titles, or proper nouns as tags
- No tags that are just item types (e.g. not "journal article" or "book")

Return ONLY a YAML list, nothing else:
- tag one
- tag two
..."""

        try:
            client = ollama.Client(host=self.host)
            response = client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            return _parse_yaml_list(response.message.content)
        except Exception as e:
            print(f"\n  [WARN] Batch failed: {e}")
            return []

    def _consolidate(
        self,
        candidates: list[str],
        existing_tags: list[str],
        target_size: int,
    ) -> list[str]:
        """
        Ask the LLM to merge synonyms and reduce to the target vocabulary size.

        This is a single "cleanup" pass over all the raw candidates collected
        across batches. It handles things like:
          - Merging "digital humanities" and "dh" → "digital humanities"
          - Removing tags that are too similar to each other
          - Ensuring the final list is stylistically consistent
        """
        candidates_str = "\n".join(f"  - {t}" for t in candidates)
        existing_str = "\n".join(f"  - {t}" for t in sorted(existing_tags))

        min_size = max(40, target_size - 10)
        max_size = target_size + 10

        prompt = f"""You are a librarian finalizing a controlled vocabulary for a humanities research library.

The library covers: digital humanities, print culture, American literature,
environmental humanities, and library/information science (~1,150 items total).

These are the library's existing tags (must all appear in the final vocabulary):
{existing_str}

These candidate tags were proposed from analyzing a sample of the library:
{candidates_str}

Create a final controlled vocabulary of {min_size}–{max_size} tags by:
1. Including all existing tags above
2. Selecting the most useful candidates (prefer broader, reusable tags)
3. Merging synonyms or near-duplicates into the better phrasing
   (e.g. "llm" and "llms" → "llms"; "dh" and "digital humanities" → "digital humanities")
4. If the candidates don't reach {min_size} tags after merging, add new tags
   that cover important areas of the library's domains not yet represented
5. Ensuring consistent style: lowercase noun phrases, 1-4 words

Return ONLY a YAML list, nothing else:
- tag one
- tag two
..."""

        try:
            client = ollama.Client(host=self.host)
            response = client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            result = _parse_yaml_list(response.message.content)
            # If the LLM returned essentially nothing, fall back to raw candidates
            if len(result) < 10:
                print(f"  [WARN] Consolidation returned only {len(result)} tags, "
                      f"falling back to deduplicated candidates.")
                return sorted(candidates[:target_size])
            return result
        except Exception as e:
            print(f"  [WARN] Consolidation failed: {e}. Using raw candidates.")
            return sorted(candidates[:target_size])


# ── Public helpers ────────────────────────────────────────────────────────────

def save_proposals(tags: list[str], path: Path, metadata: dict | None = None) -> None:
    """
    Write the proposed vocabulary to a YAML file for human review.

    The file is human-readable and editable — the user should open it,
    review the proposed tags, add or remove entries, then save it.
    Phase 5 reads this file directly.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    meta = metadata or {}
    header_lines = [
        "# Proposed controlled vocabulary — review and edit before running Phase 5",
        f"# Generated: {date.today()}",
        f"# Items analyzed: {meta.get('items_analyzed', '?')}  "
        f"| Batches: {meta.get('batches', '?')}  "
        f"| Model: {meta.get('model', '?')}",
        "#",
        "# Instructions:",
        "#   - Add, remove, or rename any tags",
        "#   - Keep style: lowercase noun phrases (e.g. 'book history', not 'historical')",
        "#   - This file is read directly by Phase 5 — save it when done editing",
        "",
        "vocabulary:",
    ]

    tag_lines = [f"  - {tag}" for tag in sorted(tags)]

    with open(path, "w") as f:
        f.write("\n".join(header_lines) + "\n")
        f.write("\n".join(tag_lines) + "\n")

    print(f"  Proposals saved to {path} ({len(tags)} tags)")


def load_proposals(path: Path) -> list[str]:
    """
    Load the approved vocabulary from the YAML file.

    Called by Phase 5 (tag assigner) to get the vocabulary to apply.
    Raises FileNotFoundError if the file doesn't exist yet.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"\n\nvocab_proposals.yaml not found at {path}\n"
            f"Run 'python scripts/generate_vocab.py' to generate it.\n"
        )
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("vocabulary", [])


# ── Internal helpers ──────────────────────────────────────────────────────────

def _format_item(item: dict) -> str:
    """
    Produce a compact one-line summary of an item for use in LLM prompts.

    Keeps token count low while giving the LLM the signal it needs.
    PDF text is truncated to 200 chars — just enough for topical context.
    """
    title = item.get("title", "(no title)")[:80]
    item_type = item.get("item_type", "")
    creators = item.get("creators", [])
    creator_str = "; ".join(creators[:2]) if creators else ""
    pdf_snippet = ""
    if item.get("pdf_text"):
        pdf_snippet = " | " + item["pdf_text"][:200].replace("\n", " ")

    return f'"{title}" ({item_type}) — {creator_str}{pdf_snippet}'


def _parse_yaml_list(text: str) -> list[str]:
    """
    Parse a YAML list from LLM output, handling common formatting noise.

    LLMs sometimes wrap their response in markdown code fences or add
    explanatory text before/after the list. This function strips that
    and extracts just the list items.
    """
    # Strip markdown code fences if present
    text = re.sub(r"```(?:yaml)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)

    try:
        parsed = yaml.safe_load(text.strip())
        if isinstance(parsed, list):
            # Filter to strings only, strip whitespace
            return [str(t).strip().lower() for t in parsed if t and str(t).strip()]
    except yaml.YAMLError:
        pass

    # Fallback: extract lines starting with "- "
    tags = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- "):
            tag = line[2:].strip().lower()
            if tag:
                tags.append(tag)
    return tags
