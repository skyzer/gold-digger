"""last30days full integration — social, web, prediction markets, video, everything.

Calls last30days CLI with maximum-recall settings:
  --deep          : higher recall per source
  --store         : persist ALL findings to SQLite (compounding research lake)
  --web-backend parallel : fire ALL available search APIs simultaneously
  --auto-resolve  : discover where a project is discussed

Also wraps store.py (query, search, trending) and watchlist.py for
cross-session intelligence.

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
    env_path = os.environ.get("LAST30DAYS_ROOT")
    if env_path:
        p = Path(env_path).expanduser()
        if (p / "scripts" / "last30days.py").exists():
            return p
    for p in DEFAULT_INSTALL_PATHS:
        if (p / "scripts" / "last30days.py").exists():
            return p
    return None


def _uv_prefix() -> List[str]:
    root = _locate_last30days()
    if not root:
        return []
    return ["uv", "run", "--project", str(root), "python"]


def _run(topic: str, extra_args: List[str], timeout: int = 300) -> Optional[Dict[str, Any]]:
    """Invoke last30days with full-power flags. Returns parsed JSON or None.

    Every call:
      --deep              higher recall (was --quick)
      --store             persist to SQLite for compounding queries
      --web-backend parallel  fire ALL available search APIs
      --auto-resolve      discover subreddits/handles automatically
    """
    root = _locate_last30days()
    if not root:
        return None
    if shutil.which("uv") is None:
        return None
    cmd = [
        *_uv_prefix(),
        str(root / "scripts" / "last30days.py"),
        "--emit=json",
        "--deep",
        "--store",
        "--web-backend", "parallel",
        "--auto-resolve",
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
        for line in reversed(result.stdout.splitlines()):
            line = line.strip()
            if line.startswith("{") or line.startswith("["):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None


def _run_store(subcommand: str, args: List[str], timeout: int = 30) -> Optional[str]:
    """Run store.py subcommand, return raw stdout."""
    root = _locate_last30days()
    if not root:
        return None
    cmd = [*_uv_prefix(), str(root / "scripts" / "store.py"), subcommand, *args]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env={**os.environ},
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return result.stdout if result.returncode == 0 else None


# ---------------------------------------------------------------------------
# Public API — research functions
# ---------------------------------------------------------------------------

def available() -> bool:
    return _locate_last30days() is not None and shutil.which("uv") is not None


def research_topic(topic: str, days: int = 7) -> Optional[Dict[str, Any]]:
    """Run a full-power topic research pass."""
    return _run(topic, [f"--days={days}"])


def research_handle(handle: str, days: int = 7) -> Optional[Dict[str, Any]]:
    """Research a specific X handle."""
    return _run(handle, [f"--days={days}", f"--x-handle={handle}"])


def research_with_related(topic: str, related_handles: List[str], days: int = 7) -> Optional[Dict[str, Any]]:
    """Research a topic + discover content from related X handles."""
    related_str = ",".join(related_handles)
    return _run(topic, [f"--days={days}", f"--x-related={related_str}"])


def discover_related_handles(handle: str) -> Optional[Dict[str, Any]]:
    """Use --x-related to find handles similar to a tracked KOL.

    Returns last30days' output which includes discovered handles + their
    recent posts. Gold Digger extracts handles from the output.
    """
    return _run(
        f"crypto AI agent projects mentioned by @{handle}",
        [f"--x-related={handle}", "--days=7"],
    )


# ---------------------------------------------------------------------------
# Store API — query the compounding research lake
# ---------------------------------------------------------------------------

def store_query(topic: str, days: int = 90) -> Optional[str]:
    """Query accumulated findings for a topic from the SQLite store."""
    return _run_store("query", [topic, "--days", str(days)])


def store_search(query: str) -> Optional[str]:
    """FTS5 full-text search across ALL historical findings."""
    return _run_store("search", [query])


def store_trending() -> Optional[str]:
    """What topics are trending across all research runs."""
    return _run_store("trending", [])


def store_stats() -> Optional[str]:
    """Database statistics: total findings, topics, date range."""
    return _run_store("stats", [])


# ---------------------------------------------------------------------------
# Source class
# ---------------------------------------------------------------------------

class Last30Days(Source):
    """Full social + web + prediction market research via last30days.

    Covers: Reddit (all subreddits), HN, YouTube, Polymarket, Bluesky,
    TikTok, Instagram, web search (Brave + Exa + Serper in parallel).

    Every call persists to the SQLite store (--store), so the research
    compounds across days without Gold Digger needing to re-query.
    """
    name = "last30days"
    requires_keys: List[str] = []

    def available(self, keys: Dict[str, Optional[str]]) -> bool:
        return available()

    def fetch_watchlist(self, project: Dict[str, Any], keys: Dict[str, Optional[str]]) -> Dict[str, Any]:
        """Pull general social buzz across ALL platforms."""
        from lib import entity as entity_lib

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

        all_items: List[Dict[str, Any]] = []
        if isinstance(payload, dict):
            for k in ("items", "results", "threads", "findings", "posts"):
                val = payload.get(k)
                if isinstance(val, list):
                    all_items.extend(val)

        if not all_items:
            return {"mention_count_30d": 0}

        # Entity disambiguation: filter false positives
        project_identity = {
            "name": name,
            "ticker": ticker,
            "twitter": twitter,
        }
        verified_items = entity_lib.filter_relevant_mentions(all_items, project_identity)

        updates: Dict[str, Any] = {"mention_count_30d": len(verified_items)}
        top_sources: List[str] = []
        for item in verified_items:
            url = item.get("url") or item.get("link")
            if url and len(top_sources) < 5:
                top_sources.append(url)
        existing = project.get("sources") or []
        for url in top_sources:
            if url not in existing:
                existing.append(url)
        if top_sources:
            updates["sources"] = existing[:20]
        return updates

    def fetch_scout(self, keys: Dict[str, Optional[str]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Social scout: trending topics from the store + fresh search."""
        if not available():
            return []
        from lib import entity as entity_lib

        # Pull trending from the store (accumulated across all prior runs)
        trending_raw = store_trending()
        candidates: List[Dict[str, Any]] = []
        # Trending output is free-form text; extract tickers/names from it
        if trending_raw:
            tickers = entity_lib.extract_crypto_entities(trending_raw)
            for t in tickers[:10]:
                candidates.append({
                    "slug": t.lower().replace(" ", "-"),
                    "name": t,
                    "narrative": ["ai-crypto"],
                    "tier": "scout",
                    "sources": ["last30days-store-trending"],
                })
        return candidates
