"""
Autoflow CLI - Duplication Detection Commands

Detect and report code duplication using AI-powered analysis.

Usage:
    autoflow duplication scan
    autoflow duplication scan --path ./src --threshold 0.8
    autoflow duplication report --format json
"""

from __future__ import annotations

import click

from autoflow.cli.utils import _print_json


@click.group()
def duplication() -> None:
    """Code duplication detection commands."""
    pass


@duplication.command("scan")
@click.option(
    "--path",
    "-p",
    type=click.Path(exists=True, path_type=click.Path),
    default=None,
    help="Path to scan for duplications (default: current directory).",
)
@click.option(
    "--threshold",
    "-t",
    type=click.FloatRange(0.0, 1.0),
    default=0.8,
    help="Similarity threshold for reporting duplications (0.0-1.0).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=click.Path),
    default=None,
    help="Output file for the scan report.",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json", "markdown"]),
    default="text",
    help="Output format for the report.",
)
@click.pass_context
def duplication_scan(
    ctx: click.Context,
    path: click.Path | None,
    threshold: float,
    output: click.Path | None,
    output_format: str,
) -> None:
    """
    Scan code for duplications.

    Uses AI-powered semantic analysis to detect code duplication
    beyond simple text matching.

    \b
    Examples:
        autoflow duplication scan
        autoflow duplication scan --path ./src --threshold 0.9
        autoflow duplication scan --output report.json --format json
    """
    output_json = ctx.obj.get("output_json", False) if ctx.obj else False
    if output_json:
        _print_json({
            "status": "placeholder",
            "path": str(path) if path else ".",
            "threshold": threshold,
            "output": str(output) if output else None,
            "format": output_format,
            "message": "Duplication scanning requires async execution. This is a placeholder.",
        })
    else:
        click.echo("Code Duplication Scan")
        click.echo("=" * 60)
        click.echo(f"Path: {path if path else '.'}")
        click.echo(f"Threshold: {threshold}")
        click.echo(f"Format: {output_format}")
        if output:
            click.echo(f"Output: {output}")
        click.echo("")
        click.echo("Note: This is a CLI placeholder. Full duplication scanning")
        click.echo("      requires async runtime and AI model integration.")


@duplication.command("report")
@click.option(
    "--file",
    "-f",
    type=click.Path(exists=True, path_type=click.Path),
    default=None,
    help="Report file to display (default: latest scan).",
)
@click.option(
    "--format",
    "-o",
    "output_format",
    type=click.Choice(["text", "json", "markdown"]),
    default="text",
    help="Output format for the report.",
)
@click.pass_context
def duplication_report(
    ctx: click.Context,
    file: click.Path | None,
    output_format: str,
) -> None:
    """
    Display a duplication report.

    Shows the results of a previous duplication scan.

    \b
    Examples:
        autoflow duplication report
        autoflow duplication report --file scan_results.json --format json
    """
    output_json = ctx.obj.get("output_json", False) if ctx.obj else False
    if output_json:
        _print_json({
            "status": "placeholder",
            "file": str(file) if file else "latest",
            "format": output_format,
            "message": "Report display requires async execution. This is a placeholder.",
        })
    else:
        click.echo("Duplication Report")
        click.echo("=" * 60)
        click.echo(f"File: {file if file else 'latest scan'}")
        click.echo(f"Format: {output_format}")
        click.echo("")
        click.echo("Note: This is a CLI placeholder. Full report display")
        click.echo("      requires async runtime and persistence integration.")


