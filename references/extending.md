# Extending Gold Digger

Four extension points, all file-system-based — no Gold Digger core changes required.

## 1. Adding a data source

Drop a Python file in `scripts/sources/_custom/` subclassing `Source`:

```python
# scripts/sources/_custom/cielo.py
from sources._base import Source

class CieloWalletTracker(Source):
    name = "cielo"
    requires_keys = ["CIELO_API_KEY"]

    def fetch_watchlist(self, project, keys):
        key = keys.get("CIELO_API_KEY")
        # Fetch wallet activity for this project's token contract
        return {"insider_activity": ...}

    def fetch_scout(self, keys, config):
        # Discover tokens insiders are accumulating
        return [{"slug": "xyz", "name": "XYZ", "tier": "scout", ...}]
```

Register it in `scripts/gold_digger.py`'s `SOURCES` list (or let the auto-discovery loader find it — planned for v0.2). Add `CIELO_API_KEY` to `scripts/lib/keys.py` `KNOWN_KEYS` so `setup` reports it.

## 2. Adding a signal extractor

Extractors parse source output for structured patterns (ticker mentions, TGE dates, points programs). Drop a file in `scripts/extractors/_custom/`:

```python
# scripts/extractors/_custom/points_program.py
import re

POINTS_PATTERN = re.compile(r"(points?|airdrop)\s+(program|campaign|season)", re.I)

def extract(text: str) -> dict:
    if POINTS_PATTERN.search(text):
        return {"points_farming": "yes"}
    return {}
```

The daily pipeline runs every extractor over relevant source output (tweets, articles, project pages) and merges the results into the project frontmatter.

## 3. Adding a narrative

Edit `references/narratives.md` directly — no code change. Add a section with keywords and seed projects. The scout uses these to tag discoveries automatically.

Format:
```markdown
## my-new-narrative

**Keywords:** term1, term2, term3
**Seeds:** project-slug-1, project-slug-2
```

## 4. Custom scoring

Replace `scripts/lib/scoring.py`. Exposes one function:

```python
def score(project: dict) -> float:
    """Return a float 0–100 representing how interesting this project is."""
    ...
```

Default scoring weights: KOL mention velocity (30%), dev-to-price divergence (20%), narrative hotness (15%), mcap bracket < $100M (15%), GitHub activity (10%), new catalysts (10%). Override freely.

## Running extensions

```bash
# Verify a new source is detected
gold-digger setup

# Run the single source against a project
gold-digger enrich openserv --only-source cielo   # (v0.2 flag)

# Full pipeline picks up extensions automatically
gold-digger daily
```
