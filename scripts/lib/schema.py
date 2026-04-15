"""Project schema — the canonical frontmatter spec.

Every project file has these fields. Missing data is `null`. Source plugins
fill in what they can; other fields stay null.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


def empty_project(slug: str, name: str | None = None) -> Dict[str, Any]:
    """Return a fresh project frontmatter dict with all schema fields set to null."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        # Identity
        "slug": slug,
        "name": name or slug,
        "ticker": None,
        "narrative": [],
        "chains": [],
        "website": None,
        "twitter": None,
        "github": None,
        "docs": None,
        "coingecko_id": None,
        "defillama_slug": None,

        # Token status
        "has_token": "unknown",  # yes | no | announced | rumored | unknown
        "price_usd": None,
        "mcap": None,
        "fdv": None,
        "change_24h_pct": None,
        "change_7d_pct": None,
        "change_30d_pct": None,
        "circulating_supply": None,
        "total_supply": None,
        "max_supply": None,
        "exchanges": [],
        "tge_date": None,
        "listed_since": None,

        # Funding
        "raised_usd": None,
        "latest_round": None,
        "latest_round_date": None,
        "valuation_usd": None,
        "investors": [],

        # Traction
        "twitter_followers": None,
        "twitter_followers_delta_30d": None,
        "discord_members": None,
        "telegram_members": None,
        "github_stars": None,
        "github_commits_30d": None,
        "github_contributors": None,
        "tvl_usd": None,
        "daily_active_users": None,
        "mainnet_status": "unknown",  # testnet | mainnet | live | unknown

        # Catalysts
        "points_farming": "unknown",
        "points_program_end": None,
        "airdrop_eligible": "unknown",
        "features_shipped_30d": [],
        "partnerships_30d": [],
        "upcoming_tge": None,

        # KOL signal
        "mentioned_by": [],
        "mention_count_7d": 0,
        "mention_count_30d": 0,
        "mention_velocity": None,  # +N = accelerating, -N = cooling
        "first_kol_mention_date": None,

        # Risk
        "audit_status": "unknown",
        "auditor": None,
        "team_doxxed": "unknown",
        "vc_unlock_schedule": None,
        "red_flags": [],

        # Meta
        "tier": "tracked",  # tracked | scout | archived
        "first_added": today,
        "last_updated": today,
        "sources": [],
    }


def project_body_template(name: str) -> str:
    """Default body for a freshly-added project file."""
    return f"""
# {name}

## Overview

_Notes go here. Gold Digger never overwrites the body._

## Recent updates

## Theses

## Questions to answer

## Sources
"""
