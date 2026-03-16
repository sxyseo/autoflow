"""
Autoflow Feature Extraction

Extracts features from specs, files, agents, and temporal data for ML-based
quality prediction. Features are structured as dataclasses with to_dict()
methods for easy serialization.

Usage:
    from autoflow.prediction import FeatureExtractor

    extractor = FeatureExtractor()
    features = extractor.extract_spec_features(spec_path)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class WorkflowType(StrEnum):
    """Type of workflow for a spec."""

    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    TEST = "test"
    DOCUMENTATION = "documentation"
    PERFORMANCE = "performance"
    SECURITY = "security"
    OTHER = "other"


@dataclass
class SpecFeatures:
    """
    Features extracted from a spec's implementation plan.

    Attributes:
        spec_id: Unique identifier for the spec
        num_phases: Number of phases in the implementation plan
        num_subtasks: Total number of subtasks across all phases
        complexity_score: Calculated complexity based on phases, subtasks, and dependencies
        num_dependencies: Total number of phase dependencies
        has_test_phase: Whether a test/verification phase exists
        workflow_type: Type of workflow (feature, bugfix, etc.)
        parallel_safe: Whether phases can run in parallel
    """

    spec_id: str
    num_phases: int
    num_subtasks: int
    complexity_score: float
    num_dependencies: int
    has_test_phase: bool
    workflow_type: WorkflowType
    parallel_safe: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for ML model consumption."""
        return {
            "spec_num_phases": self.num_phases,
            "spec_num_subtasks": self.num_subtasks,
            "spec_complexity_score": self.complexity_score,
            "spec_num_dependencies": self.num_dependencies,
            "spec_has_test_phase": 1 if self.has_test_phase else 0,
            "spec_workflow_type_" + str(self.workflow_type): 1,
            "spec_parallel_safe": 1 if self.parallel_safe else 0,
        }


@dataclass
class FileFeatures:
    """
    Features extracted from file change history.

    Attributes:
        files_modified_count: Number of files modified
        file_change_frequency: Average number of changes per file
        test_file_ratio: Ratio of test files to total files
        previous_failures: Number of previous failures in modified files
        file_complexity: Average complexity score of modified files
    """

    files_modified_count: int = 0
    file_change_frequency: float = 0.0
    test_file_ratio: float = 0.0
    previous_failures: int = 0
    file_complexity: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for ML model consumption."""
        return {
            "file_count": self.files_modified_count,
            "file_change_freq": self.file_change_frequency,
            "test_file_ratio": self.test_file_ratio,
            "previous_failures": self.previous_failures,
            "file_complexity": self.file_complexity,
        }


@dataclass
class AgentFeatures:
    """
    Features extracted from agent performance data.

    Attributes:
        agent_model: Model used by the agent
        success_rate: Historical success rate for this agent
        avg_duration: Average duration of tasks completed by this agent
    """

    agent_model: str = ""
    success_rate: float = 0.0
    avg_duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for ML model consumption."""
        return {
            "agent_success_rate": self.success_rate,
            "agent_avg_duration": self.avg_duration,
        }


@dataclass
class TemporalFeatures:
    """
    Features extracted from temporal patterns.

    Attributes:
        hour_of_day: Hour of day (0-23)
        day_of_week: Day of week (0-6, Monday=0)
        time_since_last_change: Seconds since last code change
        concurrent_tasks: Number of concurrent tasks in progress
    """

    hour_of_day: int = 0
    day_of_week: int = 0
    time_since_last_change: float = 0.0
    concurrent_tasks: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for ML model consumption."""
        return {
            "temporal_hour": self.hour_of_day,
            "temporal_day_of_week": self.day_of_week,
            "temporal_time_since_last": self.time_since_last_change,
            "temporal_concurrent_tasks": self.concurrent_tasks,
        }


@dataclass
class FeatureVector:
    """
    Unified feature vector combining all feature types.

    Attributes:
        spec: Spec-based features
        file: File-based features
        agent: Agent-based features
        temporal: Temporal features
    """

    spec: SpecFeatures | None = None
    file: FileFeatures | None = None
    agent: AgentFeatures | None = None
    temporal: TemporalFeatures | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Flatten all features into a single dictionary for ML consumption.

        Returns:
            Dictionary with all features flattened and prefixed by type
        """
        result: dict[str, Any] = {}

        if self.spec:
            result.update(self.spec.to_dict())
        if self.file:
            result.update(self.file.to_dict())
        if self.agent:
            result.update(self.agent.to_dict())
        if self.temporal:
            result.update(self.temporal.to_dict())

        return result


