"""Daily snapshot writer + reader.

Each daily run writes a single `snapshots/YYYY-MM-DD.md` file: one row per
tracked project, columns for price/mcap/social/mention signals. Markdown
tables are fully Obsidian-readable AND parseable by the aggregator.

The aggregator reads N days of snapshots to compute velocity and divergence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib import storage

# Canonical column order — add new columns at the end to preserve parseability.
COLUMNS: List[str] = [
    "slug",
    "name",
    "ticker",
    "tier",
    "price_usd",
    "mcap",
    "fdv",
    "change_24h_pct",
    "change_7d_pct",
    "change_30d_pct",
    "twitter_followers",
    "github_stars",
    "github_commits_30d",
    "tvl_usd",
    "mention_count_7d",
    "mention_count_30d",
]


def _snapshots_dir() -> Path:
    d = storage.data_root() / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cell(value: Any) -> str:
    """Render a value for a markdown table cell."""
    if value is None:
        return "—"
    if isinstance(value, float):
        if abs(value) >= 1e9:
            return f"{value/1e9:.2f}B"
        if abs(value) >= 1e6:
            return f"{value/1e6:.2f}M"
        if abs(value) >= 1e3:
            return f"{value/1e3:.2f}k"
        if abs(value) < 1 and abs(value) > 0:
            return f"{value:.6f}"
        return f"{value:.2f}"
    if isinstance(value, int):
        if value >= 1_000_000:
            return f"{value/1e6:.2f}M"
        if value >= 1_000:
            return f"{value/1e3:.1f}k"
        return str(value)
    return str(value)


def _raw_cell(value: Any) -> str:
    """Render a value as a machine-parseable cell (no scaling)."""
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    return str(value)


def write_daily_snapshot(projects: List[Dict[str, Any]], date: Optional[str] = None) -> Path:
    """Write a snapshot row per project to today's file. Preserves any prior
    snapshot for the same date by overwriting (idempotent within a day).

    Writes TWO tables:
      1. Human-readable (formatted numbers, for Obsidian display)
      2. Raw values section (for aggregator parsing — unformatted)
    """
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = _snapshots_dir() / f"{date}.md"

    lines = [f"# Gold Digger snapshot — {date}", ""]
    lines.append(f"_{len(projects)} projects tracked_")
    lines.append("")

    # Pretty table
    header = "| " + " | ".join(COLUMNS) + " |"
    sep = "| " + " | ".join(["---"] * len(COLUMNS)) + " |"
    lines.append(header)
    lines.append(sep)
    for p in sorted(projects, key=lambda x: (x.get("mcap") or 0)):
        row = "| " + " | ".join(_cell(p.get(c)) for c in COLUMNS) + " |"
        lines.append(row)

    # Raw values as a fenced code block for machine parsing
    lines.append("")
    lines.append("## Raw values (machine-readable)")
    lines.append("")
    lines.append("```csv")
    lines.append(",".join(COLUMNS))
    for p in projects:
        lines.append(",".join(_raw_cell(p.get(c)) for c in COLUMNS))
    lines.append("```")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def read_snapshot(date: str) -> List[Dict[str, Any]]:
    """Parse a snapshot file's raw CSV block back into a list of dicts."""
    path = _snapshots_dir() / f"{date}.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    # Find ```csv ... ```
    marker = "```csv"
    start = text.find(marker)
    if start == -1:
        return []
    start += len(marker)
    end = text.find("```", start)
    if end == -1:
        return []
    block = text[start:end].strip()
    lines = [l for l in block.splitlines() if l.strip()]
    if not lines:
        return []
    headers = lines[0].split(",")
    result = []
    for line in lines[1:]:
        parts = line.split(",")
        row = {}
        for i, h in enumerate(headers):
            val = parts[i] if i < len(parts) else ""
            if val == "":
                row[h] = None
            else:
                # Coerce numerics
                try:
                    row[h] = float(val) if "." in val else int(val)
                except ValueError:
                    row[h] = val
        result.append(row)
    return result


def recent_snapshots(days: int = 7) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """Return (date, rows) tuples for the last N days of snapshots."""
    d = _snapshots_dir()
    if not d.exists():
        return []
    files = sorted(d.glob("*.md"), reverse=True)[:days]
    return [(f.stem, read_snapshot(f.stem)) for f in files]
