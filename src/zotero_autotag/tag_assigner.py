"""
tag_assigner.py — assign controlled vocabulary tags using semantic similarity.

The main class is TagAssigner. It uses sentence-transformers to embed both the
vocabulary tags and each item's content, then assigns the tags whose embeddings
are most similar to the item.

Pipeline:
  1. Embed all vocabulary tags once (cheap — only 39 tags)
  2. For each item, build a text representation (title + PDF snippet)
  3. Embed the item text
  4. Compute cosine similarity between item embedding and all tag embeddings
  5. Assign tags above the similarity threshold, capped at max_tags_per_item
  6. Apply business logic: skip tbr items, overwrite vs. add-only based on item age

The output is a list of assignment dicts — one per item — describing what tags would
be written to Zotero. Nothing is written here; the script reads this output and
decides whether to apply it.

Module-level helpers:
  save_assignments(assignments, path)  — write the dry-run preview to JSON
  load_assignments(path)               — read it back for the --apply step
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from sentence_transformers import SentenceTransformer, util


# ── TagAssigner ───────────────────────────────────────────────────────────────

class TagAssigner:
    """
    Assigns controlled vocabulary tags to library items using semantic similarity.

    Usage:
        from zotero_autotag.config import load_config
        from zotero_autotag.tag_assigner import TagAssigner, save_assignments
        from zotero_autotag.vocab_generator import load_proposals

        config = load_config()
        vocabulary = load_proposals(Path("data/vocab_proposals.yaml"))
        assigner = TagAssigner(config)
        assignments = assigner.assign(items, vocabulary)
        save_assignments(assignments, Path("data/cache/tag_assignments.json"))
    """

    # Max characters of PDF text to include in the item embedding.
    # 800 chars ≈ 150-180 tokens, safely within all-MiniLM-L6-v2's 256-token limit
    # when combined with the title.
    PDF_SNIPPET_CHARS = 800

    def __init__(self, config: dict):
        pipeline_cfg = config["pipeline"]
        self.max_tags = pipeline_cfg["max_tags_per_item"]
        self.threshold = pipeline_cfg["similarity_threshold"]
        self.protected = set(pipeline_cfg.get("protected_tags", []))
        self.horizon_days = pipeline_cfg["date_horizon_days"]

        model_name = config["model"]["embedding_model"]
        print(f"  Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)

    def assign(
        self,
        items: list[dict],
        vocabulary: list[str],
        descriptions: dict[str, str] | None = None,
    ) -> list[dict]:
        """
        Compute tag assignments for all items and return a list of assignment dicts.

        This method does NOT write to Zotero. It only computes what would be written.

        Steps:
          1. Embed all vocabulary tags (once — reused for every item)
          2. For each item, embed its text and compute similarities
          3. Apply business logic (skip/overwrite/add-only) and package results

        If descriptions is provided, each tag is embedded as "<tag>: <description>"
        instead of just the bare tag name. This significantly improves discrimination
        between tags whose names share words (e.g. 'digital humanities' vs
        'environmental humanities') because the model has richer context to work with.
        The vocabulary list is still used for tag names in the output — descriptions
        only affect the embedding, not what gets written to Zotero.
        """
        tag_texts = [
            f"{tag}: {descriptions[tag]}" if descriptions and tag in descriptions else tag
            for tag in vocabulary
        ]
        n_with_desc = sum(1 for t in vocabulary if descriptions and t in descriptions)
        print(f"  Embedding {len(vocabulary)} vocabulary tags "
              f"({n_with_desc} with descriptions, {len(vocabulary) - n_with_desc} bare)...")
        tag_embeddings = self.model.encode(tag_texts, convert_to_tensor=True)

        now = datetime.now(timezone.utc)
        assignments = []

        for item in items:
            assignment = self._assign_item(item, vocabulary, tag_embeddings, now)
            assignments.append(assignment)

        return assignments

    def _assign_item(
        self,
        item: dict,
        vocabulary: list[str],
        tag_embeddings,
        now: datetime,
    ) -> dict:
        """
        Compute the tag assignment for a single item.

        Returns an assignment dict with status, proposed_tags, final_tags, and scores.
        The 'status' field tells the apply step what to do:
          "skipped"   — item has a protected tag; do not touch it
          "overwrite" — item is old enough; replace all its tags
          "add_only"  — item is recent; only add new tags, keep existing ones
        """
        existing_tags = item.get("tags", [])

        # ── Semantic similarity ───────────────────────────────────────────────
        text = self._item_text(item)
        item_embedding = self.model.encode(text, convert_to_tensor=True)
        selected = self._select_tags(item_embedding, tag_embeddings, vocabulary)

        proposed_tags = [tag for tag, _ in selected]
        scores = {tag: round(float(score), 4) for tag, score in selected}

        # ── Date-horizon logic ────────────────────────────────────────────────
        age_days = _item_age_days(item, now)
        is_old = age_days > self.horizon_days

        # Protected tags (e.g. "tbr") are always preserved in final_tags.
        # They are never added or removed — we can tag the item, we just
        # carry any protected tags through unchanged.
        protected_existing = [t for t in existing_tags if t in self.protected]

        if is_old:
            # Overwrite: replace non-protected tags with proposed tags,
            # but always keep any protected tags the item already has.
            final_tags = protected_existing + proposed_tags
            status = "overwrite"
        else:
            # Add-only: keep all existing tags (including protected ones),
            # add proposed ones not already present.
            existing_set = set(existing_tags)
            additions = [t for t in proposed_tags if t not in existing_set]
            final_tags = list(existing_tags) + additions
            status = "add_only"

        return {
            "key": item["key"],
            "title": item.get("title", ""),
            "item_type": item.get("item_type", ""),
            "existing_tags": existing_tags,
            "status": status,
            "proposed_tags": proposed_tags,
            "final_tags": final_tags,
            "scores": scores,
        }

    def _item_text(self, item: dict) -> str:
        """
        Build the text representation for embedding an item.

        The title alone is usually enough to assign broad tags like "book history"
        or "digital humanities". The PDF snippet adds topical context for items
        whose titles are opaque (edited volumes, collected works, etc.).
        """
        title = item.get("title", "")
        pdf_text = item.get("pdf_text") or ""
        if pdf_text:
            snippet = pdf_text[: self.PDF_SNIPPET_CHARS].replace("\n", " ")
            return f"{title}. {snippet}"
        return title

    def _select_tags(
        self,
        item_embedding,
        tag_embeddings,
        vocabulary: list[str],
    ) -> list[tuple[str, float]]:
        """
        Return (tag, score) pairs above the similarity threshold.

        Results are sorted by score descending and capped at max_tags_per_item.
        Items that don't match any tag above the threshold get no tags assigned
        (rather than forcing a best-guess assignment).
        """
        scores = util.cos_sim(item_embedding, tag_embeddings)[0]
        scored = [(vocabulary[i], float(scores[i])) for i in range(len(vocabulary))]
        above_threshold = [
            (tag, score) for tag, score in scored if score >= self.threshold
        ]
        above_threshold.sort(key=lambda x: x[1], reverse=True)
        return above_threshold[: self.max_tags]


# ── Public helpers ─────────────────────────────────────────────────────────────

def save_assignments(assignments: list[dict], path: Path) -> None:
    """
    Write the dry-run assignment preview to a JSON file.

    The file is machine-readable (for --apply) and human-inspectable (for review).
    Open it after a dry run to spot-check the proposed tags before applying.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(assignments, f, indent=2, ensure_ascii=False)
    print(f"  Assignments saved to {path} ({len(assignments)} items)")


def load_assignments(path: Path) -> list[dict]:
    """
    Load the saved assignment preview for the --apply step.

    Raises FileNotFoundError if the dry run hasn't been run yet.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"\n\nAssignment preview not found at {path}\n"
            f"Run 'python scripts/assign_tags.py' (dry run) first.\n"
        )
    with open(path) as f:
        assignments = json.load(f)
    print(f"  Loaded {len(assignments)} assignments from {path}")
    return assignments


# ── Internal helpers ───────────────────────────────────────────────────────────

def _item_age_days(item: dict, now: datetime) -> int:
    """
    Return how many days ago the item was added to the Zotero library.

    date_added is stored as ISO 8601 UTC (e.g. "2026-02-16T11:44:27Z").
    Returns 0 if the field is missing or unparseable (treats it as brand new).
    """
    date_str = item.get("date_added", "")
    if not date_str:
        return 0
    try:
        date_added = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return (now - date_added).days
    except ValueError:
        return 0
