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
from lib import kols as kol_lib  # noqa: E402
from lib import first_mention  # noqa: E402
from lib import narratives as narrative_lib  # noqa: E402
from lib import ignore as ignore_list  # noqa: E402
from sources._base import Source  # noqa: E402
from sources.coingecko import CoinGecko  # noqa: E402
from sources.xai import XaiGrok, fetch_kol_posts  # noqa: E402
from sources.last30days import Last30Days  # noqa: E402
from sources.defillama import DeFiLlama  # noqa: E402
from sources.github import GitHub  # noqa: E402
from sources.perplexity import Perplexity, research as pplx_research, project_dd_prompt  # noqa: E402


# Source registry — add new sources here (or drop files in sources/_custom/).
# Order matters: earlier sources run first, later sources can override fields.
SOURCES: List[Source] = [
    CoinGecko(),
    DeFiLlama(),
    GitHub(),
    XaiGrok(),
    Last30Days(),
    Perplexity(),
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


def _load_or_seed(slug: str) -> Dict[str, Any]:
    """Load a project from the data directory. If it doesn't exist, create
    a fresh empty template so the caller can still work with it."""
    live = _slug_to_path(slug)
    if live.exists():
        fm, _body = storage.read_project(live)
        fm.setdefault("slug", slug)
        return fm
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


# ---------------------------------------------------------------------------
# Default starter projects + KOLs for `gold-digger init`
# ---------------------------------------------------------------------------
STARTER_PROJECTS = [
    {
        "slug": "unigox",
        "name": "Unigox",
        "twitter": "unigox",
        "narrative": "ai-crypto",
        "note": "Pre-token AI-crypto project. Gold Digger tracks X mentions and Perplexity DD while waiting for token launch.",
    },
    {
        "slug": "ai16z",
        "name": "ai16z",
        "coingecko_id": "ai16z",
        "twitter": "ai16zdao",
        "narrative": "ai-agents",
        "note": "AI-agent DAO. One of the earliest AI-agent narrative leaders.",
    },
    {
        "slug": "virtuals",
        "name": "Virtuals Protocol",
        "coingecko_id": "virtual-protocol",
        "twitter": "virtaboreal",
        "narrative": "ai-agents",
        "note": "AI-agent launchpad on Base. High volume, high narrative velocity.",
    },
    {
        "slug": "openserv",
        "name": "OpenServ",
        "coingecko_id": "openserv",
        "twitter": "openservAI",
        "narrative": "ai-agents",
        "note": "AI-agent platform. Reference low-cap ($15M entry zone).",
    },
]

STARTER_KOLS = [
    {"handle": "DegenSensei", "focus": "ai-crypto,low-cap"},
    {"handle": "resdegen", "focus": "ai-crypto,low-cap"},
]


def cmd_init(args: argparse.Namespace) -> int:
    """First-time setup: populate the watchlist with starter examples."""
    root = storage.ensure_layout()
    existing_projects = list((root / "projects").glob("*.md"))
    existing_kols = list((root / "kols").glob("*.md"))

    if existing_projects and not args.force:
        print(f"Watchlist already has {len(existing_projects)} project(s).")
        print("Run with --force to add starter examples anyway, skipping existing.")
        if not args.force:
            return 0

    added_p = 0
    for p in STARTER_PROJECTS:
        path = root / "projects" / f"{p['slug']}.md"
        if path.exists():
            print(f"  [skip] {p['slug']} (already exists)")
            continue
        fm = schema.empty_project(p["slug"], name=p.get("name"))
        if p.get("coingecko_id"):
            fm["coingecko_id"] = p["coingecko_id"]
        if p.get("twitter"):
            fm["twitter"] = p["twitter"]
        if p.get("narrative"):
            fm["narrative"] = [n.strip() for n in p["narrative"].split(",")]
        body = schema.project_body_template(fm["name"])
        if p.get("note"):
            body = body.replace(
                "_Notes go here. Gold Digger never overwrites the body._",
                p["note"],
            )
        storage.write_project(path, fm, body)
        print(f"  [added] {p['slug']} — {p.get('name', '')}")
        added_p += 1

    added_k = 0
    for k in STARTER_KOLS:
        path = root / "kols" / f"{k['handle'].lower()}.md"
        if path.exists():
            print(f"  [skip] @{k['handle']} (already exists)")
            continue
        kol_lib.write_kol(
            handle=k["handle"],
            focus=[f.strip() for f in k.get("focus", "").split(",") if f.strip()],
        )
        print(f"  [added] @{k['handle']}")
        added_k += 1

    print(f"\nDone: {added_p} projects + {added_k} KOLs added.")
    if added_p > 0 or added_k > 0:
        print(f"Data directory: {root}")
        print("\nRun `gold-digger daily` to start your first research cycle.")
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


def cmd_add_kol(args: argparse.Namespace) -> int:
    """Add a new KOL to the watchlist."""
    storage.ensure_layout()
    path = kol_lib.write_kol(
        handle=args.handle,
        platform=args.platform,
        weight=args.weight,
        focus=[f.strip() for f in (args.focus or "").split(",") if f.strip()],
    )
    print(f"Created: {path}")
    print(f"Edit `{path}` to add notes or change weight. Run `gold-digger kols` to verify.")
    return 0


def cmd_research(args: argparse.Namespace) -> int:
    """Run a cited deep-dive on a single project via Perplexity."""
    from datetime import datetime, timezone
    keys = all_keys()
    pplx_key = keys.get("PERPLEXITY_API_KEY")
    if not pplx_key:
        print("PERPLEXITY_API_KEY not found. Add to ~/.config/shared/.env.")
        return 1
    slug = args.slug
    project = _load_or_seed(slug)
    # Run enrichment first so the DD prompt has fresh data
    print(f"[research] {slug} — enriching first...")
    enrich_args = argparse.Namespace(slug=slug)
    cmd_enrich(enrich_args)
    # Reload after enrichment
    project, _body = storage.read_project(_slug_to_path(slug))
    print(f"\n[research] calling Perplexity sonar-pro for cited DD brief...")
    prompt = project_dd_prompt(project)
    result = pplx_research(prompt, pplx_key, model="sonar-pro")
    if not result:
        print("Perplexity returned no result.")
        return 1
    text, citations = result
    # Write research brief
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    research_dir = storage.data_root() / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    brief_path = research_dir / f"{slug}-{date}.md"
    lines = [
        f"# Gold Digger research brief — {project.get('name', slug)}",
        f"_Date: {date} · Model: sonar-pro · Project: [[{slug}]]_",
        "",
        "## Current data",
        "",
        f"- **Ticker:** {project.get('ticker') or '—'}",
        f"- **Price:** ${project.get('price_usd') or '—'}",
        f"- **Mcap:** ${project.get('mcap') or '—'}",
        f"- **30d change:** {project.get('change_30d_pct') or '—'}%",
        f"- **GitHub stars:** {project.get('github_stars') or '—'}",
        f"- **Mentions 7d:** {project.get('mention_count_7d') or 0}",
        "",
        "## Research brief",
        "",
        text,
        "",
        "## Citations",
        "",
    ]
    for i, url in enumerate(citations, 1):
        lines.append(f"{i}. {url}")
    brief_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[research] brief → {brief_path}")
    print(f"[research] {len(citations)} citations")
    # Print a short preview
    print()
    print("=" * 60)
    print(text[:1500])
    if len(text) > 1500:
        print(f"\n... ({len(text)-1500} more chars in file)")
    return 0


def cmd_first_mentions(args: argparse.Namespace) -> int:
    """Run the KOL first-mention auto-scout pass in isolation."""
    keys = all_keys()
    xai_key = keys.get("XAI_API_KEY")
    if not xai_key:
        print("XAI_API_KEY required.")
        return 1
    since = args.since_hours
    kols = kol_lib.load_all()
    print(f"[first-mention] polling {len(kols)} KOLs over last {since}h\n")
    all_posts: List[Dict[str, Any]] = []
    for kol in kols:
        handle = kol.get("handle")
        posts = fetch_kol_posts(handle, xai_key, since_hours=since, limit=15)
        print(f"  @{handle}: {len(posts)} posts")
        all_posts.extend(posts)
    if not all_posts:
        print("No posts retrieved.")
        return 0
    results = first_mention.process_posts(all_posts, coingecko_key=keys.get("COINGECKO_API_KEY"))
    print(f"\nProcessed {len(results)} ticker mentions:")
    for action_type in ("first-mention-added", "first-mention-unresolved", "existing-watchlist", "ignored", "already-processed"):
        subset = [r for r in results if r.get("action") == action_type]
        if not subset:
            continue
        print(f"\n  {action_type} ({len(subset)}):")
        for r in subset[:20]:
            suffix = f" → [[{r.get('resolved_slug')}]]" if r.get("resolved_slug") else ""
            print(f"    @{r.get('kol')} → ${r.get('ticker')}{suffix}")
    return 0


def cmd_kols(args: argparse.Namespace) -> int:
    """Fetch recent posts from every tracked KOL. Prints a digest."""
    keys = all_keys()
    xai_key = keys.get("XAI_API_KEY")
    if not xai_key:
        print("XAI_API_KEY not found — cannot fetch KOL feeds. Add key to ~/.config/shared/.env.")
        return 1
    kols = kol_lib.load_all()
    if not kols:
        print("No KOLs configured. Drop .md files in seed/kols/ or $GOLD_DIGGER_DATA/kols/.")
        return 1
    since = args.since_hours
    print(f"KOL digest — last {since}h, {len(kols)} handles\n")
    all_posts = []
    for kol in kols:
        handle = kol.get("handle")
        print(f"[@{handle}] fetching...")
        posts = fetch_kol_posts(handle, xai_key, since_hours=since, limit=10)
        if not posts:
            print(f"  (no posts returned)")
            continue
        for post in posts:
            tickers = ", ".join(post.get("tickers") or []) or "—"
            date = post.get("date", "")[:19]
            text_preview = (post.get("text") or "").replace("\n", " ")[:140]
            print(f"  {date}  tickers=[{tickers}]")
            print(f"    {text_preview}")
            print(f"    {post.get('url', '')}")
        all_posts.extend(posts)
    # Summary: ticker frequency across all posts
    ticker_counts: Dict[str, int] = {}
    for post in all_posts:
        for ticker in post.get("tickers") or []:
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
    if ticker_counts:
        print("\nTicker frequency:")
        for ticker, count in sorted(ticker_counts.items(), key=lambda x: -x[1]):
            print(f"  ${ticker}: {count}")
    return 0


def cmd_daily(_args: argparse.Namespace) -> int:
    """Full daily pipeline: enrich all tracked + snapshot + scout + KOL digest + report."""
    from lib import snapshots, render, aggregate
    keys = all_keys()
    root = storage.ensure_layout()
    print(f"Gold Digger daily run — data dir: {root}\n")

    # 1. Enrich all tracked projects. Watchlist lives in the user's data dir,
    #    populated via `gold-digger add-project` / `add-kol`. Empty on first run.
    tracked = sorted((root / "projects").glob("*.md"))
    if not tracked:
        print("Watchlist is empty. Run `gold-digger add-project <slug>` first.")
        print("See README.md Quick Start for example commands.\n")

    enriched_projects: List[Dict[str, Any]] = []
    for path in tracked:
        slug = path.stem
        fm, _body = storage.read_project(path)
        if fm.get("tier") == "archived":
            continue
        print(f"[enrich] {slug}")
        updates: Dict[str, Any] = {}
        for src in SOURCES:
            if not src.available(keys):
                continue
            try:
                src_updates = src.fetch_watchlist(fm, keys)
                if src_updates:
                    updates.update(src_updates)
            except Exception as exc:
                print(f"  {src.name}: error {exc}")
        if updates:
            merged = storage.update_project_frontmatter(path, updates)
            enriched_projects.append(merged)
            print(f"  → {len(updates)} fields updated")
        else:
            enriched_projects.append(fm)

    # 2. Scout pass happens later; pre-compute narrative distribution only if
    #    we already have scout candidates. We'll re-snapshot after scout runs.
    scout_candidates_pre: List[Dict[str, Any]] = []

    # Write today's snapshot (projects only for now)
    snap_path = snapshots.write_daily_snapshot(enriched_projects)
    print(f"\n[snapshot] written → {snap_path}")

    # 3. Aggregate trends
    velocity = aggregate.compute_velocity(root, window_days=7)
    print(f"[aggregate] velocity computed for {len(velocity)} projects")

    # 4. Scout pass
    print("\n[scout] discovering new candidates...")
    scout_candidates: List[Dict[str, Any]] = []
    for src in SOURCES:
        if not src.available(keys):
            continue
        try:
            found = src.fetch_scout(keys, config={})
            if found:
                print(f"  {src.name}: {len(found)} candidates (pre-filter)")
                scout_candidates.extend(found)
        except Exception as exc:
            print(f"  {src.name}: error {exc}")

    # Apply ignore filter + narrative classification
    scout_candidates = ignore_list.filter_candidates(scout_candidates)
    narrative_lib.tag_candidates(scout_candidates)
    narrative_counts = narrative_lib.compute_rotation(scout_candidates)
    print(f"  {len(scout_candidates)} candidates after ignore filter")
    print(f"  narratives detected: {len(narrative_counts)}")

    # Re-write snapshot with narrative distribution included
    snapshots.write_daily_snapshot(enriched_projects, narrative_counts=narrative_counts)

    # 5. KOL digest
    print("\n[kols] running KOL digest...")
    kol_posts: List[Dict[str, Any]] = []
    xai_key = keys.get("XAI_API_KEY")
    if xai_key:
        for kol in kol_lib.load_all():
            handle = kol.get("handle")
            posts = fetch_kol_posts(handle, xai_key, since_hours=24, limit=10)
            kol_posts.extend(posts)
            print(f"  @{handle}: {len(posts)} posts")
    else:
        print("  (skipped — no XAI_API_KEY)")

    # 6. KOL first-mention auto-scout
    first_mention_results: List[Dict[str, Any]] = []
    if kol_posts:
        print("\n[first-mention] classifying KOL ticker mentions...")
        first_mention_results = first_mention.process_posts(
            kol_posts, coingecko_key=keys.get("COINGECKO_API_KEY")
        )
        added = [r for r in first_mention_results if r.get("action") == "first-mention-added"]
        unresolved = [r for r in first_mention_results if r.get("action") == "first-mention-unresolved"]
        existing = [r for r in first_mention_results if r.get("action") == "existing-watchlist"]
        ignored = [r for r in first_mention_results if r.get("action") == "ignored"]
        print(f"  {len(added)} auto-added · {len(unresolved)} unresolved · "
              f"{len(existing)} existing-watchlist · {len(ignored)} ignored")

    # 7. Render reports
    full_path, brief_path = render.write_daily_reports(
        projects=enriched_projects,
        velocity=velocity,
        scout=scout_candidates,
        kol_posts=kol_posts,
        first_mentions=first_mention_results,
        narrative_rotation=narrative_lib.compute_rotation(scout_candidates),
    )
    print(f"\n[report] full  → {full_path}")
    print(f"[report] brief → {brief_path}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gold-digger",
        description="Research early crypto-AI projects with daily compounding reports.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_setup = sub.add_parser("setup", help="show API key availability and sources")
    p_setup.set_defaults(func=cmd_setup)

    p_init = sub.add_parser("init", help="first-time setup: populate with starter projects + KOLs")
    p_init.add_argument("--force", action="store_true", help="add starters even if watchlist exists")
    p_init.set_defaults(func=cmd_init)

    p_enrich = sub.add_parser("enrich", help="enrich a single project")
    p_enrich.add_argument("slug", help="project slug (filename without .md)")
    p_enrich.set_defaults(func=cmd_enrich)

    p_scout = sub.add_parser("scout", help="scout-discovery pass")
    p_scout.set_defaults(func=cmd_scout)

    p_daily = sub.add_parser("daily", help="run the full daily pipeline")
    p_daily.set_defaults(func=cmd_daily)

    p_kols = sub.add_parser("kols", help="fetch recent posts from tracked KOLs")
    p_kols.add_argument("--since-hours", type=int, default=24)
    p_kols.set_defaults(func=cmd_kols)

    p_research = sub.add_parser("research", help="cited deep-dive via Perplexity")
    p_research.add_argument("slug", help="project slug to research")
    p_research.set_defaults(func=cmd_research)

    p_fm = sub.add_parser("first-mentions", help="classify KOL ticker mentions + auto-add scout projects")
    p_fm.add_argument("--since-hours", type=int, default=48)
    p_fm.set_defaults(func=cmd_first_mentions)

    p_add = sub.add_parser("add-project", help="add a new project to the watchlist")
    p_add.add_argument("slug")
    p_add.add_argument("--name")
    p_add.add_argument("--coingecko-id", dest="coingecko_id")
    p_add.add_argument("--twitter")
    p_add.add_argument("--narrative", help="comma-separated narrative tags")
    p_add.set_defaults(func=cmd_add_project)

    p_kol_add = sub.add_parser("add-kol", help="add a new KOL to the watchlist")
    p_kol_add.add_argument("handle", help="X/Twitter handle without @")
    p_kol_add.add_argument("--platform", default="x")
    p_kol_add.add_argument("--weight", type=float, default=1.0)
    p_kol_add.add_argument("--focus", help="comma-separated focus tags (e.g. ai-crypto,low-cap)")
    p_kol_add.set_defaults(func=cmd_add_kol)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
