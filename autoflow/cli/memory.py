"""
Autoflow CLI - Memory Commands

Manage persistent memory for storing and retrieving information
across sessions and tasks.

Usage:
    autoflow memory list
    autoflow memory get <key>
    autoflow memory set <key> <value>
    autoflow memory add <key> <value>
    autoflow memory delete <key>
"""

from __future__ import annotations

import click

from autoflow.cli.utils import _get_state_manager, _print_json
from autoflow.core.config import Config


@click.group()
def memory() -> None:
    """Manage persistent memory."""
    pass


@memory.command("list")
@click.option(
    "--category",
    "-c",
    type=str,
    default=None,
    help="Filter by category.",
)
@click.pass_context
def memory_list(ctx: click.Context, category: str | None) -> None:
    """
    List memory entries.

    Shows all memory entries, optionally filtered by category.

    \b
    Examples:
        autoflow memory list
        autoflow memory list --category general
        autoflow memory list -c project
    """
    config: Config | None = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    state_manager = _get_state_manager(config)
    memories = state_manager.list_memory(category=category)

    if ctx.obj.get("output_json"):
        _print_json({"memories": memories, "count": len(memories)})
        return

    click.echo("Memory Entries")
    click.echo("=" * 60)

    if not memories:
        click.echo("No memory entries found.")
        return

    for mem in memories:
        click.echo(f"\n[{mem.get('key', 'unknown')}]")
        click.echo(f"  Category: {mem.get('category', 'N/A')}")
        click.echo(f"  Created: {mem.get('created_at', 'N/A')}")


@memory.command("get")
@click.argument("key", type=str)
@click.pass_context
def memory_get(ctx: click.Context, key: str) -> None:
    """
    Get a memory entry by key.

    Retrieves and displays the value associated with the given key.

    \b
    Examples:
        autoflow memory get project_name
        autoflow memory get last_commit
    """
    config: Config | None = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    state_manager = _get_state_manager(config)
    value = state_manager.load_memory(key)

    if value is None:
        click.echo(f"Error: Memory '{key}' not found.", err=True)
        ctx.exit(1)

    if ctx.obj.get("output_json"):
        _print_json({"key": key, "value": value})
    else:
        click.echo(f"{key}: {value}")


@memory.command("set")
@click.argument("key", type=str)
@click.argument("value", type=str)
@click.option(
    "--category",
    "-c",
    type=str,
    default="general",
    help="Category for the memory.",
)
@click.pass_context
def memory_set(ctx: click.Context, key: str, value: str, category: str) -> None:
    """
    Set a memory entry.

    Stores a key-value pair in persistent memory, optionally with a category.

    \b
    Examples:
        autoflow memory set project_name myproject
        autoflow memory set last_commit abc123 --category git
        autoflow memory set status "in progress" -c workflow
    """
    config: Config | None = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    state_manager = _get_state_manager(config)
    state_manager.initialize()
    state_manager.save_memory(key, value, category=category)

    if ctx.obj.get("output_json"):
        _print_json({"key": key, "value": value, "category": category, "status": "saved"})
    else:
        click.echo(f"Saved: {key} = {value}")


@memory.command("add")
@click.argument("key", type=str)
@click.argument("value", type=str)
@click.option(
    "--category",
    "-c",
    type=str,
    default="general",
    help="Category for the memory.",
)
@click.pass_context
def memory_add(ctx: click.Context, key: str, value: str, category: str) -> None:
    """
    Add a memory entry.

    Adds a new key-value pair to persistent memory, optionally with a category.

    \b
    Examples:
        autoflow memory add project_name myproject
        autoflow memory add last_commit abc123 --category git
        autoflow memory add status "in progress" -c workflow
    """
    config: Config | None = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    state_manager = _get_state_manager(config)
    state_manager.initialize()
    state_manager.save_memory(key, value, category=category)

    if ctx.obj.get("output_json"):
        _print_json({"key": key, "value": value, "category": category, "status": "added"})
    else:
        click.echo(f"Added: {key} = {value}")


@memory.command("delete")
@click.argument("key", type=str)
@click.pass_context
def memory_delete(ctx: click.Context, key: str) -> None:
    """
    Delete a memory entry.

    Removes the memory entry associated with the given key.

    \b
    Examples:
        autoflow memory delete old_key
        autoflow memory delete temp_data
    """
    config: Config | None = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    state_manager = _get_state_manager(config)

    if state_manager.delete_memory(key):
        if ctx.obj.get("output_json"):
            _print_json({"key": key, "status": "deleted"})
        else:
            click.echo(f"Deleted: {key}")
    else:
        click.echo(f"Error: Memory '{key}' not found.", err=True)
        ctx.exit(1)
