"""Tests for group-chat @mention parsing and routing logic."""

from factory.groupchat.mentions import TEAM_ALIASES, parse_mentions


# ── parse_mentions ─────────────────────────────────────────────────────────────

def test_parse_single_mention() -> None:
    assert parse_mentions("@solArch what did you decide?") == ["solution_arch"]


def test_parse_multiple_mentions() -> None:
    result = parse_mentions("@backend and @qa please review this")
    assert result == ["backend_eng", "qa_eng"]


def test_parse_canonical_team_name_as_mention() -> None:
    assert parse_mentions("@solution_arch explain the ADR") == ["solution_arch"]


def test_parse_no_mentions_returns_empty() -> None:
    assert parse_mentions("what is the DB schema?") == []


def test_parse_deduplicates_same_team() -> None:
    # @solArch and @arch both resolve to solution_arch — only one entry expected
    result = parse_mentions("@solArch please check, also @arch")
    assert result == ["solution_arch"]


def test_parse_unknown_mention_ignored() -> None:
    # @nonexistent should be silently skipped
    result = parse_mentions("@nonexistent team please respond")
    assert result == []


def test_parse_mixed_case_tokens() -> None:
    # aliases are matched case-insensitively
    assert parse_mentions("@SolArch help") == ["solution_arch"]
    assert parse_mentions("@BACKEND status?") == ["backend_eng"]


def test_parse_preserves_insertion_order() -> None:
    result = parse_mentions("@qa and @devops should sign off")
    assert result == ["qa_eng", "devops"]


# ── TEAM_ALIASES sanity ────────────────────────────────────────────────────────

def test_all_aliases_map_to_known_teams() -> None:
    known = {
        "product_mgmt", "biz_analysis", "solution_arch", "api_design", "ux_ui",
        "frontend_eng", "backend_eng", "database_eng", "data_eng", "ml_eng",
        "security_eng", "compliance", "devops", "qa_eng", "sre_ops",
        "docs_team", "feature_eng",
    }
    for alias, canonical in TEAM_ALIASES.items():
        assert canonical in known, f"Alias {alias!r} maps to unknown team {canonical!r}"
