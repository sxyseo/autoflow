"""
Tests for the test framework module.
"""

import sys
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from test_framework import (
    TestConfig,
    TestDiscovery,
    TestFile,
    TestResult,
    TestRunResult,
    TestStatus,
)


class TestTestConfig:
    """Tests for TestConfig class."""

    def test_default_config(self):
        """Test that default configuration is loaded."""
        config = TestConfig()
        assert config.test_directories is not None
        assert len(config.test_directories) > 0

    def test_test_patterns(self):
        """Test that test patterns are configured."""
        config = TestConfig()
        assert "test_*.py" in config.test_patterns

    def test_auto_retry_config(self):
        """Test auto-retry configuration."""
        config = TestConfig()
        assert config.auto_retry_enabled in [True, False]
        assert config.max_retry_attempts >= 1

    def test_coverage_threshold(self):
        """Test coverage threshold configuration."""
        config = TestConfig()
        assert 0 <= config.coverage_threshold <= 100

    def test_flaky_detection_config(self):
        """Test flaky detection configuration."""
        config = TestConfig()
        assert config.flaky_min_runs >= 1
        assert 0 <= config.flaky_quarantine_threshold <= 1


class TestTestDiscovery:
    """Tests for TestDiscovery class."""

    def test_discovery_initialization(self):
        """Test that discovery can be initialized."""
        config = TestConfig()
        discovery = TestDiscovery(config)
        assert discovery is not None

    def test_discover_returns_list(self):
        """Test that discover returns a list."""
        config = TestConfig()
        discovery = TestDiscovery(config)
        result = discovery.discover()
        assert isinstance(result, list)

    def test_discover_finds_test_files(self):
        """Test that discover finds test files."""
        config = TestConfig()
        discovery = TestDiscovery(config)
        test_files = discovery.discover()
        # This test file should be discovered
        assert len(test_files) >= 1


class TestTestStatus:
    """Tests for TestStatus enum."""

    def test_status_values(self):
        """Test that all expected status values exist."""
        assert TestStatus.PASSED.value == "passed"
        assert TestStatus.FAILED.value == "failed"
        assert TestStatus.SKIPPED.value == "skipped"
        assert TestStatus.ERROR.value == "error"
        assert TestStatus.FLAKY.value == "flaky"


class TestTestResult:
    """Tests for TestResult dataclass."""

    def test_create_test_result(self):
        """Test creating a test result."""
        result = TestResult(
            name="test_example",
            file_path="tests/test_example.py",
            status=TestStatus.PASSED,
            duration=0.5
        )
        assert result.name == "test_example"
        assert result.status == TestStatus.PASSED
        assert result.duration == 0.5

    def test_test_result_with_message(self):
        """Test test result with message."""
        result = TestResult(
            name="test_example",
            file_path="tests/test_example.py",
            status=TestStatus.FAILED,
            duration=1.0,
            message="Assertion failed"
        )
        assert result.message == "Assertion failed"


class TestTestRunResult:
    """Tests for TestRunResult dataclass."""

    def test_create_run_result(self):
        """Test creating a run result."""
        result = TestRunResult(
            total=10,
            passed=8,
            failed=2,
            skipped=0,
            errors=0,
            duration=5.0
        )
        assert result.total == 10
        assert result.passed == 8
        assert result.failed == 2

    def test_run_result_success(self):
        """Test run result success property."""
        success_result = TestRunResult(
            total=10,
            passed=10,
            failed=0,
            skipped=0,
            errors=0,
            duration=5.0
        )
        assert success_result.success is True

        failed_result = TestRunResult(
            total=10,
            passed=8,
            failed=2,
            skipped=0,
            errors=0,
            duration=5.0
        )
        assert failed_result.success is False


class TestTestFile:
    """Tests for TestFile dataclass."""

    def test_create_test_file(self):
        """Test creating a test file."""
        test_file = TestFile(
            path=Path("tests/test_example.py"),
            module_name="tests.test_example",
            test_functions=["test_one", "test_two"]
        )
        assert test_file.module_name == "tests.test_example"
        assert len(test_file.test_functions) == 2
