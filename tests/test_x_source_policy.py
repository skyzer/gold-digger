import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import gold_digger  # noqa: E402


def test_oauth_empty_result_does_not_fall_back_to_paid_api(monkeypatch) -> None:
    monkeypatch.setattr(gold_digger.hermes_x, "available", lambda: True)
    monkeypatch.setattr(gold_digger.hermes_x, "paid_fallback_allowed", lambda: True)
    monkeypatch.setattr(gold_digger, "fetch_hermes_kol_posts", lambda *args, **kwargs: [])

    def unexpected_paid_call(*args, **kwargs):
        raise AssertionError("paid xAI fallback must not run after an OAuth result")

    monkeypatch.setattr(gold_digger, "fetch_xai_kol_posts", unexpected_paid_call)
    provider, posts = gold_digger._fetch_kol_posts_with_fallback(
        "DegenSensei",
        {"XAI_API_KEY": "configured", "X_BEARER_TOKEN": "configured"},
    )
    assert provider == "xai-oauth"
    assert posts == []


def test_paid_api_key_is_ignored_without_explicit_approval(monkeypatch) -> None:
    monkeypatch.setattr(gold_digger.hermes_x, "available", lambda: False)
    monkeypatch.setattr(gold_digger.hermes_x, "paid_fallback_allowed", lambda: False)
    provider, posts = gold_digger._fetch_kol_posts_with_fallback(
        "DegenSensei",
        {"XAI_API_KEY": "configured", "X_BEARER_TOKEN": None},
    )
    assert provider == "none (paid fallback not approved)"
    assert posts == []


def test_paid_api_key_runs_only_after_explicit_approval(monkeypatch) -> None:
    monkeypatch.setattr(gold_digger.hermes_x, "available", lambda: False)
    monkeypatch.setattr(gold_digger.hermes_x, "paid_fallback_allowed", lambda: True)
    monkeypatch.setattr(
        gold_digger,
        "fetch_xai_kol_posts",
        lambda *args, **kwargs: [{"text": "Watching $SERV"}],
    )
    provider, posts = gold_digger._fetch_kol_posts_with_fallback(
        "DegenSensei",
        {"XAI_API_KEY": "approved", "X_BEARER_TOKEN": None},
    )
    assert provider == "xai"
    assert posts[0]["source"] == "xai"
