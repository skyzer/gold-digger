import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from sources import hermes_x  # noqa: E402


def _export_record(credential_source: str = "xai-oauth", success: bool = True) -> str:
    payload = {
        "success": success,
        "credential_source": credential_source,
        "model": "grok-4.20-reasoning",
        "answer": "[]",
    }
    record = {
        "id": "session-123",
        "messages": [{
            "role": "tool",
            "tool_name": "x_search",
            "content": json.dumps(payload),
        }],
    }
    return json.dumps(record)


def test_parse_supported_hermes_version() -> None:
    assert hermes_x._parse_version("Hermes Agent v0.18.2 (2026.7.7.2)") == (0, 18, 2)


def test_finds_standard_user_install_when_agent_path_is_restricted(monkeypatch, tmp_path) -> None:
    binary = tmp_path / ".local" / "bin" / "hermes"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o700)
    monkeypatch.delenv("GOLD_DIGGER_HERMES_BIN", raising=False)
    monkeypatch.setattr(hermes_x.shutil, "which", lambda _name: None)
    monkeypatch.setattr(hermes_x.Path, "home", lambda: tmp_path)

    assert hermes_x._hermes_binary() == str(binary)


def test_extract_session_id_uses_last_id() -> None:
    text = "session_id: old\nanswer\nsession_id: 20260719_182746_ad1f76\n"
    assert hermes_x._extract_session_id(text) == "20260719_182746_ad1f76"


def test_accepts_actual_xai_oauth_tool_result() -> None:
    payload, error = hermes_x._extract_verified_tool_result(_export_record(), "session-123")
    assert error == ""
    assert payload is not None
    assert payload["credential_source"] == "xai-oauth"


def test_rejects_paid_api_tool_result() -> None:
    payload, error = hermes_x._extract_verified_tool_result(
        _export_record(credential_source="xai"),
        "session-123",
    )
    assert payload is None
    assert "refused paid XAI_API_KEY" in error


def test_rejects_missing_credential_provenance() -> None:
    payload, error = hermes_x._extract_verified_tool_result(
        _export_record(credential_source=""),
        "session-123",
    )
    assert payload is None
    assert "unverified" in error


def test_paid_fallback_requires_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("GOLD_DIGGER_ALLOW_PAID_X_FALLBACK", raising=False)
    assert hermes_x.paid_fallback_allowed() is False
    monkeypatch.setenv("GOLD_DIGGER_ALLOW_PAID_X_FALLBACK", "1")
    assert hermes_x.paid_fallback_allowed() is True


def test_normalise_posts_marks_oauth_source() -> None:
    posts = hermes_x._normalise_posts(
        "DegenSensei",
        '[{"date":"2026-07-19T12:00:00Z","text":"Watching $SERV","url":"https://x.com/DegenSensei/status/1"}]',
    )
    assert posts == [{
        "handle": "DegenSensei",
        "date": "2026-07-19T12:00:00Z",
        "text": "Watching $SERV",
        "url": "https://x.com/DegenSensei/status/1",
        "tickers": ["SERV"],
        "source": "xai-oauth",
    }]


def test_search_accepts_session_id_written_to_stderr(monkeypatch) -> None:
    monkeypatch.setattr(hermes_x, "oauth_status", lambda: (True, "ready"))
    monkeypatch.setattr(hermes_x, "_hermes_binary", lambda: "/bin/hermes")
    calls = iter([
        subprocess.CompletedProcess([], 0, stdout="final answer", stderr="session_id: session-123\n"),
        subprocess.CompletedProcess([], 0, stdout=_export_record(), stderr=""),
    ])
    monkeypatch.setattr(hermes_x, "_run", lambda command, timeout: next(calls))

    payload, error = hermes_x._search("query", timeout=10)
    assert error == ""
    assert payload is not None
    assert payload["credential_source"] == "xai-oauth"
