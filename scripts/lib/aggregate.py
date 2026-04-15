"""Trend aggregator — computes velocity and divergence across N days of snapshots.

Velocity: mentions today vs 7d average. +N = accelerating, -N = cooling.
Price-vs-attention divergence: is price flat while mentions rise? Classic setup.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from lib import snapshots


def compute_velocity(root: Path, window_days: int = 7) -> Dict[str, Dict[str, Any]]:
    """For each project seen in recent snapshots, compute mention velocity and
    price-vs-attention divergence.

    Returns a dict keyed by slug with fields:
      - latest_mentions: mention_count_7d from most recent snapshot
      - avg_mentions: average over window_days
      - velocity: latest - avg (positive = heating)
      - latest_price: most recent price_usd
      - price_7d_ago: price from ~7 days ago (oldest in window)
      - price_change: pct change over the window
      - divergence: mention velocity / max(abs(price_change), 1)  — high = attention rising faster than price
    """
    series = snapshots.recent_snapshots(days=window_days)
    if not series:
        return {}

    # Index by slug: list of (date, row) pairs in chronological order
    by_slug: Dict[str, List[Dict[str, Any]]] = {}
    for date, rows in reversed(series):  # oldest first
        for row in rows:
            slug = row.get("slug")
            if not slug:
                continue
            row["_date"] = date
            by_slug.setdefault(slug, []).append(row)

    result: Dict[str, Dict[str, Any]] = {}
    for slug, rows in by_slug.items():
        if not rows:
            continue
        latest = rows[-1]
        oldest = rows[0]
        mentions_list = [r.get("mention_count_7d") or 0 for r in rows]
        latest_mentions = mentions_list[-1]
        avg_mentions = sum(mentions_list) / len(mentions_list) if mentions_list else 0
        velocity = latest_mentions - avg_mentions

        latest_price = latest.get("price_usd")
        price_7d_ago = oldest.get("price_usd")
        price_change_pct = None
        if latest_price and price_7d_ago and price_7d_ago != 0:
            price_change_pct = ((latest_price - price_7d_ago) / price_7d_ago) * 100

        divergence = None
        if velocity is not None and price_change_pct is not None:
            divergence = velocity / max(abs(price_change_pct), 1.0)

        result[slug] = {
            "latest_mentions": latest_mentions,
            "avg_mentions": round(avg_mentions, 2),
            "velocity": round(velocity, 2),
            "latest_price": latest_price,
            "price_7d_ago": price_7d_ago,
            "price_change_pct": round(price_change_pct, 2) if price_change_pct is not None else None,
            "divergence": round(divergence, 3) if divergence is not None else None,
            "data_points": len(rows),
        }
    return result


def top_heating(velocity: Dict[str, Dict[str, Any]], limit: int = 10) -> List[str]:
    """Slugs with the highest positive mention velocity."""
    ranked = sorted(
        velocity.items(),
        key=lambda kv: kv[1].get("velocity") or 0,
        reverse=True,
    )
    return [slug for slug, _ in ranked[:limit] if (ranked and (velocity[slug].get("velocity") or 0) > 0)]


def top_divergence(velocity: Dict[str, Dict[str, Any]], limit: int = 10) -> List[str]:
    """Slugs where attention is rising faster than price (potential setups)."""
    ranked = sorted(
        velocity.items(),
        key=lambda kv: kv[1].get("divergence") or 0,
        reverse=True,
    )
    return [slug for slug, v in ranked[:limit] if (v.get("divergence") or 0) > 0]
