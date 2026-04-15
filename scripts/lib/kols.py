"""KOL file loader + registry.

KOLs live in either:
  - $GOLD_DIGGER_DATA/kols/*.md   (user's live watchlist)
  - <repo>/seed/kols/*.md         (shipped seed list, copied on first use)

Each file has frontmatter with `handle`, `platform`, `url`, `weight`, `focus`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from lib import storage


def _seed_dir() -> Path:
    # scripts/lib/kols.py → scripts/ → repo root → seed/kols
    return Path(__file__).resolve().parent.parent.parent / "seed" / "kols"


def _live_dir() -> Path:
    return storage.data_root() / "kols"


def ensure_seeded() -> None:
    """Copy seed KOLs to live dir if the live dir is empty."""
    live = _live_dir()
    live.mkdir(parents=True, exist_ok=True)
    if any(live.glob("*.md")):
        return
    seed = _seed_dir()
    if not seed.exists():
        return
    for seed_file in seed.glob("*.md"):
        dest = live / seed_file.name
        if not dest.exists():
            fm, body = storage.read_project(seed_file)
            storage.write_project(dest, fm, body)


def load_all() -> List[Dict[str, Any]]:
    """Return the list of KOLs as frontmatter dicts, sorted by weight (desc)."""
    ensure_seeded()
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
