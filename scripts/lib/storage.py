"""Markdown-with-frontmatter storage for projects, KOLs, and reports.

Project files are plain markdown with YAML frontmatter plus a free-form body.
Obsidian renders frontmatter as the Properties panel and the body as normal
markdown.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import yaml


_SAMPLE_BYTES = 256
_STREAM_CHUNK_BYTES = 64 * 1024
_MAX_LINE_BYTES = 128 * 1024
_LARGE_FILE_BYTES = 8 * 1024 * 1024
_INT_RE = re.compile(r"^[+-]?[0-9]+$")
_FLOAT_RE = re.compile(
    r"^[+-]?(?:"
    r"(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
    r"|[0-9]+[eE][+-]?[0-9]+"
    r")$"
)


def _find_repo_root() -> Path:
    """Walk up from this file to find the repo root."""
    p = Path(__file__).resolve().parent
    for _ in range(5):
        p = p.parent
        if (p / "SKILL.md").exists():
            return p
    return Path.cwd()


def data_root() -> Path:
    """Return the Gold Digger data directory."""
    override = os.environ.get("GOLD_DIGGER_DATA")
    if override:
        return Path(override).expanduser()
    return _find_repo_root() / "data"


def ensure_layout() -> Path:
    """Create the standard subdirectory layout and return the data root."""
    root = data_root()
    for sub in ("projects", "kols", "reports/daily", "snapshots", "trends", "cache"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def cache_root() -> Path:
    """Return the cache directory, creating it if needed."""
    root = ensure_layout() / "cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def read_json_cache(path: Path) -> Any:
    """Best-effort JSON cache read. Returns None on missing/corrupt data."""
    if not path.exists():
        return None
    try:
        import json
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def write_json_cache(path: Path, data: Any) -> None:
    """Write JSON cache atomically enough for local single-user use."""
    path.parent.mkdir(parents=True, exist_ok=True)
    import json
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _yaml_dump(data: Dict[str, Any]) -> str:
    """Serialize frontmatter with a real YAML writer."""
    dumped = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=False,
        default_flow_style=False,
        width=10_000,
    )
    return dumped.strip()


def _yaml_parse(text: str) -> Dict[str, Any]:
    """Parse frontmatter with YAML syntax support while keeping yes/no as strings."""
    if not text.strip():
        return {}
    loaded = yaml.load(text, Loader=yaml.BaseLoader)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError("frontmatter must be a mapping")
    return {str(key): _coerce_loaded(value) for key, value in loaded.items()}


def _coerce_loaded(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _coerce_loaded(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_coerce_loaded(child) for child in value]
    if isinstance(value, str):
        return _coerce_scalar(value)
    return value


def _coerce_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"", "null", "~"}:
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if _INT_RE.fullmatch(value):
        try:
            return int(value)
        except ValueError:
            return value
    if _FLOAT_RE.fullmatch(value):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _append_sample(sample: bytearray, data: bytes) -> None:
    remaining = _SAMPLE_BYTES - len(sample)
    if remaining > 0:
        sample.extend(data[:remaining])


def _iter_lines_bounded(
    path: Path,
    *,
    max_line_bytes: int = _MAX_LINE_BYTES,
    chunk_size: int = _STREAM_CHUNK_BYTES,
) -> Iterator[Tuple[bytes, bool]]:
    """Yield logical lines without allowing a single line to consume unbounded memory."""
    line = bytearray()
    sample = bytearray()
    oversized = False

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                if line or sample or oversized:
                    yield (bytes(sample) if oversized else bytes(line), oversized)
                return

            start = 0
            while start < len(chunk):
                newline = chunk.find(b"\n", start)
                if newline == -1:
                    part = chunk[start:]
                    if oversized:
                        _append_sample(sample, part)
                    elif len(line) + len(part) <= max_line_bytes:
                        line.extend(part)
                    else:
                        _append_sample(sample, line)
                        _append_sample(sample, part)
                        line.clear()
                        oversized = True
                    break

                part = chunk[start:newline]
                if oversized:
                    _append_sample(sample, part)
                    yield bytes(sample), True
                else:
                    if len(line) + len(part) <= max_line_bytes:
                        line.extend(part)
                        yield bytes(line), False
                    else:
                        _append_sample(sample, line)
                        _append_sample(sample, part)
                        yield bytes(sample), True

                line.clear()
                sample.clear()
                oversized = False
                start = newline + 1


def salvage_project(
    path: Path,
    *,
    max_line_bytes: int = _MAX_LINE_BYTES,
) -> Tuple[Dict[str, Any], str, List[str]]:
    """Read a project file while skipping pathological oversized frontmatter lines."""
    if not path.exists():
        return {}, "", []

    mode = "start"
    frontmatter_lines: List[str] = []
    body_lines: List[str] = []
    skipped_keys: List[str] = []

    for raw_line, oversized in _iter_lines_bounded(path, max_line_bytes=max_line_bytes):
        line = raw_line.decode("utf-8", "replace").rstrip("\r")
        if mode == "start":
            if line == "---":
                mode = "frontmatter"
            else:
                mode = "body"
                body_lines.append(line)
            continue

        if mode == "frontmatter":
            if line == "---":
                mode = "body"
                continue
            if oversized:
                key = line.split(":", 1)[0].strip()
                if key:
                    skipped_keys.append(key)
                continue
            frontmatter_lines.append(line)
            continue

        body_lines.append(line)

    frontmatter = _yaml_parse("\n".join(frontmatter_lines)) if frontmatter_lines else {}
    body = "\n".join(body_lines)
    if body_lines:
        body += "\n"
    return frontmatter, body, skipped_keys


def read_project(path: Path) -> Tuple[Dict[str, Any], str]:
    """Return frontmatter and body. Falls back to streaming for large files."""
    if not path.exists():
        return {}, ""

    try:
        if path.stat().st_size > _LARGE_FILE_BYTES:
            frontmatter, body, _ = salvage_project(path)
            return frontmatter, body
    except OSError:
        pass

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text

    try:
        frontmatter = _yaml_parse(text[4:end])
    except (ValueError, yaml.YAMLError):
        frontmatter, body, _ = salvage_project(path)
        return frontmatter, body

    body = text[end + 5:]
    return frontmatter, body


def write_project(path: Path, frontmatter: Dict[str, Any], body: str) -> None:
    """Write a project file preserving the body."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "---\n" + _yaml_dump(frontmatter) + "\n---\n" + body
    path.write_text(content, encoding="utf-8")


def update_project_frontmatter(
    path: Path, updates: Dict[str, Any], touch_last_updated: bool = True
) -> Dict[str, Any]:
    """Merge updates into frontmatter while preserving the body."""
    existing, body = read_project(path)
    merged = {**existing, **{key: value for key, value in updates.items() if value is not None}}
    if touch_last_updated:
        merged["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    write_project(path, merged, body)
    return merged
