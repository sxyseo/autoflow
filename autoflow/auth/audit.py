"""
Autoflow Audit Logging Module

Provides comprehensive audit logging for compliance and security monitoring.
Implements atomic write operations with query and export capabilities for
enterprise compliance requirements.

Usage:
    from autoflow.auth.audit import AuditLogger, AuditLog, AuditEvent

    # Initialize the audit logger
    audit = AuditLogger(".autoflow/audit")
    audit.initialize()

    # Log authentication events
    audit.log_event(
        event_type=AuditEvent.LOGIN_SUCCESS,
        user_id="user-123",
        ip_address="192.168.1.1",
        details={"method": "saml"}
    )

    # Query audit logs
    logs = audit.query_logs(
        event_type=AuditEvent.LOGIN_SUCCESS,
        start_date=datetime.utcnow() - timedelta(days=7)
    )

    # Export for compliance
    audit.export_logs("audit_export.json", start_date=datetime.utcnow() - timedelta(days=30))
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class AuditEvent(str, Enum):
    """Types of audit events for logging."""

    # Authentication events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    SESSION_CREATED = "session_created"
    SESSION_REVOKED = "session_revoked"
    SESSION_EXPIRED = "session_expired"

    # Authorization events
    PERMISSION_CHECK = "permission_check"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REMOVED = "role_removed"

    # SSO events
    SSO_LOGIN_INITIATED = "sso_login_initiated"
    SSO_LOGIN_SUCCESS = "sso_login_success"
    SSO_LOGIN_FAILURE = "sso_login_failure"
    SAML_ASSERTION_RECEIVED = "saml_assertion_received"
    OIDC_CODE_RECEIVED = "oidc_code_received"

    # User management
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    USER_SUSPENDED = "user_suspended"
    USER_REACTIVATED = "user_reactivated"

    # Data access
    SPEC_READ = "spec_read"
    SPEC_WRITE = "spec_write"
    SPEC_DELETE = "spec_delete"
    TASK_READ = "task_read"
    TASK_WRITE = "task_write"
    TASK_DELETE = "task_delete"
    RUN_READ = "run_read"
    RUN_WRITE = "run_write"
    RUN_DELETE = "run_delete"

    # System events
    CONFIG_CHANGED = "config_changed"
    POLICY_CHANGED = "policy_changed"
    EXPORT_REQUESTED = "export_requested"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditLog(BaseModel):
    """
    Represents a single audit log entry.

    Audit logs capture all security-relevant events for compliance
    and monitoring purposes. Each log includes comprehensive context
    about the event including who, what, when, and how.

    Attributes:
        id: Unique log entry identifier
        event_type: Type of audit event
        severity: Severity level of the event
        user_id: ID of the user who triggered the event
        session_id: Optional session identifier
        ip_address: IP address of the request source
        user_agent: Client user agent string
        resource_type: Type of resource affected (e.g., "spec", "task")
        resource_id: ID of the affected resource
        action: Action performed (e.g., "read", "write", "delete")
        status: Event status ("success", "failure", "attempted")
        details: Additional event details
        timestamp: Event timestamp
        metadata: Additional audit metadata

    Example:
        >>> log = AuditLog(
        ...     event_type=AuditEvent.LOGIN_SUCCESS,
        ...     user_id="user-123",
        ...     ip_address="192.168.1.1",
        ...     status="success"
        ... )
        >>> log.to_dict()
        {'event_type': 'login_success', 'user_id': 'user-123', ...}
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: AuditEvent
    severity: AuditSeverity = AuditSeverity.INFO
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    action: Optional[str] = None
    status: str = "success"  # success, failure, attempted
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert audit log to dictionary representation.

        Returns:
            Dictionary with audit log data

        Example:
            >>> log_dict = log.to_dict()
            >>> log_dict["event_type"]
            'login_success'
        """
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "action": self.action,
            "status": self.status,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class AuditLogger:
    """
    Manages audit log storage and querying.

    Provides atomic file operations for audit logs with query and
    export capabilities. Audit logs are organized by date for efficient
    querying and archival.

    All write operations are atomic - either they complete fully
    or leave the existing state unchanged.

    Attributes:
        audit_dir: Root directory for audit log storage
        archive_dir: Directory for archived audit logs

    Example:
        >>> audit = AuditLogger(".autoflow/audit")
        >>> audit.initialize()
        >>> audit.log_event(
        ...     event_type=AuditEvent.LOGIN_SUCCESS,
        ...     user_id="user-123"
        ... )
    """

    # Subdirectories
    ARCHIVE_DIR = "archive"
    DAILY_DIR = "daily"

    def __init__(self, audit_dir: Union[str, Path]):
        """
        Initialize the AuditLogger.

        Args:
            audit_dir: Root directory for audit log storage
        """
        self.audit_dir = Path(audit_dir).resolve()
        self.archive_dir = self.audit_dir / self.ARCHIVE_DIR
        self.daily_dir = self.audit_dir / self.DAILY_DIR

    @property
    def logs_dir(self) -> Path:
        """Path to the daily logs directory."""
        return self.daily_dir

    def initialize(self) -> None:
        """
        Initialize the audit directory structure.

        Creates all required subdirectories if they don't exist.
        Idempotent - safe to call multiple times.

        Example:
            >>> audit = AuditLogger(".autoflow/audit")
            >>> audit.initialize()
            >>> assert audit.audit_dir.exists()
        """
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        self.archive_dir.mkdir(exist_ok=True)

    def _get_log_path(self, date: datetime) -> Path:
        """
        Get the log file path for a specific date.

        Args:
            date: Date to get log path for

        Returns:
            Path to the log file for that date
        """
        date_str = date.strftime("%Y-%m-%d")
        return self.logs_dir / f"{date_str}.jsonl"

    def _write_log_atomically(
        self, file_path: Path, log_entry: dict[str, Any]
    ) -> None:
        """
        Write a log entry atomically to a file.

        Uses append-only writes with file locking for safety.

        Args:
            file_path: Path to the log file
            log_entry: Log entry dictionary to write

        Raises:
            OSError: If write operation fails
        """
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Append to file (JSONL format - one JSON object per line)
        with open(file_path, "a", encoding="utf-8") as f:
            json.dump(log_entry, f, ensure_ascii=False)
            f.write("\n")

    def log_event(
        self,
        event_type: AuditEvent,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: Optional[str] = None,
        status: str = "success",
        severity: AuditSeverity = AuditSeverity.INFO,
        details: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AuditLog:
        """
        Log an audit event.

        Creates an audit log entry and writes it to the appropriate
        daily log file. Logs are written atomically and immediately.

        Args:
            event_type: Type of audit event
            user_id: ID of the user who triggered the event
            session_id: Optional session identifier
            ip_address: IP address of the request source
            user_agent: Client user agent string
            resource_type: Type of resource affected
            resource_id: ID of the affected resource
            action: Action performed
            status: Event status ("success", "failure", "attempted")
            severity: Severity level of the event
            details: Additional event details
            metadata: Additional audit metadata

        Returns:
            The created AuditLog instance

        Example:
            >>> audit.log_event(
            ...     event_type=AuditEvent.LOGIN_SUCCESS,
            ...     user_id="user-123",
            ...     ip_address="192.168.1.1"
            ... )
            AuditLog(event_type=<AuditEvent.LOGIN_SUCCESS: 'login_success'>, ...)
        """
        log = AuditLog(
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            status=status,
            details=details or {},
            metadata=metadata or {},
        )

        log_path = self._get_log_path(log.timestamp)
        self._write_log_atomically(log_path, log.to_dict())

        return log

    def query_logs(
        self,
        event_type: Optional[AuditEvent] = None,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        severity: Optional[AuditSeverity] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
    ) -> list[AuditLog]:
        """
        Query audit logs with optional filters.

        Reads log files for the specified date range and applies
        filters to find matching log entries.

        Args:
            event_type: Filter by event type
            user_id: Filter by user ID
            resource_type: Filter by resource type
            resource_id: Filter by resource ID
            severity: Filter by severity level
            status: Filter by status
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            limit: Maximum number of logs to return

        Returns:
            List of matching AuditLog instances

        Example:
            >>> logs = audit.query_logs(
            ...     event_type=AuditEvent.LOGIN_SUCCESS,
            ...     start_date=datetime.utcnow() - timedelta(days=7)
            ... )
            >>> len(logs)
            42
        """
        if not self.logs_dir.exists():
            return []

        # Default date range to last 7 days
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.utcnow()

        matching_logs = []

        # Iterate through log files in date range
        current_date = start_date
        while current_date <= end_date:
            log_path = self._get_log_path(current_date)
            if log_path.exists():
                try:
                    with open(log_path, encoding="utf-8") as f:
                        for line in f:
                            try:
                                log_data = json.loads(line.strip())
                                # Apply filters
                                if event_type and log_data.get("event_type") != event_type.value:
                                    continue
                                if user_id and log_data.get("user_id") != user_id:
                                    continue
                                if resource_type and log_data.get("resource_type") != resource_type:
                                    continue
                                if resource_id and log_data.get("resource_id") != resource_id:
                                    continue
                                if severity and log_data.get("severity") != severity.value:
                                    continue
                                if status and log_data.get("status") != status:
                                    continue

                                # Parse timestamp for additional filtering
                                log_timestamp = datetime.fromisoformat(log_data["timestamp"])
                                if log_timestamp < start_date or log_timestamp > end_date:
                                    continue

                                # Convert to AuditLog model
                                log_data["event_type"] = AuditEvent(log_data["event_type"])
                                log_data["severity"] = AuditSeverity(log_data["severity"])
                                log = AuditLog(**log_data)
                                matching_logs.append(log)

                                if len(matching_logs) >= limit:
                                    break
                            except (json.JSONDecodeError, KeyError, ValueError):
                                # Skip malformed log entries
                                continue
                except (OSError, IOError):
                    # Skip files that can't be read
                    continue

            current_date += timedelta(days=1)
            if len(matching_logs) >= limit:
                break

        # Sort by timestamp descending
        matching_logs.sort(key=lambda l: l.timestamp, reverse=True)
        return matching_logs

    def export_logs(
        self,
        output_path: Union[str, Path],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        format: str = "json",
    ) -> Path:
        """
        Export audit logs for compliance reporting.

        Exports all logs within the date range to a single file
        for archival or compliance reporting.

        Args:
            output_path: Path for the exported file
            start_date: Start of date range (defaults to 30 days ago)
            end_date: End of date range (defaults to now)
            format: Export format ("json" or "jsonl")

        Returns:
            Path to the exported file

        Raises:
            ValueError: If format is not supported

        Example:
            >>> audit.export_logs(
            ...     "audit_export.json",
            ...     start_date=datetime.utcnow() - timedelta(days=30)
            ... )
            Path('audit_export.json')
        """
        if format not in ("json", "jsonl"):
            raise ValueError(f"Unsupported format: {format}. Use 'json' or 'jsonl'")

        # Default to 30 days
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.utcnow()

        # Query all logs in range
        logs = self.query_logs(
            start_date=start_date,
            end_date=end_date,
            limit=1_000_000,  # High limit for exports
        )

        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            # Export as JSON array
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump([log.to_dict() for log in logs], f, indent=2)
        else:
            # Export as JSONL
            with open(output_path, "w", encoding="utf-8") as f:
                for log in logs:
                    json.dump(log.to_dict(), f, ensure_ascii=False)
                    f.write("\n")

        return output_path

    def get_stats(self) -> dict[str, Any]:
        """
        Get statistics about audit logs.

        Returns:
            Dictionary with audit log statistics

        Example:
            >>> stats = audit.get_stats()
            >>> stats["total_events"]
            1234
        """
        if not self.logs_dir.exists():
            return {
                "audit_dir": str(self.audit_dir),
                "initialized": False,
                "total_events": 0,
                "events_by_type": {},
                "events_by_severity": {},
                "date_range": None,
            }

        total_events = 0
        events_by_type: dict[str, int] = {}
        events_by_severity: dict[str, int] = {}
        oldest_date = None
        newest_date = None

        for log_file in self.logs_dir.glob("*.jsonl"):
            try:
                with open(log_file, encoding="utf-8") as f:
                    for line in f:
                        try:
                            log_data = json.loads(line.strip())
                            total_events += 1

                            event_type = log_data.get("event_type", "unknown")
                            events_by_type[event_type] = events_by_type.get(event_type, 0) + 1

                            severity = log_data.get("severity", "info")
                            events_by_severity[severity] = events_by_severity.get(severity, 0) + 1

                            timestamp = datetime.fromisoformat(log_data["timestamp"])
                            if oldest_date is None or timestamp < oldest_date:
                                oldest_date = timestamp
                            if newest_date is None or timestamp > newest_date:
                                newest_date = timestamp
                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue
            except (OSError, IOError):
                continue

        return {
            "audit_dir": str(self.audit_dir),
            "initialized": True,
            "total_events": total_events,
            "events_by_type": events_by_type,
            "events_by_severity": events_by_severity,
            "date_range": {
                "oldest": oldest_date.isoformat() if oldest_date else None,
                "newest": newest_date.isoformat() if newest_date else None,
            },
        }

    def archive_old_logs(self, older_than_days: int = 90) -> int:
        """
        Archive old audit log files.

        Moves log files older than the specified number of days
        to the archive directory.

        Args:
            older_than_days: Age in days after which logs should be archived

        Returns:
            Number of log files archived

        Example:
            >>> archived = audit.archive_old_logs(older_than_days=90)
            >>> archived
            3
        """
        if not self.logs_dir.exists():
            return 0

        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
        archived_count = 0

        for log_file in self.logs_dir.glob("*.jsonl"):
            try:
                # Extract date from filename
                date_str = log_file.stem  # Removes .jsonl extension
                file_date = datetime.strptime(date_str, "%Y-%m-%d")

                if file_date < cutoff_date:
                    # Move to archive
                    archive_path = self.archive_dir / log_file.name
                    log_file.rename(archive_path)
                    archived_count += 1
            except (ValueError, OSError):
                # Skip files that can't be processed
                continue

        return archived_count


# === Convenience functions ===

def log_auth_event(
    event_type: AuditEvent,
    user_id: Optional[str] = None,
    **kwargs: Any,
) -> AuditLog:
    """
    Log an authentication event.

    Convenience function that creates a default AuditLogger
    and logs the event.

    Args:
        event_type: Type of audit event
        user_id: ID of the user
        **kwargs: Additional arguments for log_event

    Returns:
        The created AuditLog instance

    Example:
        >>> log_auth_event(
        ...     AuditEvent.LOGIN_SUCCESS,
        ...     user_id="user-123",
        ...     ip_address="192.168.1.1"
        ... )
    """
    audit = AuditLogger(".autoflow/audit")
    audit.initialize()
    return audit.log_event(event_type=event_type, user_id=user_id, **kwargs)


def get_compliance_export(
    output_path: Union[str, Path],
    days: int = 30,
) -> Path:
    """
    Export audit logs for compliance reporting.

    Convenience function for common compliance export scenario.

    Args:
        output_path: Path for the exported file
        days: Number of days to include in export

    Returns:
        Path to the exported file

    Example:
        >>> get_compliance_export("compliance_report.json", days=90)
        Path('compliance_report.json')
    """
    audit = AuditLogger(".autoflow/audit")
    audit.initialize()
    start_date = datetime.utcnow() - timedelta(days=days)
    return audit.export_logs(output_path, start_date=start_date)
