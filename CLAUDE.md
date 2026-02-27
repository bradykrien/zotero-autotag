# zotero-autotag — Claude Code Context

## What This Project Does
Two-module Python tool for auto-tagging a Zotero library using local LLMs and semantic similarity.
- **Module 1 (Vocabulary Generator)**: Analyzes existing library + tags → proposes a controlled vocabulary for user review
- **Module 2 (Tag Assigner)**: Applies the approved vocabulary to library items using metadata + PDF full-text

## Goals (in priority order)
1. Learning — user is becoming a developer; explaining every decision matters as much as shipping
2. Open-source artifact — reusable by others with their own Zotero libraries
3. Practical outcome — working tagger for user's ~1,150-item humanities library

## Mentorship Dynamic
Senior-dev-mentoring-a-junior approach. Explain decisions, not just implementations. Move deliberately. The learning is the point. User is comfortable with Python, has NLP intuition from topic modeling work.

## Non-Negotiable Rules
- The tag `tbr` must NEVER be touched, added to, or overwritten by any code path
- No proprietary APIs — everything must be open source (no Claude API, no OpenAI)
- Secrets (API keys, file paths) must stay out of version control

## Technology Stack
| Component | Tool |
|-----------|------|
| Language | Python |
| Zotero API client | `pyzotero` |
| Local LLM runtime | Ollama (Mistral 7B) |
| Tag assignment | `sentence-transformers` |
| PDF extraction | `pdfminer.six` |
| Dashboard | Streamlit + pandas + plotly |
| Heavy compute | CHTC (UW–Madison) if needed |

## Business Logic
| Condition | Behavior |
|-----------|----------|
| Item has `tbr` tag | Leave it completely alone |
| Item added > N days ago (configurable, default 30) | Overwrite existing tags |
| Item added within N days | Add new tags only; preserve existing |
| Item has no PDF | Fall back to metadata only |

## User's Zotero Setup
- Library: ~1,151 items, Zotero Web API (account synced)
- PDFs: local at `/Users/bkrien/Zotero/storage/` (WebDAV on Raspberry Pi)
- Existing tags: ~20–30, noun-phrase style (e.g. "book history", "llms"), treat as seed vocabulary
- Domain: digital humanities, print culture, American literature, environmental lit, LIS

## Phase Status
| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Project scaffolding — repo, venv, directory structure, config system | **Complete** |
| 2 | Zotero connector — fetch items + metadata via API | **Complete** |
| 3 | PDF extractor — pull full text from local attachments + Streamlit dashboard | **Complete** |
| 4 | Vocabulary generator — local LLM proposes controlled vocabulary | **Complete** |
| 4.5 | Preview script — estimate per-tag coverage before Phase 5 | **Dropped** (Phase 5 dry-run serves this purpose) |
| 5 | Tag assigner — apply vocabulary with date-horizon logic | **Dry run complete — awaiting review + apply** |
| 6 | Test harness — evaluate on random sample, iterate | Pending |
| 7 | Docs + packaging | Pending |

## Key Files
- `config/settings.yaml` — non-secret config (date horizon, model choices, similarity threshold, etc.)
- `config/secrets.yaml` — API keys and paths (git-ignored, never committed)
- `config/secrets.example.yaml` — template committed to repo
- `src/zotero_autotag/config.py` — loads and merges both config files
- `src/zotero_autotag/zotero_connector.py` — pyzotero wrapper; fetch + cache items; write tags back to Zotero
- `src/zotero_autotag/pdf_extractor.py` — pdfminer.six extraction; enrich items with pdf_text; WebDAV zip support
- `src/zotero_autotag/vocab_generator.py` — Ollama batch sampling + consolidation; load_proposals()
- `src/zotero_autotag/tag_assigner.py` — sentence-transformers cosine similarity; business logic (skip/overwrite/add-only)
- `scripts/verify_setup.py` — manual connection check (not a pytest test)
- `scripts/fetch_items.py` — Phase 2: fetch library → `data/cache/items.json`
- `scripts/extract_text.py` — Phase 3: PDF extraction → `data/cache/items_with_text.json`
- `scripts/dashboard.py` — Phase 3: Streamlit dashboard for exploring the library
- `scripts/generate_vocab.py` — Phase 4: propose vocabulary → `data/vocab_proposals.yaml`
- `scripts/assign_tags.py` — Phase 5: dry-run (default) or `--apply` to write to Zotero; `--limit N` for testing
- `data/vocab_proposals.yaml` — git-tracked; 39 approved tags; human-reviewed before Phase 5

## Cache Files (git-ignored, machine-local)
- `data/cache/items.json` — raw items from Phase 2
- `data/cache/items_with_text.json` — items enriched with PDF text from Phase 3
- `data/cache/tag_assignments.json` — Phase 5 dry-run preview; read by `--apply`

## Pipeline Design Notes
- Abstracts are NOT included in LLM prompts or PDF extraction (too noisy, inconsistent)
- PDF extraction: max 20 pages per document (intro/early chapters have strongest signal)
- Vocabulary generation: 12 batches × 30 items, stratified by item type; consolidation targets ~65 tags
- `vocab_proposals.yaml` is committed to git — it represents a human decision, not machine state
- Resumable extraction: `extract_text.py` skips already-processed items; checkpoints every 100

## PDF Access Notes
- Local cache at `/Users/bkrien/Zotero/storage/` holds 952/955 attachments — nearly complete
- Full collection also on WebDAV server (Raspberry Pi), mounted at `/Volumes/zotero`
- WebDAV stores attachments as `<key>.zip` containing `full-text.pdf` — handled by `extract_text_from_zip()`
- PDF text source tracked per item: "local", "webdav", or None
- 880 items have usable text; 72 are scanned/image PDFs; 199 have no PDF attachment at all
