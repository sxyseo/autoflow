"""
Autoflow CLI - Run Context Command

View context for a specific run.

Usage:
    autoflow run-context <run_id> <spec_id>
    autoflow run-context <run_id> <spec_id> --max-items 10
    autoflow run-context <run_id> <spec_id> --min-score 0.5
"""

from __future__ import annotations

from pathlib import Path

import click

from autoflow.cli.utils import _print_json
from autoflow.core.config import Config
from autoflow.memory import MemoryManager


@click.command()
@click.argument("run_id", type=str)
@click.argument("spec_id", type=str)
@click.option(
    "--max-items",
    "-m",
    type=int,
    default=5,
    help="Maximum number of context items to return.",
)
@click.option(
    "--min-score",
    "-s",
    type=float,
    default=0.3,
    help="Minimum relevance score threshold (0.0 to 1.0).",
)
@click.option(
    "--include-spec",
    is_flag=True,
    default=True,
    help="Include spec-scoped memories.",
)
@click.option(
    "--include-global",
    is_flag=True,
    default=True,
    help="Include global/project-scoped memories.",
)
@click.option(
    "--consolidation-path",
    "-c",
    type=click.Path(exists=False, path_type=Path),
    default=None,
    help="Path to consolidation JSON file.",
)
@click.pass_context
def run_context(
    ctx: click.Context,
    run_id: str,
    spec_id: str,
    max_items: int,
    min_score: float,
    include_spec: bool,
    include_global: bool,
    consolidation_path: Path | None,
) -> None:
    """
    View context for a specific run.

    Retrieves and displays relevant context memories for the given run ID and spec ID.
    Context is aggregated from spec-scoped and global/project-scoped memories based
    on relevance to the task.

    \b
    Examples:
        autoflow run-context run-001 spec-001
        autoflow run-context run-001 spec-001 --max-items 10
        autoflow run-context run-001 spec-001 --min-score 0.5
    """
    config: Config | None = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    if max_items < 0:
        click.echo("Error: --max-items must be >= 0", err=True)
        ctx.exit(1)

    if not 0.0 <= min_score <= 1.0:
        click.echo("Error: --min-score must be between 0.0 and 1.0", err=True)
        ctx.exit(1)

    try:
        # Initialize memory manager
        manager = MemoryManager(
            consolidation_path=consolidation_path,
            root_dir=Path.cwd(),
        )

        # Get context for run
        context_items = manager.get_context_for_run(
            task_id=run_id,
            spec_id=spec_id,
            max_items=max_items,
            relevance_threshold=min_score,
            include_spec=include_spec,
            include_global=include_global,
        )

        if ctx.obj.get("output_json"):
            _print_json({
                "run_id": run_id,
                "spec_id": spec_id,
                "context_items": context_items,
                "count": len(context_items),
            })
            return

        # Display formatted output
        click.echo(f"Context for Run: {run_id}")
        click.echo(f"Spec: {spec_id}")
        click.echo("=" * 60)

        if not context_items:
            click.echo("No context items found.")
            click.echo("")
            click.echo("Tip: Context is built from memories extracted during previous runs.")
            click.echo("     Use 'autoflow memory list' to see available memories.")
            return

        for idx, item in enumerate(context_items, 1):
            click.echo(f"\n[{idx}] Score: {item['score']:.2f} | Scope: {item['scope']} | Type: {item['type']}")
            if item['tags']:
                click.echo(f"    Tags: {', '.join(item['tags'])}")
            click.echo(f"    Content: {item['content']}")
            click.echo("-" * 60)

        click.echo(f"\nTotal: {len(context_items)} context items")

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("", err=True)
        click.echo("The consolidation file may not exist yet. Context is built from", err=True)
        click.echo("memories extracted during previous runs.", err=True)
        ctx.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Error retrieving context: {e}", err=True)
        ctx.exit(1)
