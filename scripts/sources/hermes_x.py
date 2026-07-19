"""Cross-agent SuperGrok OAuth source for X search.

Gold Digger can run under Claude Code, Codex, OpenClaw, Hermes, or a plain
cron process.  It shells out to the Hermes CLI solely as an OAuth/tool bridge,
then exports the resulting session to verify the tool result itself.  The
host agent does not need to use Hermes as its main model or runtime.

The final assistant text is never trusted for credential provenance: only an
actual tool result with ``credential_source: xai-oauth`` is accepted.
"""
from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sources import xai

MIN_HERMES_VERSION = (0, 14, 0)
SESSION_ID_RE = re.compile(r"session_id:\s*([A-Za-z0-9_-]+)")
VERSION_RE = re.compile(r"(?:Hermes(?: Agent)? v?|v)(\d+)\.(\d+)\.(\d+)", re.IGNORECASE)
_LAST_ERROR = threading.local()


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def _hermes_binary() -> Optional[str]:
    override = os.environ.get("GOLD_DIGGER_HERMES_BIN")
    if override:
        return override
    discovered = shutil.which("hermes")
    if discovered:
        return discovered
    # Agent services and cron often have a smaller PATH than an interactive
    # shell. Check the standard per-user install location before giving up.
    candidate = Path.home() / ".local" / "bin" / "hermes"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return None


