# API keys — detailed reference

See README.md for the summary matrix. This file is the deep dive: what each key buys, where to get it, and how Gold Digger degrades without it.

## COINGECKO_API_KEY

- **What it unlocks:** token price, market cap, FDV, 24h/7d/30d % changes, circulating/total/max supply, exchange listings, new-listing scout feed
- **Without it:** Gold Digger cannot populate any market-data fields. Project files stay name-only. Scout cannot discover new tokens.
- **Get it:** https://www.coingecko.com/en/developers/dashboard (Demo tier is free)
- **Env var:** `COINGECKO_API_KEY`
- **Optional tier override:** `COINGECKO_TIER=pro` (default: demo endpoint)

## SuperGrok xai-oauth bridge (default for every agent host)

- **What it unlocks:** subscription-backed Hermes `x_search` for KOL feeds, first-mention ticker extraction, X announcements, and project mention counts
- **Host compatibility:** Claude Code, Codex, OpenClaw, Hermes, other skill hosts, and cron all use the same Gold Digger CLI; Hermes is a companion OAuth/tool bridge, not a required main agent
- **Requirement:** Hermes Agent v0.14.0+ and a SuperGrok account authorized through browser OAuth
- **Configure:** `hermes auth add xai-oauth`, then `hermes tools enable x_search`
- **Service PATH:** Gold Digger also checks `~/.local/bin/hermes`; set `GOLD_DIGGER_HERMES_BIN=/absolute/path/to/hermes` for isolated agent services
- **Verify safely:** `hermes auth list xai-oauth` (credential metadata only; never inspect or copy raw OAuth tokens)
- **Runtime verification:** Gold Digger exports the Hermes tool session and accepts only `credential_source: xai-oauth`
- **Failure policy:** 401/403, missing provenance, or `credential_source: xai` fails closed; no silent paid fallback

## XAI_API_KEY (optional, separately billed fallback)

- **What it unlocks:** the legacy direct xAI developer API path when SuperGrok OAuth is not configured
- **Default:** disabled even when the key exists
- **Approval gate:** set `GOLD_DIGGER_ALLOW_PAID_X_FALLBACK=1` for the specific run after approving separately billed API usage
- **Get it:** https://console.x.ai/ (pay-as-you-go)
- **Env var:** `XAI_API_KEY`

## X_BEARER_TOKEN

- **What it unlocks:** Raw X API v2 public timelines/search as a deterministic fallback for KOL feeds, first-mentions, and mention counts
- **Default:** disabled even when the token exists; uses the same explicit `GOLD_DIGGER_ALLOW_PAID_X_FALLBACK=1` approval gate
- **Without it:** If SuperGrok OAuth is absent and no paid fallback is approved, KOL digest and X mention velocity degrade to no social signal.
- **Get it:** https://console.x.com/ → app → Keys and tokens → Bearer Token
- **Env var:** `X_BEARER_TOKEN`
- **Notes:** X API billing is separate from X Premium/Grok subscriptions. Gold Digger uses daily caching and `X_API_DAILY_MAX_CALLS` to cap spend.

## PERPLEXITY_API_KEY

- **What it unlocks:** cited deep-research queries for the `gold-digger-researcher` subagent, web-grounded project synthesis, due-diligence briefs with citations
- **Without it:** research subagent falls back to raw Brave/Exa results — shallower, no citation graph
- **Get it:** https://www.perplexity.ai/account/api/keys
- **Env var:** `PERPLEXITY_API_KEY`
- **Alternatives:** `OPENROUTER_API_KEY` (Perplexity Sonar via OpenRouter)

## BRAVE_API_KEY

- **What it unlocks:** open-web scout for pre-launch teasers, project announcement pages, news articles
- **Without it:** web scout limited to Perplexity/Exa
- **Get it:** https://api.search.brave.com/app/keys (free 2,000 queries/month)
- **Env var:** `BRAVE_API_KEY`

## EXA_API_KEY

- **What it unlocks:** semantic-search scout — "find projects that look like ai16z" / narrative similarity matching
- **Without it:** fall back to Brave keyword search
- **Get it:** https://exa.ai (free 1,000/month)
- **Env var:** `EXA_API_KEY`

## GITHUB_TOKEN

- **What it unlocks:** repo commits/stars delta, contributor count, dev-to-price divergence signal, new-repo scout in AI-crypto organizations
- **Without it:** no GitHub signals, cannot detect "heavy commits + flat price" early-stage setups
- **Get it:** https://github.com/settings/tokens (read-only scopes sufficient)
- **Env var:** `GITHUB_TOKEN` (also inherited from `gh auth token` if set)

## Optional — lower priority

- `SCRAPECREATORS_API_KEY` — TikTok/Instagram crypto influencers (skip for v1)
- `BSKY_HANDLE` + `BSKY_APP_PASSWORD` — Bluesky crypto chatter (minor signal volume)
- `yt-dlp` — YouTube crypto channels (Bankless, Coin Bureau, etc.)
- `BROWSER_USE_API_KEY` — reserved for v2 autonomous project DD

## Checking availability

```bash
gold-digger setup
```

Prints a table of every known key, whether it's resolved, where it came from (env / which dotenv file / keychain), and which sources are therefore available.
