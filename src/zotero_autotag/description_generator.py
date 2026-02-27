"""
description_generator.py — generate tag descriptions using a local LLM.

Produces a 1-2 sentence description for each vocabulary tag, grounded in the
actual library content and calibrated to distinguish each tag from its neighbors.

Why this matters: the tag assigner embeds descriptions rather than bare tag names
when descriptions are available. A richer embedding for "digital humanities" (one
that mentions computational methods and text analysis) discriminates better from
"environmental humanities" (ecology, ecocriticism) than two 2-word phrases that
both contain "humanities".

Usage:
    generator = DescriptionGenerator(config)
    descriptions = generator.generate(vocabulary, items, existing_descriptions)
"""

import random
import re
from pathlib import Path

import yaml


# ── DescriptionGenerator ──────────────────────────────────────────────────────

class DescriptionGenerator:
    """
    Generates tag descriptions using a local LLM (Ollama/Mistral).

    Processes tags in small batches, giving the LLM:
    1. The full vocabulary (so it understands what's adjacent and can write
       descriptions that *distinguish* each tag from its neighbors)
    2. A random sample of actual library items (so descriptions are grounded
       in what's actually in the collection, not generic field-level definitions)

    Usage:
        from zotero_autotag.config import load_config
        from zotero_autotag.description_generator import DescriptionGenerator

        config = load_config()
        generator = DescriptionGenerator(config)
        descriptions = generator.generate(vocabulary, items, existing_descriptions)
    """

    # Tags to describe per LLM call. Small batches give the model enough
    # room to write thoughtful descriptions without losing context.
    BATCH_SIZE = 8

    # Number of library items to include as grounding examples.
    # These help the model understand how tags are actually used in this
    # specific collection rather than in the general academic sense.
    SAMPLE_ITEMS = 25

    def __init__(self, config: dict):
        self.model = config["model"]["name"]
        self.host = config["model"]["base_url"]

    def generate(
        self,
        vocabulary: list[str],
        items: list[dict],
        existing_descriptions: dict[str, str],
        refresh: bool = False,
    ) -> dict[str, str]:
        """
        Generate descriptions for vocabulary tags and return the full descriptions dict.

        Tags that already have descriptions are skipped unless refresh=True.
        Returns a dict merging existing descriptions with newly generated ones.

        Steps:
          1. Determine which tags need descriptions
          2. Sample a representative set of library items for grounding context
          3. Process tags in batches, querying Mistral for each batch
          4. Merge results with any pre-existing descriptions
        """
        if refresh:
            todo = list(vocabulary)
        else:
            todo = [t for t in vocabulary if t not in existing_descriptions]

        if not todo:
            print("  All tags already have descriptions. Use --refresh to regenerate.")
            return dict(existing_descriptions)

        print(f"  Generating descriptions for {len(todo)} tag(s) "
              f"({len(vocabulary) - len(todo)} already exist)...")

        # Sample items to ground the descriptions in real library content.
        sample = random.sample(items, min(self.SAMPLE_ITEMS, len(items)))

        # Process in batches
        new_descriptions: dict[str, str] = {}
        for batch_start in range(0, len(todo), self.BATCH_SIZE):
            batch = todo[batch_start : batch_start + self.BATCH_SIZE]
            print(f"  Batch {batch_start // self.BATCH_SIZE + 1}/"
                  f"{-(-len(todo) // self.BATCH_SIZE)}: {batch}...",
                  end=" ", flush=True)

            result = self._run_batch(batch, vocabulary, sample)
            new_descriptions.update(result)
            print(f"{len(result)} descriptions")

        # Merge: new descriptions override existing ones for refreshed tags,
        # existing descriptions are preserved for tags not in this run.
        merged = dict(existing_descriptions)
        merged.update(new_descriptions)
        return merged

    def _run_batch(
        self,
        batch: list[str],
        all_tags: list[str],
        sample_items: list[dict],
    ) -> dict[str, str]:
        """
        Ask Mistral to write descriptions for a batch of tags.

        The prompt provides two anchors:
        - The full vocabulary, so the model understands what's adjacent and can
          write descriptions that *distinguish* each tag from its neighbors.
        - A sample of actual library items, so descriptions reflect how these
          tags apply to the real collection rather than the field in general.

        Returns a dict of {tag: description} for the batch.
        """
        all_tags_str = "\n".join(f"  - {t}" for t in sorted(all_tags))
        batch_str = "\n".join(f"  - {t}" for t in batch)
        items_str = "\n".join(_format_item(item) for item in sample_items)

        prompt = f"""You are a librarian writing a controlled vocabulary for a humanities research library.

The library covers digital humanities, print culture, American literature,
environmental humanities, and library/information science (~1,150 items).

The full vocabulary for this library is:
{all_tags_str}

Here is a sample of actual items from the library (to ground your descriptions
in what is actually in this collection):
{items_str}

Write a short description for each of these tags (only these tags):
{batch_str}

Requirements:
- Each description should be 1-2 sentences (20-40 words)
- Emphasize what makes each tag DISTINCT from similar tags in the vocabulary
  (e.g. "digital humanities" should not sound like "environmental humanities")
- Ground the description in what kinds of items in THIS library would get the tag
- Use plain language, not jargon

Return ONLY a YAML mapping (no extra text, no code fences):
tag name: "description here"
tag name: "description here"
..."""

        try:
            import ollama
            client = ollama.Client(host=self.host)
            response = client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            return _parse_yaml_mapping(response.message.content, batch)
        except Exception as e:
            print(f"\n  [WARN] Batch failed: {e}")
            return {}


