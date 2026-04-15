"""CoinGecko source — price, mcap, supply, listings, new-listing scout.

Auto-detects Demo vs Pro API key at runtime:
  - First call tries whichever tier is cached (default: Demo).
  - On a 400/401 that mentions "pro-api.coingecko.com", switches tier and retries.
  - Subsequent calls in the same process reuse the detected tier.

Override manually with `COINGECKO_TIER=pro` or `COINGECKO_TIER=demo` if needed.

API docs: https://docs.coingecko.com/reference/introduction
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from sources._base import Source

# Mutable process-scoped tier cache. First successful call pins it.
_DETECTED_TIER: Optional[str] = None


def _initial_tier() -> str:
    """Start tier for the first call. Respects COINGECKO_TIER override."""
    env_tier = (os.environ.get("COINGECKO_TIER") or "").lower()
    if env_tier in ("pro", "demo"):
        return env_tier
    # Default: demo. Auto-upgrade on 400 if the key is actually Pro.
    return "demo"


def _endpoint(tier: str) -> tuple[str, str]:
    """Return (base_url, header_name) for a given tier."""
    if tier == "pro":
        return "https://pro-api.coingecko.com/api/v3", "x-cg-pro-api-key"
    return "https://api.coingecko.com/api/v3", "x-cg-demo-api-key"


def _request(tier: str, path: str, params: Dict[str, Any], key: str) -> tuple[int, bytes]:
    """Issue a single request. Returns (status, body_bytes). Raises urllib errors."""
    base, header = _endpoint(tier)
    qs = urllib.parse.urlencode(params)
    url = f"{base}{path}?{qs}" if qs else f"{base}{path}"
    req = urllib.request.Request(url)
    req.add_header("accept", "application/json")
    req.add_header(header, key)
    req.add_header("user-agent", "gold-digger/0.1")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status, resp.read()


def _get(path: str, params: Dict[str, Any], key: str) -> Optional[Any]:
    """HTTP GET with auto Demo↔Pro fallback. Returns parsed JSON or None."""
    global _DETECTED_TIER
    tier = _DETECTED_TIER or _initial_tier()

    def _attempt(t: str) -> Optional[Any]:
        try:
            status, body = _request(t, path, params, key)
        except urllib.error.HTTPError as e:
            body = b""
            try:
                body = e.read()
            except Exception:
                pass
            msg = body.decode("utf-8", errors="ignore")
            # 400 + Pro hint → caller will retry with pro tier
            if e.code in (400, 401) and "pro-api.coingecko.com" in msg:
                return "RETRY_PRO"
            # 400 + Demo hint → caller will retry with demo tier
            if e.code in (400, 401) and "api.coingecko.com" in msg and "pro-api" not in msg:
                return "RETRY_DEMO"
            return None
        except (urllib.error.URLError, OSError):
            return None
        if status != 200:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    result = _attempt(tier)
    if result == "RETRY_PRO":
        _DETECTED_TIER = "pro"
        return _attempt("pro")
    if result == "RETRY_DEMO":
        _DETECTED_TIER = "demo"
        return _attempt("demo")
    if result is not None:
        _DETECTED_TIER = tier  # cache the working tier
        return result
    return None


class CoinGecko(Source):
    name = "coingecko"
    requires_keys = ["COINGECKO_API_KEY"]
    optional_keys = []

    def fetch_watchlist(self, project: Dict[str, Any], keys: Dict[str, Optional[str]]) -> Dict[str, Any]:
        key = keys.get("COINGECKO_API_KEY")
        if not key:
            return {}
        cg_id = project.get("coingecko_id")
        if not cg_id:
            return {}

        # /coins/{id} gives the full payload: price, mcap, supply, exchanges, %s
        data = _get(
            f"/coins/{cg_id}",
            {
                "localization": "false",
                "tickers": "true",
                "market_data": "true",
                "community_data": "true",
                "developer_data": "true",
                "sparkline": "false",
            },
            key,
        )
        if not data:
            return {}

        md = data.get("market_data") or {}
        price = (md.get("current_price") or {}).get("usd")
        mcap = (md.get("market_cap") or {}).get("usd")
        fdv = (md.get("fully_diluted_valuation") or {}).get("usd")

        updates: Dict[str, Any] = {
            "name": data.get("name") or project.get("name"),
            "ticker": (data.get("symbol") or "").upper() or None,
            "has_token": "yes" if price is not None else project.get("has_token", "unknown"),
            "price_usd": price,
            "mcap": mcap,
            "fdv": fdv,
            "change_24h_pct": md.get("price_change_percentage_24h"),
            "change_7d_pct": md.get("price_change_percentage_7d"),
            "change_30d_pct": md.get("price_change_percentage_30d"),
            "circulating_supply": md.get("circulating_supply"),
            "total_supply": md.get("total_supply"),
            "max_supply": md.get("max_supply"),
            "website": ((data.get("links") or {}).get("homepage") or [None])[0] or project.get("website"),
            "twitter": (data.get("links") or {}).get("twitter_screen_name") or project.get("twitter"),
            "github": self._first_github((data.get("links") or {}).get("repos_url", {})) or project.get("github"),
        }

        # Exchanges (from tickers[] — unique exchange names)
        tickers = data.get("tickers") or []
        exchanges = []
        seen = set()
        for t in tickers[:50]:
            market = (t.get("market") or {}).get("name")
            if market and market not in seen:
                seen.add(market)
                exchanges.append(market)
        if exchanges:
            updates["exchanges"] = exchanges[:20]

        # Chains (from platforms)
        platforms = data.get("platforms") or {}
        chains = [p for p in platforms.keys() if p]
        if chains:
            updates["chains"] = chains

        # Source provenance
        existing_sources = project.get("sources") or []
        new_source = f"https://www.coingecko.com/en/coins/{cg_id}"
        if new_source not in existing_sources:
            updates["sources"] = list(existing_sources) + [new_source]

        return updates

    @staticmethod
    def _first_github(repos: Dict[str, Any]) -> Optional[str]:
        if not isinstance(repos, dict):
            return None
        gh = repos.get("github") or []
        if isinstance(gh, list) and gh:
            return gh[0]
        return None

    def fetch_scout(self, keys: Dict[str, Optional[str]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Discover new AI-narrative projects via CoinGecko's categories endpoint.

        Strategy: pull the top 100 AI-tagged coins by mcap (desc), then filter
        to projects under $100M — the early-stage zone where 10-100x remains
        plausible. Skips anything with null mcap (usually placeholder tokens).
        """
        key = keys.get("COINGECKO_API_KEY")
        if not key:
            return []
        max_mcap = int(config.get("scout_max_mcap", 100_000_000))
        min_mcap = int(config.get("scout_min_mcap", 500_000))

        data = _get(
            "/coins/markets",
            {
                "vs_currency": "usd",
                "category": "artificial-intelligence",
                "order": "market_cap_desc",
                "per_page": 100,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h,7d,30d",
            },
            key,
        )
        if not isinstance(data, list):
            return []

        candidates: List[Dict[str, Any]] = []
        for coin in data:
            mcap = coin.get("market_cap")
            if mcap is None or mcap < min_mcap or mcap > max_mcap:
                continue
            if not coin.get("id"):
                continue
            candidates.append({
                "slug": coin.get("id"),
                "name": coin.get("name"),
                "ticker": (coin.get("symbol") or "").upper() or None,
                "coingecko_id": coin.get("id"),
                "price_usd": coin.get("current_price"),
                "mcap": mcap,
                "fdv": coin.get("fully_diluted_valuation"),
                "change_24h_pct": coin.get("price_change_percentage_24h_in_currency"),
                "change_7d_pct": coin.get("price_change_percentage_7d_in_currency"),
                "change_30d_pct": coin.get("price_change_percentage_30d_in_currency"),
                "narrative": ["ai-crypto"],
                "tier": "scout",
                "sources": [f"https://www.coingecko.com/en/coins/{coin.get('id')}"],
            })
        # Sort ascending by mcap so the smallest (most interesting) are at the top
        candidates.sort(key=lambda c: c.get("mcap") or 0)
        return candidates
