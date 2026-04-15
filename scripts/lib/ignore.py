"""Ignore list — hard filter for tokens and slugs we never want to track.

Source of truth: `references/ignore.md`. User-editable markdown. The parser
reads every line that starts with `- ` as an entry, strips inline `# comment`
tails, and matches case-insensitively against either a ticker or a slug.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Set

# Cache the parsed set so we don't re-read the file on every check
_CACHE: Optional[Set[str]] = None
_CACHE_MTIME: float = 0.0


def _ignore_file() -> Path:
    # scripts/lib/ignore.py → scripts/ → repo root → references/
    return Path(__file__).resolve().parent.parent.parent / "references" / "ignore.md"


def _parse(text: str) -> Set[str]:
    """Extract ignore entries from the markdown body."""
    entries: Set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("- "):
            continue
        value = line[2:].strip()
        # Strip inline comment
        if "#" in value:
            value = value.split("#", 1)[0].strip()
        if not value:
            continue
        entries.add(value.lower())
    return entries


def load() -> Set[str]:
    """Return the ignore set, cached until the source file changes."""
    global _CACHE, _CACHE_MTIME
    path = _ignore_file()
    if not path.exists():
        _CACHE = set()
        return _CACHE
    mtime = path.stat().st_mtime
    if _CACHE is not None and mtime == _CACHE_MTIME:
        return _CACHE
    _CACHE = _parse(path.read_text(encoding="utf-8"))
    _CACHE_MTIME = mtime
    return _CACHE


def is_ignored(*values: Optional[str]) -> bool:
    """True if any of the supplied ticker/slug/name values match the ignore list."""
    ignored = load()
    for v in values:
        if v and str(v).strip().lower() in ignored:
            return True
    return False


def filter_candidates(candidates: list) -> list:
    """Return a new list with ignored candidates removed. Matches on ticker,
    slug, coingecko_id, or defillama_slug fields of each candidate dict."""
    return [
        c for c in candidates
        if not is_ignored(
            c.get("ticker"),
            c.get("slug"),
            c.get("coingecko_id"),
            c.get("defillama_slug"),
            c.get("name"),
        )
    ]
