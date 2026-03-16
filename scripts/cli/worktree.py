"""
Autoflow CLI - Worktree Commands

Manage git worktrees for isolated spec development.

Usage:
    from scripts.cli.worktree import add_subparser, create_worktree

    # Register worktree commands with argparse
    subparsers = parser.add_subparsers(dest="command")
    add_subparser(subparsers)

    # Use command functions directly
    create_worktree(args)
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

# Import utilities from cli.utils
from scripts.cli.utils import (
    ROOT,
    SPECS_DIR,
    WORKTREES_DIR,
    ensure_state,
    now_stamp,
    print_json,
    read_json,
    run_cmd,
    slugify,
    validate_slug_safe,
    write_json,
)

# For now, import helper functions from the monolithic autoflow.py
# These will be moved to utils.py in subtask-2-2
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _get_worktree_helper_functions():
    """Import worktree helper functions from autoflow.py (temporary)."""
    # These functions will be moved to utils.py in subtask-2-2
    import scripts.autoflow as af

    return {
        'spec_files': af.spec_files,
        'load_spec_metadata': af.load_spec_metadata,
        'save_spec_metadata': af.save_spec_metadata,
        'record_event': af.record_event,
        'repository_manager': af.repository_manager,
    }


# Get helper functions
_helpers = _get_worktree_helper_functions()
spec_files = _helpers['spec_files']
load_spec_metadata = _helpers['load_spec_metadata']
save_spec_metadata = _helpers['save_spec_metadata']
record_event = _helpers['record_event']
repository_manager = _helpers['repository_manager']


def worktree_path(spec_slug: str, repository: str | None = None) -> Path:
    """
    Get the worktree path for a spec.

    Args:
        spec_slug: Spec slug identifier
        repository: Optional repository ID for multi-repo worktrees

    Returns:
        Path to the worktree directory
    """
    if not validate_slug_safe(spec_slug):
        raise SystemExit(f"invalid spec slug: {spec_slug}")
    if repository:
        return WORKTREES_DIR / repository / spec_slug
    return WORKTREES_DIR / spec_slug


def worktree_branch(spec_slug: str) -> str:
    """
    Get the git branch name for a spec's worktree.

    Args:
        spec_slug: Spec slug identifier

    Returns:
        Branch name for the worktree (format: codex/{slugified_spec_slug})
    """
    return f"codex/{slugify(spec_slug)}"


def detect_base_branch() -> str:
    """
    Detect the git repository's base branch.

    Attempts to identify the primary branch by checking for common branch names
    (main, master) in order. Falls back to the current branch if neither is found,
    or defaults to "main" as a last resort.

    Returns:
        Name of the detected base branch ("main", "master", or current branch)
    """
    for branch in ["main", "master"]:
        result = run_cmd(["git", "rev-parse", "--verify", branch], check=False)
        if result.returncode == 0:
            return branch
    current = run_cmd(["git", "branch", "--show-current"]).stdout.strip()
    return current or "main"


def validate_spec_repository(repository_id: str) -> None:
    """
    Validate that a repository reference exists.

    Args:
        repository_id: The repository ID to validate

    Raises:
        SystemExit: If the repository doesn't exist
    """
    if not repository_id:
        return

    repo_manager = repository_manager()
    if not repo_manager.repository_exists(repository_id):
        raise SystemExit(
            f"repository '{repository_id}' not found. "
            f"Use 'repo-add' to register it first, or omit --repository to use the default repository."
        )


def normalize_worktree_metadata(spec_slug: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Normalize worktree metadata to ensure consistent structure.

    Updates the worktree path to use the expected location if it exists,
    otherwise preserves the current path. Ensures branch and base_branch
    fields are populated with defaults if missing.

    Args:
        spec_slug: Spec slug identifier
        metadata: Optional metadata dictionary to normalize (loads from disk if not provided)

    Returns:
        Normalized metadata dictionary with consistent worktree structure
    """
    payload = dict(metadata or load_spec_metadata(spec_slug))
    worktree = dict(payload.get("worktree", {}))
    expected = worktree_path(spec_slug)
    current_path = worktree.get("path", "")
    branch = worktree.get("branch", worktree_branch(spec_slug))
    base_branch = worktree.get("base_branch", detect_base_branch())
    resolved_path = ""
    if expected.exists():
        resolved_path = str(expected)
    elif current_path:
        current = Path(current_path)
        if current.exists():
            resolved_path = str(current)
    payload["worktree"] = {
        "path": resolved_path,
        "branch": branch,
        "base_branch": base_branch,
    }
    return payload


