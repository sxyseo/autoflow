"""Agent performance comparison and effectiveness tracking.

This module provides tools to track, analyze, and compare the performance
of different AI agent backends (Claude Code, Codex, OpenClaw). It measures
effectiveness through success rates, execution times, and resource usage.

The performance system supports:
- Recording agent execution results with metadata
- Calculating success rates and performance metrics
- Comparing agents across multiple dimensions
- Tracking performance trends over time
- Identifying the most effective agent for different task types

Usage:
    from autoflow.analytics.agent_performance import AgentPerformance

    perf = AgentPerformance()
    perf.record_execution(
        agent_name="claude_code",
        status="success",
        duration_seconds=45.2,
        metadata={"task_type": "bug_fix"}
    )

    summary = perf.get_agent_summary("claude_code")
    print(f"Success rate: {summary.success_rate:.1f}%")
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class AgentExecutionStatus(str, Enum):
    """Status of an agent execution.

    Attributes:
        SUCCESS: Execution completed successfully
        FAILURE: Execution failed
        TIMEOUT: Execution timed out
        ERROR: Execution encountered an error
        CANCELLED: Execution was cancelled
    """

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class AgentExecutionRecord:
    """A single agent execution record with performance metrics.

    Attributes:
        agent_name: Name of the agent (e.g., "claude_code", "codex", "openclaw")
        status: Execution status (success, failure, timeout, error, cancelled)
        duration_seconds: Execution time in seconds
        timestamp: When the execution occurred (ISO format string)
        task_type: Optional categorization of the task type
        metadata: Additional context about the execution
        exit_code: Process exit code if available
        error_message: Error message if execution failed
    """

    agent_name: str
    status: AgentExecutionStatus
    duration_seconds: float
    timestamp: str
    task_type: str | None = None
    metadata: dict[str, Any] | None = None
    exit_code: int | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "agent_name": self.agent_name,
            "status": self.status.value,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp,
            "task_type": self.task_type,
            "metadata": self.metadata or {},
            "exit_code": self.exit_code,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentExecutionRecord":
        """Create from dictionary for JSON deserialization."""
        return cls(
            agent_name=data["agent_name"],
            status=AgentExecutionStatus(data["status"]),
            duration_seconds=data["duration_seconds"],
            timestamp=data["timestamp"],
            task_type=data.get("task_type"),
            metadata=data.get("metadata"),
            exit_code=data.get("exit_code"),
            error_message=data.get("error_message"),
        )

    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.status == AgentExecutionStatus.SUCCESS


@dataclass
class AgentPerformanceSummary:
    """Performance summary statistics for an agent.

    Attributes:
        agent_name: Name of the agent
        total_executions: Total number of executions recorded
        successful_executions: Number of successful executions
        failed_executions: Number of failed executions
        success_rate: Percentage of successful executions
        avg_duration_seconds: Average execution time in seconds
        min_duration_seconds: Minimum execution time
        max_duration_seconds: Maximum execution time
        total_duration_seconds: Total time spent in this agent
        last_execution: Timestamp of most recent execution
        first_execution: Timestamp of first execution
        task_type_counts: Count of executions by task type
    """

    agent_name: str
    total_executions: int
    successful_executions: int
    failed_executions: int
    success_rate: float
    avg_duration_seconds: float
    min_duration_seconds: float
    max_duration_seconds: float
    total_duration_seconds: float
    last_execution: str | None = None
    first_execution: str | None = None
    task_type_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "agent_name": self.agent_name,
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "success_rate": self.success_rate,
            "avg_duration_seconds": self.avg_duration_seconds,
            "min_duration_seconds": self.min_duration_seconds,
            "max_duration_seconds": self.max_duration_seconds,
            "total_duration_seconds": self.total_duration_seconds,
            "last_execution": self.last_execution,
            "first_execution": self.first_execution,
            "task_type_counts": self.task_type_counts,
        }


@dataclass
class AgentComparison:
    """Comparison metrics between multiple agents.

    Attributes:
        agents: List of agent names being compared
        best_success_rate: Agent with highest success rate
        fastest_avg: Agent with lowest average duration
        most_used: Agent with most executions
        comparison_data: Detailed comparison metrics by agent
    """

    agents: list[str]
    best_success_rate: str | None = None
    fastest_avg: str | None = None
    most_used: str | None = None
    comparison_data: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "agents": self.agents,
            "best_success_rate": self.best_success_rate,
            "fastest_avg": self.fastest_avg,
            "most_used": self.most_used,
            "comparison_data": self.comparison_data,
        }


class AgentPerformance:
    """Track and compare agent performance metrics.

    This class provides comprehensive performance tracking for AI agent backends.
    It records execution results, calculates statistics, and enables comparison
    between different agents to identify the most effective option.

    Performance data is persisted in .autoflow/agent_performance.json following
    the strategy memory pattern with atomic writes.

    Example:
        perf = AgentPerformance()
        perf.record_execution(
            agent_name="claude_code",
            status=AgentExecutionStatus.SUCCESS,
            duration_seconds=45.2,
            task_type="bug_fix"
        )

        summary = perf.get_agent_summary("claude_code")
        print(f"Success rate: {summary.success_rate:.1f}%")

        comparison = perf.compare_agents(["claude_code", "codex"])
        print(f"Best success rate: {comparison.best_success_rate}")
    """

    DEFAULT_PERFORMANCE_PATH = Path(".autoflow/agent_performance.json")

    def __init__(
        self,
        performance_path: Path | None = None,
        root_dir: Path | None = None,
    ) -> None:
        """Initialize the agent performance tracker.

        Args:
            performance_path: Path to performance JSON file. If None, uses default.
            root_dir: Root directory of the project. Defaults to current directory.
        """
        if root_dir is None:
            root_dir = Path.cwd()

        if performance_path is None:
            performance_path = self.DEFAULT_PERFORMANCE_PATH

        self.performance_path = Path(performance_path)

        # Ensure parent directory exists
        self.performance_path.parent.mkdir(parents=True, exist_ok=True)

        # Execution records by agent name
        self._records: dict[str, list[AgentExecutionRecord]] = defaultdict(list)

        # Load existing records or initialize empty
        self._load_performance()

    def record_execution(
        self,
        agent_name: str,
        status: AgentExecutionStatus | str,
        duration_seconds: float,
        task_type: str | None = None,
        timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        exit_code: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """Record an agent execution with performance metrics.

        Args:
            agent_name: Name of the agent (e.g., "claude_code", "codex")
            status: Execution status (enum or string)
            duration_seconds: Execution time in seconds
            task_type: Optional categorization of the task
            timestamp: When the execution occurred. Defaults to now.
            metadata: Additional context about the execution
            exit_code: Process exit code if available
            error_message: Error message if execution failed

        Raises:
            IOError: If unable to write performance data to disk
        """
        if timestamp is None:
            timestamp = datetime.now(UTC)

        # Convert status string to enum if needed
        if isinstance(status, str):
            status = AgentExecutionStatus(status)

        # Create execution record
        record = AgentExecutionRecord(
            agent_name=agent_name,
            status=status,
            duration_seconds=float(duration_seconds),
            timestamp=timestamp.isoformat(),
            task_type=task_type,
            metadata=metadata,
            exit_code=exit_code,
            error_message=error_message,
        )

        # Add to records
        self._records[agent_name].append(record)

        # Persist to disk
        self._save_performance()

    def get_agent_summary(
        self,
        agent_name: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> AgentPerformanceSummary:
        """Calculate performance summary for an agent.

        Computes success rate, average duration, and other statistics for
        the specified agent over the given time range.

        Args:
            agent_name: Name of the agent to summarize
            start_time: Start of time window. Defaults to first execution.
            end_time: End of time window. Defaults to last execution.

        Returns:
            AgentPerformanceSummary with calculated statistics

        Raises:
            ValueError: If agent not found or no executions recorded
        """
        if agent_name not in self._records:
            raise ValueError(f"Agent not found: {agent_name}")

        # Get records for this agent
        records = self._records[agent_name]

        # Filter by time range
        filtered_records = []
        for record in records:
            record_time = datetime.fromisoformat(
                record.timestamp.replace("Z", "+00:00")
            )
            if start_time and record_time < start_time:
                continue
            if end_time and record_time > end_time:
                continue
            filtered_records.append(record)

        if not filtered_records:
            return AgentPerformanceSummary(
                agent_name=agent_name,
                total_executions=0,
                successful_executions=0,
                failed_executions=0,
                success_rate=0.0,
                avg_duration_seconds=0.0,
                min_duration_seconds=0.0,
                max_duration_seconds=0.0,
                total_duration_seconds=0.0,
            )

        # Calculate statistics
        total = len(filtered_records)
        successful = sum(1 for r in filtered_records if r.success)
        failed = total - successful
        success_rate = (successful / total * 100) if total > 0 else 0.0

        durations = [r.duration_seconds for r in filtered_records]
        total_duration = sum(durations)
        avg_duration = total_duration / total if total > 0 else 0.0
        min_duration = min(durations) if durations else 0.0
        max_duration = max(durations) if durations else 0.0

        # Get time bounds
        sorted_records = sorted(filtered_records, key=lambda r: r.timestamp)
        first_execution = sorted_records[0].timestamp
        last_execution = sorted_records[-1].timestamp

        # Count by task type
        task_type_counts: dict[str, int] = defaultdict(int)
        for record in filtered_records:
            if record.task_type:
                task_type_counts[record.task_type] += 1

        return AgentPerformanceSummary(
            agent_name=agent_name,
            total_executions=total,
            successful_executions=successful,
            failed_executions=failed,
            success_rate=success_rate,
            avg_duration_seconds=avg_duration,
            min_duration_seconds=min_duration,
            max_duration_seconds=max_duration,
            total_duration_seconds=total_duration,
            last_execution=last_execution,
            first_execution=first_execution,
            task_type_counts=dict(task_type_counts),
        )

    def compare_agents(
        self,
        agent_names: list[str] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> AgentComparison:
        """Compare performance across multiple agents.

        Computes comparison metrics and identifies the best performing
        agent across different dimensions.

        Args:
            agent_names: List of agent names to compare. If None, compares all.
            start_time: Start of time window for comparison
            end_time: End of time window for comparison

        Returns:
            AgentComparison with metrics and rankings
        """
        # Determine which agents to compare
        if agent_names is None:
            agent_names = list(self._records.keys())
        else:
            # Filter to only agents that have records
            agent_names = [name for name in agent_names if name in self._records]

        if not agent_names:
            return AgentComparison(
                agents=[],
                comparison_data={},
            )

        # Get summaries for all agents
        summaries = {}
        for agent_name in agent_names:
            try:
                summary = self.get_agent_summary(agent_name, start_time, end_time)
                summaries[agent_name] = summary
            except ValueError:
                # Skip agents with no executions
                continue

        # Find best performers
        best_success_rate = max(
            summaries.keys(),
            key=lambda k: summaries[k].success_rate,
            default=None,
        )
        fastest_avg = min(
            summaries.keys(),
            key=lambda k: summaries[k].avg_duration_seconds,
            default=None,
        )
        most_used = max(
            summaries.keys(),
            key=lambda k: summaries[k].total_executions,
            default=None,
        )

        # Build comparison data
        comparison_data = {}
        for agent_name, summary in summaries.items():
            comparison_data[agent_name] = summary.to_dict()

        return AgentComparison(
            agents=list(summaries.keys()),
            best_success_rate=best_success_rate,
            fastest_avg=fastest_avg,
            most_used=most_used,
            comparison_data=comparison_data,
        )

    def get_agent_names(self) -> list[str]:
        """Get list of all agent names with performance records.

        Returns:
            List of agent names
        """
        return list(self._records.keys())

    def get_execution_count(
        self,
        agent_name: str | None = None,
        status: AgentExecutionStatus | None = None,
    ) -> int:
        """Get count of executions for an agent or all agents.

        Args:
            agent_name: Specific agent to count. If None, counts all agents.
            status: Filter to executions with this status. If None, counts all.

        Returns:
            Number of matching executions
        """
        if agent_name:
            if agent_name not in self._records:
                return 0
            records = self._records[agent_name]
        else:
            records = []
            for agent_records in self._records.values():
                records.extend(agent_records)

        if status:
            records = [r for r in records if r.status == status]

        return len(records)

    def get_recent_executions(
        self,
        agent_name: str | None = None,
        limit: int = 10,
    ) -> list[AgentExecutionRecord]:
        """Get the most recent executions.

        Args:
            agent_name: Specific agent to query. If None, queries all agents.
            limit: Maximum number of executions to return

        Returns:
            List of execution records, most recent first
        """
        all_records: list[AgentExecutionRecord] = []

        if agent_name:
            if agent_name in self._records:
                all_records = list(self._records[agent_name])
        else:
            for records in self._records.values():
                all_records.extend(records)

        # Sort by timestamp (most recent first)
        all_records.sort(key=lambda r: r.timestamp, reverse=True)

        # Apply limit
        return all_records[:limit]

    def clear_agent_records(self, agent_name: str) -> None:
        """Clear all performance records for a specific agent.

        Args:
            agent_name: Name of the agent to clear

        Raises:
            ValueError: If agent not found
            IOError: If unable to write performance data to disk
        """
        if agent_name not in self._records:
            raise ValueError(f"Agent not found: {agent_name}")

        self._records[agent_name].clear()
        self._save_performance()

    def clear_all_records(self) -> None:
        """Clear all performance records.

        Raises:
            IOError: If unable to write performance data to disk
        """
        self._records.clear()
        self._save_performance()

    def _load_performance(self) -> None:
        """Load performance data from disk.

        Reads the performance JSON file and populates the records dictionary.
        Creates an empty performance file if none exists.
        """
        if not self.performance_path.exists():
            # Create empty performance file
            self._save_performance()
            return

        try:
            data = json.loads(self.performance_path.read_text(encoding="utf-8"))
            records_data = data.get("records", {})

            # Convert dictionaries to AgentExecutionRecord objects
            for agent_name, records_list in records_data.items():
                self._records[agent_name] = [
                    AgentExecutionRecord.from_dict(r) for r in records_list
                ]

        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
            # If file is corrupted, start fresh
            self._records = defaultdict(list)

    def _save_performance(self) -> None:
        """Save performance data to disk.

        Writes the records dictionary to the performance JSON file.
        Uses atomic write to prevent data loss.

        Raises:
            IOError: If unable to write to the performance file
        """
        # Convert records to dictionaries
        records_data = {}
        for agent_name, records_list in self._records.items():
            records_data[agent_name] = [r.to_dict() for r in records_list]

        # Build performance structure
        performance_data = {
            "records": records_data,
            "metadata": {
                "total_agents": len(self._records),
                "total_executions": self.get_execution_count(),
                "last_updated": datetime.now(UTC).isoformat(),
            },
        }

        # Write to file with atomic update
        temp_path = self.performance_path.with_suffix(".tmp")
        try:
            temp_path.write_text(
                json.dumps(performance_data, indent=2) + "\n", encoding="utf-8"
            )
            temp_path.replace(self.performance_path)
        except OSError as e:
            # Clean up temp file if write fails
            if temp_path.exists():
                temp_path.unlink()
            raise IOError(
                f"Failed to write performance data to {self.performance_path}: {e}"
            ) from e
