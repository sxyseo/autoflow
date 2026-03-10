"""
Autoflow CLI - Command Line Interface

This module provides the command-line interface for Autoflow.

For backward compatibility, this package re-exports the main CLI entry point.
Usage:
    from autoflow.cli import main
    main()
"""

from autoflow.cli.main import main

__all__ = ["main"]
