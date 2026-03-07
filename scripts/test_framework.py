#!/usr/bin/env python3
"""
Test Framework for Autoflow - Test discovery and execution utilities.

This module provides the core functionality for discovering, running, and
analyzing tests in the Autoflow project. It supports:
- Test discovery across multiple directories
- Auto-retry with exponential backoff
- Coverage tracking and enforcement
- Flaky test detection
"""

import fnmatch
import json
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class TestStatus(Enum):
    """Status of a test execution."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    FLAKY = "flaky"


@dataclass
class TestResult:
    """Result of a single test execution."""
    name: str
    file_path: str
    status: TestStatus
    duration: float
    message: Optional[str] = None
    output: Optional[str] = None


@dataclass
class TestRunResult:
    """Result of a complete test run."""
    total: int
    passed: int
    failed: int
    skipped: int
    errors: int
    duration: float
    results: list[TestResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if the test run was successful."""
        return self.failed == 0 and self.errors == 0


@dataclass
class TestFile:
    """Represents a discovered test file."""
    path: Path
    module_name: str
    test_functions: list[str] = field(default_factory=list)


class TestConfig:
    """Configuration for test framework."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize test configuration.

        Args:
            config_path: Path to configuration file. Defaults to config/test_config.json.
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "test_config.json"

        self.config_path = config_path
        self._config = self._load_config()

    def _load_config(self) -> dict:
        """Load configuration from JSON file."""
        if not self.config_path.exists():
            return self._default_config()

        with open(self.config_path, "r") as f:
            return json.load(f)

    def _default_config(self) -> dict:
        """Return default configuration."""
        return {
            "test_discovery": {
                "test_directories": ["tests"],
                "test_patterns": ["test_*.py", "*_test.py"],
                "exclude_patterns": ["__pycache__", "*.pyc"]
            },
            "test_execution": {
                "default_timeout": 300,
                "auto_retry": {
                    "enabled": True,
                    "max_attempts": 3,
                    "backoff_factor": 2.0,
                    "initial_delay": 1.0
                }
            },
            "coverage": {
                "enabled": True,
                "threshold": 80,
                "fail_under_threshold": True
            },
            "flaky_detection": {
                "enabled": True,
                "min_runs": 3,
                "quarantine_threshold": 0.3
            }
        }

    @property
    def test_directories(self) -> list[str]:
        """Get test directories."""
        return self._config.get("test_discovery", {}).get("test_directories", ["tests"])

    @property
    def test_patterns(self) -> list[str]:
        """Get test file patterns."""
        return self._config.get("test_discovery", {}).get("test_patterns", ["test_*.py"])

    @property
    def exclude_patterns(self) -> list[str]:
        """Get exclude patterns."""
        return self._config.get("test_discovery", {}).get("exclude_patterns", [])

    @property
    def auto_retry_enabled(self) -> bool:
        """Check if auto-retry is enabled."""
        return self._config.get("test_execution", {}).get("auto_retry", {}).get("enabled", True)

    @property
    def max_retry_attempts(self) -> int:
        """Get maximum retry attempts."""
        return self._config.get("test_execution", {}).get("auto_retry", {}).get("max_attempts", 3)

    @property
    def retry_backoff_factor(self) -> float:
        """Get retry backoff factor."""
        return self._config.get("test_execution", {}).get("auto_retry", {}).get("backoff_factor", 2.0)

    @property
    def retry_initial_delay(self) -> float:
        """Get initial retry delay."""
        return self._config.get("test_execution", {}).get("auto_retry", {}).get("initial_delay", 1.0)

    @property
    def coverage_threshold(self) -> int:
        """Get coverage threshold."""
        return self._config.get("coverage", {}).get("threshold", 80)

    @property
    def flaky_min_runs(self) -> int:
        """Get minimum runs for flaky detection."""
        return self._config.get("flaky_detection", {}).get("min_runs", 3)

    @property
    def flaky_quarantine_threshold(self) -> float:
        """Get quarantine threshold for flaky tests."""
        return self._config.get("flaky_detection", {}).get("quarantine_threshold", 0.3)


class TestDiscovery:
    """Discovers test files in the project."""

    def __init__(self, config: Optional[TestConfig] = None):
        """Initialize test discovery.

        Args:
            config: Test configuration. If None, uses default config.
        """
        self.config = config or TestConfig()

    def discover(self, base_path: Optional[Path] = None) -> list[TestFile]:
        """Discover all test files.

        Args:
            base_path: Base path to search from. Defaults to current working directory.

        Returns:
            List of discovered test files.
        """
        if base_path is None:
            base_path = Path.cwd()

        test_files = []

        for directory in self.config.test_directories:
            dir_path = base_path / directory
            if dir_path.exists():
                test_files.extend(self._scan_directory(dir_path, base_path))

        return test_files

    def _scan_directory(self, directory: Path, base_path: Path) -> list[TestFile]:
        """Scan a directory for test files.

        Args:
            directory: Directory to scan.
            base_path: Base path for calculating module names.

        Returns:
            List of test files found in the directory.
        """
        test_files = []

        for file_path in directory.rglob("*.py"):
            # Check if file matches test patterns
            if not self._matches_patterns(file_path.name, self.config.test_patterns):
                continue

            # Check if file should be excluded
            if self._matches_patterns(str(file_path), self.config.exclude_patterns):
                continue

            # Calculate module name
            relative_path = file_path.relative_to(base_path)
            module_name = str(relative_path.with_suffix("")).replace("/", ".").replace("\\", ".")

            test_file = TestFile(
                path=file_path,
                module_name=module_name,
                test_functions=self._extract_test_functions(file_path)
            )
            test_files.append(test_file)

        return test_files

    def _matches_patterns(self, value: str, patterns: list[str]) -> bool:
        """Check if value matches any of the patterns.

        Args:
            value: Value to check.
            patterns: Patterns to match against.

        Returns:
            True if value matches any pattern.
        """
        return any(fnmatch.fnmatch(value, pattern) for pattern in patterns)

    def _extract_test_functions(self, file_path: Path) -> list[str]:
        """Extract test function names from a file.

        Args:
            file_path: Path to the test file.

        Returns:
            List of test function names.
        """
        test_functions = []

        try:
            content = file_path.read_text()
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("def test_") and "(" in line:
                    # Extract function name
                    func_name = line[4:].split("(")[0].strip()
                    if func_name:
                        test_functions.append(func_name)
        except Exception:
            pass  # Ignore files that can't be read

        return test_functions


class TestExecutor:
    """Executes tests with retry logic."""

    def __init__(self, config: Optional[TestConfig] = None):
        """Initialize test executor.

        Args:
            config: Test configuration. If None, uses default config.
        """
        self.config = config or TestConfig()

    def run_tests(
        self,
        test_paths: Optional[list[str]] = None,
        auto_retry: bool = False,
        max_attempts: Optional[int] = None,
        verbose: bool = False
    ) -> TestRunResult:
        """Run tests with optional auto-retry.

        Args:
            test_paths: Specific test paths to run. If None, runs all tests.
            auto_retry: Enable auto-retry for failed tests.
            max_attempts: Maximum retry attempts. Uses config if None.
            verbose: Enable verbose output.

        Returns:
            Test run result.
        """
        if max_attempts is None:
            max_attempts = self.config.max_retry_attempts if auto_retry else 1

        start_time = time.time()

        # Build pytest command
        cmd = ["python3", "-m", "pytest"]
        if test_paths:
            cmd.extend(test_paths)
        else:
            cmd.append("tests/")

        if verbose:
            cmd.append("-v")

        # Run tests
        attempt = 0
        last_result = None

        while attempt < max_attempts:
            attempt += 1

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            # Parse results
            test_result = self._parse_pytest_output(result.stdout, result.stderr)

            if test_result.success or not auto_retry:
                last_result = test_result
                break

            # Wait before retry with exponential backoff
            if attempt < max_attempts:
                delay = self.config.retry_initial_delay * (
                    self.config.retry_backoff_factor ** (attempt - 1)
                )
                time.sleep(delay)

        duration = time.time() - start_time

        if last_result is None:
            last_result = TestRunResult(
                total=0, passed=0, failed=0, skipped=0, errors=0, duration=duration
            )

        last_result.duration = duration
        return last_result

    def _parse_pytest_output(self, stdout: str, stderr: str) -> TestRunResult:
        """Parse pytest output to extract test results.

        Args:
            stdout: Standard output from pytest.
            stderr: Standard error from pytest.

        Returns:
            Parsed test run result.
        """
        # Simple parsing - look for the summary line
        # Example: "5 passed, 2 failed, 1 skipped"
        output = stdout + stderr

        passed = 0
        failed = 0
        skipped = 0
        errors = 0

        for line in output.splitlines():
            line = line.strip()
            if "passed" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "passed" and i > 0:
                        try:
                            passed = int(parts[i - 1])
                        except ValueError:
                            pass
                    if part == "failed" and i > 0:
                        try:
                            failed = int(parts[i - 1])
                        except ValueError:
                            pass
                    if part == "skipped" and i > 0:
                        try:
                            skipped = int(parts[i - 1])
                        except ValueError:
                            pass
                    if part == "error" or part == "errors" and i > 0:
                        try:
                            errors = int(parts[i - 1])
                        except ValueError:
                            pass

        total = passed + failed + skipped + errors

        return TestRunResult(
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            duration=0.0,
            output=output
        )

    def run_coverage(
        self,
        threshold: Optional[int] = None,
        source_dirs: Optional[list[str]] = None
    ) -> tuple[bool, float, str]:
        """Run tests with coverage tracking.

        Args:
            threshold: Coverage threshold percentage. Uses config if None.
            source_dirs: Source directories to measure. Uses config if None.

        Returns:
            Tuple of (success, coverage_percentage, output).
        """
        if threshold is None:
            threshold = self.config.coverage_threshold

        if source_dirs is None:
            source_dirs = ["scripts"]

        # Build coverage command
        cmd = [
            "python3", "-m", "pytest",
            "tests/",
            "--cov=" + ",".join(source_dirs),
            f"--cov-fail-under={threshold}",
            "--cov-report=term-missing"
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        output = result.stdout + result.stderr

        # Extract coverage percentage
        coverage = 0.0
        for line in output.splitlines():
            if "TOTAL" in line and "%" in line:
                parts = line.split()
                for part in reversed(parts):
                    if part.endswith("%"):
                        try:
                            coverage = float(part.rstrip("%"))
                            break
                        except ValueError:
                            pass

        success = result.returncode == 0
        return success, coverage, output


class FlakyTestDetector:
    """Detects flaky tests by running them multiple times."""

    def __init__(self, config: Optional[TestConfig] = None):
        """Initialize flaky test detector.

        Args:
            config: Test configuration. If None, uses default config.
        """
        self.config = config or TestConfig()

    def detect(
        self,
        test_path: Optional[str] = None,
        runs: Optional[int] = None
    ) -> dict[str, dict]:
        """Detect flaky tests by running them multiple times.

        Args:
            test_path: Specific test path to check. If None, checks all tests.
            runs: Number of runs. Uses config if None.

        Returns:
            Dictionary of flaky test info keyed by test name.
        """
        if runs is None:
            runs = self.config.flaky_min_runs

        # Run tests multiple times and track results
        test_results: dict[str, list[bool]] = {}

        for run_num in range(runs):
            cmd = ["python3", "-m", "pytest", "-v", "--tb=no"]
            if test_path:
                cmd.append(test_path)
            else:
                cmd.append("tests/")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            output = result.stdout + result.stderr

            # Parse individual test results
            for line in output.splitlines():
                line = line.strip()
                if "PASSED" in line or "FAILED" in line:
                    # Extract test name
                    parts = line.split()
                    for part in parts:
                        if "::" in part:
                            test_name = part
                            if test_name not in test_results:
                                test_results[test_name] = []
                            test_results[test_name].append("PASSED" in line)
                            break

        # Analyze results for flakiness
        flaky_tests = {}
        threshold = self.config.flaky_quarantine_threshold

        for test_name, results in test_results.items():
            if len(results) < 2:
                continue

            pass_rate = sum(results) / len(results)

            # A test is flaky if it has inconsistent results (not 0% or 100% pass rate)
            # and the pass rate is above the quarantine threshold
            if 0 < pass_rate < 1:
                flaky_tests[test_name] = {
                    "pass_rate": pass_rate,
                    "runs": len(results),
                    "passed": sum(results),
                    "failed": len(results) - sum(results),
                    "is_flaky": pass_rate > threshold
                }

        return flaky_tests


def discover_tests(config_path: Optional[Path] = None) -> list[TestFile]:
    """Discover all test files.

    Args:
        config_path: Path to configuration file.

    Returns:
        List of discovered test files.
    """
    config = TestConfig(config_path)
    discovery = TestDiscovery(config)
    return discovery.discover()


def run_tests(
    test_paths: Optional[list[str]] = None,
    auto_retry: bool = False,
    config_path: Optional[Path] = None
) -> TestRunResult:
    """Run tests with optional auto-retry.

    Args:
        test_paths: Specific test paths to run.
        auto_retry: Enable auto-retry for failed tests.
        config_path: Path to configuration file.

    Returns:
        Test run result.
    """
    config = TestConfig(config_path)
    executor = TestExecutor(config)
    return executor.run_tests(test_paths=test_paths, auto_retry=auto_retry)


if __name__ == "__main__":
    # Simple test discovery
    files = discover_tests()
    print(f"Discovered {len(files)} test files:")
    for f in files:
        print(f"  - {f.path} ({len(f.test_functions)} tests)")
