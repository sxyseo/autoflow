"""
File Helpers - JSON and Configuration File Utilities

Provides utilities for loading JSON and configuration files with proper
error handling and default values.
"""

import json
from pathlib import Path
from typing import Any, Optional


def load_json(path: Path, default: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    Load a JSON file, returning a default value if the file doesn't exist.

    Args:
        path: Path to the JSON file
        default: Default value to return if file doesn't exist (defaults to empty dict)

    Returns:
        Parsed JSON data as a dictionary, or default value if file doesn't exist

    Raises:
        json.JSONDecodeError: If the file exists but contains invalid JSON
        IOError: If the file exists but cannot be read
    """
    if not path.exists():
        return default or {}

    return json.loads(path.read_text(encoding="utf-8"))


def load_config(path: str) -> dict[str, Any]:
    """
    Load a configuration file from a path relative to the project root.

    Args:
        path: Path to the configuration file (relative to project root)

    Returns:
        Parsed configuration data as a dictionary

    Raises:
        json.JSONDecodeError: If the file contains invalid JSON
        IOError: If the file cannot be read
        FileNotFoundError: If the file doesn't exist
    """
    from pathlib import Path

    # Determine project root (autoflow package parent)
    # This assumes the utils module is at autoflow/utils/
    current_file = Path(__file__)
    root = current_file.parent.parent.parent

    full_path = root / path
    return json.loads(full_path.read_text(encoding="utf-8"))


__all__ = ["load_json", "load_config"]