def _run(command: List[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _parse_version(text: str) -> Optional[Tuple[int, int, int]]:
    match = VERSION_RE.search(text or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


@functools.lru_cache(maxsize=1)
def oauth_status() -> Tuple[bool, str]:
    """Return whether Hermes xAI OAuth is configured, without reading tokens."""
    binary = _hermes_binary()
    if not binary:
        return False, "hermes CLI not found"
    try:
        version = _run([binary, "--version"], timeout=10)
        parsed = _parse_version(version.stdout + version.stderr)
        if version.returncode != 0 or parsed is None:
            return False, "unable to verify Hermes version"
        if parsed < MIN_HERMES_VERSION:
            return False, f"Hermes {'.'.join(map(str, parsed))} is older than 0.14.0"

        auth = _run([binary, "auth", "list", "xai-oauth"], timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False, "Hermes OAuth status check failed"
    auth_text = auth.stdout + auth.stderr
    if auth.returncode != 0:
        return False, "Hermes xai-oauth status check failed"
    if not re.search(r"xai-oauth\s*\([1-9]\d*\s+credentials?\)", auth_text, re.IGNORECASE):
        return False, "no Hermes xai-oauth credential configured"
    if "oauth" not in auth_text.lower() or "xai_pkce" not in auth_text.lower():
        return False, "Hermes xai-oauth credential is not PKCE OAuth"
    return True, "Hermes SuperGrok OAuth ready"


def available() -> bool:
    return oauth_status()[0]


def paid_fallback_allowed() -> bool:
    """Require an explicit operator opt-in before separately billed X paths."""
    return os.environ.get("GOLD_DIGGER_ALLOW_PAID_X_FALLBACK", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def last_error() -> str:
    return str(getattr(_LAST_ERROR, "message", "") or "")


def _extract_session_id(stdout: str) -> Optional[str]:
    matches = SESSION_ID_RE.findall(stdout or "")
    return matches[-1] if matches else None


def _extract_verified_tool_result(export_text: str, session_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Extract a verified x_search tool payload from Hermes JSONL export."""
    records: List[Dict[str, Any]] = []
    for line in (export_text or "").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    for record in records:
        if str(record.get("id") or "") != session_id:
            continue
        for message in reversed(record.get("messages") or []):
            if not isinstance(message, dict) or message.get("role") != "tool" or message.get("tool_name") != "x_search":
                continue
            content = message.get("content")
            if isinstance(content, str):
                try:
                    payload = json.loads(content)
                except json.JSONDecodeError:
                    return None, "Hermes x_search tool returned invalid JSON"
            elif isinstance(content, dict):
                payload = content
            else:
                return None, "Hermes x_search tool result is missing"
            source = payload.get("credential_source")
            if source != "xai-oauth":
                if source == "xai":
                    return None, "refused paid XAI_API_KEY result (credential_source: xai)"
                return None, "unverified Hermes x_search credential_source"
            if payload.get("success") is not True:
                error = payload.get("error") or payload.get("degraded_reason") or "Hermes x_search failed"
                return None, str(error)
            return payload, ""
    return None, "Hermes session contained no x_search tool result"


def _search(prompt: str, timeout: Optional[int] = None) -> Tuple[Optional[Dict[str, Any]], str]:
    ready, reason = oauth_status()
    if not ready:
        return None, reason
    binary = _hermes_binary()
    if not binary:
        return None, "hermes CLI not found"
    timeout = timeout or _env_int("HERMES_X_SEARCH_TIMEOUT_SECONDS", 180)
    command = [
        binary,
        "chat",
        "-t",
        "x_search",
        "-Q",
        "--source",
        "tool",
        "--max-turns",
        "2",
        "--ignore-rules",
        "-q",
        prompt,
    ]
    try:
        chat = _run(command, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "Hermes x_search timed out"
    except OSError:
        return None, "Hermes x_search could not start"
    if chat.returncode != 0:
        return None, "Hermes x_search command failed"
    # Hermes may route quiet-mode session metadata to stderr when stdout is
    # captured rather than attached to a TTY.
    session_id = _extract_session_id(chat.stdout + "\n" + chat.stderr)
    if not session_id:
        return None, "Hermes x_search returned no session id"
    try:
        exported = _run(
            [
                binary, "sessions", "export", "-", "--format", "jsonl",
                "--session-id", session_id, "--redact", "--yes",
            ],
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None, "Hermes session export failed"
    if exported.returncode != 0:
        return None, "Hermes session export failed"
    return _extract_verified_tool_result(exported.stdout, session_id)


def _normalise_posts(handle: str, answer: str) -> Optional[List[Dict[str, Any]]]:
    posts = xai._extract_json_array(answer)
    if posts is None:
        return None
    normalised: List[Dict[str, Any]] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        text = post.get("text") or ""
        normalised.append({
            "handle": handle,
            "date": post.get("date"),
            "text": text,
            "url": post.get("url"),
            "tickers": xai.extract_tickers(text),
            "source": "xai-oauth",
        })
    return normalised


def fetch_kol_posts(handle: str, since_hours: int = 24, limit: int = 10) -> Optional[List[Dict[str, Any]]]:
    """Fetch KOL posts via verified SuperGrok OAuth; None means failure."""
    if not handle:
        return []
    cache_key = f"oauth|{handle}|{since_hours}|{limit}"
    fresh = xai._cache_get_current("kol-posts", cache_key)
    if isinstance(fresh, dict) and fresh.get("credential_source") == "xai-oauth" and isinstance(fresh.get("posts"), list):
        return fresh["posts"]

    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(hours=max(1, since_hours))).strftime("%Y-%m-%d")
    to_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    clean_handle = handle.strip().lstrip("@")
    prompt = (
        "Use exactly one x_search tool call. "
        f"Search the latest public posts from @{clean_handle} from {from_date} through {to_date}; "
        f"set allowed_x_handles to ['{clean_handle}'], from_date to '{from_date}', and to_date to '{to_date}'. "
        f"In the x_search query request at most {limit} posts from the last {since_hours} hours. "
        "The x_search answer must be ONLY a JSON array. Each item must contain date (ISO 8601 UTC), "
        "text (first 500 characters), and url (exact full x.com status URL). Return [] when none are found."
    )
    payload, error = _search(prompt)
    if not payload:
        _LAST_ERROR.message = error
        return None
    _LAST_ERROR.message = ""
    posts = _normalise_posts(clean_handle, str(payload.get("answer") or ""))
    if posts is None:
        return None
    xai._cache_store_current("kol-posts", cache_key, {
        "credential_source": "xai-oauth",
        "model": payload.get("model"),
        "posts": posts,
    })
    return posts


def search_x_mentions(query: str, since_hours: int = 168, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
    """Search X broadly via verified SuperGrok OAuth; None means failure."""
    if not query:
        return []
    cache_key = f"oauth|{query}|{since_hours}|{limit}"
    fresh = xai._cache_get_current("mentions", cache_key)
    if isinstance(fresh, dict) and fresh.get("credential_source") == "xai-oauth" and isinstance(fresh.get("posts"), list):
        return fresh["posts"]

    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(hours=max(1, since_hours))).strftime("%Y-%m-%d")
    to_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    prompt = (
        "Use exactly one x_search tool call. "
        f"Search X for posts mentioning {query!r} from {from_date} through {to_date}; "
        f"set from_date to '{from_date}' and to_date to '{to_date}'. "
        f"Request at most {limit} relevant recent posts from the last {since_hours} hours. "
        "The x_search answer must be ONLY a JSON array. Each item must contain date (ISO 8601 UTC), "
        "author (handle), text (first 500 characters), and url (exact full x.com status URL). Return [] when none are found."
    )
    payload, error = _search(prompt)
    if not payload:
        _LAST_ERROR.message = error
        return None
    _LAST_ERROR.message = ""
    posts = xai._extract_json_array(str(payload.get("answer") or ""))
    if posts is None:
        return None
    normalised = [post for post in posts if isinstance(post, dict)]
    xai._cache_store_current("mentions", cache_key, {
        "credential_source": "xai-oauth",
        "model": payload.get("model"),
        "posts": normalised,
    })
    return normalised
