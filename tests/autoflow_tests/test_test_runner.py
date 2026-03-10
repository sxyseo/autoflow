"""
Tests for the test runner module.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from test_runner import (
    add_to_quarantine,
    cmd_coverage,
    cmd_detect_flaky,
    cmd_discover,
    cmd_quarantine_clear,
    cmd_quarantine_list,
    cmd_quarantine_remove,
    cmd_run,
    get_quarantined_tests,
    load_quarantine_config,
    remove_from_quarantine,
    save_quarantine_config,
)


class TestLoadQuarantineConfig:
    """Tests for load_quarantine_config function."""

    def test_load_config_nonexistent_file(self, tmp_path, monkeypatch):
        """Test loading config when file doesn't exist."""
        config_path = tmp_path / "config" / "flaky_tests.json"
        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        config = load_quarantine_config()

        assert "quarantined_tests" in config
        assert "metadata" in config
        assert config["quarantined_tests"] == {}

    def test_load_config_existing_file(self, tmp_path, monkeypatch):
        """Test loading config from existing file."""
        config_path = tmp_path / "config" / "flaky_tests.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        test_config = {
            "quarantined_tests": {"test_example": {"pass_rate": 0.5}},
            "metadata": {"created_at": "2024-01-01"},
        }
        with open(config_path, "w") as f:
            json.dump(test_config, f)

        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        config = load_quarantine_config()

        assert config["quarantined_tests"]["test_example"]["pass_rate"] == 0.5


class TestSaveQuarantineConfig:
    """Tests for save_quarantine_config function."""

    def test_save_config_creates_directory(self, tmp_path, monkeypatch):
        """Test that saving config creates parent directories."""
        config_path = tmp_path / "config" / "subdir" / "flaky_tests.json"
        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        config = {
            "quarantined_tests": {},
            "metadata": {"created_at": None, "last_updated": None},
        }

        save_quarantine_config(config)

        assert config_path.exists()

    def test_save_config_updates_timestamp(self, tmp_path, monkeypatch):
        """Test that saving config updates timestamps."""
        config_path = tmp_path / "config" / "flaky_tests.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        config = {
            "quarantined_tests": {},
            "metadata": {"created_at": None, "last_updated": None},
        }

        save_quarantine_config(config)

        assert config["metadata"]["last_updated"] is not None
        assert config["metadata"]["created_at"] is not None


class TestAddToQuarantine:
    """Tests for add_to_quarantine function."""

    def test_add_to_quarantine(self, tmp_path, monkeypatch):
        """Test adding a test to quarantine."""
        config_path = tmp_path / "config" / "flaky_tests.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        add_to_quarantine(
            test_name="tests/test_example.py::test_flaky",
            pass_rate=0.6,
            runs=10,
            passed=6,
        )

        config = load_quarantine_config()
        assert "tests/test_example.py::test_flaky" in config["quarantined_tests"]
        assert (
            config["quarantined_tests"]["tests/test_example.py::test_flaky"][
                "pass_rate"
            ]
            == 0.6
        )
        assert (
            config["quarantined_tests"]["tests/test_example.py::test_flaky"]["runs"]
            == 10
        )
        assert (
            config["quarantined_tests"]["tests/test_example.py::test_flaky"]["failed"]
            == 4
        )


class TestRemoveFromQuarantine:
    """Tests for remove_from_quarantine function."""

    def test_remove_existing_test(self, tmp_path, monkeypatch):
        """Test removing an existing test from quarantine."""
        config_path = tmp_path / "config" / "flaky_tests.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        # Add a test first
        add_to_quarantine("test_to_remove", 0.5, 5, 3)

        # Remove it
        result = remove_from_quarantine("test_to_remove")

        assert result is True
        config = load_quarantine_config()
        assert "test_to_remove" not in config["quarantined_tests"]

    def test_remove_nonexistent_test(self, tmp_path, monkeypatch):
        """Test removing a test that doesn't exist."""
        config_path = tmp_path / "config" / "flaky_tests.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        result = remove_from_quarantine("nonexistent_test")

        assert result is False


