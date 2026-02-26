# Zotero Tagging Workflow — Project Handoff
 
This document captures a conversation from the Claude.ai web interface for continuation in VS Code / Claude Code.
 
---
 
## Project Goals (in priority order)
 
1. **Learning** — the user wants to become a developer; understanding every step is the primary outcome
2. **Open source artifact** — a reusable project others can adapt for their own libraries
3. **Practical outcome** — a working tag generation and assignment workflow for the user's Zotero library
 
The senior-dev-mentoring-a-junior-dev dynamic was explicitly established. Move deliberately, explain every decision, and don't just make it work quickly.
 
---
 
## User Background
 
- Comfortable with Python
- Familiar with the command line (not super fluent)
- Some data pipeline experience via dissertation research (topic modeling with gensim on HathiTrust Extracted Features dataset — has real NLP intuition)
- Amateurish GitHub user; learning to build robust repos is an explicit goal
- Hardware: Two Apple Silicon MacBooks (one M2, one M3) + access to CHTC resources at UW–Madison
 
---
 
## Zotero Setup
 
- **Library size**: 1,151 items
- **Metadata sync**: Zotero.org account (username signed in) — Zotero Web API is available
- **PDF storage**: WebDAV server on a Raspberry Pi (self-hosted)
- **Local data directory**: `/Users/bkrien/Zotero`
- **Local PDF path**: `/Users/bkrien/Zotero/storage/`
- **Access plan**: Use the Zotero Web API for reading/writing metadata and tags; read PDFs directly from local storage path
 
---
 
## Existing Tags
 
- ~20–30 tags currently, sparsely applied
- Style is noun-based phrases: "book history," "llms," "data structures," "periodicals," etc.
- User wants to keep and build on these — the vocabulary generator should treat them as seed vocabulary
- One protected tag: **`tbr`** (To Be Read) — must never be touched, added to, or overwritten by any module
 
---
 
## Domain
 
Humanities — specifically:
- Digital humanities
- Print culture
- American literature
- Environmental literature
- Library and information science (LIS)
 
Tag vocabulary and model prompting will need to reflect this domain.
 
---
 
## System Architecture (Two Modules)
 
### Module 1 — Vocabulary Generator
- Ingests the library (metadata + full text where available)
- Analyzes existing tags as seed vocabulary
- Proposes a controlled vocabulary to supplement existing tags
- User reviews and tweaks the suggested vocabulary before it is used
- Outputs a curated tag list the user approves
 
### Module 2 — Tag Assigner
- Takes the approved controlled vocabulary
- Applies tags to items in the library
- Uses both metadata and full-text (PDF extraction where PDFs exist)
- Respects the business logic rules below
 
---
 
## Business Logic Rules
 
| Condition | Behavior |
|-----------|----------|
| Item has the `tbr` tag | Never touch it; leave it completely alone |
| Item was added more than [configurable horizon] days ago | Overwrite existing tags with new assignments |
| Item was added within the horizon period | Add new tags only; do not overwrite existing ones |
| Item has no PDF | Fall back to metadata only (title, abstract, authors, journal, etc.) |
 
- The date horizon should be a **configurable parameter** (not hardcoded to 30 days), so other users can set their own cutoff reflecting when they started tagging thoughtfully
- Default suggestion: 30 days
 
---
 
## Testing Harness
 
Before running on the full library:
- Random sample of 20–50 items
- Evaluate tag assignment quality
- Tune and iterate before full run
- This is a first-class part of the project, not an afterthought
 
---
 
## Technology Stack
 
| Component | Tool | Rationale |
|-----------|------|-----------|
| Language | Python | User comfortable; best library ecosystem |
| Zotero client | `pyzotero` | Most mature Zotero API client |
| Local model runtime | **Ollama** | Manages models like a package manager; no API key needed |
| Vocabulary generation | Mistral 7B or Llama 3.2 3B | Reasoning over domain themes; runs well on Apple Silicon |
| Tag assignment | `sentence-transformers` | Lightweight embeddings; semantic similarity to topic modeling work user already knows |
| PDF extraction | TBD (likely `pdfminer` or `pypdf`) | Extract full text from local PDFs |
| Heavy compute (if needed) | CHTC (UW–Madison) | Available to user |
 
Everything must be **open source** — no proprietary APIs (no Claude API, no OpenAI).
 
---
 
## Project Phase Plan
 
The conversation had just finalized the architecture and was about to begin **Phase 1**.
 
| Phase | Description | Status |
|-------|-------------|--------|
| **1** | Project scaffolding — GitHub repo, Python virtual environment, project directory structure, config system (keep secrets out of version control) | **Next up — not started** |
| 2 | Zotero connector — fetch items + metadata via API | Pending |
| 3 | PDF extractor — pull full text from local attachments | Pending |
| 4 | Vocabulary generator — local LLM suggests controlled vocabulary | Pending |
| 5 | Tag assigner — apply vocabulary with date-horizon logic | Pending |
| 6 | Test harness — evaluate on random samples, iterate | Pending |
| 7 | Docs + packaging — make it usable by others | Pending |
 
---
 
## Phase 1 — What Was About to Be Built
 
Phase 1 covers four things, in order:
1. Creating a well-structured GitHub repository
2. Setting up a Python virtual environment (isolated from system Python)
3. Scaffolding the project directory layout
4. Creating a configuration system that keeps secrets (API keys, file paths) out of version control
 
This is where to pick up.
 
---
 
## Mentorship Notes
 
- User wants to understand every line of code before moving forward
- Explain decisions, not just implementations
- Resist the urge to move fast
- The learning is the point