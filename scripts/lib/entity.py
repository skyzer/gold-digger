"""Entity disambiguation — separate real crypto project mentions from noise.

The core problem: "circle" the English word vs. Circle the USDC company.
"magic" the concept vs. Treasure (MAGIC) the token. Gold Digger needs to
distinguish between these to avoid false positives in mention counting.

Strategy:
  1. Distinctive names (multi-word, unusual) → high confidence, count directly
  2. Ambiguous names (common English words) → require crypto context signals
  3. Ticker-format mentions ($TICKER) → always count (explicit signal)

Crypto context signals (any ONE is enough to confirm):
  - Appears near a $ sign or ticker-like word
  - Post is from a crypto subreddit or crypto-tagged source
  - Contains other crypto keywords (token, blockchain, defi, nft, etc.)
  - URL domain is a known crypto source (coingecko, dexscreener, etc.)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

# Common English words that are also crypto project names — require context.
# Add to this list as false positives are discovered.
AMBIGUOUS_NAMES: Set[str] = {
    "circle", "magic", "flux", "mira", "treasure", "akash", "reef",
    "near", "sand", "rose", "celo", "flow", "dash", "waves", "ocean",
    "aurora", "harmony", "loom", "storm", "nest", "alpha", "beta",
    "quant", "graph", "mask", "iris", "lens", "mirror", "anchor",
    "spell", "rune", "plasma", "ion", "atom", "cosmos", "nova",
    "orbit", "pulse", "glow", "terra", "luna", "sonic", "super",
    "hero", "core", "safe", "layer", "fuel", "spark", "prime",
    "origin", "portal", "nexus", "genesis", "vertex", "apex",
    "credit", "reserve", "compound", "maker", "aave",
}

# Regex for crypto context keywords
CRYPTO_CONTEXT_RE = re.compile(
    r"\b(?:token|blockchain|defi|nft|airdrop|staking|yield|tvl|mcap|"
    r"market\s*cap|dex|cex|swap|liquidity|smart\s*contract|web3|"
    r"crypto|altcoin|bullish|bearish|hodl|fud|dyor|ape\s*in|"
    r"tokenomics|tge|ido|ico|mainnet|testnet|whitepaper|"
    r"\$[A-Za-z]{2,10})\b",
    re.IGNORECASE,
)

# Known crypto source domains
CRYPTO_DOMAINS = {
    "coingecko.com", "coinmarketcap.com", "dexscreener.com",
    "defillama.com", "etherscan.io", "bscscan.com", "solscan.io",
    "dextools.io", "dune.com", "messari.io", "theblock.co",
    "decrypt.co", "coindesk.com", "cointelegraph.com",
}

# Known crypto subreddits (lowercase)
CRYPTO_SUBREDDITS = {
    "cryptocurrency", "cryptomoonshots", "altcoin", "defi",
    "ethfinance", "bitcoin", "solana", "bittensor_",
    "ethereum", "cosmosnetwork", "algorand", "cardano",
}

# Ticker pattern
TICKER_RE = re.compile(r"\$[A-Za-z][A-Za-z0-9]{1,9}\b")


def is_ambiguous(name: str) -> bool:
    """True if this project name is a common English word that could easily
    false-positive in general text."""
    if not name:
        return False
    return name.lower().strip() in AMBIGUOUS_NAMES


def has_crypto_context(item: Dict[str, Any]) -> bool:
    """Check whether a social mention has enough crypto context to be trusted."""
    # Check text content
    text = str(item.get("title", "")) + " " + str(item.get("text", "")) + " " + str(item.get("body", ""))
    if TICKER_RE.search(text):
        return True
    if CRYPTO_CONTEXT_RE.search(text):
        return True

    # Check source/platform
    source = str(item.get("source", "")).lower()
    platform = str(item.get("platform", "")).lower()
    subreddit = str(item.get("subreddit", "")).lower()
    if subreddit in CRYPTO_SUBREDDITS:
        return True
    if any(d in source or d in platform for d in CRYPTO_DOMAINS):
        return True

    # Check URL
    url = str(item.get("url", "")) + str(item.get("link", ""))
    if any(d in url for d in CRYPTO_DOMAINS):
        return True

    return False


def filter_relevant_mentions(
    items: List[Dict[str, Any]],
    project_identity: Dict[str, Optional[str]],
) -> List[Dict[str, Any]]:
    """Filter a list of social mentions to only those genuinely about the project.

    For distinctive names: all mentions pass.
    For ambiguous names: only mentions with crypto context pass.
    """
    name = project_identity.get("name")
    if not name:
        return items

    if not is_ambiguous(name):
        return items  # Distinctive name like "Bittensor" or "OpenServ" — trust all

    # Ambiguous name — require crypto context for each mention
    return [item for item in items if has_crypto_context(item)]


def extract_crypto_entities(text: str) -> List[str]:
    """Extract probable crypto project names and tickers from free-form text.

    Used for parsing `store.py trending` output and general social posts.
    Returns unique entity strings (tickers uppercase, names as-found).
    """
    if not text:
        return []

    entities: List[str] = []
    seen: Set[str] = set()

    # 1. $TICKER mentions (highest confidence)
    for match in TICKER_RE.finditer(text):
        ticker = match.group(0)[1:].upper()  # strip $, uppercase
        if ticker not in seen:
            entities.append(ticker)
            seen.add(ticker)

    # 2. CamelCase/PascalCase words that look like project names
    #    (e.g., "OpenServ", "ChainGPT", "DeFiLlama")
    camel_re = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b")
    for match in camel_re.finditer(text):
        name = match.group(0)
        if name not in seen and len(name) >= 5:
            entities.append(name)
            seen.add(name)

    # 3. ALL-CAPS words 3-10 chars near crypto context keywords
    #    (e.g., "TAO is looking good" → TAO if near crypto words)
    allcaps_re = re.compile(r"\b([A-Z]{3,10})\b")
    for match in allcaps_re.finditer(text):
        word = match.group(1)
        if word in seen:
            continue
        # Check if crypto context exists within 200 chars
        start = max(0, match.start() - 200)
        end = min(len(text), match.end() + 200)
        window = text[start:end]
        if CRYPTO_CONTEXT_RE.search(window):
            # Skip common English all-caps (THE, AND, etc.)
            if word not in {"THE", "AND", "FOR", "BUT", "NOT", "YOU", "ARE",
                            "WAS", "HIS", "HER", "HAS", "HAD", "ITS", "THIS",
                            "THAT", "WITH", "FROM", "THEY", "BEEN", "HAVE",
                            "WILL", "WHAT", "WHEN", "WHO", "HOW", "WHY",
                            "ALL", "CAN", "NEW", "NOW", "ONE", "TWO", "GET",
                            "JUST", "MORE", "ALSO", "VERY", "SOME", "ANY",
                            "MOST", "THAN", "THEM", "EACH", "MAKE", "LIKE",
                            "OUR", "OUT", "USE", "WAY", "MAY", "SAY", "SHE",
                            "USD", "ETH", "BTC", "API", "CEO", "CTO", "NFT",
                            "DID", "PUT", "TOP", "RUN", "SET", "TRY", "ASK",
                            "OWN", "TOO", "BIG", "FEW", "OLD", "END", "LET"}:
                entities.append(word)
                seen.add(word)

    return entities
