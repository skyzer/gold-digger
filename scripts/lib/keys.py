"""Multi-location API key resolver.

Searches, in order of priority:
    1. Process environment (set by shell, launchd, cron, harness, whatever)
    2. ~/.config/shared/.env   (shared across local tools — recommended)
    3. ~/.config/last30days/.env   (inherit from last30days if installed)
    4. ~/.config/cowork/.env   (Anthropic Cowork shared location)
    5. ~/.config/gold-digger/.env   (dedicated fallback)
    6. macOS Keychain (optional, lookup only)
    7. 1Password CLI references (optional, lookup only)

Never writes to any shared location. Never clobbers an existing value.
Keys are masked in any string representation.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Canonical search order. The first file that contains a key wins.
SEARCH_PATHS: List[Path] = [
    Path.home() / ".config" / "shared" / ".env",
    Path.home() / ".config" / "last30days" / ".env",
    Path.home() / ".config" / "cowork" / ".env",
    Path.home() / ".config" / "gold-digger" / ".env",
]

# Known keys and what they unlock. Used by `setup` to report availability.
KNOWN_KEYS: Dict[str, str] = {
    "COINGECKO_API_KEY": "CoinGecko — price, mcap, supply, new-listing scout",
    "XAI_API_KEY": "xAI grok-search — KOL feeds, first-mention auto-scout",
    "PERPLEXITY_API_KEY": "Perplexity — cited deep-research for DD subagent",
    "BRAVE_API_KEY": "Brave Search — open-web scout (free 2k/mo)",
    "EXA_API_KEY": "Exa — semantic search scout (free 1k/mo)",
    "OPENROUTER_API_KEY": "OpenRouter — alt path to Perplexity Sonar",
    "GITHUB_TOKEN": "GitHub — repo commits/stars, dev-to-price divergence",
    "SCRAPECREATORS_API_KEY": "ScrapeCreators — TikTok/IG crypto influencers",
    "BSKY_HANDLE": "Bluesky handle (with BSKY_APP_PASSWORD)",
    "BSKY_APP_PASSWORD": "Bluesky app password (with BSKY_HANDLE)",
    "BROWSER_USE_API_KEY": "Browser Use — autonomous DD (v2)",
}


def _parse_env_file(path: Path) -> Dict[str, str]:
    """Minimal shell env parser. Handles `export KEY=value`, `KEY=value`,
    quoted values, and `#` comments. Does NOT execute shell."""
    if not path.exists():
        return {}
    result: Dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip matching quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            result[key] = value
    except (OSError, UnicodeDecodeError):
        return {}
    return result


def _try_keychain(name: str) -> Optional[str]:
    """macOS Keychain lookup. Silent failure (returns None) on any error."""
    if shutil.which("security") is None:
        return None
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-a", "gold-digger", "-s", name, "-w"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if out.returncode == 0:
            value = out.stdout.strip()
            return value or None
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _try_onepassword(ref: str) -> Optional[str]:
    """1Password CLI lookup for `op://...` references. Silent failure."""
    if not ref.startswith("op://") or shutil.which("op") is None:
        return None
    try:
        out = subprocess.run(
            ["op", "read", ref],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def resolve_key(name: str) -> Optional[str]:
    """Resolve a single key by name. Returns None if not found anywhere.

    Resolution order:
        1. os.environ[name]
        2. Each file in SEARCH_PATHS
        3. os.environ points at an op:// reference → resolve via 1Password CLI
        4. macOS Keychain
    """
    # 1. Process environment (canonical — everything else is a fallback)
    value = os.environ.get(name)
    if value:
        # If it's an op:// reference, resolve it
        if value.startswith("op://"):
            resolved = _try_onepassword(value)
            if resolved:
                return resolved
        else:
            return value

    # 2. Search path of dotenv files
    for path in SEARCH_PATHS:
        parsed = _parse_env_file(path)
        if name in parsed and parsed[name]:
            val = parsed[name]
            if val.startswith("op://"):
                resolved = _try_onepassword(val)
                if resolved:
                    return resolved
            else:
                return val

    # 3. Keychain
    keychain_value = _try_keychain(name)
    if keychain_value:
        return keychain_value

    return None


def mask(value: Optional[str]) -> str:
    """Return a safe-to-display mask of a secret value."""
    if not value:
        return "<unset>"
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


def resolved_source(name: str) -> Tuple[Optional[str], str]:
    """Like resolve_key, but also returns where it came from for diagnostics."""
    env_val = os.environ.get(name)
    if env_val:
        if env_val.startswith("op://"):
            resolved = _try_onepassword(env_val)
            if resolved:
                return resolved, "env→1password"
        else:
            return env_val, "env"
    for path in SEARCH_PATHS:
        parsed = _parse_env_file(path)
        if name in parsed and parsed[name]:
            val = parsed[name]
            if val.startswith("op://"):
                resolved = _try_onepassword(val)
                if resolved:
                    return resolved, f"{path}→1password"
            else:
                return val, str(path)
    keychain_value = _try_keychain(name)
    if keychain_value:
        return keychain_value, "keychain"
    return None, "not-found"


def report_availability() -> List[Tuple[str, Optional[str], str, str]]:
    """Return a list of (key, masked_value, source, description) for every known key.
    Used by `gold_digger setup` to show a human-readable availability matrix."""
    rows: List[Tuple[str, Optional[str], str, str]] = []
    for key, desc in KNOWN_KEYS.items():
        value, source = resolved_source(key)
        rows.append((key, mask(value), source, desc))
    return rows
