"""KOL first-mention auto-scout.

When a tracked KOL mentions a `$TICKER` Gold Digger hasn't seen before:
  1. Check the ignore list — skip noise (BTC, CRCL, stables, etc.)
  2. Check the watchlist — if the ticker belongs to an existing project,
     update that project's `mentioned_by` + `mention_count_7d` instead
  3. Otherwise attempt to resolve via CoinGecko `/search` — if a coin is
     found, auto-add a scout-tier project file with KOL attribution
  4. If resolution fails, log as `unresolved` — the daily report surfaces
     these so the user can manually investigate a pre-launch project

Persistent memory lives in `$GOLD_DIGGER_DATA/trends/kol-mentions.md` as a
markdown table. This is Gold Digger's long-term record of every KOL call
so we can backtest their accuracy over time.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib import ignore as ignore_list
from lib import storage
from lib import schema


MEMORY_FILE = "trends/kol-mentions.md"
MEMORY_COLUMNS = ["date", "kol", "ticker", "post_url", "resolved_slug", "action", "first_seen"]


def _memory_path() -> Path:
    root = storage.data_root()
    path = root / MEMORY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_memory() -> List[Dict[str, str]]:
    """Read the kol-mentions table. Returns empty list if file doesn't exist yet."""
    path = _memory_path()
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    records: List[Dict[str, str]] = []
    in_table = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("| date "):
            in_table = True
            continue
        if line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < len(MEMORY_COLUMNS):
                cells += [""] * (len(MEMORY_COLUMNS) - len(cells))
            record = dict(zip(MEMORY_COLUMNS, cells))
            records.append(record)
        elif in_table and not line.startswith("|"):
            in_table = False
    return records


def _save_memory(records: List[Dict[str, str]]) -> None:
    """Write the memory table. Sort by first_seen desc so newest lands at top."""
    path = _memory_path()
    lines = [
        "# KOL mention memory",
        "",
        "_Every `$TICKER` extracted from a tracked KOL's post, with its resolution._",
        "_This is Gold Digger's long-term record — used for dedupe, backtest, and accuracy scoring._",
        "",
        "| " + " | ".join(MEMORY_COLUMNS) + " |",
        "|" + "|".join(["---"] * len(MEMORY_COLUMNS)) + "|",
    ]
    records_sorted = sorted(
        records,
        key=lambda r: r.get("first_seen") or r.get("date") or "",
        reverse=True,
    )
    for r in records_sorted:
        row = "| " + " | ".join(r.get(c, "") or "—" for c in MEMORY_COLUMNS) + " |"
        lines.append(row)
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _seen_before(records: List[Dict[str, str]], kol: str, ticker: str) -> bool:
    """True if we've already processed this (kol, ticker) pair on any prior day."""
    for r in records:
        if r.get("kol", "").lower() == kol.lower() and r.get("ticker", "").upper() == ticker.upper():
            return True
    return False


def _projects_by_ticker() -> Dict[str, Path]:
    """Map TICKER → project file path for every file in $GOLD_DIGGER_DATA/projects/."""
    result: Dict[str, Path] = {}
    projects_dir = storage.data_root() / "projects"
    if not projects_dir.exists():
        return result
    for path in projects_dir.glob("*.md"):
        fm, _body = storage.read_project(path)
        ticker = fm.get("ticker")
        if ticker:
            result[str(ticker).upper()] = path
    return result


def _auto_add_scout(
    ticker: str,
    name: str,
    coingecko_id: Optional[str],
    kol_handle: str,
    post_url: str,
    post_date: str,
) -> Path:
    """Create a new scout-tier project file with KOL attribution."""
    slug = (coingecko_id or ticker.lower()).replace(" ", "-")
    root = storage.data_root()
    path = root / "projects" / f"{slug}.md"
    if path.exists():
        # Existing file — just append KOL attribution
        fm, body = storage.read_project(path)
        mentioned_by = fm.get("mentioned_by") or []
        if kol_handle not in mentioned_by:
            mentioned_by.append(kol_handle)
        fm["mentioned_by"] = mentioned_by
        storage.write_project(path, fm, body)
        return path

    fm = schema.empty_project(slug, name=name)
    fm["ticker"] = ticker.upper()
    fm["coingecko_id"] = coingecko_id
    fm["tier"] = "scout"
    fm["narrative"] = ["ai-crypto"]
    fm["mentioned_by"] = [kol_handle]
    fm["mention_count_7d"] = 1
    fm["has_token"] = "yes" if coingecko_id else "unknown"
    fm["sources"] = [post_url] if post_url else []
    body = (
        f"\n# {name}\n\n"
        f"## Overview\n\n"
        f"Auto-added by Gold Digger first-mention scout.\n\n"
        f"## Discovery\n\n"
        f"- **First seen:** {post_date}\n"
        f"- **Via:** @{kol_handle}\n"
        f"- **Post:** {post_url}\n\n"
        f"## Theses\n\n"
        f"_(Investigate — Gold Digger has no fundamentals data yet.)_\n\n"
        f"## Questions to answer\n\n"
        f"- Does this token exist live or is it pre-launch?\n"
        f"- What's the narrative — AI agents, infra, data, something else?\n"
        f"- Why is {kol_handle} mentioning it?\n\n"
        f"## Sources\n\n"
        f"- {post_url}\n"
    )
    storage.write_project(path, fm, body)
    return path


