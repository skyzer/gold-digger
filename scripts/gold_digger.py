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


# Each key's signup URL + description for the interactive wizard.
KEY_GUIDE: Dict[str, Dict[str, str]] = {
    "COINGECKO_API_KEY": {
        "url": "https://www.coingecko.com/en/developers/dashboard",
        "desc": "CoinGecko — price, mcap, supply, new-listing scout (Demo tier is free)",
        "priority": "required",
    },
    "XAI_API_KEY": {
        "url": "https://console.x.ai/",
        "desc": "xAI grok-search — KOL feed tracking, first-mention auto-scout",
        "priority": "highly recommended",
    },
    "PERPLEXITY_API_KEY": {
        "url": "https://www.perplexity.ai/account/api/keys",
        "desc": "Perplexity — cited deep-research for DD briefs",
        "priority": "recommended",
    },
    "BRAVE_API_KEY": {
        "url": "https://api.search.brave.com/app/keys",
        "desc": "Brave Search — open-web scout (free 2k queries/month)",
        "priority": "recommended",
    },
    "GITHUB_TOKEN": {
        "url": "https://github.com/settings/tokens (or run `gh auth login`)",
        "desc": "GitHub — repo commits, stars, dev-to-price divergence",
        "priority": "recommended",
    },
    "EXA_API_KEY": {
        "url": "https://exa.ai",
        "desc": "Exa — semantic search scout (free 1k/month, alt to Brave)",
        "priority": "optional",
    },
    "OPENROUTER_API_KEY": {
        "url": "https://openrouter.ai/keys",
        "desc": "OpenRouter — alt Perplexity Sonar path",
        "priority": "optional",
    },
}


def cmd_setup(args: argparse.Namespace) -> int:
    """Show key availability OR run interactive wizard with --interactive."""
    if getattr(args, "interactive", False):
        return _cmd_setup_interactive()
    # Default: show the availability matrix
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
    print()
    print("Missing keys? Run `gold-digger setup --interactive` to add them.")
    return 0


