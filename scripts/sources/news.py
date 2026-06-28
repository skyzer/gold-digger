"""Recent news and announcement enrichment for tracked projects.

Uses Perplexity selectively for tracked projects that have enough identity
surface (name / ticker / handle / website). Keeps cost bounded by requesting a
compact structured summary focused on the last 30 days only.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from sources._base import Source
from sources.perplexity import research

DEFAULT_MODEL = "sonar-pro"


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _clean_list(value: Any, limit: int = 5) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        if item is None:
            continue
        s = str(item).strip()
        if not s:
            continue
        if s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


class ProjectNews(Source):
    name = "news"
    requires_keys = ["PERPLEXITY_API_KEY"]

    def fetch_watchlist(self, project: Dict[str, Any], keys: Dict[str, Optional[str]]) -> Dict[str, Any]:
        key = keys.get("PERPLEXITY_API_KEY")
        if not key:
            return {}

        name = project.get("name") or project.get("slug")
        ticker = project.get("ticker")
        twitter = project.get("twitter")
        website = project.get("website")
        github = project.get("github")
        if not name:
            return {}

        ticker_str = f" (${ticker})" if ticker else ""
        ctx = [f"Project: {name}{ticker_str}"]
        if twitter:
            ctx.append(f"X: @{twitter}")
        if website:
            ctx.append(f"Website: {website}")
        if github:
            ctx.append(f"GitHub: {github}")

        prompt = f"""You are extracting only factual recent project updates for a crypto/AI project.

{chr(10).join(ctx)}

Find notable project-specific updates from the last 30 days only. Focus on:
- launches, product updates, mainnet/testnet/beta milestones
- partnerships/integrations
- funding or strategic announcements
- exchange listings / token utility changes
- official roadmap or launch announcements

Return ONLY a JSON object with this exact shape:
{{
  "recent_announcements_30d": ["..."],
  "features_shipped_30d": ["..."],
  "partnerships_30d": ["..."],
  "red_flags": ["..."]
}}

Rules:
- 0 to 5 short bullets per field
- no marketing fluff
- only include items if they are specifically about this project
- if nothing solid is found for a field, return []
- return JSON only, no markdown
"""
        result = research(prompt, key, model=DEFAULT_MODEL)
        if not result:
            return {}
        text, citations = result
        parsed = _extract_json_object(text)
        if not parsed:
            return {}

        updates: Dict[str, Any] = {
            "recent_announcements_30d": _clean_list(parsed.get("recent_announcements_30d")),
            "features_shipped_30d": _clean_list(parsed.get("features_shipped_30d")),
            "partnerships_30d": _clean_list(parsed.get("partnerships_30d")),
        }

        fresh_red_flags = _clean_list(parsed.get("red_flags"))
        if fresh_red_flags:
            existing = list(project.get("red_flags") or [])
            for item in fresh_red_flags:
                if item not in existing:
                    existing.append(item)
            updates["red_flags"] = existing[:10]

        if citations:
            existing_sources = list(project.get("sources") or [])
            for url in citations[:8]:
                if url not in existing_sources:
                    existing_sources.append(url)
            updates["sources"] = existing_sources[:30]

        return updates
