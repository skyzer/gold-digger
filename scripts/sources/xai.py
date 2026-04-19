"""xAI (grok) source — KOL feed polling via the Agent Tools API.

Uses the /v1/responses endpoint with the `x_search` tool, which lets grok
hit X's search directly. Cost per call is typically $0.01-$0.05.

Reference: https://docs.x.ai/docs/guides/tools/overview
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from lib import storage
from sources._base import Source

XAI_ENDPOINT = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-4.20-reasoning"

# TTLs per cache kind. Keep short enough that same-day repeat runs stay fresh,
# but long enough that manual re-runs within a short window are cheap.
# Override via XAI_CACHE_TTL_* env vars for debugging.
_TTL_SECONDS: Dict[str, int] = {
    "kol-posts": 30 * 60,   # 30 min — KOLs post throughout the day
    "mentions":  60 * 60,   # 60 min — broader, less time-sensitive
}


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cache_path(kind: str) -> Path:
    return storage.cache_root() / f"xai-{kind}-{_today_utc()}.json"


def _cache_load(kind: str) -> Dict[str, Any]:
    data = storage.read_json_cache(_cache_path(kind))
    return data if isinstance(data, dict) else {}


def _cache_save(kind: str, data: Dict[str, Any]) -> None:
    storage.write_json_cache(_cache_path(kind), data)


def _cache_get_fresh(cache: Dict[str, Any], key: str, kind: str) -> Optional[Any]:
    """Return cached data if the entry exists AND is within TTL.

    Handles both new wrapped format {fetched_at, data} and legacy flat format
    (treats legacy entries as expired so they get refreshed on next run).
    """
    entry = cache.get(key)
    if entry is None:
        return None
    # Legacy flat entry (pre-TTL) — treat as expired to force refresh
    if not isinstance(entry, dict) or "fetched_at" not in entry:
        return None
    fetched_at = entry.get("fetched_at")
    if not isinstance(fetched_at, str):
        return None
    try:
        # ISO 8601 with Z suffix
        ts = datetime.strptime(fetched_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    ttl = _TTL_SECONDS.get(kind, 30 * 60)
    if age > ttl:
        return None
    return entry.get("data")


def _cache_put(cache: Dict[str, Any], key: str, data: Any) -> None:
    """Store data in the cache dict with a fetched_at timestamp."""
    cache[key] = {"fetched_at": _now_utc_iso(), "data": data}


def _post(body: Dict[str, Any], key: str, timeout: int = 25) -> Optional[Dict[str, Any]]:
    """POST to xAI, return parsed JSON or None on any failure."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(XAI_ENDPOINT, data=data, method="POST")
    req.add_header("authorization", f"Bearer {key}")
    req.add_header("content-type", "application/json")
    req.add_header("user-agent", "gold-digger/0.1")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError:
        return None
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def _extract_message_text(response: Dict[str, Any]) -> Optional[str]:
    """Pull the final assistant message text out of the responses API output."""
    output = response.get("output") or []
    for item in output:
        if item.get("type") == "message" and item.get("role") == "assistant":
            content = item.get("content") or []
            for chunk in content:
                if chunk.get("type") == "output_text":
                    return chunk.get("text")
    return None


def _extract_json_array(text: str) -> Optional[List[Any]]:
    """Best-effort JSON array extractor — handles cases where the model wraps
    the array in explanatory text or code fences."""
    if not text:
        return None
    # Try direct parse first
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    # Strip code fences
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    # Find first `[` and last `]`
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


#: Regex for extracting $TICKER mentions from post text. Requires the dollar
#: sign to disambiguate from English words. Case-insensitive: `$serv` and
#: `$SERV` both match, then normalised to uppercase. 2-10 alphanumeric chars.
TICKER_RE = re.compile(r"\$([A-Za-z][A-Za-z0-9]{1,9})\b")


