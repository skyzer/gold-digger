# API keys — detailed reference

See README.md for the summary matrix. This file is the deep dive: what each key buys, where to get it, and how Gold Digger degrades without it.

## COINGECKO_API_KEY

- **What it unlocks:** token price, market cap, FDV, 24h/7d/30d % changes, circulating/total/max supply, exchange listings, new-listing scout feed
- **Without it:** Gold Digger cannot populate any market-data fields. Project files stay name-only. Scout cannot discover new tokens.
- **Get it:** https://www.coingecko.com/en/developers/dashboard (Demo tier is free)
- **Env var:** `COINGECKO_API_KEY`
- **Optional tier override:** `COINGECKO_TIER=pro` (default: demo endpoint)

## XAI_API_KEY

- **What it unlocks:** KOL feed polling via grok-search, first-mention ticker extraction, X announcements, sentiment on project tweets
- **Without it:** No KOL digest. Cannot follow DegenSensei / resdegen / any X-native signal. First-mention auto-scout disabled.
- **Get it:** https://console.x.ai/ (pay-as-you-go)
- **Env var:** `XAI_API_KEY`

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
