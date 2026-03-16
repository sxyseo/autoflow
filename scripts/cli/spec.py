"""
Autoflow CLI - Spec Commands

Manage specification documents for AI-driven development.

Usage:
    from scripts.cli.spec import add_subparser, create_spec, show_spec

    # Register spec commands with argparse
    subparsers = parser.add_subparsers(dest="command")
    add_subparser(subparsers)

    # Use command functions directly
    create_spec(args)
    show_spec(args)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# Import utilities from cli.utils
from scripts.cli.utils import (
    ROOT,
    SPECS_DIR,
    ensure_state,
    now_stamp,
    print_json,
    read_json,
    slugify,
    write_json,
    spec_files,
    load_spec_metadata,
    save_spec_metadata,
    normalize_worktree_metadata,
    worktree_branch,
    detect_base_branch,
    load_review_state,
    save_review_state,
    review_state_default,
    review_status_summary,
    record_event,
    task_file,
)


def _get_spec_helper_functions():
    """Import spec helper functions from autoflow.py (lazy import to avoid circular dependency)."""
    # These functions will be moved to utils.py in future subtasks
    import scripts.autoflow as af

    return {
        'replace_markdown_section': af.replace_markdown_section,
        'default_tasks': af.default_tasks,
    }


def replace_markdown_section(markdown: str, heading: str, content: str) -> str:
    """Wrapper for lazy-imported replace_markdown_section function."""
    _helpers = _get_spec_helper_functions()
    return _helpers['replace_markdown_section'](markdown, heading, content)


def default_tasks() -> list:
    """Wrapper for lazy-imported default_tasks function."""
    _helpers = _get_spec_helper_functions()
    return _helpers['default_tasks']()


def create_spec(args: argparse.Namespace) -> None:
    """
    Create a new spec directory with markdown, metadata, and initial task files.

    Creates a spec directory structure containing:
    - spec.md: Main specification document with title, summary, problem, goals, etc.
    - metadata.json: Spec metadata including slug, title, dates, and worktree info
    - handoff.md: Handoff notes for role transitions
    - tasks.json: Initial task list with default tasks
    - review_state.json: Initial review state
    - handoffs/: Directory for role handoff notes

    Args:
        args: Namespace containing spec creation parameters:
            - title: Spec title
            - summary: Brief description of the spec
            - slug: Optional URL-friendly slug (auto-generated from title if not provided)

    Raises:
        SystemExit: If a spec with the same slug already exists

    Side Effects:
        Creates spec directory and all initial files
        Records a spec.created event
    """
    ensure_state()
    slug = slugify(args.slug or args.title)
    files = spec_files(slug)
    if files["spec"].exists():
        raise SystemExit(f"spec already exists: {slug}")
    files["dir"].mkdir(parents=True, exist_ok=True)
    files["handoffs_dir"].mkdir(parents=True, exist_ok=True)
    spec_markdown = f"""# {args.title}

## Summary

{args.summary}

## Problem

Describe the problem this system is solving.

## Goals

- Build a reliable autonomous development harness.
- Keep orchestration separate from model-specific execution.
- Make every run resumable and auditable.

## Non-goals

- Fully unsupervised production deploys in v1.
- Vendor lock-in to a single coding model.

## Constraints

- Use explicit specs and task artifacts.
- Support `codex` and `claude` style CLIs.
- Support background execution with `tmux`.
- Require review before marking coding work complete.
- Prefer isolated git worktrees for implementation runs.

## Acceptance Criteria

