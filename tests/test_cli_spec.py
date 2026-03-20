"""Unit tests for the package CLI spec commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from autoflow.cli.main import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _write_spec(state_dir: Path, slug: str, metadata: dict, review: dict | None = None, archived: bool = False) -> None:
    base_dir = state_dir / "specs" / ("archive" if archived else "")
    spec_dir = base_dir / slug
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    if review is not None:
        (spec_dir / "review_state.json").write_text(json.dumps(review), encoding="utf-8")


def test_spec_list_json_output_includes_metadata(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        state_dir = Path(".autoflow")
        _write_spec(
            state_dir,
            "spec-001",
            {
                "slug": "spec-001",
                "title": "Test Spec 1",
                "summary": "First test spec",
                "status": "in_progress",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
                "worktree": {"branch": "feature-001", "base_branch": "main", "path": ""},
            },
            review={"approved": True, "approved_by": "reviewer-1", "review_count": 2},
        )

        result = runner.invoke(main, ["--json", "spec", "list"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["count"] == 1
        spec = payload["specs"][0]
        assert spec["slug"] == "spec-001"
        assert spec["title"] == "Test Spec 1"
        assert spec["status"] == "in_progress"
        assert spec["worktree"]["branch"] == "feature-001"
        assert spec["review"]["approved"] is True
        assert spec["review"]["review_count"] == 2


def test_spec_list_human_output_shows_status_branch_and_review(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        state_dir = Path(".autoflow")
        _write_spec(
            state_dir,
            "spec-001",
            {
                "slug": "spec-001",
                "title": "Approved Spec",
                "status": "review",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
                "worktree": {"branch": "codex/spec-001"},
            },
            review={"approved": True, "approved_by": "qa", "review_count": 1},
        )

        result = runner.invoke(main, ["spec", "list"])

        assert result.exit_code == 0
        assert "Specifications" in result.output
        assert "[spec-001] Approved Spec" in result.output
        assert "Status: review" in result.output
        assert "Branch: codex/spec-001" in result.output
        assert "Review: ✓ Approved" in result.output


def test_spec_list_respects_limit_and_sort_order(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        state_dir = Path(".autoflow")
        _write_spec(
            state_dir,
            "spec-001",
            {"slug": "spec-001", "title": "Oldest", "created_at": "2024-01-01T00:00:00Z"},
        )
        _write_spec(
            state_dir,
            "spec-002",
            {"slug": "spec-002", "title": "Newest", "created_at": "2024-01-03T00:00:00Z"},
        )
        _write_spec(
            state_dir,
            "spec-003",
            {"slug": "spec-003", "title": "Middle", "created_at": "2024-01-02T00:00:00Z"},
        )

        result = runner.invoke(main, ["--json", "spec", "list", "--limit", "2"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["count"] == 2
        assert [item["slug"] for item in payload["specs"]] == ["spec-002", "spec-003"]


def test_spec_list_can_include_archived_specs(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        state_dir = Path(".autoflow")
        _write_spec(
            state_dir,
            "active-spec",
            {"slug": "active-spec", "title": "Active", "created_at": "2024-01-02T00:00:00Z"},
        )
        _write_spec(
            state_dir,
            "archived-spec",
            {"slug": "archived-spec", "title": "Archived", "created_at": "2024-01-01T00:00:00Z"},
            archived=True,
        )

        result = runner.invoke(main, ["--json", "spec", "list", "--archived"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert [item["slug"] for item in payload["specs"]] == ["active-spec", "archived-spec"]
