"""X API v2 source — deterministic public-post reads via app-only bearer auth.

This is the cheap fallback for social signal when xAI's `x_search` tool is
unfunded or unavailable. It does not ask Grok to reason over X; it fetches raw
public posts, extracts tickers locally, and caches daily results.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib import storage
from sources._base import Source
from sources.xai import extract_tickers

X_API_BASE = "https://api.x.com/2"
USER_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60

_TTL_SECONDS: Dict[str, int] = {
    "kol-posts": 30 * 60,
    "mentions": 60 * 60,
    "users": USER_CACHE_TTL_SECONDS,
}
_CACHE_LOCKS: Dict[str, threading.Lock] = {}
_CACHE_LOCKS_GUARD = threading.Lock()
_BUDGET_LOCK = threading.Lock()


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _start_time(hours: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=max(1, hours))
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def _cache_path(kind: str) -> Path:
    if kind == "users":
        return storage.cache_root() / "x-api-users.json"
    return storage.cache_root() / f"x-api-{kind}-{_today_utc()}.json"


def _usage_path() -> Path:
    return storage.cache_root() / f"x-api-usage-{_today_utc()}.json"


def _cache_lock(kind: str) -> threading.Lock:
    with _CACHE_LOCKS_GUARD:
        lock = _CACHE_LOCKS.get(kind)
        if lock is None:
            lock = threading.Lock()
            _CACHE_LOCKS[kind] = lock
        return lock


def _cache_load(kind: str) -> Dict[str, Any]:
    data = storage.read_json_cache(_cache_path(kind))
    return data if isinstance(data, dict) else {}


def _cache_save(kind: str, data: Dict[str, Any]) -> None:
    storage.write_json_cache(_cache_path(kind), data)


def _cache_get_current(kind: str, key: str) -> Optional[Any]:
    with _cache_lock(kind):
        cache = _cache_load(kind)
        entry = cache.get(key)
        if not isinstance(entry, dict) or "fetched_at" not in entry:
            return None
        try:
            ts = datetime.strptime(entry["fetched_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None
        if (datetime.now(timezone.utc) - ts).total_seconds() > _TTL_SECONDS.get(kind, 30 * 60):
            return None
        return entry.get("data")


def _cache_store_current(kind: str, key: str, data: Any) -> None:
    with _cache_lock(kind):
        cache = _cache_load(kind)
        cache[key] = {"fetched_at": _now_utc_iso(), "data": data}
        _cache_save(kind, cache)


def _consume_call_budget() -> bool:
    """Return True if another live X API request is allowed today."""
    max_calls = _env_int("X_API_DAILY_MAX_CALLS", 75)
    with _BUDGET_LOCK:
        path = _usage_path()
        data = storage.read_json_cache(path)
        if not isinstance(data, dict):
            data = {"date": _today_utc(), "calls": 0}
        calls = int(data.get("calls") or 0)
        if calls >= max_calls:
            return False
        data["date"] = _today_utc()
        data["calls"] = calls + 1
        data["max_calls"] = max_calls
        storage.write_json_cache(path, data)
        return True


def _get(path: str, params: Dict[str, Any], bearer_token: str, timeout: int = 20) -> Optional[Dict[str, Any]]:
    if not bearer_token or not _consume_call_budget():
        return None
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{X_API_BASE}{path}"
    if query:
        url = f"{url}?{query}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("authorization", f"Bearer {bearer_token}")
    req.add_header("user-agent", "gold-digger/0.1")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def _clean_handle(handle: str) -> str:
    return (handle or "").strip().lstrip("@")


def _tweet_url(username: str, tweet_id: str) -> str:
    return f"https://x.com/{username}/status/{tweet_id}"


def resolve_user(handle: str, bearer_token: str) -> Optional[Dict[str, Any]]:
    handle = _clean_handle(handle)
    if not handle or not bearer_token:
        return None
    key = handle.lower()
    fresh = _cache_get_current("users", key)
    if isinstance(fresh, dict):
        return fresh
    data = _get(
        f"/users/by/username/{urllib.parse.quote(handle)}",
        {
            "user.fields": "id,name,username,verified,public_metrics",
        },
        bearer_token,
    )
    user = (data or {}).get("data")
    if not isinstance(user, dict) or not user.get("id"):
        return None
    _cache_store_current("users", key, user)
    return user


def _normalise_tweet(tweet: Dict[str, Any], username: str, handle: Optional[str] = None) -> Dict[str, Any]:
    text = tweet.get("text") or ""
    tweet_id = str(tweet.get("id") or "")
    return {
        "handle": handle or username,
        "date": tweet.get("created_at"),
        "text": text,
        "url": _tweet_url(username, tweet_id) if tweet_id else None,
        "tickers": extract_tickers(text),
        "source": "x_api",
    }


def fetch_kol_posts(handle: str, bearer_token: str, since_hours: int = 24, limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch recent public posts from one handle via X API v2."""
    handle = _clean_handle(handle)
    if not handle or not bearer_token:
        return []
    bounded_limit = max(1, min(100, limit))
    cache_key = f"{handle}|{since_hours}|{bounded_limit}"
    fresh = _cache_get_current("kol-posts", cache_key)
    if isinstance(fresh, list):
        return fresh

    user = resolve_user(handle, bearer_token)
    if not user:
        return []
    username = user.get("username") or handle
    max_results = max(5, min(100, bounded_limit))
    data = _get(
        f"/users/{urllib.parse.quote(str(user['id']))}/tweets",
        {
            "max_results": max_results,
            "start_time": _start_time(since_hours),
            "exclude": "retweets",
            "tweet.fields": "created_at,author_id,public_metrics,referenced_tweets,entities,lang",
        },
        bearer_token,
    )
    tweets = (data or {}).get("data")
    if not isinstance(tweets, list):
        _cache_store_current("kol-posts", cache_key, [])
        return []
    normalised = [_normalise_tweet(t, username=username, handle=handle) for t in tweets if isinstance(t, dict)]
    normalised = normalised[:bounded_limit]
    _cache_store_current("kol-posts", cache_key, normalised)
    return normalised


