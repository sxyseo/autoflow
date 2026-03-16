#!/usr/bin/env python3
"""Verify Python syntax for all files in the autoflow package."""

import ast
import os
import sys


def verify_syntax(directory: str) -> tuple[int, list[str]]:
    """Verify syntax of all Python files in directory.

    Returns:
        Tuple of (file_count, errors)
    """
    files = []
    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in filenames:
            if f.endswith(".py"):
                files.append(os.path.join(root, f))

    errors = []
    for f in files:
        try:
            with open(f) as fp:
                ast.parse(fp.read())
        except SyntaxError as e:
            errors.append(f"{f}: {e}")

    return len(files), errors


def main():
    """Run syntax verification."""
    print("=== Python Syntax Verification ===\n")

    # Verify autoflow package
    count, errors = verify_syntax("autoflow")
    if errors:
        print(f"SYNTAX ERRORS in autoflow/ ({count} files):")
        for e in errors:
            print(f"  {e}")
        return 1
    print(f"autoflow/: All {count} Python files have valid syntax")

    # Verify tests
    count, errors = verify_syntax("tests")
    if errors:
        print(f"SYNTAX ERRORS in tests/ ({count} files):")
        for e in errors:
            print(f"  {e}")
        return 1
    print(f"tests/: All {count} Python files have valid syntax")

    print("\nAll syntax checks passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