@duplication.command("analyze")
@click.option(
    "--path",
    "-p",
    type=click.Path(exists=True, path_type=click.Path),
    default=None,
    help="Path to analyze for duplications (default: current directory).",
)
@click.option(
    "--threshold",
    "-t",
    type=click.FloatRange(0.0, 1.0),
    default=0.8,
    help="Similarity threshold for reporting duplications (0.0-1.0).",
)
@click.option(
    "--detailed/--summary",
    default=False,
    help="Show detailed analysis vs summary view.",
)
@click.pass_context
def duplication_analyze(
    ctx: click.Context,
    path: click.Path | None,
    threshold: float,
    detailed: bool,
) -> None:
    """
    Analyze code for duplications and display results.

    Performs a one-shot duplication analysis without creating a report file.

    \b
    Examples:
        autoflow duplication analyze
        autoflow duplication analyze --path ./src --threshold 0.9
        autoflow duplication analyze --detailed
    """
    output_json = ctx.obj.get("output_json", False) if ctx.obj else False
    if output_json:
        _print_json({
            "status": "placeholder",
            "path": str(path) if path else ".",
            "threshold": threshold,
            "detailed": detailed,
            "message": "Duplication analysis requires async execution. This is a placeholder.",
        })
    else:
        click.echo("Code Duplication Analysis")
        click.echo("=" * 60)
        click.echo(f"Path: {path if path else '.'}")
        click.echo(f"Threshold: {threshold}")
        click.echo(f"Mode: {'Detailed' if detailed else 'Summary'}")
        click.echo("")
        click.echo("Note: This is a CLI placeholder. Full duplication analysis")
        click.echo("      requires async runtime and AI model integration.")


@duplication.group()
def config() -> None:
    """Manage duplication detection configuration."""
    pass


@config.command("show")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format for the configuration.",
)
@click.pass_context
def config_show(ctx: click.Context, output_format: str) -> None:
    """
    Show current duplication detection configuration.

    Displays the current threshold settings and file-specific overrides.

    \b
    Examples:
        autoflow duplication config show
        autoflow duplication config show --format json
    """
    # Import here to avoid circular dependency
    try:
        from autoflow.analysis.duplication_detector import DuplicationThreshold
    except ImportError:
        click.echo("Error: Duplication detector module not available.", err=True)
        ctx.exit(1)

    # Get current threshold configuration
    threshold = DuplicationThreshold()

    output_json = ctx.obj.get("output_json", False) if ctx.obj else False
    if output_json or output_format == "json":
        _print_json({
            "minimum_similarity": threshold.minimum_similarity,
            "minimum_lines": threshold.minimum_lines,
            "token_similarity_weight": threshold.token_similarity_weight,
            "structure_similarity_weight": threshold.structure_similarity_weight,
            "file_overrides": threshold.file_overrides,
        })
    else:
        click.echo("Duplication Detection Configuration")
        click.echo("=" * 60)
        click.echo(f"Minimum Similarity: {threshold.minimum_similarity:.2f}")
        click.echo(f"Minimum Lines: {threshold.minimum_lines}")
        click.echo(f"Token Similarity Weight: {threshold.token_similarity_weight:.2f}")
        click.echo(f"Structure Similarity Weight: {threshold.structure_similarity_weight:.2f}")
        if threshold.file_overrides:
            click.echo("")
            click.echo("File-Specific Overrides:")
            for pattern, override in threshold.file_overrides.items():
                click.echo(f"  {pattern}:")
                for key, value in override.items():
                    click.echo(f"    {key}: {value}")
        else:
            click.echo("")
            click.echo("File-Specific Overrides: None")


