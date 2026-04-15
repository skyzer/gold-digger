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
    ticker_str = f" (${ticker})" if ticker else ""
    context_parts = [f"Project: {name}{ticker_str}"]
    if twitter:
        context_parts.append(f"X/Twitter: @{twitter}")
    if website:
        context_parts.append(f"Website: {website}")
    if github:
        context_parts.append(f"GitHub: {github}")
    context = "\n".join(context_parts)
    return f"""Conduct crypto/AI due diligence on this project. Be concise, cite sources.

{context}

Answer each question with a short paragraph (2-4 sentences) and cite sources:

1. What is {name} in one sentence?
2. Does it have a token live today? What's the current status (live / announced / rumored / none)?
3. Is there a points/airdrop farming program active? Any end date?
4. Has the project raised funding? Latest round, amount, lead investors if known.
5. What's the product/network status? Testnet, mainnet, beta, live with users?
6. Who's building it? Team pedigree if public.
7. What narrative does it belong to (AI agents, DePIN, RWA, infra, etc.)?
8. Any major recent announcements (last 30 days)?
9. Notable risks or red flags?
10. What would a 10-100x bullcase for this project look like over the next 12 months?

Focus on fact-based sources: project docs, reputable news, GitHub, on-chain data, VC announcements."""


class Perplexity(Source):
    """Perplexity is used on-demand by the researcher subagent, not in the
    daily enrichment loop. Kept as a Source for discoverability in `setup`."""
    name = "perplexity"
    requires_keys = ["PERPLEXITY_API_KEY"]

    def fetch_watchlist(self, project: Dict[str, Any], keys: Dict[str, Optional[str]]) -> Dict[str, Any]:
        # Intentionally no-op in daily enrichment — too expensive per project.
        # Invoke via `gold-digger research <slug>` for on-demand DD.
        return {}
