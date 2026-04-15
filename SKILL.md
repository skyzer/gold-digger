---
name: gold-digger
description: Research early crypto-AI projects and generate daily compounding reports. Use whenever the user asks to research a crypto project, find low-cap AI-agent tokens, track KOLs like DegenSensei or resdegen, check whether a project has announced a token or points program, audit a watchlist, compute mention velocity for a ticker, compare a project against similar narratives, generate a daily briefing of crypto-AI signals, or discover new projects that look like ai16z, openserv, virtuals, or other AI-agent plays. Also handles adding projects and KOLs to the watchlist, running scout discovery, and producing structured daily markdown reports.
---

# Gold Digger

Research engine for early crypto-AI projects. Watchlist enrichment + scout discovery + KOL signal digest, emitting daily markdown reports that compound over time.

## When to use this skill

Trigger on any of:
- "research project X" where X is a crypto or AI-crypto project
- "find new AI agent / DePIN / intent / restaking projects"
- "what's DegenSensei saying about X"
- "what did resdegen mention this week"
- "how much has [ticker] moved"
- "does [project] have a token / points program / airdrop"
- "run the daily gold-digger report"
- "add [project] to my watchlist"
- "what's heating up"

## Architecture (two-sentence version)

Gold Digger is a thin crypto-research layer over [last30days](https://github.com/mvanhorn/last30days-skill) + direct calls to CoinGecko / DeFiLlama / GitHub / Perplexity. It maintains a markdown-native watchlist (one `.md` per project with frontmatter), runs enrichment + scout + aggregation daily, and writes structured reports that link back to the project pages.

## How to run

**Always invoke via the Python CLI** — never reimplement the research logic in conversation.

```bash
# Full daily run (enrich all tracked projects + scout + report)
python3 ~/projects/gold-digger/scripts/gold_digger.py daily

# Enrich a single project (handy for testing / on-demand research)
python3 ~/projects/gold-digger/scripts/gold_digger.py enrich <slug>

# Scout pass only
python3 ~/projects/gold-digger/scripts/gold_digger.py scout

# Add a project by slug + coingecko id
python3 ~/projects/gold-digger/scripts/gold_digger.py add-project <slug> --coingecko-id <id>

# First-run key check
python3 ~/projects/gold-digger/scripts/gold_digger.py setup
```

The CLI emits to stdout (compact summary) and writes full output to the data directory. When the user just wants a quick answer, parse the compact summary and respond. When they want the full report, show them the path and wiki-link it.

## Key discovery

Do not ask the user for API keys in conversation. Keys live in the environment or in one of the supported config files (see README). The `gold_digger setup` subcommand shows which keys are present and which sources are therefore available. If the user reports "source X isn't working," run `setup` first and check the relevant row.

## Degradation policy

Every source is optional. Gold Digger prefers to run in degraded mode rather than fail:
- **No `COINGECKO_API_KEY`** — skip price/mcap enrichment; still write identity + social frontmatter
- **No `XAI_API_KEY`** — skip KOL digest and first-mention scout; still run watchlist enrichment and market-data scout
- **No `PERPLEXITY_API_KEY`** — deep-dive subagent falls back to raw Brave/Exa results
- **No `last30days` installed** — skip social aggregation; still run direct-API enrichment
- **All sources missing** — still runs; emits a report explaining which keys would unlock which features and stops

## Markdown conventions

Projects live at `$GOLD_DIGGER_DATA/projects/<slug>.md` with frontmatter holding structured fields and body holding notes. **Never overwrite user notes in the body** — only update frontmatter. When updating, preserve any frontmatter fields the user added manually that aren't in the schema.

Reports wiki-link to project pages (`[[openserv]]`) so Obsidian backlinks work.

Snapshots are daily tables in `snapshots/YYYY-MM-DD.md` — one row per project. The aggregator reads N days of snapshots to compute velocity and divergence.

## Referenced files

- `references/schema.md` — full project frontmatter field spec (load when the user asks about tracked fields or you need to write a new project file)
- `references/narratives.md` — user-editable narrative taxonomy (load when tagging projects or running scout with a narrative filter)
- `references/api-keys.md` — detailed matrix of which keys unlock which sources (load when the user asks "what should I get" or setup reports a missing key)
- `references/extending.md` — how to add sources, extractors, narrative tags, or custom scoring (load when the user wants to extend Gold Digger)
- `agents/gold-digger-researcher.md` — deep-dive subagent definition (invoke for full project due-diligence beyond daily enrichment)

## Output format

Daily report sections (in order):
1. **New discoveries** (scout finds from the last 24h)
2. **Watchlist deltas** (price moves, social jumps, announcements)
3. **KOL digest** (what each tracked KOL said in the last 24h, with extracted tickers)
4. **Trending narratives** (which categories are heating up)
5. **Heating up** (projects with rising mention velocity)
6. **Action queue** (projects worth deep-dive tomorrow)

Brief report: 5 bullets — best find, biggest mover, hottest KOL signal, action item, narrative of the day.

## What NOT to do

- Do not ask the user for API keys in chat — read them from the environment
- Do not overwrite user-authored notes in project file bodies
- Do not commit keys or frontmatter data to the skill repo
- Do not fabricate prices, mcap, or funding data — if a source fails, mark the field `null` in the frontmatter
- Do not reimplement social research — call last30days via subprocess
- Do not treat the daily run as idempotent — each run appends a new snapshot and may add new scout-tier projects