@config.command("set")
@click.option(
    "--similarity",
    "-s",
    "minimum_similarity",
    type=click.FloatRange(0.0, 1.0),
    default=None,
    help="Minimum similarity threshold (0.0-1.0).",
)
@click.option(
    "--min-lines",
    "-m",
    "minimum_lines",
    type=click.IntRange(1, 1000),
    default=None,
    help="Minimum number of lines to consider for duplication.",
)
@click.option(
    "--token-weight",
    "-t",
    "token_weight",
    type=click.FloatRange(0.0, 1.0),
    default=None,
    help="Weight for token-based similarity (0.0-1.0).",
)
@click.option(
    "--structure-weight",
    "-w",
    "structure_weight",
    type=click.FloatRange(0.0, 1.0),
    default=None,
    help="Weight for structure-based similarity (0.0-1.0).",
)
@click.pass_context
def config_set(
    ctx: click.Context,
    minimum_similarity: float | None,
    minimum_lines: int | None,
    token_weight: float | None,
    structure_weight: float | None,
) -> None:
    """
    Set duplication detection thresholds.

    Updates the global threshold configuration. Changes are applied to
    all files unless file-specific overrides are defined.

    \b
    Examples:
        autoflow duplication config set --similarity 0.9
        autoflow duplication config set --min-lines 10 --token-weight 0.7
        autoflow duplication config set --structure-weight 0.8
    """
    # Import here to avoid circular dependency
    try:
        from autoflow.analysis.duplication_detector import DuplicationThreshold
    except ImportError:
        click.echo("Error: Duplication detector module not available.", err=True)
        ctx.exit(1)

    # Get current threshold
    current = DuplicationThreshold()

    # Create new threshold with updated values
    updated = DuplicationThreshold(
        minimum_similarity=minimum_similarity if minimum_similarity is not None else current.minimum_similarity,
        minimum_lines=minimum_lines if minimum_lines is not None else current.minimum_lines,
        token_similarity_weight=token_weight if token_weight is not None else current.token_similarity_weight,
        structure_similarity_weight=structure_weight if structure_weight is not None else current.structure_similarity_weight,
        file_overrides=current.file_overrides,
    )

    output_json = ctx.obj.get("output_json", False) if ctx.obj else False
    if output_json:
        _print_json({
            "status": "updated",
            "previous": {
                "minimum_similarity": current.minimum_similarity,
                "minimum_lines": current.minimum_lines,
                "token_similarity_weight": current.token_similarity_weight,
                "structure_similarity_weight": current.structure_similarity_weight,
            },
            "updated": {
                "minimum_similarity": updated.minimum_similarity,
                "minimum_lines": updated.minimum_lines,
                "token_similarity_weight": updated.token_similarity_weight,
                "structure_similarity_weight": updated.structure_similarity_weight,
            },
            "message": "Threshold configuration updated (Note: Persistence not yet implemented)",
        })
    else:
        click.echo("Duplication Threshold Configuration Updated")
        click.echo("=" * 60)
        changes = []
        if minimum_similarity is not None:
            changes.append(f"Minimum Similarity: {current.minimum_similarity:.2f} → {updated.minimum_similarity:.2f}")
        if minimum_lines is not None:
            changes.append(f"Minimum Lines: {current.minimum_lines} → {updated.minimum_lines}")
        if token_weight is not None:
            changes.append(f"Token Weight: {current.token_similarity_weight:.2f} → {updated.token_similarity_weight:.2f}")
        if structure_weight is not None:
            changes.append(f"Structure Weight: {current.structure_similarity_weight:.2f} → {updated.structure_similarity_weight:.2f}")

        for change in changes:
            click.echo(f"  {change}")
        click.echo("")
        click.echo("Note: Configuration persistence will be implemented in phase 5.")


@config.command("override")
@click.argument("pattern", type=click.STRING)
@click.option(
    "--similarity",
    "-s",
    "minimum_similarity",
    type=click.FloatRange(0.0, 1.0),
    default=None,
    help="Minimum similarity threshold (0.0-1.0).",
)
@click.option(
    "--min-lines",
    "-m",
    "minimum_lines",
    type=click.IntRange(1, 1000),
    default=None,
    help="Minimum number of lines to consider for duplication.",
)
@click.option(
    "--token-weight",
    "-t",
    "token_weight",
    type=click.FloatRange(0.0, 1.0),
    default=None,
    help="Weight for token-based similarity (0.0-1.0).",
)
@click.option(
    "--structure-weight",
    "-w",
    "structure_weight",
    type=click.FloatRange(0.0, 1.0),
    default=None,
    help="Weight for structure-based similarity (0.0-1.0).",
)
@click.pass_context
def config_override(
    ctx: click.Context,
    pattern: str,
    minimum_similarity: float | None,
    minimum_lines: int | None,
    token_weight: float | None,
    structure_weight: float | None,
) -> None:
    """
    Add or update a file-specific threshold override.

    Sets custom thresholds for files matching the given pattern.
    Patterns can be exact file paths or glob patterns (e.g., "autoflow/core/*").

    \b
    Examples:
        autoflow duplication config override "autoflow/core/*" --similarity 0.9
        autoflow duplication config override "tests/*" --min-lines 3
        autoflow duplication config override "utils/helpers.py" --token-weight 0.8
    """
    # Import here to avoid circular dependency
    try:
        from autoflow.analysis.duplication_detector import DuplicationThreshold
    except ImportError:
        click.echo("Error: Duplication detector module not available.", err=True)
        ctx.exit(1)

    # At least one option must be specified
    if all(v is None for v in [minimum_similarity, minimum_lines, token_weight, structure_weight]):
        click.echo("Error: At least one threshold option must be specified.", err=True)
        ctx.exit(1)

    # Build override dictionary
    override = {}
    if minimum_similarity is not None:
        override["minimum_similarity"] = minimum_similarity
    if minimum_lines is not None:
        override["minimum_lines"] = minimum_lines
    if token_weight is not None:
        override["token_similarity_weight"] = token_weight
    if structure_weight is not None:
        override["structure_similarity_weight"] = structure_weight

    output_json = ctx.obj.get("output_json", False) if ctx.obj else False
    if output_json:
        _print_json({
            "status": "override_added",
            "pattern": pattern,
            "override": override,
            "message": "File override added (Note: Persistence not yet implemented)",
        })
    else:
        click.echo(f"File Override Added: {pattern}")
        click.echo("=" * 60)
        for key, value in override.items():
            click.echo(f"  {key}: {value}")
        click.echo("")
        click.echo("Note: Configuration persistence will be implemented in phase 5.")


