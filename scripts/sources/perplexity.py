"""Perplexity source — cited deep research for the researcher subagent.

Uses the Perplexity Sonar API (OpenAI-compatible) to run web-grounded
research queries that return synthesis + citation URLs.

Docs: https://docs.perplexity.ai/api-reference/chat-completions-post
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from sources._base import Source

ENDPOINT = "https://api.perplexity.ai/chat/completions"
DEFAULT_MODEL = "sonar-pro"


def _post(body: Dict[str, Any], key: str, timeout: int = 90) -> Optional[Dict[str, Any]]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=data, method="POST")
    req.add_header("authorization", f"Bearer {key}")
    req.add_header("content-type", "application/json")
    req.add_header("user-agent", "gold-digger/0.1")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode("utf-8")
            return {"_error": body_text, "_status": e.code}
        except Exception:
            return None
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def research(prompt: str, key: str, model: str = DEFAULT_MODEL, system: Optional[str] = None) -> Optional[Tuple[str, List[str]]]:
    """Run a web-grounded research query. Returns (text, citations) or None.

    `citations` is a list of URLs the model grounded its answer in.
    """
    if not key:
        return None
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = {
        "model": model,
        "messages": messages,
        "return_citations": True,
        "temperature": 0.2,
    }
    response = _post(body, key)
    if not response or "choices" not in response:
        return None
    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    text = message.get("content") or ""
    # Perplexity returns citations at the top level of the response
    citations: List[str] = response.get("citations") or []
    return text, citations


def project_dd_prompt(project: Dict[str, Any]) -> str:
    """Build a structured due-diligence prompt for a single project."""
    name = project.get("name") or project.get("slug") or "?"
    ticker = project.get("ticker")
    twitter = project.get("twitter")
    website = project.get("website")
    github = project.get("github")
    docs = project.get("docs")
    coingecko_id = project.get("coingecko_id")
    chains = project.get("chains") or []
    exchanges = project.get("exchanges") or []
    ticker_str = f" (${ticker})" if ticker else ""
    context_parts = [f"Project: {name}{ticker_str}"]
    if twitter:
        context_parts.append(f"X/Twitter: @{twitter}")
    if website:
        context_parts.append(f"Website: {website}")
    if github:
        context_parts.append(f"GitHub: {github}")
    if docs:
        context_parts.append(f"Docs: {docs}")
    if coingecko_id:
        context_parts.append(f"CoinGecko id: {coingecko_id}")
    if chains:
        context_parts.append(f"Known chains: {', '.join(chains)}")
    if exchanges:
        context_parts.append(f"Known exchanges/pools: {', '.join(exchanges[:10])}")
    for field, label in (
        ("price_usd", "Current price USD"),
        ("mcap", "Current market cap USD"),
        ("fdv", "Current FDV USD"),
        ("circulating_supply", "Circulating supply"),
        ("total_supply", "Total supply"),
        ("max_supply", "Max supply"),
        ("tge_date", "TGE date"),
        ("listed_since", "Listed since"),
        ("github_stars", "GitHub stars"),
        ("github_commits_30d", "GitHub commits 30d"),
        ("github_contributors", "GitHub contributors"),
    ):
        value = project.get(field)
        if value not in (None, "", []):
            context_parts.append(f"{label}: {value}")
    context = "\n".join(context_parts)
    return f"""Conduct crypto/AI due diligence on this project for a high-risk asymmetric-bet investor. Be concise, cite sources, and do not invent missing data.

{context}

Answer each question with a short paragraph or compact table where useful. Cite sources for factual claims and call out uncertainty or source conflicts clearly:

1. What is {name} in one sentence?
2. Who is behind it? Include public founders/team, company/legal entity, investor pedigree, and official contact paths if available.
3. Does it have a token live today? Give token status (live / announced / rumored / none), chain(s), official contract address(es), and whether the address is verified by official sources.
4. When was the token TGE or first tradable listing? If the date is uncertain, explain the evidence and uncertainty.
5. Summarize tokenomics: supply, circulating vs FDV, allocations, unlocks/vesting, emissions, burns, staking, and any known team/VC wallets.
6. Explain token value capture: fees, revenue share, buybacks/burns, staking, governance, network demand, or no clear capture. Distinguish real rights from marketing claims.
7. Show current market data: price, market cap, FDV, 24h volume, 24h/7d/30d changes, and a last-14-days market-cap series if available.
8. Assess liquidity and holder risk: main DEX/CEX venues, pool liquidity, volume quality, slippage risk, holder concentration, contract ownership/mint/freeze controls if visible.
9. Is there a points/airdrop farming program active? Any end date, snapshot, claim, or migration risk?
10. Has the project raised funding? Latest round, amount, lead investors, valuation if known, and whether the announcement is official or press-only.
11. What is the product/network status? Include site, app, docs, API, testnet/mainnet/beta/live usage, and any signs of broken infrastructure.
12. What is the code activity? Include official GitHub repos, stars, contributors, recent commits, and an active-vs-abandoned read.
13. What narrative does it belong to (AI agents, DePIN, RWA, infra, data, Bittensor subnet, etc.) and what comparable projects should it be benchmarked against?
14. Any major announcements or catalysts in the last 30 days?
15. Notable risks, red flags, source conflicts, or things that must be verified before deploying capital.
16. What would a 10-100x bull case look like over the next 12 months, and what evidence would confirm or kill it?
17. Final buy/no-buy read for today: best entry zone, position sizing style, play/risk, downside scenario, and time sensitivity.

Focus on fact-based sources: official project docs, reputable news, GitHub, CoinGecko/GeckoTerminal/Dexscreener, block explorers, on-chain data, VC announcements, and official social posts."""


class Perplexity(Source):
    """Perplexity is used on-demand by the researcher subagent, not in the
    daily enrichment loop. Kept as a Source for discoverability in `setup`."""
    name = "perplexity"
    requires_keys = ["PERPLEXITY_API_KEY"]

    def fetch_watchlist(self, project: Dict[str, Any], keys: Dict[str, Optional[str]]) -> Dict[str, Any]:
        # Intentionally no-op in daily enrichment — too expensive per project.
        # Invoke via `gold-digger research <slug>` for on-demand DD.
        return {}
