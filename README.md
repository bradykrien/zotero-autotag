# zotero-autotag

A two-module Python tool for automatically tagging a [Zotero](https://www.zotero.org/) library using a local LLM and semantic similarity. Designed for humanities researchers with large, partially-tagged collections.

## What it does

1. **Vocabulary Generator** — analyzes your library's metadata and existing tags, then uses a local LLM (via [Ollama](https://ollama.com/)) to propose a controlled vocabulary. You review and approve the vocabulary before anything is written to your library.

2. **Tag Assigner** — applies the approved vocabulary to your items using semantic similarity (`sentence-transformers`). Uses PDF full text where available, falls back to metadata (title, abstract, authors, journal) otherwise.

## Design principles

- **No proprietary APIs** — runs entirely with open-source models on your own hardware
- **Non-destructive by default** — recent items get new tags added, not overwritten
- **One protected tag** — the `tbr` (To Be Read) tag is never touched
- **Configurable** — date horizon and model choices live in a config file, not hardcoded

## Status

Under active development. See [Project Phases](#project-phases) below.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com/) installed and running
- A Zotero account with Web API access
- Local Zotero data directory (for PDF access)

## Setup

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/zotero-autotag.git
cd zotero-autotag

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy the secrets template and fill in your values
cp config/secrets.example.yaml config/secrets.yaml
```

Then edit `config/secrets.yaml` with your Zotero API key and local paths.

## Project Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Project scaffolding | In progress |
| 2 | Zotero connector | Pending |
| 3 | PDF extractor | Pending |
| 4 | Vocabulary generator | Pending |
| 5 | Tag assigner | Pending |
| 6 | Test harness | Pending |
| 7 | Docs + packaging | Pending |

## License

MIT