@config.command("list-overrides")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format for the overrides.",
)
@click.pass_context
def config_list_overrides(ctx: click.Context, output_format: str) -> None:
    """
    List all file-specific threshold overrides.

    Shows all configured file pattern overrides with their threshold settings.

    \b
    Examples:
        autoflow duplication config list-overrides
        autoflow duplication config list-overrides --format json
    """
    # Import here to avoid circular dependency
    try:
        from autoflow.analysis.duplication_detector import DuplicationThreshold
    except ImportError:
        click.echo("Error: Duplication detector module not available.", err=True)
        ctx.exit(1)

    threshold = DuplicationThreshold()

    if not threshold.file_overrides:
        if ctx.obj.get("output_json") or output_format == "json":
            _print_json({
                "overrides": [],
                "message": "No file-specific overrides configured",
            })
        else:
            click.echo("No file-specific overrides configured.")
        return

    if ctx.obj.get("output_json") or output_format == "json":
        _print_json({
            "overrides": threshold.file_overrides,
        })
    else:
        click.echo("File-Specific Overrides")
        click.echo("=" * 60)
        for pattern, override in threshold.file_overrides.items():
            click.echo(f"{pattern}:")
            for key, value in override.items():
                click.echo(f"  {key}: {value}")
            click.echo("")


@config.command("remove-override")
@click.argument("pattern", type=click.STRING)
@click.confirmation_option(prompt="Are you sure you want to remove this override?")
@click.pass_context
def config_remove_override(ctx: click.Context, pattern: str) -> None:
    """
    Remove a file-specific threshold override.

    Removes the override for the given file pattern, reverting to
    global threshold settings.

    \b
    Examples:
        autoflow duplication config remove-override "autoflow/core/*"
        autoflow duplication config remove-override "tests/test_*.py"
    """
    # Import here to avoid circular dependency
    try:
        from autoflow.analysis.duplication_detector import DuplicationThreshold
    except ImportError:
        click.echo("Error: Duplication detector module not available.", err=True)
        ctx.exit(1)

    threshold = DuplicationThreshold()

    if pattern not in threshold.file_overrides:
        click.echo(f"Error: No override found for pattern '{pattern}'.", err=True)
        ctx.exit(1)

    output_json = ctx.obj.get("output_json", False) if ctx.obj else False
    if output_json:
        _print_json({
            "status": "override_removed",
            "pattern": pattern,
            "removed_override": threshold.file_overrides[pattern],
            "message": "Override removed (Note: Persistence not yet implemented)",
        })
    else:
        click.echo(f"Override Removed: {pattern}")
        click.echo("=" * 60)
        click.echo("Note: Configuration persistence will be implemented in phase 5.")
