"""
Autoflow CLI - Memory Commands

Manage memory files for capturing and retrieving context across runs.

Usage:
    from scripts.cli.memory import add_subparser, write_memory_cmd, show_memory_cmd

    # Register memory commands with argparse
    subparsers = parser.add_subparsers(dest="command")
    add_subparser(subparsers)

    # Use command functions directly
    write_memory_cmd(args)
    show_memory_cmd(args)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# Import utilities from cli.utils
from scripts.cli.utils import (
    ROOT,
    RUNS_DIR,
    MEMORY_DIR,
    STATE_DIR,
    ensure_state,
    now_stamp,
    read_json,
)

# For now, import helper functions from the monolithic autoflow.py
# These will be moved to utils.py in future tasks
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _get_memory_helper_functions():
    """Import memory helper functions from autoflow.py (temporary)."""
    # These functions will be moved to utils.py in future tasks
    import scripts.autoflow as af

    return {
        'resolve_root_path': af.resolve_root_path,
        'load_system_config': af.load_system_config,
        'memory_file': af.memory_file,
        'append_memory': af.append_memory,
    }


def memory_file(scope: str, spec_slug: str | None = None) -> Path:
    """
    Resolve the path to a memory file based on scope and optional spec slug.

    Delegates to the memory_file function in autoflow.py to avoid duplication.

    Args:
        scope: Memory scope, either "global" or "spec"
        spec_slug: Optional spec identifier for spec-scoped memory

    Returns:
        Resolved Path object to the memory file

    Raises:
        SystemExit: If scope is "spec" but no spec_slug is provided
    """
    helpers = _get_memory_helper_functions()
    return helpers['memory_file'](scope, spec_slug)


def append_memory(scope: str, content: str, spec_slug: str | None = None, title: str = "") -> Path:
    """
    Append content to a memory file with a timestamped heading.

    Delegates to the append_memory function in autoflow.py to avoid duplication.

    Args:
        scope: Memory scope, either "global" or "spec"
        content: Content to append to the memory file
        spec_slug: Optional spec identifier for spec-scoped memory
        title: Optional title for the memory entry (defaults to timestamp)

    Returns:
        Path object for the memory file that was appended to
    """
    helpers = _get_memory_helper_functions()
    return helpers['append_memory'](scope, content, spec_slug, title)


def write_memory_cmd(args: argparse.Namespace) -> None:
    """
    Append content to a memory file.

    Creates a timestamped memory entry in either global or spec-scoped memory.
    The entry is written as a markdown section with an optional title. If no
    title is provided, a timestamp is used.

    Args:
        args: Namespace containing:
            - scope: Memory scope ("global" or "spec")
            - spec: Optional spec slug for spec-scoped memory
            - title: Optional title for the memory entry
            - content: Content to append to memory

    Output:
        Prints the path to the updated memory file
    """
    path = append_memory(args.scope, args.content, spec_slug=args.spec, title=args.title)
    print(str(path))


def show_memory_cmd(args: argparse.Namespace) -> None:
    """
    Display stored memory content.

    Retrieves and displays the content of a memory file. The memory file
    is determined by the scope (global or spec) and optional spec slug.

    Args:
        args: Namespace containing:
            - scope: Memory scope ("global" or "spec")
            - spec: Optional spec slug for spec-scoped memory

    Output:
        Prints the memory file contents, or empty string if file doesn't exist
    """
    helpers = _get_memory_helper_functions()
    path = helpers['memory_file'](args.scope, args.spec)
    if not path.exists():
        print("")
        return
    print(path.read_text(encoding="utf-8"))


def capture_memory_cmd(args: argparse.Namespace) -> None:
    """
    Capture memory from a completed run.

    Extracts the summary and metadata from a completed run and writes it
    to the memory scopes configured for that run. If no scopes are specified,
    uses the scopes from the agent's memory_scopes configuration.

    Args:
        args: Namespace containing:
            - run: Run ID to capture memory from
            - scopes: Optional list of scopes to capture to

    Output:
        Prints JSON with run ID, scopes, and list of written file paths
    """
    helpers = _get_memory_helper_functions()
    run_dir = RUNS_DIR / args.run
    metadata_path = run_dir / "run.json"
    if not metadata_path.exists():
        raise SystemExit(f"unknown run: {args.run}")
    metadata = read_json(metadata_path)
    if metadata.get("status") != "completed":
        raise SystemExit("capture-memory requires a completed run")
    summary_path = run_dir / "summary.md"
    summary = summary_path.read_text(encoding="utf-8").strip() if summary_path.exists() else ""
    scopes = args.scopes or metadata.get("agent_config", {}).get("memory_scopes") or ["spec"]
    written = []
    content = "\n".join(
        [
            f"run={metadata.get('id', '')}",
            f"spec={metadata.get('spec', '')}",
            f"task={metadata.get('task', '')}",
            f"role={metadata.get('role', '')}",
            f"result={metadata.get('result', '')}",
            "",
            summary or "No summary recorded.",
        ]
    )
    for scope in scopes:
        written.append(
            str(
                helpers['append_memory'](
                    scope,
                    content,
                    spec_slug=metadata.get("spec", ""),
                    title=f"{metadata.get('task', '')} {metadata.get('role', '')} {metadata.get('result', '')}".strip(),
                )
            )
        )
    print(json.dumps({"run": args.run, "scopes": scopes, "written": written}, indent=2, ensure_ascii=True))


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """
    Add memory commands to the argument parser.

    Creates three subcommands:
    - write-memory: Append content to a memory file
    - show-memory: Display stored memory content
    - capture-memory: Capture memory from a completed run

    Args:
        subparsers: The argparse subparsers object to add commands to
    """
    write_memory = subparsers.add_parser("write-memory", help="append to global or spec memory")
    write_memory.add_argument("--scope", choices=["global", "spec"], required=True)
    write_memory.add_argument("--spec")
    write_memory.add_argument("--title", default="")
    write_memory.add_argument("--content", required=True)
    write_memory.set_defaults(func=write_memory_cmd)

    show_memory = subparsers.add_parser("show-memory", help="show stored memory context")
    show_memory.add_argument("--scope", choices=["global", "spec"], required=True)
    show_memory.add_argument("--spec")
    show_memory.set_defaults(func=show_memory_cmd)

    capture_memory = subparsers.add_parser(
        "capture-memory",
        help="capture memory from a completed run into its configured scopes"
    )
    capture_memory.add_argument("--run", required=True)
    capture_memory.add_argument("--scopes", nargs="+")
    capture_memory.set_defaults(func=capture_memory_cmd)
