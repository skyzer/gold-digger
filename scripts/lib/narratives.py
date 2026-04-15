"""Narrative taxonomy classifier.

Reads `references/narratives.md`, parses each `## <tag>` section with its
`**Keywords:**` and `**Seeds:**` lines, and exposes:

  - `classify(project_dict)` → list of matching narrative tags
  - `compute_rotation(candidates)` → dict of {tag: {count, sample_slugs}} for
    today's scout output (snapshot input for velocity computation tomorrow)
  - `rotation_velocity(root)` → compares today's narrative counts against
    historical snapshots to detect rotations

The taxonomy file is user-editable; parsing is cached until mtime changes.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_CACHE: Optional[Dict[str, Dict[str, List[str]]]] = None
_CACHE_MTIME: float = 0.0


def _narratives_file() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "references" / "narratives.md"


def _parse_narratives(text: str) -> Dict[str, Dict[str, List[str]]]:
    """Parse the narratives.md markdown into a dict of tag → {keywords, seeds}."""
    result: Dict[str, Dict[str, List[str]]] = {}
    current_tag: Optional[str] = None
    for raw in text.splitlines():
        line = raw.strip()
        # Section header: `## tag-name`
        if line.startswith("## "):
            tag = line[3:].strip().lower().replace(" ", "-")
            # Skip non-narrative sections like "Adding a narrative"
            if not tag or " " in tag or tag in ("adding-a-narrative",):
                current_tag = None
                continue
            current_tag = tag
            result[tag] = {"keywords": [], "seeds": []}
            continue
        if current_tag is None:
            continue
        # Keyword / seed lines
        if line.lower().startswith("**keywords:**"):
            body = line.split(":", 1)[1].strip().lstrip("*").strip()
            kws = [k.strip().lower() for k in body.split(",") if k.strip()]
            result[current_tag]["keywords"] = kws
        elif line.lower().startswith("**seeds:**"):
            body = line.split(":", 1)[1].strip().lstrip("*").strip()
            seeds = [s.strip().lower() for s in body.split(",") if s.strip()]
            result[current_tag]["seeds"] = seeds
    return result


def load() -> Dict[str, Dict[str, List[str]]]:
    """Return the parsed narrative taxonomy, cached until the file changes."""
    global _CACHE, _CACHE_MTIME
    path = _narratives_file()
    if not path.exists():
        _CACHE = {}
        return _CACHE
    mtime = path.stat().st_mtime
    if _CACHE is not None and mtime == _CACHE_MTIME:
        return _CACHE
    _CACHE = _parse_narratives(path.read_text(encoding="utf-8"))
    _CACHE_MTIME = mtime
    return _CACHE


def _haystack(project: Dict[str, Any]) -> str:
    parts = [
        project.get("name") or "",
        project.get("slug") or "",
        project.get("ticker") or "",
        " ".join(project.get("categories") or []) if isinstance(project.get("categories"), list) else "",
    ]
    return " ".join(parts).lower()


def classify(project: Dict[str, Any]) -> List[str]:
    """Return a list of narrative tags that match this project.

    Uses word-boundary regex matching against keywords. Seeds count as
    exact-match tags (a seed slug/name in the project = auto-tag).
    """
    taxonomy = load()
    if not taxonomy:
        return ["ai-crypto"]  # Sensible default if taxonomy file missing
    hay = _haystack(project)
    slug = (project.get("slug") or "").lower()
    name = (project.get("name") or "").lower()
    matched: List[str] = []
    for tag, spec in taxonomy.items():
        # Exact seed match — strongest signal
        if slug in spec.get("seeds", []) or name in spec.get("seeds", []):
            matched.append(tag)
            continue
        # Keyword regex — word-boundary
        for kw in spec.get("keywords", []):
            if not kw:
                continue
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, hay, re.IGNORECASE):
                matched.append(tag)
                break
    # De-dupe preserving order
    seen: List[str] = []
    for t in matched:
        if t not in seen:
            seen.append(t)
    return seen or ["ai-crypto"]


def tag_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply `classify` to each candidate's `narrative` field. Mutates in place."""
    for c in candidates:
        tags = classify(c)
        existing = c.get("narrative") or []
        merged = list(dict.fromkeys(existing + tags))
        c["narrative"] = merged
    return candidates


def compute_rotation(candidates: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Compute today's narrative distribution. Returns tag → count + samples.

    This is the input to the report's 'Narrative rotation' section. When
    combined with yesterday's and last week's numbers (via
    `rotation_velocity` once snapshots accumulate), it reveals which
    narratives are heating up vs. cooling off.
    """
    tag_candidates(candidates)
    result: Dict[str, Dict[str, Any]] = {}
    for c in candidates:
        for tag in c.get("narrative") or []:
            bucket = result.setdefault(tag, {"count": 0, "samples": []})
            bucket["count"] += 1
            if len(bucket["samples"]) < 5:
                bucket["samples"].append(c.get("name") or c.get("slug") or "?")
    return result


def rotation_velocity(root: Path, today: Dict[str, Dict[str, Any]], window_days: int = 7) -> Dict[str, Dict[str, Any]]:
    """Compare today's narrative distribution against the last N days of
    historical narrative snapshots (written by snapshots.write_narrative_snapshot).

    Returns tag → {today, avg, velocity}. Positive velocity = narrative heating.
    """
    from lib import snapshots
    history = snapshots.read_narrative_history(window_days)
    if not history:
        return {tag: {"today": data["count"], "avg": None, "velocity": None} for tag, data in today.items()}

    # history is [{date, counts: {tag: int}}]
    all_tags = set(today.keys())
    for h in history:
        all_tags.update(h.get("counts", {}).keys())

    result: Dict[str, Dict[str, Any]] = {}
    for tag in all_tags:
        today_count = today.get(tag, {}).get("count", 0)
        past_counts = [h.get("counts", {}).get(tag, 0) for h in history]
        avg = sum(past_counts) / len(past_counts) if past_counts else 0
        velocity = today_count - avg
        result[tag] = {
            "today": today_count,
            "avg": round(avg, 2),
            "velocity": round(velocity, 2),
        }
    return result
