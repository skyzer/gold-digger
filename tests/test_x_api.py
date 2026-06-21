import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from sources import x_api  # noqa: E402


def test_query_for_project_uses_cashtag_and_quoted_name() -> None:
    query = x_api._query_for_project({"ticker": "SERV", "name": "OpenServ AI"})

    assert query == '($SERV OR "OpenServ AI") -is:retweet'


def test_normalise_tweet_extracts_tickers_and_url() -> None:
    tweet = {
        "id": "123",
        "created_at": "2026-06-21T12:00:00Z",
        "text": "Watching $SERV and $zero. $SERV again.",
    }

    normalised = x_api._normalise_tweet(tweet, username="DegenSensei", handle="DegenSensei")

    assert normalised["handle"] == "DegenSensei"
    assert normalised["url"] == "https://x.com/DegenSensei/status/123"
    assert normalised["tickers"] == ["SERV", "ZERO"]
    assert normalised["source"] == "x_api"
