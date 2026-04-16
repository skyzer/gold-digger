"""Export the full Gold Digger state as JSON / JSONL.

Produces two files:
  - export.json   : single object with all projects, KOLs, latest snapshot,
                    KOL memory, and report summaries
  - export.jsonl  : one JSON object per line per project (streamable)

Other agents can `cat export.json | jq ...` or feed it to an LLM as context.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib import storage, snapshots


def _read_all_projects() -> List[Dict[str, Any]]:
    root = storage.data_root()
    projects_dir = root / "projects"
    if not projects_dir.exists():
        return []
    result = []
    for path in sorted(projects_dir.glob("*.md")):
        fm, body = storage.read_project(path)
        fm["_body_preview"] = body.strip()[:500] if body else ""
        result.append(fm)
    return result


def _read_all_kols() -> List[Dict[str, Any]]:
    root = storage.data_root()
    kols_dir = root / "kols"
    if not kols_dir.exists():
        return []
    result = []
    for path in sorted(kols_dir.glob("*.md")):
        fm, _ = storage.read_project(path)
        result.append(fm)
    return result


def _read_kol_memory() -> List[Dict[str, str]]:
    root = storage.data_root()
    path = root / "trends" / "kol-mentions.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    records = []
    in_table = False
    headers = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("| date "):
            headers = [h.strip() for h in line.strip("|").split("|")]
            in_table = True
            continue
        if line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            record = {}
            for i, h in enumerate(headers):
                record[h] = cells[i] if i < len(cells) else ""
            records.append(record)
        elif in_table:
            in_table = False
    return records


def _latest_snapshot() -> Optional[Dict[str, Any]]:
    root = storage.data_root()
    snap_dir = root / "snapshots"
    if not snap_dir.exists():
        return None
    files = sorted(snap_dir.glob("*.md"))
    if not files:
        return None
    latest = files[-1]
    rows = snapshots.read_snapshot(latest.stem)
    return {"date": latest.stem, "projects": rows}


def _recent_reports(days: int = 7) -> List[Dict[str, str]]:
    root = storage.data_root()
    reports_dir = root / "reports" / "daily"
    if not reports_dir.exists():
        return []
    result = []
    for path in sorted(reports_dir.glob("*-brief.md"))[-days:]:
        text = path.read_text(encoding="utf-8")
        result.append({"date": path.stem.replace("-brief", ""), "brief": text})
    return result


def build_export(since: Optional[str] = None) -> Dict[str, Any]:
    """Build the full export payload."""
    projects = _read_all_projects()
    kols = _read_all_kols()
    memory = _read_kol_memory()
    snapshot = _latest_snapshot()
    reports = _recent_reports(days=30)

    if since:
        memory = [m for m in memory if (m.get("first_seen") or "") >= since]
        reports = [r for r in reports if r.get("date", "") >= since]

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "gold_digger_version": "0.5",
        "data_root": str(storage.data_root()),
        "summary": {
            "total_projects": len(projects),
            "tracked": len([p for p in projects if p.get("tier") == "tracked"]),
            "scout": len([p for p in projects if p.get("tier") == "scout"]),
            "total_kols": len(kols),
            "kol_mentions_recorded": len(memory),
            "daily_reports": len(reports),
        },
        "projects": projects,
        "kols": kols,
        "kol_memory": memory,
        "latest_snapshot": snapshot,
        "recent_reports": reports,
    }


def write_export(since: Optional[str] = None) -> tuple[Path, Path]:
    """Write export.json + export.jsonl to the data root. Returns both paths."""
    root = storage.data_root()
    payload = build_export(since=since)

    json_path = root / "export.json"
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    jsonl_path = root / "export.jsonl"
    lines = []
    for project in payload.get("projects", []):
        lines.append(json.dumps(project, default=str))
    jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return json_path, jsonl_path
