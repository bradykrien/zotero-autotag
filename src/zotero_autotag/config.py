"""
config.py — loads and merges settings.yaml and secrets.yaml.

Other modules import this and call load_config() to get their settings.
"""

from pathlib import Path
import yaml

# The config directory sits at the project root, two levels above this file.
# This file: src/zotero_autotag/config.py
# Project root: ../../  →  zotero-autotag/
# Config dir:   ../../config/
CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def load_config() -> dict:
    """
    Load settings.yaml and secrets.yaml and return a merged config dict.

    Raises FileNotFoundError if secrets.yaml is missing (with a helpful message).
    """
    settings_path = CONFIG_DIR / "settings.yaml"
    secrets_path = CONFIG_DIR / "secrets.yaml"

    with open(settings_path) as f:
        settings = yaml.safe_load(f)

    if not secrets_path.exists():
        raise FileNotFoundError(
            f"\n\nsecrets.yaml not found at {secrets_path}\n"
            f"Copy config/secrets.example.yaml to config/secrets.yaml "
            f"and fill in your Zotero API key and storage path.\n"
        )

    with open(secrets_path) as f:
        secrets = yaml.safe_load(f)

    # Merge into a single dict. Settings and secrets stay in separate
    # top-level namespaces so it's always clear where a value came from.
    return {**settings, **secrets}
