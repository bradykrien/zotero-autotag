"""
verify_setup.py — confirm that all connections work before running the pipeline.

Run this before your first real pipeline run:
    python scripts/verify_setup.py

Checks:
    1. Config loads correctly (settings.yaml + secrets.yaml)
    2. Zotero API is reachable and credentials are valid
    3. Local Zotero storage directory is accessible
    4. WebDAV mount is accessible (if configured)
"""

import sys
from pathlib import Path

# ── Path fix ──────────────────────────────────────────────────────────────────
# Because our package lives in src/, Python can't find it by default when we
# run this script directly. This line adds src/ to Python's search path so
# that "from zotero_autotag.config import load_config" works.
# (Long-term, we'll replace this with a proper package install via pyproject.toml.)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from zotero_autotag.config import load_config


# ── Individual checks ─────────────────────────────────────────────────────────

def check_config():
    """Load config and print key settings so you can confirm they look right."""
    print("── 1. Config ────────────────────────────────────────")
    try:
        config = load_config()
        print("  [OK] Config loaded")
        print(f"       Date horizon : {config['pipeline']['date_horizon_days']} days")
        print(f"       Model        : {config['model']['name']}")
        print(f"       Protected    : {config['pipeline']['protected_tags']}")
        return config
    except FileNotFoundError as e:
        print(f"  [FAIL] {e}")
        return None
    except Exception as e:
        print(f"  [FAIL] Unexpected error loading config: {e}")
        return None


def check_zotero(config):
    """Make a lightweight Zotero API call to confirm credentials work."""
    print("\n── 2. Zotero API ────────────────────────────────────")
    try:
        from pyzotero import zotero

        zot = zotero.Zotero(
            library_id=config["zotero"]["library_id"],
            library_type=config["zotero"]["library_type"],
            api_key=config["zotero"]["api_key"],
        )

        # Fetch a single item — lightweight, just enough to confirm the connection.
        items = zot.items(limit=1)
        title = items[0]["data"].get("title", "(no title)")[:70]
        print("  [OK] Zotero API connected")
        print(f"       Sample item  : {title}")

    except ImportError:
        print("  [FAIL] pyzotero not installed. Run: pip install pyzotero")
    except Exception as e:
        print(f"  [FAIL] Zotero API error: {e}")


def check_local_storage(config):
    """Confirm the local Zotero storage cache is readable."""
    print("\n── 3. Local Zotero storage ──────────────────────────")
    storage_path = Path(config.get("paths", {}).get("zotero_storage", ""))

    if not storage_path.exists():
        print(f"  [FAIL] Path not found: {storage_path}")
        return

    cached_dirs = [d for d in storage_path.iterdir() if d.is_dir()]
    print(f"  [OK] Accessible: {storage_path}")
    print(f"       Cached item folders: {len(cached_dirs)}")


def check_webdav_mount(config):
    """Confirm the WebDAV mount point exists and is readable."""
    print("\n── 4. WebDAV mount ──────────────────────────────────")
    mount_str = config.get("paths", {}).get("webdav_mount", "")

    if not mount_str:
        print("  [SKIP] webdav_mount not set in secrets.yaml")
        return

    mount_path = Path(mount_str)

    if not mount_path.exists():
        print(f"  [FAIL] Mount point not found: {mount_path}")
        print("         Is the WebDAV drive mounted?")
        print("         Finder → Go → Connect to Server → enter your WebDAV URL")
        return

    try:
        entries = list(mount_path.iterdir())
        print(f"  [OK] Mount accessible: {mount_path}")
        print(f"       Items at mount root: {len(entries)}")
    except PermissionError:
        print(f"  [FAIL] Path exists but cannot be read: {mount_path}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Zotero Autotag — Setup Verification")
    print("=" * 52)

    config = check_config()

    if config is None:
        print("\nCannot continue — fix config errors above first.")
        sys.exit(1)

    check_zotero(config)
    check_local_storage(config)
    check_webdav_mount(config)

    print("\n" + "=" * 52)
    print("Done. Fix any [FAIL] items above before running the pipeline.")
