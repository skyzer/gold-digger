"""Daily report renderer — writes two markdown files per run.

1. `reports/daily/YYYY-MM-DD.md`       — full report
2. `reports/daily/YYYY-MM-DD-brief.md` — 5-bullet TL;DR
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from lib import storage


def _fmt_mcap(v: Any) -> str:
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.1f}M"
    if v >= 1e3:
        return f"${v/1e3:.1f}k"
    return f"${v:.0f}"


def _fmt_pct(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):+.1f}%"
    except (TypeError, ValueError):
        return str(v)


def _reports_dir() -> Path:
    d = storage.data_root() / "reports" / "daily"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _biggest_mover(projects: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    ranked = [p for p in projects if p.get("change_24h_pct") is not None]
    if not ranked:
        return None
    return max(ranked, key=lambda p: abs(p.get("change_24h_pct") or 0))


def _hottest_kol_ticker(kol_posts: List[Dict[str, Any]]) -> str | None:
    tickers: List[str] = []
    for post in kol_posts:
        tickers.extend(post.get("tickers") or [])
    if not tickers:
        return None
    counts = Counter(tickers)
    ticker, count = counts.most_common(1)[0]
    return f"${ticker} ({count} mention{'s' if count > 1 else ''})"


def _trending_narratives(scout: List[Dict[str, Any]]) -> List[Tuple[str, int]]:
    narratives: List[str] = []
    for c in scout:
        narratives.extend(c.get("narrative") or [])
    if not narratives:
        return []
    return Counter(narratives).most_common(5)


def write_daily_reports(
    projects: List[Dict[str, Any]],
    velocity: Dict[str, Dict[str, Any]],
    scout: List[Dict[str, Any]],
    kol_posts: List[Dict[str, Any]],
) -> Tuple[Path, Path]:
    """Write full and brief reports. Returns (full_path, brief_path)."""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    full_path = _reports_dir() / f"{date}.md"
    brief_path = _reports_dir() / f"{date}-brief.md"

    # --- FULL REPORT ---
    lines: List[str] = []
    lines.append(f"# Gold Digger — {date}")
    lines.append("")
    lines.append(f"_{len(projects)} tracked · {len(scout)} scout candidates · {len(kol_posts)} KOL posts digested_")
    lines.append("")

    # 1. New discoveries
    lines.append("## New discoveries (scout)")
    lines.append("")
    if scout:
        lines.append("Top 15 low-cap AI-crypto candidates, sorted by mcap ascending:")
        lines.append("")
        lines.append("| Name | Ticker | Mcap | 24h | 7d | 30d |")
        lines.append("|---|---|---|---|---|---|")
        for c in scout[:15]:
            lines.append(
                f"| {c.get('name', '?')} | {c.get('ticker') or '—'} | "
                f"{_fmt_mcap(c.get('mcap'))} | {_fmt_pct(c.get('change_24h_pct'))} | "
                f"{_fmt_pct(c.get('change_7d_pct'))} | {_fmt_pct(c.get('change_30d_pct'))} |"
            )
    else:
        lines.append("_No scout candidates this run._")
    lines.append("")

    # 2. Watchlist deltas
    lines.append("## Watchlist — current state")
    lines.append("")
    if projects:
        lines.append("| Project | Ticker | Price | Mcap | 24h | 7d | 30d | Mentions 7d |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for p in sorted(projects, key=lambda x: (x.get("mcap") or 0)):
            slug = p.get("slug")
            wiki = f"[[{slug}]]" if slug else p.get("name", "?")
            lines.append(
                f"| {wiki} | {p.get('ticker') or '—'} | "
                f"${p.get('price_usd')} | {_fmt_mcap(p.get('mcap'))} | "
                f"{_fmt_pct(p.get('change_24h_pct'))} | {_fmt_pct(p.get('change_7d_pct'))} | "
                f"{_fmt_pct(p.get('change_30d_pct'))} | {p.get('mention_count_7d') or 0} |"
            )
    else:
        lines.append("_Watchlist empty._")
    lines.append("")

    # 3. KOL digest
    lines.append("## KOL digest (last 24h)")
    lines.append("")
    if kol_posts:
        by_handle: Dict[str, List[Dict[str, Any]]] = {}
        for post in kol_posts:
            by_handle.setdefault(post.get("handle", "?"), []).append(post)
        for handle, posts in by_handle.items():
            lines.append(f"### @{handle}")
            lines.append("")
            for post in posts[:8]:
                tickers = ", ".join(f"${t}" for t in (post.get("tickers") or [])) or "—"
                date_str = (post.get("date") or "")[:19]
                text = (post.get("text") or "").replace("\n", " ").strip()[:280]
                url = post.get("url", "")
                lines.append(f"- **{date_str}** · tickers: {tickers}")
                lines.append(f"  > {text}")
                if url:
                    lines.append(f"  [{url}]({url})")
            lines.append("")
    else:
        lines.append("_No KOL posts retrieved (check XAI_API_KEY)._")
    lines.append("")

    # 4. Trending narratives
    lines.append("## Trending narratives")
    lines.append("")
    narratives = _trending_narratives(scout)
    if narratives:
        for tag, count in narratives:
            lines.append(f"- **{tag}**: {count} candidates")
    else:
        lines.append("_No narratives inferred._")
    lines.append("")

    # 5. Heating up (velocity)
    lines.append("## Heating up (mention velocity)")
    lines.append("")
    if velocity:
        heating = sorted(
            velocity.items(),
            key=lambda kv: kv[1].get("velocity") or 0,
            reverse=True,
        )[:10]
        lines.append("| Project | Velocity | Latest mentions | 7d avg | Price Δ 7d | Divergence |")
        lines.append("|---|---|---|---|---|---|")
        for slug, v in heating:
            lines.append(
                f"| [[{slug}]] | {v.get('velocity'):+.1f} | {v.get('latest_mentions')} | "
                f"{v.get('avg_mentions')} | {_fmt_pct(v.get('price_change_pct'))} | "
                f"{v.get('divergence') or '—'} |"
            )
    else:
        lines.append("_Velocity needs at least 2 days of snapshots to compute._")
    lines.append("")

    # 6. Action queue
    lines.append("## Action queue — deep dive tomorrow")
    lines.append("")
    # Heuristic: projects in tracked watchlist with big 24h moves + any scout candidate > 50% over 7d
    actions: List[str] = []
    for p in projects:
        c24 = p.get("change_24h_pct") or 0
        if abs(c24) >= 10:
            actions.append(f"- [[{p.get('slug')}]] — 24h move {_fmt_pct(c24)}")
    for c in scout[:30]:
        c7 = c.get("change_7d_pct") or 0
        if c7 >= 50:
            actions.append(f"- **{c.get('name')}** ({c.get('ticker') or '—'}) — scout, 7d {_fmt_pct(c7)}, mcap {_fmt_mcap(c.get('mcap'))}")
    if actions:
        lines.extend(actions[:15])
    else:
        lines.append("_No immediate action items._")
    lines.append("")

    full_path.write_text("\n".join(lines), encoding="utf-8")

    # --- BRIEF REPORT ---
    brief_lines = [f"# Gold Digger brief — {date}", ""]
    # Best find
    best_find = scout[0] if scout else None
    if best_find:
        brief_lines.append(
            f"- **Best new find:** {best_find.get('name')} ({best_find.get('ticker') or '—'}) "
            f"— mcap {_fmt_mcap(best_find.get('mcap'))}, 7d {_fmt_pct(best_find.get('change_7d_pct'))}"
        )
    # Biggest mover
    mover = _biggest_mover(projects)
    if mover:
        brief_lines.append(
            f"- **Biggest mover (watchlist):** [[{mover.get('slug')}]] "
            f"{_fmt_pct(mover.get('change_24h_pct'))} in 24h · mcap {_fmt_mcap(mover.get('mcap'))}"
        )
    # Hottest KOL ticker
    hottest = _hottest_kol_ticker(kol_posts)
    if hottest:
        brief_lines.append(f"- **Hottest KOL signal:** {hottest}")
    # Action item
    if actions:
        brief_lines.append(f"- **Action:** {actions[0]}")
    # Narrative of the day
    if narratives:
        top_narrative = narratives[0][0]
        brief_lines.append(f"- **Narrative of the day:** `{top_narrative}` ({narratives[0][1]} candidates)")

    if len(brief_lines) == 2:
        brief_lines.append("_Not enough signal today — check again tomorrow._")

    brief_path.write_text("\n".join(brief_lines), encoding="utf-8")

    return full_path, brief_path