- A spec-driven task graph exists.
- Runs can be created from roles and agent mappings.
- Review is a separate step from implementation.
- Git workflow hooks can prepare isolated task branches.
"""
    metadata = {
        "slug": slug,
        "title": args.title,
        "summary": args.summary,
        "created_at": now_stamp(),
        "updated_at": now_stamp(),
        "status": "draft",
        "worktree": {
            "path": "",
            "branch": worktree_branch(slug),
            "base_branch": detect_base_branch(),
        },
    }
    if getattr(args, "repository", None):
        # validate_spec_repository will be imported from utils in subtask-2-2
        import scripts.autoflow as af
        if hasattr(af, 'validate_spec_repository'):
            af.validate_spec_repository(args.repository)
        metadata["repository"] = args.repository
    handoff = "# Handoff\n\nInitial spec created. Next role should refine scope and derive tasks.\n"
    files["spec"].write_text(spec_markdown, encoding="utf-8")
    files["handoff"].write_text(handoff, encoding="utf-8")
    write_json(files["metadata"], metadata)
    save_review_state(slug, review_state_default())
    if not task_file(slug).exists():
        write_json(
            task_file(slug),
            {
                "spec_slug": slug,
                "updated_at": now_stamp(),
                "tasks": default_tasks(),
            },
        )
    record_event(slug, "spec.created", {"title": args.title})
    print(str(files["dir"]))


def show_spec(args: argparse.Namespace) -> None:
    """
    Display complete spec information including metadata, review state, tasks, and markdown.

    Args:
        args: Namespace containing:
            - slug: Spec slug identifier

    Side Effects:
        Prints JSON payload with spec information to stdout
    """
    metadata = normalize_worktree_metadata(args.slug)
    files = spec_files(args.slug)
    payload = {
        "metadata": metadata,
        "review_status": review_status_summary(args.slug),
        "tasks": _load_tasks(args.slug),
        "spec_markdown": files["spec"].read_text(encoding="utf-8"),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def _load_tasks(spec_slug: str) -> dict[str, Any]:
    """Load tasks for a spec (temporary helper function)."""
    import scripts.autoflow as af
    return af.load_tasks(spec_slug)


def update_spec(args: argparse.Namespace) -> None:
    """
    Update spec metadata and/or markdown content.

    Args:
        args: Namespace containing:
            - slug: Spec slug identifier
            - title: Optional new title
            - summary: Optional new summary
            - status: Optional new status
            - append: Optional content to append to spec markdown

    Side Effects:
        Updates spec files and records an update event
    """
    metadata = load_spec_metadata(args.slug)
    files = spec_files(args.slug)
    spec_markdown = files["spec"].read_text(encoding="utf-8")
    changes = []
    if args.title:
        metadata["title"] = args.title
        lines = spec_markdown.splitlines()
        if lines and lines[0].startswith("# "):
            lines[0] = f"# {args.title}"
            spec_markdown = "\n".join(lines).rstrip() + "\n"
        changes.append("title")
    if args.summary:
        metadata["summary"] = args.summary
        spec_markdown = replace_markdown_section(spec_markdown, "Summary", args.summary)
        changes.append("summary")
    if args.status:
        metadata["status"] = args.status
        changes.append("status")
    if args.append:
        spec_markdown = spec_markdown.rstrip() + (
            f"\n\n## Updates\n\n### {now_stamp()}\n\n{args.append.strip()}\n"
        )
        changes.append("append")
    files["spec"].write_text(spec_markdown, encoding="utf-8")
    save_spec_metadata(args.slug, normalize_worktree_metadata(args.slug, metadata))
    import scripts.autoflow as af
    if hasattr(af, 'sync_review_state'):
        af.sync_review_state(args.slug, reason="spec_updated")
    record_event(args.slug, "spec.updated", {"changes": changes or ["touch"]})
    print(
        json.dumps(
            {
                "slug": args.slug,
                "changed_fields": changes,
                "metadata": normalize_worktree_metadata(args.slug),
            },
            indent=2,
            ensure_ascii=True,
        )
    )


def list_specs(_: argparse.Namespace) -> None:
    """
    List all specs with metadata including status, worktree, and review state.

    Args:
        _: Unused namespace argument (required for CLI command interface)

    Side Effects:
        Prints JSON array of spec information to stdout
    """
    items = []
    for metadata_path in SPECS_DIR.glob("*/metadata.json"):
        metadata = normalize_worktree_metadata(metadata_path.parent.name, read_json(metadata_path))
        slug = metadata.get("slug", metadata_path.parent.name)
        review_state = load_review_state(slug)
        items.append(
            {
                "slug": slug,
                "title": metadata.get("title", ""),
                "summary": metadata.get("summary", ""),
                "status": metadata.get("status", ""),
                "created_at": metadata.get("created_at", ""),
                "updated_at": metadata.get("updated_at", ""),
                "worktree": metadata.get("worktree", {}),
                "review": {
                    "approved": review_state.get("approved", False),
                    "approved_by": review_state.get("approved_by", ""),
                    "review_count": review_state.get("review_count", 0),
                },
            }
        )
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    print(json.dumps(items, indent=2, ensure_ascii=True))


def add_subparser(sub: argparse._SubParsersAction) -> None:
    """
    Register spec command subparsers with the argument parser.

    This function is called during CLI initialization to add all spec-related
    commands to the argument parser.

    Args:
        sub: The subparsers action from the main argument parser

    Example:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_subparser(subparsers)
    """
    spec_cmd = sub.add_parser("new-spec", help="create a spec scaffold")
    spec_cmd.add_argument("--slug", default="")
    spec_cmd.add_argument("--title", required=True)
    spec_cmd.add_argument("--summary", required=True)
    spec_cmd.add_argument("--repository", default="", help="repository ID for multi-repo specs")
    spec_cmd.set_defaults(func=create_spec)

    show_spec_cmd = sub.add_parser("show-spec", help="show spec metadata, markdown, review state, and tasks")
    show_spec_cmd.add_argument("--slug", required=True)
    show_spec_cmd.set_defaults(func=show_spec)

    update_spec_cmd = sub.add_parser("update-spec", help="update a spec's metadata or append new context")
    update_spec_cmd.add_argument("--slug", required=True)
    update_spec_cmd.add_argument("--title", default="")
    update_spec_cmd.add_argument("--summary", default="")
    update_spec_cmd.add_argument("--status", default="")
    update_spec_cmd.add_argument("--append", default="")
    update_spec_cmd.set_defaults(func=update_spec)

    list_specs_cmd = sub.add_parser("list-specs", help="list all specs with metadata including status, worktree, and review state")
    list_specs_cmd.set_defaults(func=list_specs)