def _cmd_setup_interactive() -> int:
    """Interactive wizard — prompts for each missing key, writes to user-chosen location."""
    import os as _os

    print("\n" + "=" * 60)
    print("  Gold Digger — Interactive Setup")
    print("=" * 60)
    print("\nThis wizard will help you configure your API keys.")
    print("For each missing key, you'll see a URL to sign up + a prompt.")
    print()
    print("  • Press Enter (empty input) to SKIP a specific key")
    print("  • Press Ctrl+C to abort the entire wizard")
    print("  • You can re-run `gold-digger setup --interactive` later to add")
    print("    any keys you skipped today")
    print()

    # Step 1: show what's already configured
    print("Checking existing configuration...\n")
    found_count = 0
    missing = []
    for key_name in KEY_GUIDE:
        value, source = key_resolver.resolved_source(key_name)
        if value:
            print(f"  ✓ {key_name:<24} found at {source}")
            found_count += 1
        else:
            missing.append(key_name)
            print(f"  ✗ {key_name:<24} missing ({KEY_GUIDE[key_name]['priority']})")
    print(f"\n{found_count} already configured, {len(missing)} missing.\n")

    if not missing:
        print("All known keys are set. Nothing to do!")
        return 0

    # Step 2: prompt for each missing key
    new_keys: Dict[str, str] = {}
    for key_name in missing:
        guide = KEY_GUIDE[key_name]
        print(f"\n─── {key_name} ({guide['priority']}) ───")
        print(f"  {guide['desc']}")
        print(f"  Get a key: {guide['url']}")
        try:
            raw = input(f"  Paste key (or Enter to skip): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n(aborted)")
            return 1
        if raw:
            new_keys[key_name] = raw
            print(f"  ✓ captured")
        else:
            print(f"  ⊘ skipped")

    if not new_keys:
        print("\nNo keys entered. Nothing written.")
        return 0

    # Step 3: choose destination
    print("\n" + "─" * 60)
    print("Where should I save these keys?\n")
    print("  [1] ~/.config/shared/.env   (recommended — reused by other tools)")
    print("  [2] ~/.config/gold-digger/.env   (dedicated to Gold Digger)")
    print("  [3] Print export lines I can paste into my shell profile")
    try:
        choice = input("\n  Choice [1]: ").strip() or "1"
    except (EOFError, KeyboardInterrupt):
        print("\n(aborted)")
        return 1

    if choice == "3":
        print("\n" + "─" * 60)
        print("Add these lines to ~/.bash_profile or ~/.zshrc:\n")
        for k, v in new_keys.items():
            print(f'  export {k}="{v}"')
        print("\nThen `source ~/.bash_profile` or open a new terminal.")
        return 0

    # Choose file path
    if choice == "2":
        target = Path.home() / ".config" / "gold-digger" / ".env"
    else:
        target = Path.home() / ".config" / "shared" / ".env"

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _os.chmod(target.parent, 0o700)
    except Exception:
        pass

    # Merge with existing file content (preserve other keys)
    existing_lines: List[str] = []
    existing_keys: set[str] = set()
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("export ") and "=" in stripped:
                k = stripped[7:].split("=", 1)[0].strip()
                if k in new_keys:
                    continue  # will be rewritten
                existing_keys.add(k)
            existing_lines.append(line)

    with target.open("w", encoding="utf-8") as f:
        if not existing_lines:
            f.write("# Shared API credentials for local research tools.\n")
            f.write("# Location: {}\n".format(target))
            f.write("# Permissions: 0600 (owner read/write only)\n\n")
        else:
            f.write("\n".join(existing_lines) + "\n")
        for k, v in new_keys.items():
            f.write(f'export {k}="{v}"\n')
    try:
        _os.chmod(target, 0o600)
    except Exception:
        pass

    print(f"\n✓ Saved {len(new_keys)} keys to {target}")
    print(f"✓ Permissions set to 0600 (owner-only)")

    # Offer to add source line to shell profile
    for profile in (Path.home() / ".bash_profile", Path.home() / ".zshrc"):
        if not profile.exists():
            continue
        text = profile.read_text(encoding="utf-8") if profile.exists() else ""
        if str(target) in text or f'"$HOME/.config/{target.parent.name}/.env"' in text:
            continue  # already sourced
        try:
            choice2 = input(f"\nAdd source line to {profile}? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice2 = "n"
        if choice2 in ("", "y", "yes"):
            with profile.open("a", encoding="utf-8") as f:
                f.write(f"\n# Gold Digger credentials\n")
                f.write(f'if [ -f "{target}" ]; then set -a; . "{target}"; set +a; fi\n')
            print(f"  ✓ Added source line to {profile}")
        break  # only one profile needed

    print("\n" + "=" * 60)
    print("Setup complete! New shells will pick up the keys automatically.")
    print("For THIS shell, run: source {}".format(target))
    print("\nNext: `gold-digger init` to add starter projects")
    print("      `gold-digger daily` to run your first research cycle")
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    """Diagnostic report: what's configured, what's broken, how to fix it."""
    import os
    import sys as _sys
    import shutil as _shutil

    print("\n" + "=" * 60)
    print("  Gold Digger — Diagnostic")
    print("=" * 60)

    # Environment
    print(f"\n[Environment]")
    print(f"  Python:          {_sys.version.split()[0]}")
    print(f"  Platform:        {_sys.platform}")
    print(f"  Repo location:   {Path(__file__).resolve().parent.parent}")
    print(f"  Data directory:  {storage.data_root()}")
    print(f"  Data writable:   {'yes' if storage.data_root().exists() and os.access(storage.data_root(), os.W_OK) else 'NO — run setup'}")

    # Keys
    print(f"\n[API Keys]")
    keys = all_keys()
    configured = 0
    for key_name in KEY_GUIDE:
        value, source = key_resolver.resolved_source(key_name)
        priority = KEY_GUIDE[key_name]["priority"]
        if value:
            print(f"  ✓ {key_name:<24} {priority:<20} {source}")
            configured += 1
        else:
            print(f"  ✗ {key_name:<24} {priority:<20} NOT FOUND")
    print(f"\n  {configured}/{len(KEY_GUIDE)} configured. Missing? → gold-digger setup --interactive")

    # Sources
    print(f"\n[Data Sources]")
    for src in SOURCES:
        if src.available(keys):
            print(f"  ✓ {src.name:<20} ready")
        else:
            missing_keys = [k for k in src.requires_keys if not keys.get(k)]
            print(f"  ✗ {src.name:<20} missing: {', '.join(missing_keys)}")

    # Dependencies
    print(f"\n[Dependencies]")
    for binary in ("python3", "uv", "gh", "git"):
        path = _shutil.which(binary)
        status = path if path else "NOT FOUND"
        print(f"  {'✓' if path else '✗'} {binary:<20} {status}")

    # last30days
    print(f"\n[last30days skill]")
    from sources.last30days import _locate_last30days
    l30_root = _locate_last30days()
    if l30_root:
        print(f"  ✓ Installed at:     {l30_root}")
    else:
        print(f"  ✗ NOT FOUND. Install with:")
        print(f"      gh repo clone mvanhorn/last30days-skill ~/projects/last30days-skill")
        print(f"      cd ~/projects/last30days-skill && uv sync")

    # Harness detection
    print(f"\n[Harness Integration]")
    harness_paths = {
        "Claude Code skill": Path.home() / ".claude" / "skills" / "gold-digger",
        "OpenClaw plugin":   Path.home() / ".openclaw" / "plugins" / "gold-digger",
        "Codex plugin":      Path.home() / ".codex" / "plugins" / "gold-digger",
        "Hermes plugin":     Path.home() / ".hermes" / "plugins" / "gold-digger",
    }
    for label, path in harness_paths.items():
        if path.exists() or path.is_symlink():
            print(f"  ✓ {label:<22} {path}")
        else:
            print(f"  ⊘ {label:<22} not installed")

    # Data status
    print(f"\n[Data State]")
    root = storage.data_root()
    projects = list((root / "projects").glob("*.md")) if (root / "projects").exists() else []
    kols = list((root / "kols").glob("*.md")) if (root / "kols").exists() else []
    snaps = list((root / "snapshots").glob("*.md")) if (root / "snapshots").exists() else []
    reports = list((root / "reports" / "daily").glob("*.md")) if (root / "reports" / "daily").exists() else []
    print(f"  Projects:        {len(projects)}")
    print(f"  KOLs:            {len(kols)}")
    print(f"  Snapshots:       {len(snaps)}")
    print(f"  Daily reports:   {len(reports)}")
    if not projects:
        print(f"\n  No projects yet. Run: gold-digger init  (starter kit)")
        print(f"                  or:  gold-digger add-project <name>")

    # last30days store
    print(f"\n[Research Store (SQLite)]")
    db_path = Path.home() / ".local" / "share" / "last30days" / "research.db"
    if db_path.exists():
        size_kb = db_path.stat().st_size / 1024
        print(f"  ✓ {db_path} ({size_kb:.0f} KB)")
    else:
        print(f"  ⊘ not yet created — will be built on first `gold-digger daily`")

    # Status summary
    print("\n" + "=" * 60)
    blocked = []
    if configured == 0:
        blocked.append("no keys configured")
    if not l30_root:
        blocked.append("last30days not installed")
    if not projects:
        blocked.append("no projects in watchlist")
    if blocked:
        print(f"STATUS: {', '.join(blocked)}")
        print(f"\nRecommended fix: gold-digger install  (does all bootstrap)")
    else:
        print(f"STATUS: ready — run `gold-digger daily`")
    return 0


def cmd_install(_args: argparse.Namespace) -> int:
    """Bootstrap everything: clone last30days, run setup wizard, init, first daily."""
    import shutil as _shutil

    print("\n" + "=" * 60)
    print("  Gold Digger — Install & Bootstrap")
    print("=" * 60)

    # Step 1: ensure last30days is installed
    from sources.last30days import _locate_last30days
    if _locate_last30days():
        print("\n[1/4] ✓ last30days already installed")
    else:
        print("\n[1/4] Installing last30days...")
        if not _shutil.which("gh"):
            print("  ✗ `gh` CLI not found. Install from https://cli.github.com/ first.")
            return 1
        if not _shutil.which("uv"):
            print("  ✗ `uv` not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh")
            return 1
        target = Path.home() / "projects" / "last30days-skill"
        target.parent.mkdir(parents=True, exist_ok=True)
        import subprocess
        subprocess.run(["gh", "repo", "clone", "mvanhorn/last30days-skill", str(target)], check=False)
        subprocess.run(["uv", "sync"], cwd=target, check=False)
        if _locate_last30days():
            print(f"  ✓ Installed to {target}")
        else:
            print(f"  ✗ Install failed. Try manually.")
            return 1

    # Step 2: interactive key setup
    print("\n[2/4] API key setup")
    _cmd_setup_interactive()

    # Step 3: starter watchlist
    print("\n[3/4] Starter watchlist")
    try:
        choice = input("Add starter projects + KOLs (unigox, openserv, DegenSensei, resdegen)? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = "n"
    if choice in ("", "y", "yes"):
        fake_args = argparse.Namespace(force=False)
        cmd_init(fake_args)

    # Step 4: offer first daily run
    print("\n[4/4] First research cycle")
    try:
        choice = input("Run `gold-digger daily` now to prove everything works? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = "n"
    if choice in ("y", "yes"):
        fake_args = argparse.Namespace()
        cmd_daily(fake_args)

    print("\n" + "=" * 60)
    print("Install complete.")
    print("\nDaily usage:")
    print("  gold-digger daily              # full research cycle")
    print("  gold-digger dashboard          # open the HTML dashboard")
    print("  gold-digger doctor             # diagnostic if anything breaks")
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
    """Add a project. If only a slug/name is given, auto-resolve via CoinGecko."""
    from sources.coingecko import search_coin, CoinGecko
    slug = args.slug
    path = _slug_to_path(slug)
    if path.exists():
        print(f"Already exists: {path}")
        return 1

    keys = all_keys()
    fm = schema.empty_project(slug, name=args.name or slug)

    # Manual overrides take priority
    if args.coingecko_id:
        fm["coingecko_id"] = args.coingecko_id
    if args.twitter:
        fm["twitter"] = args.twitter
    if args.narrative:
        fm["narrative"] = [n.strip() for n in args.narrative.split(",")]

    # Auto-resolve if no coingecko_id was provided explicitly
    cg_key = keys.get("COINGECKO_API_KEY")
    if not fm.get("coingecko_id") and cg_key:
        print(f"Searching CoinGecko for \"{slug}\"...")
        coin = search_coin(slug, cg_key)
        if coin:
            cg_id = coin.get("id") or coin.get("api_symbol")
            name = coin.get("name") or slug
            print(f"  Found: {name} (id={cg_id}, symbol={coin.get('symbol')})")
            fm["coingecko_id"] = cg_id
            fm["name"] = name
            fm["ticker"] = (coin.get("symbol") or "").upper() or None
            # Now do a full enrichment pass using CoinGecko
            print(f"  Enriching from CoinGecko...")
            cg_source = CoinGecko()
            enrichment = cg_source.fetch_watchlist(fm, keys)
            if enrichment:
                fm.update(enrichment)
                print(f"  Auto-filled {len(enrichment)} fields")
        else:
            print(f"  Not found on CoinGecko — creating as pre-token project")
            print(f"  Tip: run `gold-digger research {slug}` for a Perplexity DD brief")

    # Classify narrative if not set manually
    if not fm.get("narrative") or fm["narrative"] == []:
        tags = narrative_lib.classify(fm)
        fm["narrative"] = tags

    body = schema.project_body_template(fm.get("name") or slug)
    storage.write_project(path, fm, body)
    print(f"\nCreated: {path}")

    # --- Auto-research: run ALL enrichment sources + Perplexity DD ---
    if not args.skip_research:
        print(f"\nResearching {fm.get('name', slug)}...\n")
        # Run every source for enrichment (GitHub, XAI mentions, last30days social, DeFiLlama)
        all_updates: Dict[str, Any] = {}
        for src in SOURCES:
            if not src.available(keys):
                continue
            try:
                updates = src.fetch_watchlist(fm, keys)
                if updates:
                    all_updates.update(updates)
                    print(f"  [{src.name}] {len(updates)} fields")
            except Exception as exc:
                print(f"  [{src.name}] error: {exc}")
        if all_updates:
            fm.update(all_updates)
            storage.update_project_frontmatter(path, all_updates)

        # Perplexity cited DD brief — the real online research
        pplx_key = keys.get("PERPLEXITY_API_KEY")
        if pplx_key:
            from datetime import datetime, timezone as tz
            print(f"\n  [perplexity] running cited DD brief...")
            prompt = project_dd_prompt(fm)
            result = pplx_research(prompt, pplx_key, model="sonar-pro")
            if result:
                text, citations = result
                date = datetime.now(tz.utc).strftime("%Y-%m-%d")
                research_dir = storage.data_root() / "research"
                research_dir.mkdir(parents=True, exist_ok=True)
                brief_path = research_dir / f"{slug}-{date}.md"
                brief_lines = [
                    f"# Gold Digger research brief — {fm.get('name', slug)}",
                    f"_Date: {date} · Model: sonar-pro · Project: [[{slug}]]_",
                    "", "## Research brief", "", text,
                    "", "## Citations", "",
                ]
                for i, url in enumerate(citations, 1):
                    brief_lines.append(f"{i}. {url}")
                brief_path.write_text("\n".join(brief_lines), encoding="utf-8")
                print(f"  [perplexity] {len(citations)} citations → {brief_path}")
                # Show a short preview
                preview = text[:500].replace("\n", "\n    ")
                print(f"\n    {preview}")
                if len(text) > 500:
                    print(f"\n    ... (full brief in {brief_path})")
            else:
                print(f"  [perplexity] no result returned")
        else:
            print(f"\n  (Perplexity DD skipped — no PERPLEXITY_API_KEY)")

    # Final summary
    print(f"\nProject ready: {path}")
    for field in ("name", "ticker", "coingecko_id", "price_usd", "mcap",
                   "narrative", "website", "twitter", "github_stars",
                   "mention_count_7d", "mention_count_30d"):
        val = fm.get(field)
        if val is not None and val != [] and val != "" and val != 0:
            print(f"  {field}: {val}")
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


def cmd_discover_kols(args: argparse.Namespace) -> int:
    """Discover new KOLs similar to your tracked ones via --x-related."""
    from sources.last30days import discover_related_handles
    kols = kol_lib.load_all()
    if not kols:
        print("No KOLs tracked. Run `gold-digger add-kol <handle>` first.")
        return 1
    print(f"Discovering KOLs related to {len(kols)} tracked handles...\n")
    for kol in kols:
        handle = kol.get("handle")
        print(f"[@{handle}] searching for related accounts...")
        payload = discover_related_handles(handle)
        if payload:
            print(f"  Got results — check output for new handle suggestions")
        else:
            print(f"  (no results)")
    print("\nReview suggestions above. Add interesting ones with:")
    print("  gold-digger add-kol <handle> --focus ai-crypto")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export full Gold Digger state as JSON + JSONL."""
    from lib import export as export_lib
    since = getattr(args, "since", None)
    json_path, jsonl_path = export_lib.write_export(since=since)
    import json
    data = json.loads(json_path.read_text())
    summary = data.get("summary", {})
    print(f"Exported: {summary.get('total_projects', 0)} projects, "
          f"{summary.get('total_kols', 0)} KOLs, "
          f"{summary.get('kol_mentions_recorded', 0)} KOL mentions, "
          f"{summary.get('daily_reports', 0)} reports")
    print(f"\n  JSON  → {json_path}")
    print(f"  JSONL → {jsonl_path}")
    print(f"\nUsage: cat {json_path} | jq '.projects[] | .name, .mcap'")
    return 0


def cmd_dashboard(_args: argparse.Namespace) -> int:
    """Generate a static HTML dashboard."""
    from lib import dashboard, export as export_lib
    # Ensure export exists first
    export_lib.write_export()
    path = dashboard.write_dashboard()
    print(f"Dashboard → {path}")
    print(f"\nOpen: open {path}")
    return 0


def cmd_store_trending(_args: argparse.Namespace) -> int:
    """Show what's trending across the accumulated research store."""
    from sources.last30days import store_trending, store_stats
    stats = store_stats()
    if stats:
        print("=== Research store stats ===")
        print(stats)
    trending = store_trending()
    if trending:
        print("=== Trending across all research ===")
        print(trending)
    else:
        print("No trending data yet. Run `gold-digger daily` a few times to build the store.")
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

    # 7. Research store trending (compounding intelligence from all prior runs)
    from sources.last30days import store_trending as _store_trending
    trending_raw = _store_trending()
    if trending_raw:
        print(f"\n[store] trending topics pulled from research lake")
    else:
        print(f"\n[store] no trending data yet (builds over time)")

    # 8. Render reports
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

    # 9. Export + dashboard (auto-generated every daily run)
    from lib import export as export_lib, dashboard
    json_path, jsonl_path = export_lib.write_export()
    print(f"[export] → {json_path}")
    dash_path = dashboard.write_dashboard()
    print(f"[dashboard] → {dash_path}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gold-digger",
        description="Research early crypto-AI projects with daily compounding reports.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_setup = sub.add_parser("setup", help="show API key availability and sources")
    p_setup.add_argument("--interactive", "-i", action="store_true", help="interactive key wizard")
    p_setup.set_defaults(func=cmd_setup)

    p_install = sub.add_parser("install", help="bootstrap everything: last30days + keys + starter + first run")
    p_install.set_defaults(func=cmd_install)

    p_doctor = sub.add_parser("doctor", help="diagnose setup problems + show what's configured")
    p_doctor.set_defaults(func=cmd_doctor)

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
    p_add.add_argument("--skip-research", action="store_true", help="skip auto-enrichment + Perplexity DD")
    p_add.set_defaults(func=cmd_add_project)

    p_kol_add = sub.add_parser("add-kol", help="add a new KOL to the watchlist")
    p_kol_add.add_argument("handle", help="X/Twitter handle without @")
    p_kol_add.add_argument("--platform", default="x")
    p_kol_add.add_argument("--weight", type=float, default=1.0)
    p_kol_add.add_argument("--focus", help="comma-separated focus tags (e.g. ai-crypto,low-cap)")
    p_kol_add.set_defaults(func=cmd_add_kol)

    p_discover = sub.add_parser("discover-kols", help="find KOLs similar to your tracked ones")
    p_discover.set_defaults(func=cmd_discover_kols)

    p_trending = sub.add_parser("trending", help="show trending topics from the research store")
    p_trending.set_defaults(func=cmd_store_trending)

    p_export = sub.add_parser("export", help="export full state as JSON + JSONL")
    p_export.add_argument("--since", help="only include data from this date (YYYY-MM-DD)")
    p_export.set_defaults(func=cmd_export)

    p_dash = sub.add_parser("dashboard", help="generate static HTML dashboard")
    p_dash.set_defaults(func=cmd_dashboard)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
