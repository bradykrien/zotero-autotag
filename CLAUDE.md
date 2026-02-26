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
| Local LLM runtime | Ollama (Mistral 7B or Llama 3.2 3B) |
| Tag assignment | `sentence-transformers` |
| PDF extraction | TBD (`pdfminer` or `pypdf`) |
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
| 2 | Zotero connector — fetch items + metadata via API | **Next up** |
| 3 | PDF extractor — pull full text from local attachments | Pending |
| 4 | Vocabulary generator — local LLM proposes controlled vocabulary | Pending |
| 5 | Tag assigner — apply vocabulary with date-horizon logic | Pending |
| 6 | Test harness — evaluate on random sample, iterate | Pending |
| 7 | Docs + packaging | Pending |

## Key Files
- `config/settings.yaml` — non-secret config (date horizon, model choices, etc.)
- `config/secrets.yaml` — API keys and paths (git-ignored, never committed)
- `config/secrets.example.yaml` — template committed to repo
- `src/zotero_autotag/config.py` — loads and merges both config files
- `scripts/verify_setup.py` — manual connection check (not a pytest test)

## PDF Access Notes (relevant for Phase 3)
- Local cache at `/Users/bkrien/Zotero/storage/` is partial (~2 orders of magnitude fewer than full collection)
- Full collection is on WebDAV server (Raspberry Pi)
- Plan: mount WebDAV share as network drive; code reads it like a local path
- WebDAV credentials captured in secrets.yaml under `webdav:` key