class FeatureExtractor:
    """
    Extract features from specs, files, agents, and temporal data.

    This class provides methods to extract various types of features
    from historical data for ML-based quality prediction.
    """

    def __init__(self, root_dir: Path | None = None) -> None:
        """
        Initialize the feature extractor.

        Args:
            root_dir: Root directory of the project. Defaults to current directory.
        """
        self.root_dir = root_dir or Path.cwd()

    def extract_spec_features(self, spec_path: Path) -> SpecFeatures:
        """
        Extract features from a spec's implementation plan.

        Args:
            spec_path: Path to the spec directory containing implementation_plan.json

        Returns:
            SpecFeatures object with extracted features

        Raises:
            FileNotFoundError: If implementation_plan.json doesn't exist
            ValueError: If implementation_plan.json is malformed
        """
        plan_file = spec_path / "implementation_plan.json"

        if not plan_file.exists():
            raise FileNotFoundError(f"Implementation plan not found: {plan_file}")

        try:
            plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in implementation plan: {e}") from e

        # Extract spec ID from path
        spec_id = spec_path.name

        # Extract phases
        phases = plan_data.get("phases", [])
        num_phases = len(phases)

        # Count subtasks
        num_subtasks = sum(len(phase.get("subtasks", [])) for phase in phases)

        # Count dependencies
        num_dependencies = sum(len(phase.get("depends_on", [])) for phase in phases)

        # Calculate complexity score
        complexity_score = self._calculate_complexity(
            num_phases, num_subtasks, num_dependencies
        )

        # Check for test phase
        has_test_phase = any(
            "test" in phase.get("name", "").lower()
            or "test" in phase.get("type", "").lower()
            or "verification" in phase.get("name", "").lower()
            for phase in phases
        )

        # Extract workflow type
        workflow_type_str = plan_data.get("workflow_type", "other")
        try:
            workflow_type = WorkflowType(workflow_type_str)
        except ValueError:
            workflow_type = WorkflowType.OTHER

        # Check if phases are parallel safe
        parallel_safe = all(phase.get("parallel_safe", False) for phase in phases)

        return SpecFeatures(
            spec_id=spec_id,
            num_phases=num_phases,
            num_subtasks=num_subtasks,
            complexity_score=complexity_score,
            num_dependencies=num_dependencies,
            has_test_phase=has_test_phase,
            workflow_type=workflow_type,
            parallel_safe=parallel_safe,
        )

    def _calculate_complexity(
        self, num_phases: int, num_subtasks: int, num_dependencies: int
    ) -> float:
        """
        Calculate a complexity score based on spec characteristics.

        Args:
            num_phases: Number of phases
            num_subtasks: Total number of subtasks
            num_dependencies: Number of dependencies

        Returns:
            Complexity score (higher is more complex)
        """
        # Weighted complexity formula
        phase_weight = 2.0
        subtask_weight = 1.0
        dependency_weight = 1.5

        base_score = (
            num_phases * phase_weight
            + num_subtasks * subtask_weight
            + num_dependencies * dependency_weight
        )

        # Normalize to reasonable range (0-100 approximately)
        return min(base_score, 100.0)

    def extract_file_features(
        self, file_timelines_dir: Path | None = None
    ) -> FileFeatures:
        """
        Extract features from file change history.

        Args:
            file_timelines_dir: Path to directory containing file timeline JSON files.
                              Defaults to .auto-claude/file-timelines/

        Returns:
            FileFeatures object with extracted features

        Raises:
            FileNotFoundError: If file_timelines_dir doesn't exist
        """
        if file_timelines_dir is None:
            file_timelines_dir = self.root_dir / ".auto-claude" / "file-timelines"

        if not file_timelines_dir.exists():
            raise FileNotFoundError(
                f"File timelines directory not found: {file_timelines_dir}"
            )

        # Read all timeline JSON files
        timeline_files = list(file_timelines_dir.glob("*.json"))

        if not timeline_files:
            return FileFeatures()

        # Aggregate data from all timelines
        all_files: set[str] = set()
        total_changes = 0
        test_files: set[str] = set()
        failed_files: set[str] = set()
        file_complexities: list[int] = []

        for timeline_file in timeline_files:
            try:
                timeline_data = json.loads(timeline_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            # Extract file information from timeline
            # Timeline structure: {task_id: {files: [{path, changes, status, ...}]}}
            for task_data in timeline_data.values():
                if not isinstance(task_data, dict):
                    continue

                files = task_data.get("files", [])
                if not isinstance(files, list):
                    continue

                for file_info in files:
                    if not isinstance(file_info, dict):
                        continue

                    file_path = file_info.get("path", "")
                    if not file_path:
                        continue

                    all_files.add(file_path)

                    # Count changes
                    changes = file_info.get("changes", 0)
                    if isinstance(changes, int):
                        total_changes += changes

                    # Check if test file
                    if "test" in file_path.lower():
                        test_files.add(file_path)

                    # Check for previous failures
                    status = file_info.get("status", "")
                    if status and "fail" in status.lower():
                        failed_files.add(file_path)

                    # Calculate file complexity (based on lines or function count)
                    complexity = file_info.get("complexity", 0)
                    if not complexity:
                        # Estimate complexity from changes if not provided
                        complexity = min(changes or 1, 50)
                    if isinstance(complexity, (int, float)):
                        file_complexities.append(int(complexity))

        # Calculate features
        files_modified_count = len(all_files)

        file_change_frequency = (
            total_changes / files_modified_count if files_modified_count > 0 else 0.0
        )

        test_file_ratio = (
            len(test_files) / files_modified_count if files_modified_count > 0 else 0.0
        )

        previous_failures = len(failed_files)

        file_complexity = (
            sum(file_complexities) / len(file_complexities)
            if file_complexities
            else 0.0
        )

        return FileFeatures(
            files_modified_count=files_modified_count,
            file_change_frequency=file_change_frequency,
            test_file_ratio=test_file_ratio,
            previous_failures=previous_failures,
            file_complexity=file_complexity,
        )

    def extract_agent_features(self, runs_dir: Path | None = None) -> AgentFeatures:
        """
        Extract features from agent performance data.

        Args:
            runs_dir: Path to directory containing run JSON files.
                     Defaults to .autoflow/runs/

        Returns:
            AgentFeatures object with extracted features

        Raises:
            FileNotFoundError: If runs_dir doesn't exist
        """
        if runs_dir is None:
            runs_dir = self.root_dir / ".autoflow" / "runs"

        if not runs_dir.exists():
            raise FileNotFoundError(f"Runs directory not found: {runs_dir}")

        # Find all run.json files
        run_files = list(runs_dir.glob("*/run.json"))

        if not run_files:
            return AgentFeatures()

        # Aggregate agent data
        agent_stats: dict[str, dict[str, Any]] = {}

        for run_file in run_files:
            try:
                run_data = json.loads(run_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            # Extract agent information
            agent_model = run_data.get("agent_model", "unknown")
            status = run_data.get("status", "")
            duration = run_data.get("duration", 0)

            # Initialize agent stats if not exists
            if agent_model not in agent_stats:
                agent_stats[agent_model] = {
                    "total_tasks": 0,
                    "successful_tasks": 0,
                    "total_duration": 0.0,
                }

            # Update stats
            agent_stats[agent_model]["total_tasks"] += 1

            if status and "success" in status.lower():
                agent_stats[agent_model]["successful_tasks"] += 1

            if isinstance(duration, (int, float)):
                agent_stats[agent_model]["total_duration"] += duration

        # Calculate features for the most common agent
        if not agent_stats:
            return AgentFeatures()

        # Get the agent with the most tasks
        most_common_agent = max(
            agent_stats.keys(), key=lambda k: agent_stats[k]["total_tasks"]
        )

        stats = agent_stats[most_common_agent]
        success_rate = (
            stats["successful_tasks"] / stats["total_tasks"]
            if stats["total_tasks"] > 0
            else 0.0
        )
        avg_duration = (
            stats["total_duration"] / stats["total_tasks"]
            if stats["total_tasks"] > 0
            else 0.0
        )

        return AgentFeatures(
            agent_model=most_common_agent,
            success_rate=success_rate,
            avg_duration=avg_duration,
        )

    def extract_temporal_features(
        self,
    ) -> TemporalFeatures:
        """
        Extract features from temporal patterns.

        Returns:
            TemporalFeatures object with extracted features
        """
        now = datetime.now(UTC)

        # Current time features
        hour_of_day = now.hour
        day_of_week = now.weekday()  # Monday=0, Sunday=6

        # Time since last change (from file timelines)
        file_timelines_dir = self.root_dir / ".auto-claude" / "file-timelines"
        time_since_last_change = 0.0

        if file_timelines_dir.exists():
            timeline_files = list(file_timelines_dir.glob("*.json"))
            latest_timestamp = 0.0

            for timeline_file in timeline_files:
                try:
                    timeline_data = json.loads(
                        timeline_file.read_text(encoding="utf-8")
                    )

                    # Extract timestamps from timeline data
                    for task_data in timeline_data.values():
                        if isinstance(task_data, dict):
                            timestamp = task_data.get("timestamp", 0)
                            if isinstance(timestamp, (int, float)):
                                latest_timestamp = max(latest_timestamp, timestamp)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

            if latest_timestamp > 0:
                time_since_last_change = now.timestamp() - latest_timestamp

        # Count concurrent tasks (active specs with in-progress subtasks)
        specs_dir = self.root_dir / ".auto-claude" / "specs"
        concurrent_tasks = 0

        if specs_dir.exists():
            for spec_dir in specs_dir.iterdir():
                if not spec_dir.is_dir():
                    continue

                plan_file = spec_dir / "implementation_plan.json"
                if not plan_file.exists():
                    continue

                try:
                    plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
                    phases = plan_data.get("phases", [])

                    # Count in-progress subtasks
                    for phase in phases:
                        for subtask in phase.get("subtasks", []):
                            if subtask.get("status") == "in_progress":
                                concurrent_tasks += 1
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

        return TemporalFeatures(
            hour_of_day=hour_of_day,
            day_of_week=day_of_week,
            time_since_last_change=time_since_last_change,
            concurrent_tasks=concurrent_tasks,
        )