def create_worktree(args: argparse.Namespace) -> None:
    """
    Create a git worktree for isolated spec development.

    Creates a new git worktree linked to a spec-specific branch, allowing
    parallel development without affecting the main branch. The worktree
    is created at `.autoflow/worktrees/tasks/{spec_slug}`.

    If the worktree already exists, updates the spec metadata with the
    worktree information without recreating it.

    The branch name follows the pattern `codex/{slugified_spec}` and is
    created from the base branch if it doesn't already exist.

    Args:
        args: Namespace with attributes:
            - spec: Spec slug identifier
            - base_branch: Base branch to create worktree from (optional,
              defaults to detected base branch)
            - repository: Optional repository ID for multi-repo worktrees
            - force: If True, remove existing worktree before creating

    Side Effects:
        - Creates git worktree directory
        - Creates or checks out spec-specific branch
        - Updates spec metadata with worktree path and branch info
        - Records worktree.created event

    Example:
        >>> args = argparse.Namespace(spec="feature-auth", base_branch="main", force=False, repository=None)
        >>> create_worktree(args)
        {"path": ".autoflow/worktrees/tasks/feature-auth",
         "branch": "codex/feature-auth",
         "base_branch": "main"}
    """
    ensure_state()
    repository = getattr(args, "repository", None)
    if repository:
        validate_spec_repository(repository)
    path = worktree_path(args.spec, repository=repository)
    branch = worktree_branch(args.spec)
    base_branch = args.base_branch or detect_base_branch()
    metadata = load_spec_metadata(args.spec)

    if args.force and path.exists():
        run_cmd(["git", "worktree", "remove", "--force", str(path)], check=False)
        shutil.rmtree(path, ignore_errors=True)

    if path.exists():
        worktree_metadata = {
            "path": str(path),
            "branch": branch,
            "base_branch": base_branch,
        }
        if repository:
            worktree_metadata["repository"] = repository
        metadata["worktree"] = worktree_metadata
        save_spec_metadata(args.spec, metadata)
        print_json(metadata["worktree"])
        return

    branch_exists = run_cmd(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        check=False,
    ).returncode == 0
    if branch_exists:
        run_cmd(["git", "worktree", "add", str(path), branch])
    else:
        run_cmd(["git", "worktree", "add", "-b", branch, str(path), base_branch])

    worktree_metadata = {
        "path": str(path),
        "branch": branch,
        "base_branch": base_branch,
    }
    if repository:
        worktree_metadata["repository"] = repository
    metadata["worktree"] = worktree_metadata
    save_spec_metadata(args.spec, metadata)
    record_event(args.spec, "worktree.created", metadata["worktree"])
    print_json(metadata["worktree"])


def remove_worktree(args: argparse.Namespace) -> None:
    """
    Remove a git worktree for a spec.

    Removes the worktree directory and optionally deletes the associated branch.
    Updates the spec metadata to clear the worktree path.

    Args:
        args: Namespace with attributes:
            - spec: Spec slug identifier
            - repository: Optional repository ID for multi-repo worktrees
            - delete_branch: If True, delete the associated git branch

    Side Effects:
        - Removes git worktree directory if it exists
        - Deletes the associated branch if delete_branch is True
        - Updates spec metadata to clear worktree path
        - Records worktree.removed event
    """
    repository = getattr(args, "repository", None)
    if repository:
        validate_spec_repository(repository)
    path = worktree_path(args.spec, repository=repository)
    branch = worktree_branch(args.spec)
    if path.exists():
        run_cmd(["git", "worktree", "remove", "--force", str(path)])
    if args.delete_branch:
        run_cmd(["git", "branch", "-D", branch], check=False)
    worktree_metadata = {"path": "", "branch": branch, "base_branch": detect_base_branch()}
    if repository:
        worktree_metadata["repository"] = repository
    metadata = load_spec_metadata(args.spec)
    metadata["worktree"] = worktree_metadata
    save_spec_metadata(args.spec, metadata)
    record_event(args.spec, "worktree.removed", {"path": str(path), "branch_deleted": args.delete_branch})
    print_json(metadata["worktree"])


def list_worktrees(_: argparse.Namespace) -> None:
    """
    List all worktrees across all specs.

    Scans all spec metadata files to collect worktree information, including
    the spec slug, worktree path, associated branch, and base branch.

    Args:
        _: Unused namespace argument (required for CLI command interface)

    Output:
        Prints JSON array of worktree information, one entry per spec:
        - spec: Spec slug identifier
        - worktree: Dictionary containing:
            - path: Path to worktree directory (empty if not created)
            - branch: Branch name for the worktree
            - base_branch: Base branch the worktree was created from

    Example:
        >>> list_worktrees(None)
        [
          {
            "spec": "feature-auth",
            "worktree": {
              "path": ".autoflow/worktrees/tasks/feature-auth",
              "branch": "codex/feature-auth",
              "base_branch": "main"
            }
          },
          {
            "spec": "bugfix-login",
            "worktree": {"path": "", "branch": "codex/bugfix-login", "base_branch": "main"}
          }
        ]
    """
    items = []
    for metadata_path in sorted(SPECS_DIR.glob("*/metadata.json")):
        metadata = normalize_worktree_metadata(metadata_path.parent.name, read_json(metadata_path))
        items.append(
            {
                "spec": metadata.get("slug", metadata_path.parent.name),
                "worktree": metadata.get("worktree", {}),
            }
        )
    print_json(items)


def add_subparser(sub: argparse._SubParsersAction) -> None:
    """
    Register worktree command subparsers with the argument parser.

    This function is called during CLI initialization to add all worktree-related
    commands to the argument parser.

    Args:
        sub: The subparsers action from the main argument parser

    Example:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_subparser(subparsers)
    """
    worktree_create_cmd = sub.add_parser("create-worktree", help="create or reuse an isolated git worktree for a spec")
    worktree_create_cmd.add_argument("--spec", required=True)
    worktree_create_cmd.add_argument("--base-branch", default="")
    worktree_create_cmd.add_argument("--repository", default="", help="repository ID for multi-repo worktrees")
    worktree_create_cmd.add_argument("--force", action="store_true")
    worktree_create_cmd.set_defaults(func=create_worktree)

    worktree_remove_cmd = sub.add_parser("remove-worktree", help="remove a spec worktree")
    worktree_remove_cmd.add_argument("--spec", required=True)
    worktree_remove_cmd.add_argument("--delete-branch", action="store_true")
    worktree_remove_cmd.add_argument("--repository", default="", help="repository ID for multi-repo worktrees")
    worktree_remove_cmd.set_defaults(func=remove_worktree)

    worktree_list_cmd = sub.add_parser("list-worktrees", help="show known spec worktrees")
    worktree_list_cmd.set_defaults(func=list_worktrees)
