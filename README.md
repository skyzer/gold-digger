# Gold Digger

Research early crypto-AI projects and generate daily compounding reports. Watchlist enrichment + scout discovery + KOL signal digest, writing markdown that lives in your notes vault.

**Goal:** surface projects — with or without a token today — that could 10–100x during the next bull run.

## Quick start

```bash
# 1. Install (choose your harness)
/plugin install github.com/skyzer/gold-digger        # Claude Code
openclaw install github.com/skyzer/gold-digger        # OpenClaw
codex plugin install github.com/skyzer/gold-digger    # Codex
hermes install github.com/skyzer/gold-digger          # Hermes

# 2. Set your API keys once (see "Where to put keys" below)
#    Gold Digger finds keys in the environment or in ~/.config/shared/.env

# 3. First run
gold-digger setup         # interactive: picks location, checks what's available
gold-digger daily         # full daily run: enrich + scout + report
gold-digger enrich openserv  # enrich a single project
```

Reports land in `$GOLD_DIGGER_DATA/reports/daily/YYYY-MM-DD.md`. If you don't set `GOLD_DIGGER_DATA`, the default is `~/Documents/GoldDigger/`.

## What it does

**Two modes, both always on:**

1. **Watchlist enrichment** — every project in `projects/*.md` gets refreshed daily: price, mcap, FDV, supply, 24h/7d/30d %, TVL, GitHub commits, follower deltas, KOL mentions, new announcements.
2. **Scout discovery** — automatically finds new projects you don't know about yet: CoinGecko new listings, DeFiLlama new raises, Cookie.fun / Virtuals launchpad drops, first-mention extraction from your KOL feeds, open-web search for emerging narratives.

Scout finds enter the watchlist as `tier: scout` (light tracking). You manually promote the interesting ones to `tier: tracked` (full daily enrichment).

**Daily reports** (markdown, two files per day):
- `YYYY-MM-DD.md` — full report: new discoveries, watchlist deltas, KOL digest, trending narratives, heating-up projects, action queue
- `YYYY-MM-DD-brief.md` — TL;DR: best find, biggest mover, hottest KOL signal, action item, narrative of the day

**Trends compound across days.** Mention counts, price snapshots, follower deltas roll into `snapshots/` as daily markdown tables. The aggregator computes velocity (today vs 7d avg) and price-vs-attention divergence. That's what makes the reports compounding instead of resetting.

## API key matrix

Nothing is required. Gold Digger runs with zero keys, just with progressively weaker signal. Add keys to unlock features.

| Key / tool | Cost | What it unlocks | What's lost without it |
|---|---|---|---|
| `COINGECKO_API_KEY` | Free Demo / Pro paid | Token price, mcap, FDV, 24h/7d/30d %, supply, exchange listings, new-listing scout | **Severe** — no price data, no new-token scout |
| `DEFILLAMA` (no key) | Free | TVL, revenue/fees, fundraising rounds DB, new-raises scout | No TVL, no funding round discovery |
| `GITHUB_TOKEN` (`gh` CLI) | Free | Commits/stars Δ, dev-to-price divergence, new-repo scout in AI-crypto orgs | No GitHub signals |
| `XAI_API_KEY` | Paid, ~$0.20/call | KOL feeds, first-mention auto-scout, X announcements, sentiment | **Major** — no KOL digest, no X alpha |
| `PERPLEXITY_API_KEY` | Paid, cheap | Deep-research subagent, cited due-diligence briefs, web-grounded synthesis | Research subagent falls back to raw search — shallower |
| `BRAVE_API_KEY` | Free 2k/mo | Open-web scout for pre-launch teasers and unannounced projects | Web scout limited |
| `EXA_API_KEY` | Free 1k/mo | Semantic-search scout ("projects that look like ai16z") | Alt to Brave |
| `OPENROUTER_API_KEY` | Paid, ~$0.02/run | Alt Perplexity Sonar path | Alt to Perplexity direct |
| `SCRAPECREATORS_API_KEY` | 10k free | TikTok/IG crypto influencer feeds | Skip for v1 — crypto alpha is on X |
| `BSKY_HANDLE` + `BSKY_APP_PASSWORD` | Free | Bluesky chatter | Minor |
| `yt-dlp` binary | Free (`pip install`) | YouTube crypto channels | No YT signals |
| `BROWSER_USE_API_KEY` | Paid | v2 feature — autonomous project website DD | Reserved for v2 |

**Minimum recommended:** `COINGECKO_API_KEY` + `XAI_API_KEY` + `BRAVE_API_KEY`. That unlocks the price/KOL/web triad — the core of the value.

## Where to put keys

Gold Digger looks in this order (first hit wins, never clobbers):

