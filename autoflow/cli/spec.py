"""
Autoflow CLI - Specification Commands

List control-plane specifications and their workflow metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from autoflow.cli.utils import (
    _get_review_state_metadata,
    _get_worktree_metadata,
    _print_json,
    _read_json_or_default,
)
from autoflow.core.config import Config, get_state_dir


@click.group()
def spec() -> None:
    """Manage specifications."""
    pass


def _state_dir_from_context(ctx: click.Context) -> Path:
    state_dir = ctx.obj.get("state_dir")
    if state_dir:
        return Path(state_dir).expanduser().resolve()
    config: Config | None = ctx.obj.get("config")
    return get_state_dir(config)


def _iter_spec_metadata_files(state_dir: Path, include_archived: bool) -> list[Path]:
    active_root = state_dir / "specs"
    metadata_files = sorted(active_root.glob("*/metadata.json"))
    if include_archived:
        metadata_files.extend(sorted((active_root / "archive").glob("*/metadata.json")))
    return metadata_files


def _load_spec_entry(metadata_path: Path, config: Config | None) -> dict[str, Any]:
    metadata = _read_json_or_default(metadata_path, {})
    slug = metadata.get("slug", metadata_path.parent.name)
    review_state = _get_review_state_metadata(slug, config)
    return {
        "slug": slug,
        "title": metadata.get("title", ""),
        "summary": metadata.get("summary", ""),
        "status": metadata.get("status", ""),
        "created_at": metadata.get("created_at", ""),
        "updated_at": metadata.get("updated_at", ""),
        "worktree": _get_worktree_metadata(slug, config),
        "review": {
            "approved": review_state.get("approved", False),
            "approved_by": review_state.get("approved_by", ""),
            "review_count": review_state.get("review_count", 0),
        },
    }


@spec.command("list")
@click.option(
    "--archived",
    "-a",
    is_flag=True,
    help="Include archived specifications.",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=20,
    help="Maximum number of specs to show.",
)
@click.pass_context
def spec_list(ctx: click.Context, archived: bool, limit: int) -> None:
    """List specifications with status, worktree, and review metadata."""
    config: Config | None = ctx.obj.get("config")
    state_dir = _state_dir_from_context(ctx)
    specs = []

    for metadata_path in _iter_spec_metadata_files(state_dir, include_archived=archived):
        entry = _load_spec_entry(metadata_path, config)
        specs.append(entry)

    specs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    specs = specs[:limit]

    if ctx.obj.get("output_json"):
        _print_json({"specs": specs, "count": len(specs)})
        return

    click.echo("Specifications")
    click.echo("=" * 60)

    if not specs:
        click.echo("No specifications found.")
        return

    for spec_data in specs:
        click.echo(f"\n[{spec_data.get('slug', 'unknown')}] {spec_data.get('title', 'N/A')}")
        click.echo(f"  Status: {spec_data.get('status', 'N/A')}")
        branch = spec_data.get("worktree", {}).get("branch")
        if branch:
            click.echo(f"  Branch: {branch}")
        review = spec_data.get("review", {})
        review_status = "✓ Approved" if review.get("approved") else "Pending"
        click.echo(f"  Review: {review_status}")
