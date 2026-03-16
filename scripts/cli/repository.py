"""
Autoflow CLI - Repository Commands

Manage repository registration, listing, and validation for multi-repo workflows.

Usage:
    from scripts.cli.repository import add_subparser, repo_add_cmd

    # Register repository commands with argparse
    subparsers = parser.add_subparsers(dest="command")
    add_subparser(subparsers)

    # Use command functions directly
    repo_add_cmd(args)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# Import utilities from cli.utils
from scripts.cli.utils import (
    REPOSITORIES_DIR,
    ensure_state,
    print_json,
    read_json,
    write_json,
)

# Import STATE_DIR for repository manager
from scripts.cli.utils import STATE_DIR


def repository_manager():
    """
    Load RepositoryManager only when repository features are used.

    Creates a RepositoryManager instance with the Autoflow state directory,
    allowing validation and management of registered repositories.

    Returns:
        RepositoryManager: Instance configured with the Autoflow state directory
    """
    from autoflow.core.repository import RepositoryManager

    return RepositoryManager(STATE_DIR)


def repo_add_cmd(args: argparse.Namespace) -> None:
    """
    Add a repository to the registry.

    Creates a new repository configuration file in the repositories directory.
    The repository configuration includes metadata like name, path, URL, description,
    and branch information for multi-repo workflows.

    Args:
        args: Namespace with required attributes:
            - id: Unique repository identifier
            - name: Human-readable repository name
            - path: Filesystem path to the repository
            - url: Optional git remote URL
            - description: Optional repository description
            - branch: Optional default branch name (defaults to "main")

    Raises:
        SystemExit: If a repository with the same ID already exists
    """
    ensure_state()
    repo_id = args.id
    repo_file = REPOSITORIES_DIR / f"{repo_id}.json"

    if repo_file.exists():
        raise SystemExit(f"repository already exists: {repo_id}")

    # Build repository data
    repo_data = {
        "id": repo_id,
        "name": args.name,
        "path": args.path,
        "url": args.url if args.url else None,
        "description": args.description if args.description else None,
        "enabled": True,
        "branch": {
            "default": args.branch if args.branch else "main",
            "current": None,
            "protected": ["main", "master"]
        }
    }

    write_json(repo_file, repo_data)
    print(f"Repository '{repo_id}' added successfully")


def repo_list_cmd(_: argparse.Namespace) -> None:
    """
    List all registered repositories.

    Loads and displays all repository configuration files from the repositories
    directory. The output is formatted as JSON for programmatic consumption.

    Returns:
        JSON array of repository configurations, each containing:
        - id: Repository identifier
        - name: Human-readable name
        - path: Filesystem path
        - url: Git remote URL (optional)
        - description: Repository description (optional)
        - enabled: Whether the repository is active
        - branch: Branch configuration with default, current, and protected branches
    """
    items = []
    for repo_path in sorted(REPOSITORIES_DIR.glob("*.json")):
        repo_data = read_json(repo_path)
        items.append(repo_data)
    print(json.dumps(items, indent=2, ensure_ascii=True))


def repo_validate_cmd(args: argparse.Namespace) -> None:
    """
    Validate repositories and dependencies.

    Performs validation checks on registered repositories and their dependencies.
    Can validate either a single repository (when --repo is specified) or all
    repositories and their cross-repository dependencies.

    For single repository validation:
        - Validates the repository configuration
        - Checks that the repository path exists
        - Validates git repository structure
        - Exits with error code 1 if validation fails

    For all repositories validation:
        - Validates all registered repositories
        - Checks cross-repository dependencies
        - Reports summary of valid/invalid repositories
        - Exits with error code 1 if any validation fails

    Args:
        args: Namespace with optional repo attribute:
            - repo: If specified, validates only that repository.
                   If empty, validates all repositories and dependencies.

    Raises:
        SystemExit: With code 1 if any validation fails, 0 otherwise
    """
    ensure_state()

    # Create repository manager
    manager = repository_manager()

    # Check if validating specific repository or all
    if args.repo:
        # Validate single repository
        errors = manager.validate(args.repo)
        if errors:
            print(f"❌ Repository '{args.repo}' validation failed:")
            for error in errors:
                print(f"  - {error}")
            raise SystemExit(1)
        else:
            print(f"✅ Repository '{args.repo}' is valid")
    else:
        # Validate all repositories and dependencies
        print("Validating repositories...")
        repo_results = manager.validate_all()

        # Count errors
        total_repos = len(repo_results)
        invalid_repos = {repo_id: errs for repo_id, errs in repo_results.items() if errs}
        valid_repos = total_repos - len(invalid_repos)

        # Print repository results
        if invalid_repos:
            print(f"\n❌ Found {len(invalid_repos)} invalid repositories:")
            for repo_id, errors in invalid_repos.items():
                print(f"\n  {repo_id}:")
                for error in errors:
                    print(f"    - {error}")
        else:
            if total_repos > 0:
                print(f"✅ All {total_repos} repositories are valid")
            else:
                print("⚠️  No repositories registered")

        # Validate dependencies
        print("\nValidating dependencies...")
        dep_errors = manager.validate_dependencies()

        if dep_errors:
            print(f"❌ Found {len(dep_errors)} dependency errors:")
            for error in dep_errors:
                print(f"  - {error}")
            raise SystemExit(1)
        else:
            print("✅ All dependencies are valid")

        # Exit with error if any repositories are invalid
        if invalid_repos:
            raise SystemExit(1)


def add_subparser(sub: argparse._SubParsersAction) -> None:
    """
    Register repository command subparsers with the argument parser.

    This function is called during CLI initialization to add all repository-related
    commands to the argument parser.

    Args:
        sub: The subparsers action from the main argument parser

    Example:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_subparser(subparsers)
    """
    repo_add_cmd_parser = sub.add_parser("repo-add", help="register a repository with autoflow")
    repo_add_cmd_parser.add_argument("--id", required=True, help="unique repository identifier")
    repo_add_cmd_parser.add_argument("--name", required=True, help="human-readable repository name")
    repo_add_cmd_parser.add_argument("--path", required=True, help="filesystem path to the repository")
    repo_add_cmd_parser.add_argument("--url", default="", help="git remote URL (optional)")
    repo_add_cmd_parser.add_argument("--description", default="", help="repository description (optional)")
    repo_add_cmd_parser.add_argument("--branch", default="", help="default branch name (default: main)")
    repo_add_cmd_parser.set_defaults(func=repo_add_cmd)

    repo_list_cmd_parser = sub.add_parser("repo-list", help="list all registered repositories")
    repo_list_cmd_parser.set_defaults(func=repo_list_cmd)

    repo_validate_cmd_parser = sub.add_parser("repo-validate", help="validate repositories and dependencies")
    repo_validate_cmd_parser.add_argument("--repo", default="", help="validate specific repository (validates all if not specified)")
    repo_validate_cmd_parser.set_defaults(func=repo_validate_cmd)
