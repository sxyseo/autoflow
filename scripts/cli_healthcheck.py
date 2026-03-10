#!/usr/bin/env python3
"""CLI health check script for Codex/Claude/tmux availability.

This script uses the probe_binary function from autoflow.orchestration.autonomy
to check system binary availability and capabilities.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path to import from autoflow package
# (avoid shadowing by scripts/autoflow.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoflow.orchestration.autonomy import build_report


def main() -> None:
    """Main entry point for CLI health check.

    Builds a health report of system binaries and tmux sessions,
    optionally checking for required binaries.
    """
    parser = argparse.ArgumentParser(description="Report local Codex/Claude/tmux health")
    parser.add_argument("--require", action="append", default=[], help="Require specified binaries")
    args = parser.parse_args()

    report = build_report()
    required = set(args.require)
    missing = [
        item["name"]
        for item in report["binaries"]
        if item["name"] in required and not item["available"]
    ]
    print(json.dumps(report, indent=2, ensure_ascii=True))
    if missing:
        raise SystemExit(f"required binaries missing: {', '.join(sorted(missing))}")


if __name__ == "__main__":
    main()
