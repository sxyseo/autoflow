"""
File Helpers - JSON and Configuration File Utilities

Provides utilities for loading JSON and configuration files with proper
error handling and default values. Includes type-safe versions that work
with TypedDict types for better static analysis.
"""

import json
from pathlib import Path
from typing import Any, Optional, TypeVar

# Type variable for generic JSON loading
T = TypeVar("T", bound=dict[str, Any])


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


def load_json_typed(path: Path, default: Optional[T] = None) -> T:
    """
    Load a JSON file with type-safe return value for TypedDict types.

    This function provides type hints for static type checkers when working
    with TypedDict types. At runtime, it behaves like load_json but returns
    data cast to the specified type for type checker compatibility.

    Note: This function does not perform runtime type validation. It relies
    on static type checkers (mypy, pyright) to ensure type correctness.

    Args:
        path: Path to the JSON file
        default: Default value to return if file doesn't exist (defaults to empty dict)

    Returns:
        Parsed JSON data cast to type T, or default value if file doesn't exist

    Raises:
        json.JSONDecodeError: If the file exists but contains invalid JSON
        IOError: If the file exists but cannot be read

    Example:
        from autoflow.core.types import TasksFile

        tasks: TasksFile = load_json_typed(Path("tasks.json"))
        # Type checker knows 'tasks' is of type TasksFile
    """
    if not path.exists():
        return default or {}  # type: ignore[return-value]

    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[return-value]


def save_json_typed(path: Path, data: T) -> None:
    """
    Save data to a JSON file with type-safe input for TypedDict types.

    This function accepts TypedDict types and serializes them to JSON.
    It provides type hints for static type checkers while maintaining
    compatibility with the standard JSON encoder.

    Args:
        path: Path to the JSON file to write
        data: Data to serialize (typically a TypedDict instance)

    Raises:
        TypeError: If data contains non-JSON-serializable objects
        IOError: If the file cannot be written

    Example:
        from autoflow.core.types import TasksFile

        tasks: TasksFile = {"tasks": [...]}
        save_json_typed(Path("tasks.json"), tasks)
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


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


__all__ = ["load_json", "load_json_typed", "save_json_typed", "load_config"]
