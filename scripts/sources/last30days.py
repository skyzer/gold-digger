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
    name = "last30days"
    requires_keys: List[str] = []  # last30days has its own graceful degradation

    def available(self, keys: Dict[str, Optional[str]]) -> bool:
        return available()

    def fetch_watchlist(self, project: Dict[str, Any], keys: Dict[str, Optional[str]]) -> Dict[str, Any]:
        """Pull recent social buzz for this project. v0.2: returns mention_count_30d
        as the headline number; finer-grained extraction in v0.3."""
        topic_parts = []
        name = project.get("name")
        ticker = project.get("ticker")
        if ticker:
            topic_parts.append(f"${ticker}")
        if name and name != ticker:
            topic_parts.append(name)
        if not topic_parts:
            return {}
        topic = " ".join(topic_parts)
        payload = research_topic(topic, days=30)
        if not payload:
            return {}
        # last30days returns a shape we can't fully predict across versions.
        # Extract a rough "total items" count as mention_count_30d.
        count = 0
        if isinstance(payload, dict):
            for key in ("items", "results", "threads", "findings"):
                items = payload.get(key)
                if isinstance(items, list):
                    count += len(items)
        return {"mention_count_30d": count or None}
