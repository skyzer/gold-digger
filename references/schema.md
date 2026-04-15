# Project schema

Full frontmatter field spec for `projects/*.md`. Any field not yet filled is `null` (or `unknown` for enum-typed fields). Gold Digger never overwrites user-added frontmatter fields that aren't in this spec.

## Identity

| Field | Type | Notes |
|---|---|---|
| `slug` | string | Filename stem. Must match `<slug>.md`. |
| `name` | string | Display name. |
| `ticker` | string \| null | Uppercase ticker if token exists. |
| `narrative` | string[] | Tag list from `references/narratives.md`. |
| `chains` | string[] | Platforms the token lives on. |
| `website` | url \| null | |
| `twitter` | string \| null | Handle without `@`. |
| `github` | url \| null | Full org/repo URL. |
| `docs` | url \| null | |
| `coingecko_id` | string \| null | Required for price enrichment. |
| `defillama_slug` | string \| null | Required for TVL. |

## Token

| Field | Type | Notes |
|---|---|---|
| `has_token` | enum | `yes` / `no` / `announced` / `rumored` / `unknown` |
| `price_usd` | number \| null | |
| `mcap` | number \| null | Market cap in USD. |
| `fdv` | number \| null | Fully diluted valuation. |
| `change_24h_pct` | number \| null | |
| `change_7d_pct` | number \| null | |
| `change_30d_pct` | number \| null | |
| `circulating_supply` | number \| null | |
| `total_supply` | number \| null | |
| `max_supply` | number \| null | |
| `exchanges` | string[] | CEX/DEX names. |
| `tge_date` | date \| null | ISO date. |
| `listed_since` | date \| null | ISO date. |

## Funding

| Field | Type | Notes |
|---|---|---|
| `raised_usd` | number \| null | Lifetime total raised. |
| `latest_round` | string \| null | e.g. "Series A" / "Seed" / "Strategic". |
| `latest_round_date` | date \| null | |
| `valuation_usd` | number \| null | |
| `investors` | string[] | Firm names. |

## Traction

| Field | Type | Notes |
|---|---|---|
| `twitter_followers` | number \| null | |
| `twitter_followers_delta_30d` | number \| null | +/- over last 30d. |
| `discord_members` | number \| null | |
| `telegram_members` | number \| null | |
| `github_stars` | number \| null | |
| `github_commits_30d` | number \| null | |
| `github_contributors` | number \| null | |
| `tvl_usd` | number \| null | DeFi only. |
| `daily_active_users` | number \| null | |
| `mainnet_status` | enum | `testnet` / `mainnet` / `live` / `unknown` |

## Catalysts

| Field | Type | Notes |
|---|---|---|
| `points_farming` | enum | `yes` / `no` / `unknown`. |
| `points_program_end` | date \| null | |
| `airdrop_eligible` | enum | `yes` / `no` / `unknown`. |
| `features_shipped_30d` | string[] | Short feature titles. |
| `partnerships_30d` | string[] | |
| `upcoming_tge` | date \| null | |

## KOL signal

| Field | Type | Notes |
|---|---|---|
| `mentioned_by` | string[] | Handles from `kols/`. |
| `mention_count_7d` | number | Integer. |
| `mention_count_30d` | number | Integer. |
| `mention_velocity` | number \| null | `+N` accelerating, `-N` cooling. |
| `first_kol_mention_date` | date \| null | |

## Risk

| Field | Type | Notes |
|---|---|---|
| `audit_status` | enum | `audited` / `in-progress` / `none` / `unknown` |
| `auditor` | string \| null | |
| `team_doxxed` | enum | `yes` / `partial` / `no` / `unknown` |
| `vc_unlock_schedule` | string \| null | Free-text cliff dates. |
| `red_flags` | string[] | Short descriptors. |

## Meta

| Field | Type | Notes |
|---|---|---|
| `tier` | enum | `tracked` / `scout` / `archived` |
| `first_added` | date | ISO date. |
| `last_updated` | date | Auto-touched on every enrichment. |
| `sources` | string[] | URLs used for enrichment. |
