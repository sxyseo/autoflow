"""
Autoflow CLI - Utility Functions

Provides helper functions for state management, output formatting,
and async execution used across CLI commands.

Usage:
    from autoflow.cli.utils import (
        _get_state_manager,
        _print_json,
        _run_async,
        _format_datetime
    )

    # Get state manager instance
    state_manager = _get_state_manager(config)

    # Print JSON output
    _print_json({"status": "ok", "data": [...]})

    # Run async coroutine synchronously
    result = _run_async(async_function())

    # Format datetime for display
    formatted = _format_datetime(datetime.now())
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Optional

import click

from autoflow.core.config import Config, get_state_dir
from autoflow.core.state import StateManager


def _get_state_manager(config: Optional[Config] = None) -> StateManager:
    """Get a StateManager instance."""
    state_dir = get_state_dir(config)
    return StateManager(state_dir)


def _print_json(data: Any, indent: int = 2) -> None:
    """Print data as formatted JSON."""
    click.echo(json.dumps(data, indent=indent, default=str))


def _run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # If we're already in an async context, create a new loop
        return asyncio.run(coro)
    else:
        return asyncio.run(coro)


def _format_datetime(dt: Optional[datetime]) -> str:
    """Format a datetime for display."""
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S")
