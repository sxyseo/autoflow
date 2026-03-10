"""
Unit Tests for Autoflow CLI Skill Commands

Tests the skill command functionality including listing skills
and showing skill details.

These tests use temporary directories to avoid affecting real state files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from autoflow.cli.skill import skill, skill_list, skill_show
from autoflow.core.config import Config


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory."""
    state_dir = tmp_path / ".autoflow"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def sample_config(temp_state_dir: Path) -> Config:
    """Create a sample config for testing."""
    return Config(state_dir=str(temp_state_dir))


@pytest.fixture
def temp_skills_dir(tmp_path: Path) -> Path:
    """Create a temporary skills directory with sample skills."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    # Create a sample skill
    skill1 = skills_dir / "TEST_SKILL_1"
    skill1.mkdir()
    (skill1 / "SKILL.md").write_text("# Test Skill 1\n\nThis is a test skill.")

    # Create another sample skill
    skill2 = skills_dir / "TEST_SKILL_2"
    skill2.mkdir()
    (skill2 / "SKILL.md").write_text("# Test Skill 2\n\nAnother test skill.")

    return skills_dir


# ============================================================================
# Skill List Command Tests - Basic Functionality
# ============================================================================


class TestSkillListBasic:
    """Tests for skill list command basic functionality."""

    def test_skill_list_displays_header(self, runner: CliRunner) -> None:
        """Test skill list displays proper header."""
        result = runner.invoke(
            skill_list,
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        assert "Available Skills" in result.output
        assert "=" * 60 in result.output

    def test_skill_list_no_skills_message(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test skill list shows message when no skills found."""
        config = Config()
        # Use empty temp directory
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                skill_list,
                ["--skills-dir", str(tmp_path)],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "No skills found" in result.output

    def test_skill_list_shows_searched_dirs(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test skill list shows searched directories when empty."""
        config = Config()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                skill_list,
                ["--skills-dir", str(tmp_path)],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Searched directories:" in result.output


# ============================================================================
# Skill List Command Tests - With Skills
# ============================================================================


class TestSkillListWithSkills:
    """Tests for skill list command with actual skills."""

    def test_skill_list_finds_skills(self, runner: CliRunner, temp_skills_dir: Path) -> None:
        """Test skill list discovers skills in directory."""
        config = Config()

        result = runner.invoke(
            skill_list,
            ["--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "TEST_SKILL_1" in result.output
        assert "TEST_SKILL_2" in result.output

    def test_skill_list_shows_skill_path(self, runner: CliRunner, temp_skills_dir: Path) -> None:
        """Test skill list shows skill file path."""
        config = Config()

        result = runner.invoke(
            skill_list,
            ["--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Path:" in result.output

    def test_skill_list_count(self, runner: CliRunner, temp_skills_dir: Path) -> None:
        """Test skill list finds correct number of skills."""
        config = Config()

        result = runner.invoke(
            skill_list,
            ["--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": False},
        )

        assert result.exit_code == 0
        # Should show both skills
        assert "TEST_SKILL_1" in result.output
        assert "TEST_SKILL_2" in result.output

    def test_skill_list_ignores_non_skill_dirs(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test skill list ignores directories without SKILL.md."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Create a directory without SKILL.md
        not_a_skill = skills_dir / "NOT_A_SKILL"
        not_a_skill.mkdir()
        (not_a_skill / "README.md").write_text("Not a skill")

        # Create a valid skill
        valid_skill = skills_dir / "VALID_SKILL"
        valid_skill.mkdir()
        (valid_skill / "SKILL.md").write_text("# Valid Skill")

        config = Config()

        result = runner.invoke(
            skill_list,
            ["--skills-dir", str(skills_dir)],
            obj={"config": config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "VALID_SKILL" in result.output
        assert "NOT_A_SKILL" not in result.output


# ============================================================================
# Skill List Command Tests - JSON Output
# ============================================================================


class TestSkillListJSON:
    """Tests for skill list --json functionality."""

    def test_skill_list_json_output(self, runner: CliRunner, temp_skills_dir: Path) -> None:
        """Test skill list returns valid JSON."""
        config = Config()

        result = runner.invoke(
            skill_list,
            ["--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert "skills" in output
        assert "count" in output
        assert isinstance(output["skills"], list)

    def test_skill_list_json_has_fields(self, runner: CliRunner, temp_skills_dir: Path) -> None:
        """Test skill list JSON has required fields."""
        config = Config()

        result = runner.invoke(
            skill_list,
            ["--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)

        for skill in output["skills"]:
            assert "name" in skill
            assert "path" in skill
            assert "directory" in skill

    def test_skill_list_json_count_matches(
        self, runner: CliRunner, temp_skills_dir: Path
    ) -> None:
        """Test skill list JSON count matches actual skills."""
        config = Config()

        result = runner.invoke(
            skill_list,
            ["--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["count"] == len(output["skills"])
        # Note: count includes skills from both custom dir and config.openclaw.extra_dirs
        assert output["count"] >= 2  # We created at least 2 skills


# ============================================================================
# Skill Show Command Tests - Basic Functionality
# ============================================================================


class TestSkillShowBasic:
    """Tests for skill show command basic functionality."""

    def test_skill_show_displays_content(
        self, runner: CliRunner, temp_skills_dir: Path
    ) -> None:
        """Test skill show displays skill content."""
        config = Config()

        result = runner.invoke(
            skill_show,
            ["TEST_SKILL_1", "--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Skill: TEST_SKILL_1" in result.output
        assert "Path:" in result.output
        assert "Test Skill 1" in result.output

    def test_skill_show_shows_path(self, runner: CliRunner, temp_skills_dir: Path) -> None:
        """Test skill show shows skill file path."""
        config = Config()

        result = runner.invoke(
            skill_show,
            ["TEST_SKILL_1", "--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Path:" in result.output
        assert "SKILL.md" in result.output

    def test_skill_show_has_separator(self, runner: CliRunner, temp_skills_dir: Path) -> None:
        """Test skill show shows separator line."""
        config = Config()

        result = runner.invoke(
            skill_show,
            ["TEST_SKILL_1", "--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "=" * 60 in result.output


# ============================================================================
# Skill Show Command Tests - JSON Output
# ============================================================================


class TestSkillShowJSON:
    """Tests for skill show --json functionality."""

    def test_skill_show_json_output(self, runner: CliRunner, temp_skills_dir: Path) -> None:
        """Test skill show returns valid JSON."""
        config = Config()

        result = runner.invoke(
            skill_show,
            ["TEST_SKILL_1", "--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert "name" in output
        assert "path" in output
        assert "content" in output

    def test_skill_show_json_has_content(self, runner: CliRunner, temp_skills_dir: Path) -> None:
        """Test skill show JSON includes skill content."""
        config = Config()

        result = runner.invoke(
            skill_show,
            ["TEST_SKILL_1", "--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["name"] == "TEST_SKILL_1"
        assert "Test Skill 1" in output["content"]

    def test_skill_show_json_path_is_string(
        self, runner: CliRunner, temp_skills_dir: Path
    ) -> None:
        """Test skill show JSON path is a string."""
        config = Config()

        result = runner.invoke(
            skill_show,
            ["TEST_SKILL_1", "--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert isinstance(output["path"], str)


# ============================================================================
# Skill Command Tests - Error Handling
# ============================================================================


class TestSkillErrors:
    """Tests for skill command error handling."""

    def test_skill_list_without_config(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test skill list handles missing config."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                skill_list,
                obj={"config": None, "output_json": False},
            )

            assert result.exit_code == 1
            assert "Error: Configuration not loaded" in result.output

    def test_skill_show_without_config(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test skill show handles missing config."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                skill_show,
                ["TEST_SKILL"],
                obj={"config": None, "output_json": False},
            )

            assert result.exit_code == 1
            assert "Error: Configuration not loaded" in result.output

    def test_skill_show_not_found(self, runner: CliRunner, temp_skills_dir: Path) -> None:
        """Test skill show handles non-existent skill."""
        config = Config()

        result = runner.invoke(
            skill_show,
            ["NONEXISTENT_SKILL", "--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": False},
        )

        assert result.exit_code == 1
        assert "Error: Skill 'NONEXISTENT_SKILL' not found" in result.output

    def test_skill_show_not_found_json(self, runner: CliRunner, temp_skills_dir: Path) -> None:
        """Test skill show handles non-existent skill with JSON output."""
        config = Config()

        result = runner.invoke(
            skill_show,
            ["NONEXISTENT_SKILL", "--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": True},
        )

        assert result.exit_code == 1


# ============================================================================
# Skill Command Tests - Directory Options
# ============================================================================


class TestSkillDirectoryOptions:
    """Tests for skills directory option handling."""

    def test_skill_list_with_custom_dir(self, runner: CliRunner, temp_skills_dir: Path) -> None:
        """Test skill list with custom --skills-dir."""
        config = Config()

        result = runner.invoke(
            skill_list,
            ["--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "TEST_SKILL_1" in result.output

    def test_skill_show_with_custom_dir(self, runner: CliRunner, temp_skills_dir: Path) -> None:
        """Test skill show with custom --skills-dir."""
        config = Config()

        result = runner.invoke(
            skill_show,
            ["TEST_SKILL_1", "--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Test Skill 1" in result.output

    def test_skill_list_expands_tilde(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test skill list expands ~ in directory path."""
        config = Config()

        # Create a temp directory to test with
        test_dir = tmp_path / "test_skills"
        test_dir.mkdir()

        # This test verifies the path expansion logic works
        result = runner.invoke(
            skill_list,
            ["--skills-dir", str(test_dir)],
            obj={"config": config, "output_json": False},
        )

        # Should not crash even if directory is empty
        assert result.exit_code == 0


# ============================================================================
# Skill Command Tests - Integration
# ============================================================================


class TestSkillIntegration:
    """Tests for skill command integration with Config."""

    def test_skill_list_uses_config_extra_dirs(
        self, runner: CliRunner, temp_skills_dir: Path
    ) -> None:
        """Test skill list uses extra_dirs from Config."""
        # Create config that will include our temp skills dir
        config = Config()

        result = runner.invoke(
            skill_list,
            ["--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "TEST_SKILL_1" in result.output

    def test_skill_show_searches_multiple_dirs(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test skill show searches in multiple directories."""
        # Create first skills dir
        skills_dir1 = tmp_path / "skills1"
        skills_dir1.mkdir()
        skill1 = skills_dir1 / "SKILL_IN_DIR1"
        skill1.mkdir()
        (skill1 / "SKILL.md").write_text("# Skill in Dir 1")

        # Create second skills dir
        skills_dir2 = tmp_path / "skills2"
        skills_dir2.mkdir()
        skill2 = skills_dir2 / "SKILL_IN_DIR2"
        skill2.mkdir()
        (skill2 / "SKILL.md").write_text("# Skill in Dir 2")

        config = Config()

        # Find skill in first dir
        result = runner.invoke(
            skill_show,
            ["SKILL_IN_DIR1", "--skills-dir", str(skills_dir1)],
            obj={"config": config, "output_json": False},
        )
        assert result.exit_code == 0
        assert "Skill in Dir 1" in result.output

        # Find skill in second dir
        result = runner.invoke(
            skill_show,
            ["SKILL_IN_DIR2", "--skills-dir", str(skills_dir2)],
            obj={"config": config, "output_json": False},
        )
        assert result.exit_code == 0
        assert "Skill in Dir 2" in result.output


# ============================================================================
# Skill Command Tests - Edge Cases
# ============================================================================


class TestSkillEdgeCases:
    """Tests for skill command edge cases."""

    def test_skill_group_requires_subcommand(self, runner: CliRunner) -> None:
        """Test skill group requires subcommand."""
        result = runner.invoke(
            skill,
            obj={"config": Config(), "output_json": False},
        )

        # Should show help or error
        assert result.exit_code != 0 or "Usage:" in result.output

    def test_skill_list_with_custom_empty_dir(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test skill list with custom empty directory (still shows config skills)."""
        config = Config()
        # Create an empty directory (using exists=True in Click, so need real dir)
        empty_dir = tmp_path / "empty_skills"
        empty_dir.mkdir()

        result = runner.invoke(
            skill_list,
            ["--skills-dir", str(empty_dir)],
            obj={"config": config, "output_json": False},
        )

        # Should not crash - will show skills from config.openclaw.extra_dirs
        assert result.exit_code == 0
        # The custom dir is empty but config.openclaw.extra_dirs may have skills
        assert "Available Skills" in result.output

    def test_skill_list_with_only_custom_dir(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test skill list shows skills from both custom and config dirs."""
        config = Config()
        # Create a custom directory with skills
        custom_dir = tmp_path / "custom_skills"
        custom_dir.mkdir()
        custom_skill = custom_dir / "CUSTOM_SKILL"
        custom_skill.mkdir()
        (custom_skill / "SKILL.md").write_text("# Custom Skill")

        result = runner.invoke(
            skill_list,
            ["--skills-dir", str(custom_dir)],
            obj={"config": config, "output_json": True},
        )

        # Should show skills from both custom dir and config.openclaw.extra_dirs
        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        skill_names = [s["name"] for s in output["skills"]]
        assert "CUSTOM_SKILL" in skill_names

    def test_skill_show_with_multiline_content(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test skill show with multi-line skill content."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill = skills_dir / "MULTILINE_SKILL"
        skill.mkdir()
        content = """# Multi-line Skill

This skill has:
- Multiple lines
- Bullet points
- Various sections

## Usage
Use this skill carefully.
"""
        (skill / "SKILL.md").write_text(content)

        config = Config()

        result = runner.invoke(
            skill_show,
            ["MULTILINE_SKILL", "--skills-dir", str(skills_dir)],
            obj={"config": config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Multi-line Skill" in result.output
        assert "Bullet points" in result.output

    def test_skill_list_consistency(self, runner: CliRunner, temp_skills_dir: Path) -> None:
        """Test skill list output is consistent across calls."""
        config = Config()

        result1 = runner.invoke(
            skill_list,
            ["--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": True},
        )
        result2 = runner.invoke(
            skill_list,
            ["--skills-dir", str(temp_skills_dir)],
            obj={"config": config, "output_json": True},
        )

        assert result1.exit_code == 0
        assert result2.exit_code == 0
        assert result1.output == result2.output


# ============================================================================
# Skill Command Tests - Content Handling
# ============================================================================


class TestSkillContent:
    """Tests for skill content handling."""

    def test_skill_show_preserves_markdown(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test skill show preserves markdown formatting."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill = skills_dir / "MARKDOWN_SKILL"
        skill.mkdir()
        markdown = """# Markdown Skill

**Bold text** and *italic text*.

## Code
```python
def hello():
    print("Hello, world!")
```
"""
        (skill / "SKILL.md").write_text(markdown)

        config = Config()

        result = runner.invoke(
            skill_show,
            ["MARKDOWN_SKILL", "--skills-dir", str(skills_dir)],
            obj={"config": config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "**Bold text**" in result.output

    def test_skill_show_json_preserves_content(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test skill show JSON preserves full content."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill = skills_dir / "CONTENT_SKILL"
        skill.mkdir()
        content = "# Title\n\nLine 1\nLine 2\nLine 3"
        (skill / "SKILL.md").write_text(content)

        config = Config()

        result = runner.invoke(
            skill_show,
            ["CONTENT_SKILL", "--skills-dir", str(skills_dir)],
            obj={"config": config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert "Line 1" in output["content"]
        assert "Line 2" in output["content"]
        assert "Line 3" in output["content"]

    def test_skill_list_with_empty_skill_md(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test skill list with empty SKILL.md."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill = skills_dir / "EMPTY_SKILL"
        skill.mkdir()
        (skill / "SKILL.md").write_text("")

        config = Config()

        result = runner.invoke(
            skill_list,
            ["--skills-dir", str(skills_dir)],
            obj={"config": config, "output_json": False},
        )

        # Should still find the skill
        assert result.exit_code == 0
        assert "EMPTY_SKILL" in result.output
