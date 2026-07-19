"""Combined X social signal source.

Preferred path is Hermes ``x_search`` backed by SuperGrok OAuth. Separately
billed xAI/X API credentials are only used when OAuth is not configured and
the operator explicitly enables paid fallback.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sources._base import Source
from sources import hermes_x, x_api, xai


class XSocial(Source):
    name = "x_social"
    requires_keys = []
    optional_keys = ["XAI_API_KEY", "X_BEARER_TOKEN"]

    def available(self, keys: Dict[str, Optional[str]]) -> bool:
        return hermes_x.available() or (
            hermes_x.paid_fallback_allowed()
            and bool(keys.get("XAI_API_KEY") or keys.get("X_BEARER_TOKEN"))
        )

    def fetch_watchlist(self, project: Dict[str, Any], keys: Dict[str, Optional[str]]) -> Dict[str, Any]:
        ticker = project.get("ticker")
        name = project.get("name")
        if ticker:
            xai_query = f"${ticker} OR {name}" if name else f"${ticker}"
        elif name:
            xai_query = name
        else:
            return {}

        if hermes_x.available():
            mentions = hermes_x.search_x_mentions(xai_query, since_hours=168, limit=25)
            if mentions is not None:
                return {"mention_count_7d": len(mentions)}
            # Never silently switch credentials after an OAuth auth,
            # entitlement, rate-limit, or provenance failure.
            return {}

        if not hermes_x.paid_fallback_allowed():
            return {}

        xai_key = keys.get("XAI_API_KEY")
        if xai_key:
            mentions = xai.search_x_mentions(xai_query, xai_key, since_hours=168, limit=25)
            if mentions is not None:
                return {"mention_count_7d": len(mentions)}

        bearer = keys.get("X_BEARER_TOKEN")
        if bearer:
            query = x_api._query_for_project(project)
            if query:
                mentions = x_api.search_x_mentions(query, bearer, since_hours=168, limit=x_api._env_int("X_API_SEARCH_LIMIT", 25))
                if mentions is not None:
                    return {"mention_count_7d": len(mentions)}

        return {}