class TestGetQuarantinedTests:
    """Tests for get_quarantined_tests function."""

    def test_get_quarantined_tests_empty(self, tmp_path, monkeypatch):
        """Test getting quarantined tests when none exist."""
        config_path = tmp_path / "config" / "flaky_tests.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        tests = get_quarantined_tests()

        assert tests == {}

    def test_get_quarantined_tests_with_data(self, tmp_path, monkeypatch):
        """Test getting quarantined tests with data."""
        config_path = tmp_path / "config" / "flaky_tests.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        add_to_quarantine("test_one", 0.5, 4, 2)
        add_to_quarantine("test_two", 0.8, 5, 4)

        tests = get_quarantined_tests()

        assert len(tests) == 2
        assert "test_one" in tests
        assert "test_two" in tests


class TestCmdDiscover:
    """Tests for cmd_discover function."""

    def test_cmd_discover_returns_zero(self):
        """Test that discover command returns 0."""
        args = MagicMock()

        result = cmd_discover(args)

        assert result == 0


class TestCmdRun:
    """Tests for cmd_run function."""

    def test_cmd_run_basic_args(self):
        """Test cmd_run with basic arguments."""
        args = MagicMock()
        args.tests = None
        args.auto_retry = False
        args.max_attempts = 3

        # This will actually try to run tests, so we just verify it returns an int
        result = cmd_run(args)
        assert isinstance(result, int)


class TestCmdCoverage:
    """Tests for cmd_coverage function."""

    def test_cmd_coverage_basic_args(self):
        """Test cmd_coverage with basic arguments."""
        args = MagicMock()
        args.threshold = None

        # This will actually try to run coverage, so we just verify it returns an int
        result = cmd_coverage(args)
        assert isinstance(result, int)


class TestCmdDetectFlaky:
    """Tests for cmd_detect_flaky function."""

    def test_cmd_detect_flaky_basic_args(self):
        """Test cmd_detect_flaky with basic arguments."""
        args = MagicMock()
        args.runs = 1  # Minimal runs for speed
        args.test = None
        args.quarantine = False

        # This will actually try to run tests, so we just verify it returns an int
        result = cmd_detect_flaky(args)
        assert isinstance(result, int)


class TestCmdQuarantineList:
    """Tests for cmd_quarantine_list function."""

    def test_cmd_quarantine_list_empty(self, tmp_path, monkeypatch):
        """Test listing quarantine when empty."""
        config_path = tmp_path / "config" / "flaky_tests.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        args = MagicMock()
        result = cmd_quarantine_list(args)

        assert result == 0

    def test_cmd_quarantine_list_with_tests(self, tmp_path, monkeypatch):
        """Test listing quarantine with tests."""
        config_path = tmp_path / "config" / "flaky_tests.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        add_to_quarantine("test_example", 0.5, 4, 2)

        args = MagicMock()
        result = cmd_quarantine_list(args)

        assert result == 0


class TestCmdQuarantineRemove:
    """Tests for cmd_quarantine_remove function."""

    def test_cmd_quarantine_remove_existing(self, tmp_path, monkeypatch):
        """Test removing existing test via CLI."""
        config_path = tmp_path / "config" / "flaky_tests.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        add_to_quarantine("test_to_remove", 0.5, 4, 2)

        args = MagicMock()
        args.test_name = "test_to_remove"
        result = cmd_quarantine_remove(args)

        assert result == 0

    def test_cmd_quarantine_remove_nonexistent(self, tmp_path, monkeypatch):
        """Test removing nonexistent test via CLI."""
        config_path = tmp_path / "config" / "flaky_tests.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        args = MagicMock()
        args.test_name = "nonexistent_test"
        result = cmd_quarantine_remove(args)

        assert result == 1


class TestCmdQuarantineClear:
    """Tests for cmd_quarantine_clear function."""

    def test_cmd_quarantine_clear_empty(self, tmp_path, monkeypatch):
        """Test clearing empty quarantine."""
        config_path = tmp_path / "config" / "flaky_tests.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        args = MagicMock()
        result = cmd_quarantine_clear(args)

        assert result == 0

    def test_cmd_quarantine_clear_with_tests(self, tmp_path, monkeypatch):
        """Test clearing quarantine with tests."""
        config_path = tmp_path / "config" / "flaky_tests.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("test_runner.FLAKY_TESTS_CONFIG_PATH", config_path)

        add_to_quarantine("test_one", 0.5, 4, 2)
        add_to_quarantine("test_two", 0.6, 5, 3)

        args = MagicMock()
        result = cmd_quarantine_clear(args)

        assert result == 0
        tests = get_quarantined_tests()
        assert len(tests) == 0
