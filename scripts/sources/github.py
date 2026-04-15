"""GitHub source — repo commits, stars, contributors, dev-to-price divergence.

Uses the GitHub REST API with a token from `GITHUB_TOKEN` (or inherited from
`gh auth token`). Read-only scopes are sufficient.

Given a project with a `github` URL, pulls:
  - stargazers_count
  - commits in the last 30 days (from /commits with since=)
  - unique contributors in the last 30 days
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sources._base import Source

API = "https://api.github.com"
REPO_RE = re.compile(r"github\.com/([^/?#]+)(?:/([^/?#]+))?")


def _parse_owner_repo(url: str) -> Optional[tuple[str, Optional[str]]]:
    """Parse a GitHub URL into (owner, repo_or_None). If the URL points at an
    org rather than a specific repo, repo will be None and the caller should
    discover the primary repo via _org_repos."""
    if not url:
        return None
    match = REPO_RE.search(url)
    if not match:
        return None
    owner = match.group(1)
    repo = match.group(2)
    if repo:
        repo = repo.replace(".git", "").strip()
        if not repo:
            repo = None
    return owner, repo


def _get(path: str, token: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    qs = urllib.parse.urlencode(params or {})
    url = f"{API}{path}?{qs}" if qs else f"{API}{path}"
    req = urllib.request.Request(url)
    req.add_header("accept", "application/vnd.github+json")
    req.add_header("authorization", f"Bearer {token}")
    req.add_header("user-agent", "gold-digger/0.1")
    req.add_header("x-github-api-version", "2022-11-28")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def _org_repos(org: str, token: str) -> Optional[List[Dict[str, Any]]]:
    """List public repos for an org/user. Used to auto-discover repos when a
    project's github field points at an org rather than a specific repo."""
    return _get(f"/orgs/{org}/repos", token, {"per_page": 30, "sort": "updated"})


def fetch_repo_stats(owner: str, repo: str, token: str) -> Dict[str, Any]:
    """Return stars, commit count last 30d, contributor count last 30d."""
    repo_data = _get(f"/repos/{owner}/{repo}", token)
    if not repo_data:
        return {}
    stars = repo_data.get("stargazers_count")
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    commits = _get(f"/repos/{owner}/{repo}/commits", token, {"since": since, "per_page": 100})
    commit_count = len(commits) if isinstance(commits, list) else None
    contributors: set[str] = set()
    if isinstance(commits, list):
        for c in commits:
            author = (c.get("author") or {}).get("login")
            if author:
                contributors.add(author)
    return {
        "github_stars": stars,
        "github_commits_30d": commit_count,
        "github_contributors": len(contributors) if contributors else None,
    }


class GitHub(Source):
    name = "github"
    requires_keys = ["GITHUB_TOKEN"]

    def fetch_watchlist(self, project: Dict[str, Any], keys: Dict[str, Optional[str]]) -> Dict[str, Any]:
        token = keys.get("GITHUB_TOKEN")
        if not token:
            return {}
        gh_url = project.get("github")
        if not gh_url:
            return {}
        parsed = _parse_owner_repo(gh_url)
        if not parsed:
            return {}
        owner, repo = parsed

        # Org-only URL → find the primary repo by most recent activity
        if not repo:
            repos = _org_repos(owner, token) or []
            if not repos:
                return {}
            repo = repos[0].get("name")
            if not repo:
                return {}

        stats = fetch_repo_stats(owner, repo, token)
        if not stats:
            # Fallback: maybe the repo name is wrong, try the org's top repo
            repos = _org_repos(owner, token) or []
            if repos:
                primary = repos[0].get("name")
                if primary and primary != repo:
                    stats = fetch_repo_stats(owner, primary, token)
                    if stats:
                        repo = primary
        if not stats:
            return {}
        existing = project.get("sources") or []
        source_url = f"https://github.com/{owner}/{repo}"
        if source_url not in existing:
            stats["sources"] = list(existing) + [source_url]
        return stats
