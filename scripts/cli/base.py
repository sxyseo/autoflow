"""
Autoflow CLI - Base Subcommand Class

Provides the abstract base class for all CLI subcommands. This class defines
the interface and common functionality that subcommand implementations must follow.

Usage:
    from scripts.cli.base import Subcommand

    class SpecCommand(Subcommand):
        \"\"\"Spec-related subcommands.\"\"\"

        name = "spec"
        help_text = "Manage specifications"

        def register(self, subparsers) -> None:
            \"\"\"Register spec subcommands.\"\"\"
            # Register subcommands here

        def handle_init(self, args: argparse.Namespace) -> None:
            \"\"\"Handle spec init command.\"\"\"
            # Implementation here
            pass
"""

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from typing import Any


class Subcommand(ABC):
    """
    Abstract base class for CLI subcommands.

    Provides a consistent interface for implementing CLI subcommands.
    Each subcommand module should inherit from this class and implement
    the required methods.

    Attributes:
        name: The name of the subcommand group (e.g., "spec", "task", "run")
        help_text: Brief help text describing the subcommand group

    Example:
        class TaskCommand(Subcommand):
            name = "task"
            help_text = "Task management commands"

            def register(self, subparsers) -> None:
                parser = subparsers.add_parser(self.name, help=self.help_text)
                parser.add_argument("--spec", required=True)
                parser.set_defaults(func=self.handle_list)

            def handle_list(self, args: argparse.Namespace) -> None:
                spec = args.spec
                # List tasks for the spec
    """

    name: str = ""
    help_text: str = ""

    @abstractmethod
    def register(self, subparsers: argparse._SubParsersAction) -> None:
        """
        Register this subcommand's parsers with the argument parser.

        This method is called during CLI initialization to add the subcommand's
        argument parser(s) to the main parser. Implementations should create
        one or more subparsers using subparsers.add_parser() and configure
        their arguments and handler functions.

        Args:
            subparsers: The subparsers action from the main argument parser

        Example:
            def register(self, subparsers) -> None:
                parser = subparsers.add_parser(
                    self.name,
                    help=self.help_text
                )
                parser.add_argument("--required", required=True)
                parser.add_argument("--optional", default="value")
                parser.set_defaults(func=self.handle_command)
        """
        pass

    def handle_command(self, args: argparse.Namespace) -> None:
        """
        Default command handler.

        This method is called when the subcommand is invoked. Subclasses can
        override this method or provide their own handler functions that are
        bound via parser.set_defaults(func=...).

        Args:
            args: Parsed command-line arguments

        Example:
            def handle_command(self, args: argparse.Namespace) -> None:
                value = args.required
                print(f"Processing: {value}")
        """
        pass

    def validate_args(self, args: argparse.Namespace) -> bool:
        """
        Validate command arguments before execution.

        Subclasses can override this method to provide custom validation logic.
        This is called after argument parsing but before command execution.

        Args:
            args: Parsed command-line arguments

        Returns:
            True if arguments are valid, False otherwise

        Example:
            def validate_args(self, args: argparse.Namespace) -> bool:
                if args.count < 0:
                    print("Error: count must be non-negative")
                    return False
                return True
        """
        return True

    def execute(self, args: argparse.Namespace) -> int:
        """
        Execute the command with the given arguments.

        This method provides a wrapper around command execution that handles
        validation and error handling. Subclasses typically don't need to
        override this unless they need custom execution logic.

        Args:
            args: Parsed command-line arguments

        Returns:
            Exit code (0 for success, non-zero for error)

        Example:
            def execute(self, args: argparse.Namespace) -> int:
                if not self.validate_args(args):
                    return 1
                try:
                    self.handle_command(args)
                    return 0
                except Exception as e:
                    print(f"Error: {e}")
                    return 1
        """
        if not self.validate_args(args):
            return 1

        try:
            self.handle_command(args)
            return 0
        except Exception:
            # Let exceptions propagate to the top-level handler
            raise