1. **Process environment** — anything already `export`ed in your shell. Works everywhere. *This is the primary path.*
2. **`~/.config/shared/.env`** — **recommended shared location**. Any local tool that reads from here benefits from the same credentials. Gold Digger reads it at runtime; never writes unless you ask.
3. **`~/.config/last30days/.env`** — if last30days is installed, Gold Digger inherits its keys.
4. **`~/.config/cowork/.env`** — Anthropic Cowork shared location.
5. **`~/.config/gold-digger/.env`** — dedicated fallback.
6. **macOS Keychain** — `gold-digger setup --keychain` writes there; resolver reads via `security find-generic-password`.
7. **1Password CLI** — if `op` is present and you've set vault references like `op://Personal/GoldDigger/XAI_API_KEY`, the resolver will `op read` them.

**Recommended setup** (one-time, reusable across tools):

```bash
mkdir -p ~/.config/shared && chmod 700 ~/.config/shared
cat > ~/.config/shared/.env << 'EOF'
export COINGECKO_API_KEY="..."
export XAI_API_KEY="..."
export BRAVE_API_KEY="..."
export PERPLEXITY_API_KEY="..."
export GITHUB_TOKEN="..."
EOF
chmod 600 ~/.config/shared/.env

# Source it automatically in every shell:
echo 'if [ -f "$HOME/.config/shared/.env" ]; then set -a; . "$HOME/.config/shared/.env"; set +a; fi' >> ~/.bash_profile
```

Keys never appear in reports, logs, or committed files. The resolver masks them (`xai-****...****`) if they ever need to show in debug output.

## Storage layout (Obsidian-friendly)

Everything is markdown. Projects are first-class pages with frontmatter for structured fields and body for notes. Daily reports wiki-link to project pages via `[[reppo]]`.

```
$GOLD_DIGGER_DATA/
├── projects/
│   ├── reppo.md            # frontmatter = structured data, body = notes
│   ├── openserv.md
│   └── _template.md        # schema template
├── kols/
│   ├── degensensei.md
│   └── resdegen.md
├── sources.md              # external sources and dashboards
├── reports/
│   └── daily/
│       ├── 2026-04-15.md         # full
│       └── 2026-04-15-brief.md   # TL;DR
├── snapshots/
│   └── 2026-04-15.md       # markdown table: price + social snapshot
└── trends/
    └── velocity.md         # rolling mention-velocity tracker
```

Point Obsidian's vault root at this directory and you have a browsable research graph. Projects backlink to KOLs that mention them; reports backlink to projects.

## Schema (per project)

Every project has these frontmatter fields. Missing data is `null`. See `references/schema.md` for the full spec.

- **Identity:** name, ticker, narrative tags, chains, twitter, github, coingecko_id
- **Token:** has_token, price_usd, mcap, fdv, %24h/7d/30d, supply, exchanges, tge_date
- **Funding:** raised_usd, investors, latest_round, valuation
- **Traction:** twitter followers + Δ, GitHub stars + commits, TVL, mainnet_status
- **Catalysts:** points_farming, airdrop_eligibility, features_shipped, upcoming_tge
- **KOL signal:** mentioned_by, mention_count_7d, mention_velocity
- **Risk:** audit, team_doxxed, vc_unlock_schedule, red_flags
- **Meta:** tier (tracked / scout), first_added, last_updated, sources

## Extending Gold Digger

Four extension points, all documented in `references/extending.md`:

1. **Data sources** — drop a Python file in `scripts/sources/_custom/` implementing the `Source` base class; auto-discovered on next run.
2. **Signal extractors** — drop a file in `scripts/extractors/_custom/` that parses source output for new patterns.
3. **Narrative taxonomy** — edit `references/narratives.md` to add tag patterns for new narratives (intents, restaking, chain abstraction, etc.).
4. **Custom scoring** — replace `scripts/lib/scoring.py` to weight signals to your taste.

## Dependencies

- **Python 3.12+**
- **[last30days](https://github.com/mvanhorn/last30days-skill)** — social and web research engine. Install first; Gold Digger calls it via subprocess for Reddit / X / HN / YouTube / web signals. Without it, Gold Digger degrades to market data + GitHub only.
- `uv` (recommended) or `pip` for Python deps
- `gh` CLI (optional, for GitHub auth inheritance)

## Roadmap

- **v0.1** — Watchlist enrichment + CoinGecko + scout skeleton *(you are here)*
- **v0.2** — Full scout pass, KOL digest via last30days, daily markdown reports, trend aggregator
- **v0.3** — Deep-dive research subagent (Perplexity-powered), Notion export, launchd/cron automation
- **v1.0** — Cookie.fun / Virtuals native sources, insider wallet tracking, listing announcement watcher, Browser Use autonomous DD

## License

MIT. See [LICENSE](./LICENSE).
