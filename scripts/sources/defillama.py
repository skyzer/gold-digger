"""DeFiLlama source — TVL, protocol fees/revenue, fundraising rounds.

DeFiLlama has multiple free APIs with no key required:
  - api.llama.fi/protocol/<slug>         : TVL, chains, category
  - api.llama.fi/summary/fees/<slug>     : 24h/7d/30d fees
  - api.llama.fi/raises                  : full fundraising rounds DB

Used for (a) watchlist enrichment when a project has `defillama_slug` set, and
(b) scout discovery via the raises DB — surfaces any AI-tagged round in the
last 30 days regardless of whether the project has a token yet.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from lib import ignore as ignore_list
from sources._base import Source

BASE = "https://api.llama.fi"
RAISES_BASE = "https://api.llama.fi"


def _get_json(url: str, timeout: int = 20) -> Optional[Any]:
    req = urllib.request.Request(url)
    req.add_header("accept", "application/json")
    req.add_header("user-agent", "gold-digger/0.1")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def fetch_protocol(slug: str) -> Optional[Dict[str, Any]]:
    """Return DeFiLlama's protocol payload for the given slug, or None."""
    if not slug:
        return None
    return _get_json(f"{BASE}/protocol/{slug}")


def fetch_fees(slug: str) -> Optional[Dict[str, Any]]:
    """Return 24h/7d/30d fees breakdown, or None if not tracked by DeFiLlama."""
    if not slug:
        return None
    return _get_json(f"{BASE}/summary/fees/{slug}?dataType=dailyFees")


def fetch_raises() -> Optional[List[Dict[str, Any]]]:
    """Return the full fundraising rounds database. ~20MB, cache locally."""
    data = _get_json(f"{RAISES_BASE}/raises")
    if isinstance(data, dict):
        return data.get("raises") or []
    if isinstance(data, list):
        return data
    return None


def _latest_tvl(protocol: Dict[str, Any]) -> Optional[float]:
    """Extract the most recent TVL value from a protocol payload."""
    # Try `tvl` (single number) first
    tvl_series = protocol.get("tvl")
    if isinstance(tvl_series, (int, float)):
        return float(tvl_series)
    if isinstance(tvl_series, list) and tvl_series:
        last = tvl_series[-1]
        if isinstance(last, dict):
            return last.get("totalLiquidityUSD")
    # Fallback: `currentChainTvls`
    chains = protocol.get("currentChainTvls") or {}
    if isinstance(chains, dict) and chains:
        return sum(v for v in chains.values() if isinstance(v, (int, float)))
    return None


#: Narrative patterns for AI-crypto detection. Uses word-boundary regex to
#: avoid matching substrings like "ml" inside "xml". Matches name + category
#: only (not description) to keep the scout focused.
import re as _re

_AI_PATTERN = _re.compile(
    r"\b(?:ai|artificial intelligence|agent|agentic|machine learning|llm|inference|gpu|compute|neural|ml)\b",
    _re.IGNORECASE,
)


def _looks_ai(text: str) -> bool:
    if not text:
        return False
    return bool(_AI_PATTERN.search(text))


class DeFiLlama(Source):
    name = "defillama"
    requires_keys: List[str] = []

    def available(self, keys: Dict[str, Optional[str]]) -> bool:
        return True  # no key required

    def fetch_watchlist(self, project: Dict[str, Any], keys: Dict[str, Optional[str]]) -> Dict[str, Any]:
        slug = project.get("defillama_slug")
        if not slug:
            return {}
        protocol = fetch_protocol(slug)
        if not protocol:
            return {}
        updates: Dict[str, Any] = {
            "tvl_usd": _latest_tvl(protocol),
            "defillama_slug": slug,
        }
        # Add to sources
        existing = project.get("sources") or []
        url = f"https://defillama.com/protocol/{slug}"
        if url not in existing:
            updates["sources"] = list(existing) + [url]
        return {k: v for k, v in updates.items() if v is not None}

    def fetch_scout(self, keys: Dict[str, Optional[str]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Surface AI-narrative protocols with TVL.

        DeFiLlama's `/raises` endpoint is now paid-only, so v0.2 uses the free
        `/protocols` list instead — filters by category+name for AI keywords
        and returns protocols with non-trivial TVL as scout candidates.
        """
        protocols = _get_json(f"{BASE}/protocols")
        if not isinstance(protocols, list):
            return []
        min_tvl = int(config.get("min_tvl_usd", 500_000))
        candidates: List[Dict[str, Any]] = []
        for proto in protocols:
            if not isinstance(proto, dict):
                continue
            tvl = proto.get("tvl")
            if not isinstance(tvl, (int, float)) or tvl < min_tvl:
                continue
            # Strict: AI match must be in name or category (not description)
            name_cat = " ".join(str(proto.get(k, "")) for k in ("name", "category"))
            if not _looks_ai(name_cat):
                continue
            name = proto.get("name")
            slug = proto.get("slug") or (name.lower().replace(" ", "-") if name else None)
            if not slug or not name:
                continue
            if ignore_list.is_ignored(slug, (proto.get("symbol") or "").upper(), name):
                continue
            candidates.append({
                "slug": slug,
                "name": name,
                "ticker": (proto.get("symbol") or "").upper() or None,
                "defillama_slug": slug,
                "tvl_usd": tvl,
                "mcap": proto.get("mcap"),
                "chains": proto.get("chains") or [],
                "narrative": ["ai-crypto"],
                "tier": "scout",
                "sources": [f"https://defillama.com/protocol/{slug}"],
            })
        candidates.sort(key=lambda c: c.get("tvl_usd") or 0, reverse=True)
        return candidates
