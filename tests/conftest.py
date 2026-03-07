"""
Pytest Configuration for Autoflow Tests

Provides fixtures and configuration for testing the autoflow package.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add the project root to the path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def event_loop_policy():
    """Use default event loop policy for async tests."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()