def process_posts(posts: List[Dict[str, Any]], coingecko_key: Optional[str]) -> List[Dict[str, Any]]:
    """Main entry point: given the day's KOL posts, classify every ticker and
    take appropriate action. Returns a list of result records suitable for
    the daily report's 'KOL first-mentions' section.

    Result shape per ticker:
      {
        "kol": handle,
        "ticker": TICKER,
        "action": "ignored" | "existing-watchlist" | "first-mention-added" |
                  "first-mention-unresolved" | "already-processed",
        "resolved_slug": slug or None,
        "post_url": url,
        "post_date": iso date,
        "post_text": snippet,
      }
    """
    memory = _load_memory()
    by_ticker = _projects_by_ticker()
    results: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Lazy import to avoid circular
    from sources.coingecko import search_coin

    for post in posts:
        kol = post.get("handle", "")
        post_url = post.get("url", "")
        post_date = post.get("date", "")
        post_text = (post.get("text") or "")[:140]
        tickers = post.get("tickers") or []
        for ticker in tickers:
            ticker_upper = ticker.upper()
            base_result = {
                "kol": kol,
                "ticker": ticker_upper,
                "post_url": post_url,
                "post_date": post_date,
                "post_text": post_text,
            }

            # 1. Ignore list — hard skip
            if ignore_list.is_ignored(ticker_upper):
                base_result["action"] = "ignored"
                results.append(base_result)
                continue

            # 2. Already processed this (kol, ticker) pair — skip silently
            if _seen_before(memory, kol, ticker_upper):
                base_result["action"] = "already-processed"
                results.append(base_result)
                continue

            # 3. Ticker matches an existing tracked project — update attribution
            if ticker_upper in by_ticker:
                existing_path = by_ticker[ticker_upper]
                fm, body = storage.read_project(existing_path)
                mentioned = fm.get("mentioned_by") or []
                if kol not in mentioned:
                    mentioned.append(kol)
                    fm["mentioned_by"] = mentioned
                    storage.write_project(existing_path, fm, body)
                base_result["action"] = "existing-watchlist"
                base_result["resolved_slug"] = existing_path.stem
                results.append(base_result)
                # Record in memory so we don't re-process
                memory.append({
                    "date": post_date[:10] if post_date else now,
                    "kol": kol,
                    "ticker": ticker_upper,
                    "post_url": post_url,
                    "resolved_slug": existing_path.stem,
                    "action": "existing-watchlist",
                    "first_seen": now,
                })
                continue

            # 4. Try to resolve via CoinGecko search
            coin = search_coin(ticker_upper, coingecko_key) if coingecko_key else None
            if coin:
                coingecko_id = coin.get("id") or coin.get("api_symbol")
                name = coin.get("name") or ticker_upper
                path = _auto_add_scout(
                    ticker=ticker_upper,
                    name=name,
                    coingecko_id=coingecko_id,
                    kol_handle=kol,
                    post_url=post_url,
                    post_date=post_date,
                )
                base_result["action"] = "first-mention-added"
                base_result["resolved_slug"] = path.stem
                results.append(base_result)
                memory.append({
                    "date": post_date[:10] if post_date else now,
                    "kol": kol,
                    "ticker": ticker_upper,
                    "post_url": post_url,
                    "resolved_slug": path.stem,
                    "action": "first-mention-added",
                    "first_seen": now,
                })
            else:
                base_result["action"] = "first-mention-unresolved"
                base_result["resolved_slug"] = None
                results.append(base_result)
                memory.append({
                    "date": post_date[:10] if post_date else now,
                    "kol": kol,
                    "ticker": ticker_upper,
                    "post_url": post_url,
                    "resolved_slug": "",
                    "action": "unresolved",
                    "first_seen": now,
                })

    _save_memory(memory)
    return results
