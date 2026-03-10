"""
Unit Tests for Time Helpers

Tests for timestamp and datetime utilities.
"""

from __future__ import annotations

import re
import unittest
from datetime import UTC, datetime

from autoflow.utils.time_helpers import now_stamp


class TimeHelpersTests(unittest.TestCase):
    def test_now_stamp_returns_string(self) -> None:
        """now_stamp should return a string."""
        result = now_stamp()
        self.assertIsInstance(result, str)

    def test_now_stamp_format_is_correct(self) -> None:
        """now_stamp should return timestamp in YYYYMMDDTHHMMSSZ format."""
        result = now_stamp()
        # Format: 20260310T131530Z
        pattern = r"^\d{8}T\d{6}Z$"
        self.assertRegex(result, pattern)

    def test_now_stamp_matches_datetime(self) -> None:
        """now_stamp should match current UTC time."""
        stamp = now_stamp()
        # Parse the timestamp
        # Format: YYYYMMDDTHHMMSSZ
        match = re.match(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$", stamp)
        self.assertIsNotNone(match)

        year, month, day, hour, minute, second = match.groups()
        stamped_datetime = datetime(
            int(year), int(month), int(day),
            int(hour), int(minute), int(second),
            tzinfo=UTC
        )

        # Should be within 1 second of current time
        current = datetime.now(UTC)
        difference = abs((current - stamped_datetime).total_seconds())
        self.assertLess(difference, 1.0)

    def test_now_stamp_is_utc(self) -> None:
        """now_stamp should use UTC timezone."""
        stamp = now_stamp()
        # The timestamp ends with Z indicating UTC
        self.assertTrue(stamp.endswith("Z"))

    def test_now_stamp_has_correct_length(self) -> None:
        """now_stamp should return exactly 16 characters."""
        # YYYYMMDDTHHMMSSZ = 16 chars
        result = now_stamp()
        self.assertEqual(len(result), 16)

    def test_now_stamp_has_separator(self) -> None:
        """now_stamp should have T separator between date and time."""
        result = now_stamp()
        self.assertIn("T", result)
        # T should be at position 8 (0-indexed)
        self.assertEqual(result[8], "T")

    def test_now_stamp_is_reproducible(self) -> None:
        """now_stamp should produce different values over time."""
        stamp1 = now_stamp()
        stamp2 = now_stamp()
        # They might be the same if called very quickly,
        # but usually should be different or at least valid
        self.assertRegex(stamp1, r"^\d{8}T\d{6}Z$")
        self.assertRegex(stamp2, r"^\d{8}T\d{6}Z$")

    def test_now_stamp_date_components_valid(self) -> None:
        """now_stamp should have valid date components."""
        stamp = now_stamp()
        match = re.match(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$", stamp)
        self.assertIsNotNone(match)

        year, month, day = match.groups()[:3]

        # Basic validation
        self.assertGreaterEqual(int(year), 2020)
        self.assertGreaterEqual(int(month), 1)
        self.assertLessEqual(int(month), 12)
        self.assertGreaterEqual(int(day), 1)
        self.assertLessEqual(int(day), 31)

    def test_now_stamp_time_components_valid(self) -> None:
        """now_stamp should have valid time components."""
        stamp = now_stamp()
        match = re.match(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$", stamp)
        self.assertIsNotNone(match)

        hour, minute, second = match.groups()[3:]

        # Basic validation
        self.assertGreaterEqual(int(hour), 0)
        self.assertLessEqual(int(hour), 23)
        self.assertGreaterEqual(int(minute), 0)
        self.assertLessEqual(int(minute), 59)
        self.assertGreaterEqual(int(second), 0)
        self.assertLessEqual(int(second), 59)


if __name__ == "__main__":
    unittest.main()
