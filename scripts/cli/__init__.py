"""
Autoflow CLI - Modular Command Line Interface

This package provides the modular command-line interface for Autoflow.
This is a refactored version that splits the monolithic CLI into
organized subcommand modules.

Usage:
    # Import individual command modules
    from scripts.cli import spec, task, run, worktree

    # The package structure organizes commands by functionality:
    # - spec.py: Spec-related commands (new-spec, show-spec, etc.)
    # - task.py: Task-related commands (init-tasks, list-tasks, etc.)
    # - run.py: Run-related commands (new-run, complete-run, etc.)
    # - worktree.py: Worktree commands
    # - memory.py: Memory commands
    # - review.py: Review commands
    # - agent.py: Agent commands
    # - repository.py: Repository commands
    # - system.py: System commands
    # - integration.py: Integration commands
    # - utils.py: Shared utilities
    # - base.py: Base classes and interfaces
"""

__all__ = []