# ── Public helpers ─────────────────────────────────────────────────────────────

def update_descriptions_in_yaml(
    path: Path,
    descriptions: dict[str, str],
) -> None:
    """
    Write the descriptions dict back into vocab_proposals.yaml.

    Preserves the existing file structure (header comments, vocabulary list).
    Only the `descriptions:` section is replaced. If no `descriptions:` section
    exists yet, one is appended.
    """
    path = Path(path)
    with open(path) as f:
        content = f.read()

    # Build the new descriptions block
    desc_lines = ["descriptions:"]
    for tag, desc in sorted(descriptions.items()):
        # YAML-escape double quotes inside the description
        safe_desc = desc.replace('"', '\\"')
        desc_lines.append(f'  {tag}: "{safe_desc}"')
    new_block = "\n".join(desc_lines) + "\n"

    # Replace existing descriptions block, or append if not present
    if re.search(r"^descriptions:", content, re.MULTILINE):
        # Replace from "descriptions:" to the end of the file (or next top-level key)
        content = re.sub(
            r"^descriptions:.*",
            new_block,
            content,
            flags=re.MULTILINE | re.DOTALL,
        )
    else:
        content = content.rstrip("\n") + "\n\n" + new_block

    with open(path, "w") as f:
        f.write(content)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _format_item(item: dict) -> str:
    """Compact one-line summary of an item for use in LLM prompts."""
    title = item.get("title", "(no title)")[:80]
    item_type = item.get("item_type", "")
    creators = item.get("creators", [])
    creator_str = "; ".join(creators[:2]) if creators else ""
    return f'"{title}" ({item_type}) — {creator_str}'


def _parse_yaml_mapping(text: str, expected_keys: list[str]) -> dict[str, str]:
    """
    Parse a YAML mapping from LLM output.

    LLMs sometimes wrap responses in markdown fences or add explanatory text.
    This strips noise and extracts the mapping. Falls back to regex line parsing
    if YAML parsing fails.
    """
    # Strip markdown code fences
    text = re.sub(r"```(?:yaml)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)

    try:
        parsed = yaml.safe_load(text.strip())
        if isinstance(parsed, dict):
            return {
                str(k).strip().lower(): str(v).strip()
                for k, v in parsed.items()
                if v and str(k).strip().lower() in expected_keys
            }
    except yaml.YAMLError:
        pass

    # Fallback: parse "key: value" lines manually
    result = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().strip('"').lower()
        value = value.strip().strip('"')
        if key in expected_keys and value:
            result[key] = value
    return result
