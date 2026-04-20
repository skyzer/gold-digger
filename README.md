# Gold Digger

**A compounding research engine for early crypto-AI projects.** Daily watchlist enrichment, KOL signal digest, scout discovery, narrative rotation, and Perplexity-backed deep dives — all written as plain markdown so other agents can read it without an API.

> **Goal:** surface crypto-AI projects — with or without a token today — that could 10–100x during the next bull run, by turning daily research into an auditable data trail that gets smarter every day.

**KOL** = _Key Opinion Leader_ — a crypto influencer (typically on X/Twitter) whose calls and first-mentions move retail attention and often precede price discovery. Gold Digger's job is to capture every ticker your tracked KOLs mention, dedupe, auto-scout projects they surface, and score their accuracy over time.

---

## Why "compounding"?

A one-off crypto research session is shallow. The value comes from running Gold Digger every day and letting the data accumulate. Here's what emerges over time:

<img width="1034" height="309" alt="image" src="https://github.com/user-attachments/assets/a194fc0f-dd9c-4f6e-9526-d71db57c2ac6" />


One run is a lookup. Seven runs reveal velocity. Thirty runs show which narratives are rotating in. Ninety runs start scoring your KOLs by their hit rate. Gold Digger is not a query tool — it's a research loop.

---

## Gold Digger vs. last30days