def _quote_term(term: str) -> str:
    term = (term or "").strip()
    if not term:
        return ""
    if any(ch.isspace() for ch in term):
        return f'"{term}"'
    return term


def _query_for_project(project: Dict[str, Any]) -> Optional[str]:
    ticker = (project.get("ticker") or "").strip()
    name = (project.get("name") or "").strip()
    if ticker and name:
        return f"(${ticker} OR {_quote_term(name)}) -is:retweet"
    if ticker:
        return f"${ticker} -is:retweet"
    if name:
        return f"{_quote_term(name)} -is:retweet"
    return None


def search_x_mentions(
    query: str,
    bearer_token: str,
    since_hours: int = 168,
    limit: int = 20,
) -> Optional[List[Dict[str, Any]]]:
    """Search recent public X posts. Returns None on request failure."""
    if not query or not bearer_token:
        return None
    bounded_limit = max(1, min(100, limit))
    cache_key = f"{query}|{since_hours}|{bounded_limit}"
    fresh = _cache_get_current("mentions", cache_key)
    if isinstance(fresh, list):
        return fresh

    data = _get(
        "/tweets/search/recent",
        {
            "query": query,
            "max_results": max(10, bounded_limit),
            "start_time": _start_time(since_hours),
            "tweet.fields": "created_at,author_id,public_metrics,entities,lang",
            "expansions": "author_id",
            "user.fields": "username",
        },
        bearer_token,
    )
    if data is None:
        return None
    tweets = data.get("data") or []
    users = {
        str(u.get("id")): u.get("username")
        for u in ((data.get("includes") or {}).get("users") or [])
        if isinstance(u, dict)
    }
    normalised: List[Dict[str, Any]] = []
    for tweet in tweets:
        if not isinstance(tweet, dict):
            continue
        author = users.get(str(tweet.get("author_id"))) or tweet.get("author_id") or ""
        text = tweet.get("text") or ""
        tweet_id = str(tweet.get("id") or "")
        normalised.append({
            "author": author,
            "date": tweet.get("created_at"),
            "text": text,
            "url": _tweet_url(str(author), tweet_id) if author and tweet_id else None,
            "tickers": extract_tickers(text),
            "source": "x_api",
        })
    normalised = normalised[:bounded_limit]
    _cache_store_current("mentions", cache_key, normalised)
    return normalised


class XApi(Source):
    name = "x_api"
    requires_keys = ["X_BEARER_TOKEN"]

    def fetch_watchlist(self, project: Dict[str, Any], keys: Dict[str, Optional[str]]) -> Dict[str, Any]:
        key = keys.get("X_BEARER_TOKEN")
        if not key:
            return {}
        query = _query_for_project(project)
        if not query:
            return {}
        limit = _env_int("X_API_SEARCH_LIMIT", 25)
        mentions = search_x_mentions(query, key, since_hours=168, limit=limit)
        if mentions is None:
            return {}
        return {"mention_count_7d": len(mentions)}
