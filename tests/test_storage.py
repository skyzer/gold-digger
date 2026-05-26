from pathlib import Path

from scripts.lib import storage


def test_yaml_round_trip_preserves_commas_and_status_strings() -> None:
    data = {
        "slug": "solrouter",
        "has_token": "yes",
        "mention_count_7d": 0,
        "red_flags": [
            "No verifiable project-specific news, technical updates, or official announcements were found.",
            "Another sentence, with a comma.",
        ],
        "sources": ["https://example.com/a", "https://example.com/b"],
    }

    dumped = storage._yaml_dump(data)
    parsed = storage._yaml_parse(dumped)

    assert parsed == data


def test_salvage_project_skips_oversized_frontmatter_line_and_keeps_body(tmp_path: Path) -> None:
    huge = "x" * 400
    path = tmp_path / "demo.md"
    path.write_text(
        "\n".join(
            [
                "---",
                "slug: demo",
                "name: Demo",
                f'red_flags: ["{huge}"]',
                "tier: tracked",
                "---",
                "# Demo",
                "",
                "Notes survive.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    frontmatter, body, skipped = storage.salvage_project(path, max_line_bytes=80)

    assert frontmatter["slug"] == "demo"
    assert frontmatter["tier"] == "tracked"
    assert "red_flags" not in frontmatter
    assert skipped == ["red_flags"]
    assert "# Demo" in body
    assert "Notes survive." in body


def test_read_project_streams_large_files_when_needed(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "demo.md"
    path.write_text(
        "\n".join(
            [
                "---",
                "slug: demo",
                "has_token: yes",
                "tier: tracked",
                "---",
                "# Demo",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(storage, "_LARGE_FILE_BYTES", 1)
    frontmatter, body = storage.read_project(path)

    assert frontmatter["slug"] == "demo"
    assert frontmatter["has_token"] == "yes"
    assert frontmatter["tier"] == "tracked"
    assert "# Demo" in body