Gold Digger is built on top of [last30days](https://github.com/mvanhorn/last30days-skill) — it calls last30days for social + web research and adds a crypto intelligence layer on top. They solve different problems:

| | Gold Digger | last30days |
|---|---|---|
| **Core job** | Intelligence — track what's changing and what the change means | Recall — cast a wide net across social platforms |
| **Time horizon** | Compounding: "day 1 vs day 7 vs day 30 vs day 90" | Snapshot: "what happened in the last 30 days?" |
| **Memory** | Everything — snapshots, KOL memory, project files, trends | None by default (SQLite store is opt-in) |
| **Market data** | CoinGecko price/mcap/supply, DeFiLlama TVL, GitHub commits | Zero |
| **Output** | Mention velocity, price-vs-attention divergence, narrative rotation, KOL accuracy scoring | Raw findings per query |
| **Entity understanding** | `"circle"` = ambiguous word, requires crypto context to count as Circle the company | `"circle"` = a string |
| **Structure** | Markdown project files with frontmatter schema, readable by Obsidian and other agents | JSON blob per run |
| **KOL tracking** | Persistent memory of every KOL call, first-mention auto-scout, dedup, accuracy backtest | Can search a handle's posts |
| **Who reads it** | Other agents, dashboards, LLMs, Obsidian — plain files, no API needed | The human who ran it |

**last30days is Gold Digger's ears.** It hears what the internet is saying right now. **Gold Digger is the brain** that remembers what the ears heard yesterday, notices when today sounds different, and compounds that into actionable intelligence over weeks and months.

Without last30days, Gold Digger has market data but no social signal. Without Gold Digger, last30days is a firehose that resets every run.

---

## Quick start — the fastest path

```bash
# 1. Install (choose your harness)
/plugin install github.com/skyzer/gold-digger        # Claude Code
openclaw install github.com/skyzer/gold-digger       # OpenClaw
codex plugin install github.com/skyzer/gold-digger   # Codex
hermes install github.com/skyzer/gold-digger         # Hermes

# 2. One-shot bootstrap — installs last30days, prompts for your keys,
#    populates a starter watchlist, and offers to run the first daily cycle.
gold-digger install
```

That's it. The `install` command walks you through everything interactively. If something goes wrong, run `gold-digger doctor` — it tells you exactly what's missing and how to fix it.

### Manual setup (if you prefer control)

```bash
# Check what's detected + interactive key wizard
gold-digger setup --interactive

# See full diagnostic + recommended fixes
gold-digger doctor

# Populate watchlist manually (one word per project — AI does the rest)
gold-digger add-project unigox                  # pre-token, auto-scouts social
gold-digger add-project openserv                # finds CoinGecko, GitHub, mentions
gold-digger add-project bittensor               # 18+ fields auto-filled

# Follow KOLs
gold-digger add-kol DegenSensei --focus ai-crypto,low-cap
gold-digger add-kol resdegen    --focus ai-crypto,low-cap
gold-digger add-kol andyyy      --focus ai-crypto

# Run the full research cycle
gold-digger daily
```

Reports land in `data/reports/daily/YYYY-MM-DD.md` inside the repo. The `data/` directory is gitignored — your research stays local.

### Where your API keys live

Gold Digger checks **17 locations** for API keys, so it'll find them wherever you or your harness stored them:

1. Process environment (exported in current shell)
2. `~/.config/shared/.env` — **recommended**, reused by other tools
3. `~/.config/last30days/.env` — inherit from last30days if installed
4. `~/.config/cowork/.env` — Anthropic Cowork shared location
5. `~/.config/gold-digger/.env` — dedicated fallback
6. `~/.config/hermes/.env` — Hermes harness storage
7. `~/.config/openclaw/.env` — OpenClaw harness storage
8. `~/.config/codex/.env` — Codex harness storage
9–13. Shell profiles: `~/.bash_profile`, `~/.bashrc`, `~/.profile`, `~/.zshrc`, `~/.zshenv` — `export KEY=value` lines parsed directly
14. `~/.claude/settings.json` → `env` block — Claude Code's native env storage
15. `~/.claude.json` → `env` block — alternate Claude config path
16. macOS Keychain (optional, via `security` CLI)
17. 1Password CLI (if you use `op://...` references)

If `gold-digger install` or `setup --interactive` can't find your keys, run `gold-digger doctor` and it'll tell you exactly which paths were searched.

### Where your research lives — and how to migrate between agents

Gold Digger decouples **code** from **data**.

- **Code** is wherever the harness installed the plugin (Claude Code's `~/.claude/skills/`, OpenClaw's plugin cache, a manual git clone, etc.). Code gets reinstalled or overwritten freely.
- **Data** is a single directory you control — projects, KOLs, snapshots, reports, the SQLite research lake. Never touched by plugin updates.

**By default**, data lives at `<repo>/data/` — convenient if you only use one install.

**To share one dataset across multiple harnesses** (strongly recommended — this is the whole point of the cross-harness design), point every install at the same location via `GOLD_DIGGER_DATA`:

```bash
# Add to ~/.config/shared/.env (or wherever you keep environment variables)
export GOLD_DIGGER_DATA="$HOME/research/gold-digger/data"
```

Now:

- Claude Code skill → reads/writes to `$HOME/research/gold-digger/data`
- OpenClaw plugin → reads/writes to `$HOME/research/gold-digger/data`
- Codex plugin → reads/writes to `$HOME/research/gold-digger/data`
- Manual CLI runs → reads/writes to `$HOME/research/gold-digger/data`

**Why this matters:**

- **Switch agents freely.** Install Gold Digger in Claude Code today, run daily cycles for a week, then switch to OpenClaw for its scheduling. Research continues unbroken — no import/export, no data migration.
- **Multiple agents, one dataset.** OpenClaw runs the 2am daily on a cron. You manually trigger `gold-digger research <slug>` from Claude Code on demand. Both write to the same files.
- **Back up once, restore anywhere.** The entire portable state is one directory:
  ```bash
  tar czf gold-digger-backup-$(date +%Y%m%d).tar.gz "$GOLD_DIGGER_DATA"
  ```
- **Survive plugin wipes.** Any harness can reinstall, update, or delete its plugin cache without touching your data.

**Verify what's being used:** `gold-digger doctor` prints the resolved data directory. If it shows the wrong path, the harness didn't pass the env var — fix it there, not in Gold Digger.

---

## Architecture — how data flows

<img width="1125" height="727" alt="image" src="https://github.com/user-attachments/assets/74a32f69-026a-4294-8e81-8b7b81c298d5" />


Every arrow is a plain-text write. Every store is a flat file. No database, no API layer — any tool that reads markdown or parses an embedded JSON block can consume Gold Digger's output.

---

## Project lifecycle — state machine

<img width="1094" height="512" alt="image" src="https://github.com/user-attachments/assets/4147fb8d-85a9-4eff-8f97-fb72413082ae" />


Projects flow through tiers based on signal, not buckets. You always have the final say — Gold Digger auto-adds and auto-suggests, but promotion to `tracked` and archiving is a manual frontmatter edit. Every transition is preserved in the project file's git history.

---

## KOL first-mention flow

Tracked KOLs are a source of alpha *if* you can capture every ticker they mention, resolve it to a real project, and dedupe against what you already know. Gold Digger does this every day:

<img width="1130" height="595" alt="image" src="https://github.com/user-attachments/assets/084d6570-2741-40b8-971c-159e3c060fa3" />


The persistent memory file `trends/kol-mentions.md` records every (KOL, ticker) pair so the same mention never re-triggers, and builds a long-term record you can backtest: "which of DegenSensei's first-mentions 2x'd within 30 days?"

---

## Where the value compounds

<img width="1097" height="596" alt="image" src="https://github.com/user-attachments/assets/b8c1d4f9-0be2-4e16-a310-8333d724cc91" />


The orange nodes on the right are what Gold Digger is built to surface. None of them are visible on day 1. All of them emerge as the daily markdown trail grows.

---

## What it does

**Two modes, both always on:**

1. **Watchlist enrichment** — every tracked project gets refreshed daily: price, mcap, FDV, 24h/7d/30d %, supply, TVL, GitHub commits, follower deltas, KOL mention count.
2. **Scout discovery** — finds new projects via CoinGecko new listings, DeFiLlama protocols, KOL first-mentions, and Perplexity/Brave web search. Scout finds enter the watchlist as `tier: scout` for light tracking. You manually promote the interesting ones to `tier: tracked`.

**On-demand tools:**
- `gold-digger research <slug>` — Perplexity-powered cited DD brief
- `gold-digger kols [--since-hours N]` — KOL digest over any window
- `gold-digger first-mentions` — run the first-mention auto-scout in isolation
- `gold-digger scout` — scout pass without enrichment

**Daily reports** (two markdown files per day):
- `YYYY-MM-DD.md` — full report: new discoveries, watchlist deltas, KOL digest, first-mentions, narrative rotation, heating up, action queue
- `YYYY-MM-DD-brief.md` — 5-bullet TL;DR for quick morning read

---

## Designed for other agents to consume

Gold Digger writes plain markdown and embedded JSON. Any LLM, dashboard, CLI, or other agent can read the data directory without going through Gold Digger itself:

```bash
# List tracked projects
ls "$GOLD_DIGGER_DATA/projects/"

# Filter by narrative
grep -l "narrative:.*ai-agents" "$GOLD_DIGGER_DATA/projects/"*.md

# Feed a project to an LLM for synthesis
cat "$GOLD_DIGGER_DATA/projects/openserv.md" | llm "what should I watch for?"

# Parse today's snapshot CSV block
awk '/```csv/,/```/' "$GOLD_DIGGER_DATA/snapshots/$(date +%Y-%m-%d).md"

# Read the full KOL memory
cat "$GOLD_DIGGER_DATA/trends/kol-mentions.md"

# Check what DegenSensei has been mentioning
grep "DegenSensei" "$GOLD_DIGGER_DATA/trends/kol-mentions.md"
```

**Project files are the contract.** If you want to add your own findings to a tracked project without breaking Gold Digger's schema, append to the body of the `.md` file — Gold Digger never touches the body on enrichment, only the frontmatter. Your notes compound alongside the automated data.

---

## API key matrix

Nothing is required. Gold Digger runs with zero keys — just with progressively weaker signal. Add keys to unlock features.

| Key / tool | Cost | Unlocks | Lost without it |
|---|---|---|---|
| `COINGECKO_API_KEY` | Free Demo / Pro paid | Price, mcap, FDV, 24h/7d/30d %, supply, exchange listings, new-listing scout | **Severe** — no price data, no new-token scout |
| `DEFILLAMA` *(no key)* | Free | TVL, revenue/fees, AI-tagged protocol scout | No TVL, no DeFi scout |
| `GITHUB_TOKEN` | Free via `gh` | Commits/stars Δ, dev-to-price divergence | No GitHub signals |
| `XAI_API_KEY` | ~$0.02–0.20/call | KOL feeds, first-mention auto-scout, X announcements | **Major** — no KOL digest, no X alpha |
| `PERPLEXITY_API_KEY` | Paid, cheap | Cited deep-research for DD subagent | Research falls back to raw search |
| `BRAVE_API_KEY` | Free 2k/mo | Open-web scout for pre-launch teasers | Web scout limited |
| `EXA_API_KEY` | Free 1k/mo | Semantic-search scout ("projects like ai16z") | Alt to Brave |
| `OPENROUTER_API_KEY` | Paid, cheap | Alt Perplexity Sonar path via OpenRouter | Alt to Perplexity direct |
| `SCRAPECREATORS_API_KEY` | 10k free | TikTok/IG crypto influencers | Skip for v1 |
| `BSKY_HANDLE` + `BSKY_APP_PASSWORD` | Free | Bluesky chatter | Minor |
| `yt-dlp` binary | Free | YouTube crypto channels | No YT signals |

**Minimum recommended:** `COINGECKO_API_KEY` + `XAI_API_KEY` + `BRAVE_API_KEY`. That unlocks the core price/KOL/web triad.

---

## Where to put keys

Gold Digger looks in this order (first hit wins):

1. **Process environment** — anything `export`ed in your shell. *Primary path.*
2. **`~/.config/shared/.env`** — **recommended**, reused by any local tool
3. `~/.config/last30days/.env` — inherit from last30days
4. `~/.config/cowork/.env` — Anthropic Cowork shared location
5. `~/.config/gold-digger/.env` — dedicated fallback
6. macOS Keychain — `gold-digger setup --keychain`
7. 1Password CLI references — `op://Personal/GoldDigger/KEY`

Keys never appear in reports, logs, or committed files. Masked (`xai-****…****`) in any debug output.

---

## Storage layout (Obsidian-friendly)

```
$GOLD_DIGGER_DATA/
├── projects/
│   ├── ai16z.md            # frontmatter = structured data, body = your notes
│   ├── openserv.md
│   └── ...
├── kols/
│   ├── degensensei.md
│   └── resdegen.md
├── reports/
│   └── daily/
│       ├── 2026-04-15.md         # full report
│       └── 2026-04-15-brief.md   # TL;DR
├── snapshots/
│   └── 2026-04-15.md       # human table + CSV block + narrative JSON
├── trends/
│   └── kol-mentions.md     # persistent KOL memory
└── research/
    └── openserv-2026-04-15.md    # Perplexity cited briefs
```

Point Obsidian's vault root at this directory and you get a browsable research graph: reports wiki-link `[[project]]`, project pages show Properties panel, backlinks work automatically.

---

## Project schema (frontmatter fields)

See [`references/schema.md`](references/schema.md) for the full spec. Summary:

- **Identity** — slug, name, ticker, narrative tags, chains, website, twitter, github, coingecko_id
- **Token** — has_token, price, mcap, fdv, 24h/7d/30d %, supply, exchanges, tge_date
- **Funding** — raised_usd, latest_round, valuation, investors
- **Traction** — twitter followers + Δ, github stars/commits/contributors, tvl, mainnet_status
- **Catalysts** — points_farming, airdrop_eligible, features_shipped, upcoming_tge
- **KOL signal** — mentioned_by, mention_count_7d/30d, mention_velocity
- **Risk** — audit_status, team_doxxed, vc_unlock_schedule, red_flags
- **Meta** — tier (tracked/scout/archived), first_added, last_updated, sources

---

## Extending

Four extension points, all documented in [`references/extending.md`](references/extending.md):

1. **Data sources** — drop a Python file in `scripts/sources/_custom/` subclassing `Source`. Auto-discovered.
2. **Signal extractors** — drop a file in `scripts/extractors/_custom/` to parse source output for new patterns.
3. **Narrative taxonomy** — edit [`references/narratives.md`](references/narratives.md) to add tags, keywords, seeds.
4. **Custom scoring** — replace `scripts/lib/scoring.py` to weight signals to your taste.

You can also tune the ignore list — edit [`references/ignore.md`](references/ignore.md) to add tickers Gold Digger should silently skip (blue chips, stables, memes, etc.).

---

## Dependencies

- **Python 3.12+**
- **[last30days](https://github.com/mvanhorn/last30days-skill)** — social and web research engine. Install first; Gold Digger calls it via subprocess for Reddit / HN / YouTube / web signals. Without it, Gold Digger degrades to market data + GitHub + XAI + Perplexity.
- `uv` (recommended) or `pip` for Python deps
- `gh` CLI (optional, for GitHub auth inheritance)

---

## Glossary

Crypto research jargon, demystified.

| Term | Meaning |
|---|---|
| **KOL** | Key Opinion Leader — a crypto influencer (typically on X/Twitter) whose calls and first-mentions move retail attention |
| **TGE** | Token Generation Event — the public launch of a new token (price discovery moment) |
| **FDV** | Fully Diluted Valuation — token price × max supply (the "worst case" valuation if all tokens existed today) |
| **Mcap** | Market Cap — token price × circulating supply (current valuation) |
| **TVL** | Total Value Locked — USD value of assets deposited in a DeFi protocol |
| **Points farming** | Accruing points via on-chain activity, typically redeemable for a future airdrop |
| **Airdrop eligibility** | Whether your on-chain activity qualifies for a free token distribution |
| **First-mention** | The first time a tracked KOL mentions a ticker — Gold Digger auto-captures this as alpha |
| **Narrative** | A category/meme driving capital rotation (AI-agents, DePIN, RWA, intents, restaking, etc.) |
| **Narrative rotation** | When capital flows from one narrative to another — Gold Digger detects these shifts from mention velocity |
| **Scout tier** | Projects Gold Digger auto-discovered but you haven't manually promoted to `tracked` |
| **Mention velocity** | Today's mention count minus 7-day average — positive = heating up, negative = cooling |
| **Price-vs-attention divergence** | Attention rising while price is flat = classic early-accumulation setup |
| **Dev-to-price divergence** | Heavy GitHub commits while price is flat = undervalued by market, developers still building |
| **Scout** | Gold Digger's discovery mode — finds new projects via CoinGecko listings, DeFiLlama protocols, KOL first-mentions, web search |
| **last30days** | The underlying social/web research engine Gold Digger calls. See [comparison table](#gold-digger-vs-last30days) for the split. |

---

## Roadmap

- **v0.1** — Skeleton, schema, CoinGecko, markdown storage ✅
- **v0.2** — DeFiLlama, GitHub, XAI KOL, last30days adapter, Perplexity research, daily pipeline ✅
- **v0.3** — Ignore list, KOL first-mention auto-scout, narrative rotation ✅
- **v0.4** — Clean Quick Start (no seed/), add-kol command, Mermaid diagrams ✅
- **v0.5** — Field provenance `.history.jsonl`, `gold-digger export` unified JSON, integration patterns doc
- **v1.0** — Cookie.fun / Virtuals native sources, insider wallet tracking, CEX listing announcement watcher

---

## License

MIT. See [LICENSE](./LICENSE).