def extract_tickers(text: str) -> List[str]:
    """Return unique uppercased ticker symbols mentioned in a post body."""
    if not text:
        return []
    found = [t.upper() for t in TICKER_RE.findall(text)]
    # Preserve order, dedupe
    seen: List[str] = []
    for ticker in found:
        if ticker not in seen:
            seen.append(ticker)
    return seen


def fetch_kol_posts(handle: str, key: str, since_hours: int = 24, limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch recent posts by a single KOL. Returns a list of dicts with
    keys: date (ISO), text, url. Empty list on failure."""
    if not key or not handle:
        return []
    cache_key = f"{handle}|{since_hours}|{limit}"
    cache = _cache_load("kol-posts")
    fresh = _cache_get_fresh(cache, cache_key, "kol-posts")
    if isinstance(fresh, list):
        return fresh
    prompt = (
        f"Find the {limit} most recent posts from @{handle} on X "
        f"within the last {since_hours} hours. "
        "For each post return: date (ISO 8601 UTC with Z), text (first 500 chars), "
        "url (full x.com post URL). "
        "Return ONLY a JSON array with no surrounding text, markdown, or code fences. "
        "If no posts found in the window, return []."
    )
    body = {
        "model": DEFAULT_MODEL,
        "stream": False,
        "input": [{"role": "user", "content": prompt}],
        "tools": [{"type": "x_search"}],
    }
    response = _post(body, key, timeout=20)
    if not response:
        return []
    text = _extract_message_text(response)
    if not text:
        return []
    posts = _extract_json_array(text)
    if not posts:
        return []
    # Normalise + attach extracted tickers
    normalised: List[Dict[str, Any]] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        body_text = post.get("text") or ""
        normalised.append({
            "handle": handle,
            "date": post.get("date"),
            "text": body_text,
            "url": post.get("url"),
            "tickers": extract_tickers(body_text),
        })
    _cache_put(cache, cache_key, normalised)
    _cache_save("kol-posts", cache)
    return normalised


def search_x_mentions(query: str, key: str, since_hours: int = 168, limit: int = 20) -> List[Dict[str, Any]]:
    """Search X broadly for mentions of a project/ticker (not handle-restricted).
    Used for mention-count aggregation across all of X."""
    if not key:
        return []
    cache_key = f"{query}|{since_hours}|{limit}"
    cache = _cache_load("mentions")
    fresh = _cache_get_fresh(cache, cache_key, "mentions")
    if isinstance(fresh, list):
        return fresh
    prompt = (
        f"Search X for posts mentioning '{query}' in the last {since_hours} hours. "
        f"Return the {limit} most relevant recent posts. "
        "For each post return: date (ISO), author (handle), text (first 500 chars), url. "
        "Return ONLY a JSON array, no prose, no code fences."
    )
    body = {
        "model": DEFAULT_MODEL,
        "stream": False,
        "input": [{"role": "user", "content": prompt}],
        "tools": [{"type": "x_search"}],
    }
    response = _post(body, key, timeout=20)
    if not response:
        return []
    text = _extract_message_text(response)
    if not text:
        return []
    parsed = _extract_json_array(text)
    if not parsed:
        return []
    normalised = [p for p in parsed if isinstance(p, dict)]
    _cache_put(cache, cache_key, normalised)
    _cache_save("mentions", cache)
    return normalised


class XaiGrok(Source):
    name = "xai"
    requires_keys = ["XAI_API_KEY"]

    def fetch_watchlist(self, project: Dict[str, Any], keys: Dict[str, Optional[str]]) -> Dict[str, Any]:
        """Count X mentions of this project in the last 7 days."""
        key = keys.get("XAI_API_KEY")
        if not key:
            return {}
        # Build a search term: prefer ticker, fall back to name
        ticker = project.get("ticker")
        name = project.get("name")
        if ticker:
            query = f"${ticker} OR {name}" if name else f"${ticker}"
        elif name:
            query = name
        else:
            return {}
        mentions = search_x_mentions(query, key, since_hours=168, limit=25)
        return {
            "mention_count_7d": len(mentions),
        }
