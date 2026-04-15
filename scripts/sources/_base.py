"""Base class for pluggable data sources.

Each source file in `scripts/sources/` (and `scripts/sources/_custom/`)
defines a subclass of `Source`. The orchestrator auto-discovers them
on import and calls `fetch_watchlist` and/or `fetch_scout` as configured.

A source that can't run (missing key, service down) should return an
empty dict / empty list — never raise. Degradation is policy.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class Source:
    """Abstract base for a data source plugin."""

    #: Short canonical name, used in CLI output and debug logs.
    name: str = "<abstract>"

    #: Hard requirements — source is unavailable without every key listed here.
    requires_keys: List[str] = []

    #: Soft enhancements — source works without these but gains capabilities with them.
    optional_keys: List[str] = []

    def available(self, keys: Dict[str, Optional[str]]) -> bool:
        """True if every `requires_keys` is present in the resolver output."""
        return all(keys.get(k) for k in self.requires_keys)

    def fetch_watchlist(self, project: Dict[str, Any], keys: Dict[str, Optional[str]]) -> Dict[str, Any]:
        """Enrich a tracked project's frontmatter. Return a partial dict of
        updates to merge (null values are skipped by the storage layer)."""
        return {}

    def fetch_scout(self, keys: Dict[str, Optional[str]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Discover new candidate projects. Return a list of partial project
        dicts. Each must include at least `slug` and `name`."""
        return []
