"""last30days subprocess adapter.

Calls the last30days CLI (`uv run --project <path> python scripts/last30days.py`)
with `--emit=json` and parses the output. Gold Digger uses this for cross-platform
social + web research (Reddit, HN, YouTube, Polymarket, web).

Does NOT reimplement anything — last30days owns the research logic.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from sources._base import Source

DEFAULT_INSTALL_PATHS = [
    Path.home() / "projects" / "last30days-skill",
    Path.home() / ".claude" / "skills" / "last30days-skill",
]


def _locate_last30days() -> Optional[Path]:
    """Find the last30days repo on disk. Returns the project root or None."""
    # Env override
    env_path = os.environ.get("LAST30DAYS_ROOT")
    if env_path:
        p = Path(env_path).expanduser()
        if (p / "scripts" / "last30days.py").exists():
            return p
    for p in DEFAULT_INSTALL_PATHS:
        if (p / "scripts" / "last30days.py").exists():
            return p
    return None


def _run(topic: str, extra_args: List[str], timeout: int = 180) -> Optional[Dict[str, Any]]:
    """Invoke last30days as a subprocess. Returns parsed JSON or None."""
    root = _locate_last30days()
    if not root:
        return None
    if shutil.which("uv") is None:
        return None
    cmd = [
        "uv", "run", "--project", str(root),
        "python", str(root / "scripts" / "last30days.py"),
        "--emit=json",
        "--quick",
        *extra_args,
        topic,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ},
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # last30days may emit a JSON object on the last non-empty line
        for line in reversed(result.stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None


def available() -> bool:
    """Is last30days installed and runnable?"""
    return _locate_last30days() is not None and shutil.which("uv") is not None


def research_topic(topic: str, days: int = 7) -> Optional[Dict[str, Any]]:
    """Run a generic topic research pass. Returns last30days' JSON payload."""
    return _run(topic, [f"--days={days}"])


def research_handle(handle: str, days: int = 7) -> Optional[Dict[str, Any]]:
    """Research a specific X handle via last30days."""
    return _run(handle, [f"--days={days}", f"--x-handle={handle}"])


class Last30Days(Source):
    """Social + web research via last30days subprocess.

    This is the GENERAL social signal — covers Reddit, HN, YouTube, Polymarket,
    Bluesky, web search, etc. Complements xai.py which focuses on tracked KOLs.
    Together they answer: "what are KOLs saying?" (xai) + "what is the internet
    saying?" (last30days).
    """
    name = "last30days"
    requires_keys: List[str] = []  # last30days has its own graceful degradation

    def available(self, keys: Dict[str, Optional[str]]) -> bool:
        return available()

    def fetch_watchlist(self, project: Dict[str, Any], keys: Dict[str, Optional[str]]) -> Dict[str, Any]:
        """Pull general social buzz for a project across Reddit, HN, YouTube,
        Polymarket, web, and X (non-KOL). Returns mention count + top sources."""
        # Build a broad query: name + ticker + twitter handle
        parts = []
        name = project.get("name")
        ticker = project.get("ticker")
        twitter = project.get("twitter")
        if ticker:
            parts.append(f"${ticker}")
        if name and name != ticker:
            parts.append(name)
        if twitter and twitter.lower() not in (name or "").lower():
            parts.append(f"@{twitter}")
        if not parts:
            return {}
        topic = " ".join(parts)
        payload = research_topic(topic, days=30)
        if not payload:
            return {}

        # Extract structured signals from the last30days JSON payload.
        # The payload shape varies across last30days versions, so we try
        # multiple keys defensively.
        updates: Dict[str, Any] = {}
        all_items: List[Dict[str, Any]] = []
        if isinstance(payload, dict):
            for k in ("items", "results", "threads", "findings", "posts"):
                val = payload.get(k)
                if isinstance(val, list):
                    all_items.extend(val)

        if all_items:
            updates["mention_count_30d"] = len(all_items)
            # Extract platform breakdown for the project body
            platforms: Dict[str, int] = {}
            top_sources: List[str] = []
            for item in all_items:
                platform = item.get("source") or item.get("platform") or item.get("type") or "unknown"
                platforms[platform] = platforms.get(platform, 0) + 1
                url = item.get("url") or item.get("link")
                if url and len(top_sources) < 5:
                    top_sources.append(url)
            # Store top sources as provenance
            existing = project.get("sources") or []
            for url in top_sources:
                if url not in existing:
                    existing.append(url)
            if top_sources:
                updates["sources"] = existing[:20]  # cap at 20
        else:
            updates["mention_count_30d"] = 0

        return updates

    def fetch_scout(self, keys: Dict[str, Optional[str]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """General social scout: search last30days for "ai crypto agents new
        launches" and surface anything that mentions a project Gold Digger
        hasn't seen before. Cheap broad net."""
        if not available():
            return []
        payload = research_topic("ai crypto agents new token launch 2026", days=7)
        if not payload or not isinstance(payload, dict):
            return []
        # Try to extract project names/tickers from findings
        candidates: List[Dict[str, Any]] = []
        all_items: List[Dict[str, Any]] = []
        for k in ("items", "results", "threads", "findings", "posts"):
            val = payload.get(k)
            if isinstance(val, list):
                all_items.extend(val)
        # For v0.5 this is a stub — the items don't have structured project
        # data. A future version will run NER/ticker extraction over the text.
        return candidates
