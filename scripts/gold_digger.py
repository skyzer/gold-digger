#!/usr/bin/env python3
"""Gold Digger CLI — research early crypto-AI projects with daily compounding reports.

Subcommands:
    setup                     show which API keys are present and which sources are available
    enrich <slug>             enrich a single project in the watchlist
    daily                     run the full daily pipeline (enrich + scout + report)
    scout                     scout-discovery pass only
    add-project <slug>        add a new project by slug (with --coingecko-id, --twitter, etc.)

Entry point via `python3 scripts/gold_digger.py <subcommand>` or, once installed,
`gold-digger <subcommand>`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Make `scripts/` importable when invoked via `python3 scripts/gold_digger.py`
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib import keys as key_resolver  # noqa: E402
from lib import storage  # noqa: E402
from lib import schema  # noqa: E402
from sources._base import Source  # noqa: E402
from sources.coingecko import CoinGecko  # noqa: E402


# Source registry — add new sources here (or drop files in sources/_custom/).
# Order matters: earlier sources run first, later sources can override fields.
SOURCES: List[Source] = [
    CoinGecko(),
]


def all_keys() -> Dict[str, Optional[str]]:
    """Resolve every known key once, return a dict for source plugins."""
    return {k: key_resolver.resolve_key(k) for k in key_resolver.KNOWN_KEYS}


def cmd_setup(_args: argparse.Namespace) -> int:
    """Show the key availability matrix."""
    print("Gold Digger — key availability\n")
    print(f"{'KEY':<28} {'VALUE':<18} {'SOURCE':<32} DESCRIPTION")
    print("-" * 120)
    for key, masked, source, desc in key_resolver.report_availability():
        short_source = source if len(source) <= 30 else source[:27] + "..."
        print(f"{key:<28} {masked:<18} {short_source:<32} {desc}")
    print()
    root = storage.ensure_layout()
    print(f"Data directory: {root}")
    print()
    print("Available sources:")
    keys = all_keys()
    for src in SOURCES:
        status = "OK" if src.available(keys) else "MISSING: " + ", ".join(
            k for k in src.requires_keys if not keys.get(k)
        )
        print(f"  - {src.name:<20} {status}")
    return 0


def _slug_to_path(slug: str) -> Path:
    root = storage.ensure_layout()
    return root / "projects" / f"{slug}.md"


def _seed_path_for(slug: str) -> Path:
    return Path(__file__).resolve().parent.parent / "seed" / "projects" / f"{slug}.md"


def _load_or_seed(slug: str) -> Dict[str, Any]:
    """Load a project from the data directory, falling back to seed/ if it's
    not present yet. Copies the seed into the data dir on first touch."""
    live = _slug_to_path(slug)
    if live.exists():
        fm, _body = storage.read_project(live)
        fm.setdefault("slug", slug)
        return fm
    seed = _seed_path_for(slug)
    if seed.exists():
        fm, body = storage.read_project(seed)
        fm.setdefault("slug", slug)
        storage.write_project(live, fm, body)
        return fm
    # Create from empty template
    fm = schema.empty_project(slug)
    body = schema.project_body_template(slug)
    storage.write_project(live, fm, body)
    return fm


def cmd_enrich(args: argparse.Namespace) -> int:
    slug = args.slug
    project = _load_or_seed(slug)
    print(f"Enriching: {project.get('name', slug)} (slug={slug})")
    if project.get("coingecko_id"):
        print(f"  coingecko_id: {project['coingecko_id']}")
    else:
        print("  coingecko_id: <not set>  (price enrichment will be skipped)")

    keys = all_keys()
    all_updates: Dict[str, Any] = {}
    for src in SOURCES:
        if not src.available(keys):
            print(f"  [{src.name}] skipped (missing key)")
            continue
        print(f"  [{src.name}] fetching...")
        try:
            updates = src.fetch_watchlist(project, keys)
        except Exception as exc:  # pragma: no cover — graceful degradation
            print(f"  [{src.name}] error: {exc}")
            continue
        if updates:
            all_updates.update(updates)
            print(f"  [{src.name}] {len(updates)} fields updated")
        else:
            print(f"  [{src.name}] no data returned")

    if not all_updates:
        print("No updates — nothing written.")
        return 1

    merged = storage.update_project_frontmatter(_slug_to_path(slug), all_updates)
    print()
    print(f"Written: {_slug_to_path(slug)}")
    print()
    print("Key fields:")
    for field in (
        "name", "ticker", "has_token", "price_usd", "mcap", "fdv",
        "change_24h_pct", "change_7d_pct", "change_30d_pct",
        "circulating_supply", "total_supply",
    ):
        if merged.get(field) is not None:
            print(f"  {field}: {merged[field]}")
    return 0


def cmd_scout(_args: argparse.Namespace) -> int:
    keys = all_keys()
    print("Scout pass: discovering new AI-narrative projects (mcap $0.5M–$100M)...\n")
    total_found = 0
    for src in SOURCES:
        if not src.available(keys):
            continue
        try:
            candidates = src.fetch_scout(keys, config={})
        except Exception as exc:
            print(f"  [{src.name}] error: {exc}")
            continue
        if not candidates:
            continue
        print(f"[{src.name}] {len(candidates)} candidates (sorted by mcap ascending):")
        print(f"  {'NAME':<30} {'TICKER':<10} {'MCAP':<10} {'24H%':<9} {'7D%':<9} {'30D%':<9}")
        for c in candidates[:20]:
            mcap = c.get("mcap") or 0
            mcap_str = f"${mcap/1e6:.1f}M"
            def pct(v):
                if v is None:
                    return "—"
                return f"{v:+.1f}%"
            print(f"  {(c.get('name') or '')[:30]:<30} {(c.get('ticker') or '—')[:10]:<10} "
                  f"{mcap_str:<10} {pct(c.get('change_24h_pct')):<9} "
                  f"{pct(c.get('change_7d_pct')):<9} {pct(c.get('change_30d_pct')):<9}")
        total_found += len(candidates)
    print(f"\nTotal scout candidates: {total_found}")
    print("(v0.1 does not auto-add to watchlist — v0.2 will filter + promote via KOL + GitHub signals)")
    return 0


def cmd_add_project(args: argparse.Namespace) -> int:
    slug = args.slug
    path = _slug_to_path(slug)
    if path.exists():
        print(f"Already exists: {path}")
        return 1
    fm = schema.empty_project(slug, name=args.name or slug)
    if args.coingecko_id:
        fm["coingecko_id"] = args.coingecko_id
    if args.twitter:
        fm["twitter"] = args.twitter
    if args.narrative:
        fm["narrative"] = [n.strip() for n in args.narrative.split(",")]
    body = schema.project_body_template(fm["name"])
    storage.write_project(path, fm, body)
    print(f"Created: {path}")
    return 0


def cmd_daily(_args: argparse.Namespace) -> int:
    print("Daily pipeline not yet implemented in v0.1.")
    print("Available in v0.1: `setup`, `enrich <slug>`, `scout`, `add-project <slug>`.")
    print("Next stage wires: enrich all tracked + scout + snapshot + report render.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gold-digger",
        description="Research early crypto-AI projects with daily compounding reports.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_setup = sub.add_parser("setup", help="show API key availability and sources")
    p_setup.set_defaults(func=cmd_setup)

    p_enrich = sub.add_parser("enrich", help="enrich a single project")
    p_enrich.add_argument("slug", help="project slug (filename without .md)")
    p_enrich.set_defaults(func=cmd_enrich)

    p_scout = sub.add_parser("scout", help="scout-discovery pass")
    p_scout.set_defaults(func=cmd_scout)

    p_daily = sub.add_parser("daily", help="run the full daily pipeline")
    p_daily.set_defaults(func=cmd_daily)

    p_add = sub.add_parser("add-project", help="add a new project to the watchlist")
    p_add.add_argument("slug")
    p_add.add_argument("--name")
    p_add.add_argument("--coingecko-id", dest="coingecko_id")
    p_add.add_argument("--twitter")
    p_add.add_argument("--narrative", help="comma-separated narrative tags")
    p_add.set_defaults(func=cmd_add_project)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
