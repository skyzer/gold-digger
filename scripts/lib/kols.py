"""KOL file loader + registry.

KOLs live at `$GOLD_DIGGER_DATA/kols/*.md` — one file per tracked KOL,
populated via `gold-digger add-kol <handle>`. Each file has frontmatter
with `handle`, `platform`, `url`, `weight`, `focus`.

Empty on first install. See README Quick Start for populating commands.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from lib import storage


def _live_dir() -> Path:
    d = storage.data_root() / "kols"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_all() -> List[Dict[str, Any]]:
    """Return the list of KOLs as frontmatter dicts, sorted by weight (desc)."""
    results: List[Dict[str, Any]] = []
    for path in sorted(_live_dir().glob("*.md")):
        fm, _body = storage.read_project(path)
        if fm.get("handle"):
            fm["_path"] = str(path)
            results.append(fm)
    results.sort(key=lambda k: (k.get("weight") or 0.0), reverse=True)
    return results


def handles() -> List[str]:
    """Return just the list of handles for quick iteration."""
    return [k.get("handle") for k in load_all() if k.get("handle")]


def write_kol(handle: str, platform: str = "x", weight: float = 1.0, focus: List[str] | None = None) -> Path:
    """Create a new KOL file in the user's data dir."""
    from datetime import datetime, timezone
    live_dir = _live_dir()
    path = live_dir / f"{handle.lower()}.md"
    if path.exists():
        return path
    fm = {
        "handle": handle,
        "platform": platform,
        "url": f"https://x.com/{handle}" if platform == "x" else None,
        "weight": weight,
        "focus": focus or [],
        "added": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    body = (
        f"\n# {handle}\n\n"
        f"## Why tracked\n\n"
        f"_(Add your reason for tracking this KOL.)_\n\n"
        f"## Notes\n\n"
        f"## First-mention history\n\n"
        f"_Populated by Gold Digger's KOL first-mention auto-scout._\n"
    )
    storage.write_project(path, fm, body)
    return path
