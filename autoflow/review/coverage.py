#!/usr/bin/env python3
"""
Autoflow Coverage Tracking Module

Provides coverage tracking and analysis using coverage.py.
Integrates with the verification system to enforce coverage thresholds
and track coverage metrics over time.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class CoverageThreshold:
    """
    Coverage threshold configuration.

    Args:
        minimum: Minimum coverage percentage (0-100)
        branches: Branch coverage threshold (optional)
        functions: Function coverage threshold (optional)
        lines: Line coverage threshold (optional)
        module_overrides: Per-module threshold overrides (optional)
            Maps module patterns to threshold overrides.
            Patterns can be exact file paths or glob patterns.
            Example: {"autoflow/core/*": {"minimum": 90.0}}
    """
    minimum: float = 80.0
    branches: Optional[float] = None
    functions: Optional[float] = None
    lines: Optional[float] = None
    module_overrides: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def get_threshold_for_module(self, module_path: str) -> 'CoverageThreshold':
        """
        Get threshold configuration for a specific module.

        Checks module overrides for matching patterns and returns
        a threshold with overrides applied. Patterns are matched
        in order, with first match taking precedence.

        Args:
            module_path: Path to module file (e.g., "autoflow/core/module.py")

        Returns:
            CoverageThreshold with module-specific overrides applied
        """
        # Normalize path for matching
        normalized_path = module_path.replace("\\", "/")

        # Check for exact match first
        if normalized_path in self.module_overrides:
            override = self.module_overrides[normalized_path]
            return CoverageThreshold(
                minimum=override.get("minimum", self.minimum),
                branches=override.get("branches", self.branches),
                functions=override.get("functions", self.functions),
                lines=override.get("lines", self.lines),
                module_overrides=self.module_overrides
            )

        # Check for pattern matches (e.g., "autoflow/core/*")
        # Sort patterns by specificity (longer first)
        patterns = sorted(
            self.module_overrides.keys(),
            key=lambda p: len(p),
            reverse=True
        )

        import fnmatch
        for pattern in patterns:
            if fnmatch.fnmatch(normalized_path, pattern):
                override = self.module_overrides[pattern]
                return CoverageThreshold(
                    minimum=override.get("minimum", self.minimum),
                    branches=override.get("branches", self.branches),
                    functions=override.get("functions", self.functions),
                    lines=override.get("lines", self.lines),
                    module_overrides=self.module_overrides
                )

        # No override found, return self
        return self

    def check_passes(
        self,
        total: float,
        branches: Optional[float] = None,
        functions: Optional[float] = None,
        lines: Optional[float] = None,
        module_path: Optional[str] = None
    ) -> bool:
        """
        Check if coverage meets all configured thresholds.

        Args:
            total: Total coverage percentage
            branches: Branch coverage percentage
            functions: Function coverage percentage
            lines: Line coverage percentage
            module_path: Optional module path for per-module thresholds

        Returns:
            True if all thresholds are met
        """
        # Get module-specific threshold if module_path provided
        threshold = self.get_threshold_for_module(module_path) if module_path else self

        if total < threshold.minimum:
            return False

        if threshold.branches is not None and branches is not None:
            if branches < threshold.branches:
                return False

        if threshold.functions is not None and functions is not None:
            if functions < threshold.functions:
                return False

        if threshold.lines is not None and lines is not None:
            if lines < threshold.lines:
                return False

        return True

    def get_failing_metrics(
        self,
        total: float,
        branches: Optional[float] = None,
        functions: Optional[float] = None,
        lines: Optional[float] = None,
        module_path: Optional[str] = None
    ) -> List[str]:
        """
        Get list of metrics that fail thresholds.

        Args:
            total: Total coverage percentage
            branches: Branch coverage percentage
            functions: Function coverage percentage
            lines: Line coverage percentage
            module_path: Optional module path for per-module thresholds

        Returns:
            List of failing metric names
        """
        # Get module-specific threshold if module_path provided
        threshold = self.get_threshold_for_module(module_path) if module_path else self

        failing = []

        if total < threshold.minimum:
            msg = f"total coverage ({total:.1f}% < {threshold.minimum:.1f}%)"
            if module_path:
                msg = f"{module_path}: {msg}"
            failing.append(msg)

        if threshold.branches is not None and branches is not None:
            if branches < threshold.branches:
                msg = f"branch coverage ({branches:.1f}% < {threshold.branches:.1f}%)"
                if module_path:
                    msg = f"{module_path}: {msg}"
                failing.append(msg)

        if threshold.functions is not None and functions is not None:
            if functions < threshold.functions:
                msg = f"function coverage ({functions:.1f}% < {threshold.functions:.1f}%)"
                if module_path:
                    msg = f"{module_path}: {msg}"
                failing.append(msg)

        if threshold.lines is not None and lines is not None:
            if lines < threshold.lines:
                msg = f"line coverage ({lines:.1f}% < {threshold.lines:.1f}%)"
                if module_path:
                    msg = f"{module_path}: {msg}"
                failing.append(msg)

        return failing


@dataclass
class CoverageReport:
    """
    Coverage report data.

    Args:
        total: Total coverage percentage
        branches: Branch coverage percentage
        functions: Function coverage percentage
        lines: Line coverage percentage
        files: Per-file coverage data
        timestamp: Report generation timestamp
    """
    total: float
    branches: Optional[float]
    functions: Optional[float]
    lines: Optional[float]
    files: Dict[str, float] = field(default_factory=dict)
    timestamp: str = field(default_factory="")

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "total": self.total,
            "branches": self.branches,
            "functions": self.functions,
            "lines": self.lines,
            "files": self.files,
            "timestamp": self.timestamp
        }


class CoverageTracker:
    """
    Coverage tracking and analysis using coverage.py.

    Provides functionality to run coverage analysis, parse coverage reports,
    and check coverage against configured thresholds.
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        work_dir: str = "."
    ):
        """
        Initialize coverage tracker.

        Args:
            config_path: Path to QA gates configuration file
            work_dir: Working directory for coverage execution
        """
        self.work_dir = Path(work_dir)
        self.config_path = config_path
        self.threshold = self._load_threshold()

    def _load_threshold(self) -> CoverageThreshold:
        """
        Load coverage threshold from configuration.

        Returns:
            CoverageThreshold with configured values
        """
        if self.config_path:
            config_file = self.work_dir / self.config_path
        else:
            config_file = self.work_dir / "config" / "qa_gates.json"

        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
                    coverage_config = config.get("coverage", {})
                    thresholds = coverage_config.get("thresholds", {})

                    return CoverageThreshold(
                        minimum=thresholds.get("minimum", 80.0),
                        branches=thresholds.get("branches"),
                        functions=thresholds.get("functions"),
                        lines=thresholds.get("lines"),
                        module_overrides=coverage_config.get("module_overrides", {})
                    )
            except (json.JSONDecodeError, IOError):
                pass

        return CoverageThreshold()

    def run_coverage(
        self,
        test_command: str = "python -m unittest discover tests/",
        source_dirs: Optional[List[str]] = None
    ) -> Tuple[int, str]:
        """
        Run coverage analysis.

        Args:
            test_command: Command to run tests
            source_dirs: List of source directories to measure

        Returns:
            Tuple of (exit_code, output)
        """
        if source_dirs is None:
            source_dirs = ["autoflow"]

        # Build coverage command
        cov_args = [
            sys.executable, "-m", "coverage", "run",
            "--source", ",".join(source_dirs),
            "--branch",
        ]

        # Parse test command
        test_parts = test_command.split()
        cov_args.extend(test_parts)

        # Run coverage
        try:
            result = subprocess.run(
                cov_args,
                cwd=self.work_dir,
                capture_output=True,
                text=True
            )
            return result.returncode, result.stdout + result.stderr
        except Exception as e:
            return 1, f"Error running coverage: {e}"

    def generate_report(self) -> CoverageReport:
        """
        Generate coverage report from collected data.

        Returns:
            CoverageReport with coverage metrics

        Raises:
            RuntimeError: If coverage data is not available
        """
        # Get JSON report from coverage
        try:
            result = subprocess.run(
                [sys.executable, "-m", "coverage", "report", "--format=json"],
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                check=True
            )
            data = json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to generate coverage report: {e.stderr}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse coverage JSON: {e}")

        # Extract totals
        totals = data.get("totals", {})
        total_coverage = totals.get("percent_covered", 0.0)

        # Extract metrics (coverage.py doesn't separate branches/functions/lines in totals)
        # We'll use the total for now, but could parse individual files if needed
        branches = None
        functions = None
        lines = None

        # Extract per-file coverage
        files = {}
        for filename, file_data in data.get("files", {}).items():
            # Normalize filename
            normalized_name = filename.replace("\\", "/")
            if normalized_name.startswith("./"):
                normalized_name = normalized_name[2:]
            files[normalized_name] = file_data.get("summary", {}).get("percent_covered", 0.0)

        return CoverageReport(
            total=total_coverage,
            branches=branches,
            functions=functions,
            lines=lines,
            files=files
        )

    def check_thresholds(
        self,
        report: CoverageReport,
        check_per_module: bool = False
    ) -> Tuple[bool, List[str]]:
        """
        Check if coverage report meets configured thresholds.

        Args:
            report: CoverageReport to check
            check_per_module: If True, also check per-module thresholds

        Returns:
            Tuple of (passes, failing_metrics)
        """
        failing = self.threshold.get_failing_metrics(
            total=report.total,
            branches=report.branches,
            functions=report.functions,
            lines=report.lines
        )

        # Check per-module thresholds if enabled
        if check_per_module:
            for module_path, coverage in report.files.items():
                module_threshold = self.threshold.get_threshold_for_module(module_path)
                if not module_threshold.check_passes(coverage):
                    module_failing = module_threshold.get_failing_metrics(coverage, module_path=module_path)
                    failing.append(f"{module_path}: {', '.join(module_failing)}")

        return len(failing) == 0, failing

    def check_module_threshold(
        self,
        module_path: str,
        coverage: float
    ) -> Tuple[bool, List[str]]:
        """
        Check if a specific module meets its coverage threshold.

        Args:
            module_path: Path to module file
            coverage: Coverage percentage for the module

        Returns:
            Tuple of (passes, failing_metrics)
        """
        module_threshold = self.threshold.get_threshold_for_module(module_path)
        failing = module_threshold.get_failing_metrics(coverage, module_path=module_path)

        return len(failing) == 0, failing

    def save_report(
        self,
        report: CoverageReport,
        output_path: str
    ) -> None:
        """
        Save coverage report to file.

        Args:
            report: CoverageReport to save
            output_path: Path to output file
        """
        output_file = self.work_dir / output_path
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(report.to_dict(), f, indent=2)

    def load_report(self, input_path: str) -> CoverageReport:
        """
        Load coverage report from file.

        Args:
            input_path: Path to input file

        Returns:
            CoverageReport with loaded data
        """
        input_file = self.work_dir / input_path

        with open(input_file, "r") as f:
            data = json.load(f)

        return CoverageReport(
            total=data.get("total", 0.0),
            branches=data.get("branches"),
            functions=data.get("functions"),
            lines=data.get("lines"),
            files=data.get("files", {}),
            timestamp=data.get("timestamp", "")
        )

    def get_uncovered_files(
        self,
        report: CoverageReport,
        threshold: float = 0.0
    ) -> List[str]:
        """
        Get list of files below coverage threshold.

        Args:
            report: CoverageReport to analyze
            threshold: Minimum coverage threshold

        Returns:
            List of filenames below threshold
        """
        uncovered = []

        for filename, coverage in report.files.items():
            if coverage < threshold:
                uncovered.append(filename)

        return sorted(uncovered)

    def get_low_coverage_files(
        self,
        report: CoverageReport,
        threshold: float = 80.0
    ) -> List[Tuple[str, float]]:
        """
        Get list of files below coverage threshold with their coverage.

        Args:
            report: CoverageReport to analyze
            threshold: Minimum coverage threshold

        Returns:
            List of (filename, coverage) tuples below threshold
        """
        low_coverage = []

        for filename, coverage in report.files.items():
            if coverage < threshold:
                low_coverage.append((filename, coverage))

        return sorted(low_coverage, key=lambda x: x[1])
