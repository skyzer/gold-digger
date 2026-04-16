"""Markdown-with-frontmatter storage for projects, KOLs, and reports.

Project files are plain .md with YAML frontmatter + free-form body. Obsidian
renders frontmatter as the Properties panel; body as normal markdown.

We parse frontmatter manually (no python-frontmatter dependency) so the
script runs on a vanilla Python 3.12+ install with no extras for v0.1.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple


def _find_repo_root() -> Path:
    """Walk up from this file to find the repo root (has SKILL.md)."""
    p = Path(__file__).resolve().parent  # scripts/lib/
    for _ in range(5):
        p = p.parent
        if (p / "SKILL.md").exists():
            return p
    return Path.cwd()


def data_root() -> Path:
    """Return the Gold Digger data directory.

    Resolution order:
        1. GOLD_DIGGER_DATA env var (explicit override)
        2. <repo-root>/data/  (default — lives inside the repo, gitignored)
    """
    override = os.environ.get("GOLD_DIGGER_DATA")
    if override:
        return Path(override).expanduser()
    return _find_repo_root() / "data"


def ensure_layout() -> Path:
    """Create the standard subdirectory layout and return the data root."""
    root = data_root()
    for sub in ("projects", "kols", "reports/daily", "snapshots", "trends"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def _yaml_dump(data: Dict[str, Any]) -> str:
    """Minimal YAML emitter for flat dicts with list values. Deterministic
    key order = insertion order. Good enough for frontmatter."""
    lines = []
    for key, value in data.items():
        lines.append(f"{key}: {_yaml_value(value)}")
    return "\n".join(lines)


def _yaml_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        # Inline list for simple scalars
        if all(isinstance(v, (str, int, float, bool)) or v is None for v in value):
            inner = ", ".join(_yaml_scalar(v) for v in value)
            return f"[{inner}]"
        # Multiline for nested
        return "\n" + "\n".join(f"  - {_yaml_value(v)}" for v in value)
    if isinstance(value, dict):
        return "\n" + "\n".join(f"  {k}: {_yaml_value(v)}" for k, v in value.items())
    # string
    s = str(value)
    # Quote if it contains anything that could be YAML-special
    if any(c in s for c in ":#[]{},&*!|>'\"%@`") or s.strip() != s or not s:
        return f'"{s.replace(chr(92), chr(92)*2).replace(chr(34), chr(92) + chr(34))}"'
    return s


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    if any(c in s for c in ":#[]{},&*!|>'\"%@`") or s.strip() != s or not s:
        return f'"{s.replace(chr(92), chr(92)*2).replace(chr(34), chr(92) + chr(34))}"'
    return s


def _yaml_parse(text: str) -> Dict[str, Any]:
    """Minimal YAML parser for the subset we emit. Handles scalars, inline lists,
    multiline lists with `- ` prefix, and null/bool/number coercion."""
    result: Dict[str, Any] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        if not raw.strip() or raw.strip().startswith("#"):
            i += 1
            continue
        if not raw.startswith(" ") and ":" in raw:
            key, _, rest = raw.partition(":")
            key = key.strip()
            rest = rest.strip()
            # Inline value
            if rest and not rest.startswith("["):
                result[key] = _coerce(rest)
                i += 1
                continue
            # Inline list
            if rest.startswith("["):
                inner = rest[1:-1] if rest.endswith("]") else rest[1:]
                items = [s.strip() for s in inner.split(",") if s.strip()]
                result[key] = [_coerce(x) for x in items]
                i += 1
                continue
            # Multiline list: following lines starting with `  - `
            items = []
            i += 1
            while i < len(lines) and lines[i].startswith("  - "):
                items.append(_coerce(lines[i][4:].strip()))
                i += 1
            result[key] = items
            continue
        i += 1
    return result


def _coerce(value: str) -> Any:
    """Coerce a raw YAML scalar string to Python type."""
    if value == "null" or value == "~" or value == "":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    # Strip matching quotes
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    # Try numeric
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        pass
    return value


def read_project(path: Path) -> Tuple[Dict[str, Any], str]:
    """Return (frontmatter, body). Body preserves all user-authored notes."""
    if not path.exists():
        return {}, ""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    frontmatter = _yaml_parse(text[4:end])
    body = text[end + 5:]
    return frontmatter, body


def write_project(path: Path, frontmatter: Dict[str, Any], body: str) -> None:
    """Write a project file preserving the structure. Never destroys body."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "---\n" + _yaml_dump(frontmatter) + "\n---\n" + body
    path.write_text(content, encoding="utf-8")


def update_project_frontmatter(
    path: Path, updates: Dict[str, Any], touch_last_updated: bool = True
) -> Dict[str, Any]:
    """Merge `updates` into the frontmatter of `path`, preserving body and
    any fields the user added manually. Returns the merged frontmatter."""
    existing, body = read_project(path)
    merged = {**existing, **{k: v for k, v in updates.items() if v is not None}}
    if touch_last_updated:
        merged["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    write_project(path, merged, body)
    return merged
