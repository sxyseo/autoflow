"""
Time Helpers - Timestamp and Datetime Utilities

Provides utilities for generating timestamps and working with UTC time.
"""

from datetime import UTC, datetime


def now_stamp() -> str:
    """
    Generate a UTC timestamp in ISO 8601-like format.

    Returns:
        Timestamp string in format YYYYMMDDTHHMMSSZ

    Example:
        >>> now_stamp()
        '20260310T131530Z'
    """
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


__all__ = ["now_stamp"]
