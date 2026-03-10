#!/usr/bin/env python3
"""
Maintenance Jobs for Autoflow - Cleanup, Optimization, and Health Checks.

This module provides maintenance automation for the Autoflow system:
- Cleanup: Remove old logs, temp files, and stale cache
- Optimization: Compact databases, prune old data
- Health checks: Verify system health, disk space, dependencies

Usage:
    python3 scripts/maintenance.py --cleanup
    python3 scripts/maintenance.py --optimize
    python3 scripts/maintenance.py --health-check
    python3 scripts/maintenance.py --all
"""

import argparse
import gc
import json
import logging
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("maintenance")

# Default paths
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "maintenance_config.json"
LOGS_DIR = Path(__file__).parent.parent / "logs"
CACHE_DIR = Path(__file__).parent.parent / ".cache"
TEMP_DIR = Path(__file__).parent.parent / ".tmp"


class MaintenanceConfig:
    """Configuration for maintenance tasks."""

    def __init__(self, config_path: Path | None = None):
        """Initialize maintenance configuration.

        Args:
            config_path: Path to configuration file. Defaults to config/maintenance_config.json.
        """
        if config_path is None:
            config_path = DEFAULT_CONFIG_PATH

        self.config_path = config_path
        self._config = self._load_config()

    def _load_config(self) -> dict:
        """Load configuration from JSON file."""
        if not self.config_path.exists():
            return self._default_config()

        with open(self.config_path) as f:
            return json.load(f)

    def _default_config(self) -> dict:
        """Return default configuration."""
        return {
            "cleanup": {
                "log_retention_days": 7,
                "temp_retention_hours": 24,
                "cache_max_size_mb": 500,
                "directories_to_clean": ["logs", ".cache", ".tmp"]
            },
            "optimization": {
                "compact_databases": True,
                "prune_old_runs_days": 30,
                "gc_collect": True
            },
            "health_check": {
                "min_disk_space_gb": 5,
                "max_memory_percent": 90,
                "check_dependencies": True,
                "check_git_status": True
            }
        }

    @property
    def cleanup(self) -> dict:
        """Get cleanup configuration."""
        return self._config.get("cleanup", {})

    @property
    def optimization(self) -> dict:
        """Get optimization configuration."""
        return self._config.get("optimization", {})

    @property
    def health_check(self) -> dict:
        """Get health check configuration."""
        return self._config.get("health_check", {})

    def save(self) -> None:
        """Save current configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self._config, f, indent=2)


class CleanupManager:
    """Handles cleanup of old files and directories."""

    def __init__(self, config: MaintenanceConfig):
        """Initialize cleanup manager.

        Args:
            config: Maintenance configuration.
        """
        self.config = config
        self.stats = {
            "files_removed": 0,
            "bytes_freed": 0,
            "errors": []
        }

    def run_cleanup(self) -> dict[str, Any]:
        """Run all cleanup tasks.

        Returns:
            Dictionary with cleanup statistics.
        """
        logger.info("Starting cleanup tasks...")
        start_time = datetime.now(UTC)

        # Clean logs
        self._clean_logs()

        # Clean temp files
        self._clean_temp_files()

        # Clean cache
        self._clean_cache()

        # Clean old run data
        self._clean_old_runs()

        duration = (datetime.now(UTC) - start_time).total_seconds()

        logger.info(
            f"Cleanup completed: {self.stats['files_removed']} files removed, "
            f"{self.stats['bytes_freed'] / 1024 / 1024:.2f} MB freed"
        )

        return {
            "success": len(self.stats["errors"]) == 0,
            "files_removed": self.stats["files_removed"],
            "bytes_freed": self.stats["bytes_freed"],
            "bytes_freed_mb": round(self.stats["bytes_freed"] / 1024 / 1024, 2),
            "errors": self.stats["errors"],
            "duration_seconds": duration,
            "timestamp": start_time.isoformat()
        }

    def _clean_logs(self) -> None:
        """Clean old log files."""
        retention_days = self.config.cleanup.get("log_retention_days", 7)
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)

        if not LOGS_DIR.exists():
            logger.debug(f"Logs directory {LOGS_DIR} does not exist")
            return

        logger.info(f"Cleaning logs older than {retention_days} days...")

        for log_file in LOGS_DIR.glob("**/*"):
            if log_file.is_file():
                try:
                    mtime = datetime.fromtimestamp(log_file.stat().st_mtime, tz=UTC)
                    if mtime < cutoff:
                        size = log_file.stat().st_size
                        log_file.unlink()
                        self.stats["files_removed"] += 1
                        self.stats["bytes_freed"] += size
                        logger.debug(f"Removed old log: {log_file}")
                except Exception as e:
                    self.stats["errors"].append(f"Failed to remove {log_file}: {e}")
                    logger.error(f"Failed to remove {log_file}: {e}")

    def _clean_temp_files(self) -> None:
        """Clean temporary files."""
        retention_hours = self.config.cleanup.get("temp_retention_hours", 24)
        cutoff = datetime.now(UTC) - timedelta(hours=retention_hours)

        if not TEMP_DIR.exists():
            logger.debug(f"Temp directory {TEMP_DIR} does not exist")
            return

        logger.info(f"Cleaning temp files older than {retention_hours} hours...")

        for temp_file in TEMP_DIR.glob("**/*"):
            if temp_file.is_file():
                try:
                    mtime = datetime.fromtimestamp(temp_file.stat().st_mtime, tz=UTC)
                    if mtime < cutoff:
                        size = temp_file.stat().st_size
                        temp_file.unlink()
                        self.stats["files_removed"] += 1
                        self.stats["bytes_freed"] += size
                        logger.debug(f"Removed temp file: {temp_file}")
                except Exception as e:
                    self.stats["errors"].append(f"Failed to remove {temp_file}: {e}")
                    logger.error(f"Failed to remove {temp_file}: {e}")

        # Remove empty directories
        for temp_dir in sorted(TEMP_DIR.glob("**/"), key=lambda d: len(str(d)), reverse=True):
            if temp_dir != TEMP_DIR and temp_dir.is_dir():
                try:
                    if not any(temp_dir.iterdir()):
                        temp_dir.rmdir()
                        logger.debug(f"Removed empty temp dir: {temp_dir}")
                except Exception as e:
                    logger.debug(f"Could not remove temp dir {temp_dir}: {e}")

    def _clean_cache(self) -> None:
        """Clean cache if it exceeds max size."""
        max_size_mb = self.config.cleanup.get("cache_max_size_mb", 500)

        if not CACHE_DIR.exists():
            logger.debug(f"Cache directory {CACHE_DIR} does not exist")
            return

        # Calculate current cache size
        total_size = sum(
            f.stat().st_size for f in CACHE_DIR.glob("**/*") if f.is_file()
        )
        total_size_mb = total_size / 1024 / 1024

        logger.info(f"Cache size: {total_size_mb:.2f} MB (max: {max_size_mb} MB)")

        if total_size_mb <= max_size_mb:
            return

        # Remove oldest files until under limit
        files = []
        for cache_file in CACHE_DIR.glob("**/*"):
            if cache_file.is_file():
                mtime = cache_file.stat().st_mtime
                size = cache_file.stat().st_size
                files.append((cache_file, mtime, size))

        # Sort by modification time (oldest first)
        files.sort(key=lambda x: x[1])

        removed_size = 0
        target_reduction = total_size - (max_size_mb * 1024 * 1024)

        for cache_file, _mtime, size in files:
            if removed_size >= target_reduction:
                break

            try:
                cache_file.unlink()
                self.stats["files_removed"] += 1
                self.stats["bytes_freed"] += size
                removed_size += size
                logger.debug(f"Removed cache file: {cache_file}")
            except Exception as e:
                self.stats["errors"].append(f"Failed to remove {cache_file}: {e}")
                logger.error(f"Failed to remove {cache_file}: {e}")

        logger.info(f"Cache cleanup freed {removed_size / 1024 / 1024:.2f} MB")

    def _clean_old_runs(self) -> None:
        """Clean old run data from .auto-claude directory."""
        retention_days = self.config.optimization.get("prune_old_runs_days", 30)
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)

        auto_claude_dir = Path(__file__).parent.parent / ".auto-claude"
        if not auto_claude_dir.exists():
            return

        logger.info(f"Cleaning run data older than {retention_days} days...")

        # Clean old session files and worktrees
        for item in auto_claude_dir.glob("**/*"):
            if item.is_file():
                try:
                    mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=UTC)
                    if mtime < cutoff:
                        # Skip config files
                        if item.suffix in [".json", ".yaml", ".yml"] and "config" in item.name.lower():
                            continue
                        size = item.stat().st_size
                        item.unlink()
                        self.stats["files_removed"] += 1
                        self.stats["bytes_freed"] += size
                        logger.debug(f"Removed old run file: {item}")
                except Exception as e:
                    logger.debug(f"Could not remove {item}: {e}")


class OptimizationManager:
    """Handles system optimization tasks."""

    def __init__(self, config: MaintenanceConfig):
        """Initialize optimization manager.

        Args:
            config: Maintenance configuration.
        """
        self.config = config
        self.stats = {
            "databases_compacted": 0,
            "runs_pruned": 0,
            "gc_collected": False,
            "errors": []
        }

    def run_optimization(self) -> dict[str, Any]:
        """Run all optimization tasks.

        Returns:
            Dictionary with optimization statistics.
        """
        logger.info("Starting optimization tasks...")
        start_time = datetime.now(UTC)

        # Run garbage collection
        self._run_gc()

        # Compact databases (if any)
        self._compact_databases()

        # Prune old data
        self._prune_old_data()

        duration = (datetime.now(UTC) - start_time).total_seconds()

        logger.info(
            f"Optimization completed: {self.stats['databases_compacted']} databases compacted, "
            f"{self.stats['runs_pruned']} old runs pruned"
        )

        return {
            "success": len(self.stats["errors"]) == 0,
            "databases_compacted": self.stats["databases_compacted"],
            "runs_pruned": self.stats["runs_pruned"],
            "gc_collected": self.stats["gc_collected"],
            "errors": self.stats["errors"],
            "duration_seconds": duration,
            "timestamp": start_time.isoformat()
        }

    def _run_gc(self) -> None:
        """Run Python garbage collection."""
        if not self.config.optimization.get("gc_collect", True):
            return

        logger.info("Running garbage collection...")

        try:
            before = len(gc.get_objects())
            collected = gc.collect()
            after = len(gc.get_objects())

            self.stats["gc_collected"] = True
            logger.info(f"GC collected {collected} objects ({before} -> {after})")
        except Exception as e:
            self.stats["errors"].append(f"GC failed: {e}")
            logger.error(f"Garbage collection failed: {e}")

    def _compact_databases(self) -> None:
        """Compact SQLite databases if any exist."""
        if not self.config.optimization.get("compact_databases", True):
            return

        logger.info("Checking for databases to compact...")

        # Find SQLite databases
        for db_file in Path(__file__).parent.parent.glob("**/*.db"):
            try:
                # Vacuum the database
                import sqlite3
                conn = sqlite3.connect(str(db_file))
                conn.execute("VACUUM")
                conn.close()
                self.stats["databases_compacted"] += 1
                logger.info(f"Compacted database: {db_file}")
            except Exception as e:
                self.stats["errors"].append(f"Failed to compact {db_file}: {e}")
                logger.debug(f"Could not compact {db_file}: {e}")

    def _prune_old_data(self) -> None:
        """Prune old data from various sources."""
        retention_days = self.config.optimization.get("prune_old_runs_days", 30)
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)

        # Prune old entries from knowledge graph (if exists)
        knowledge_file = Path(__file__).parent.parent / "data" / "knowledge_graph.json"
        if knowledge_file.exists():
            try:
                with open(knowledge_file) as f:
                    data = json.load(f)

                # Prune old entries
                if "entries" in data:
                    original_count = len(data["entries"])
                    data["entries"] = [
                        e for e in data["entries"]
                        if "timestamp" not in e or
                        datetime.fromisoformat(e["timestamp"]) > cutoff
                    ]
                    self.stats["runs_pruned"] += original_count - len(data["entries"])

                with open(knowledge_file, "w") as f:
                    json.dump(data, f, indent=2)

                logger.info("Pruned knowledge graph")
            except Exception as e:
                logger.debug(f"Could not prune knowledge graph: {e}")


class HealthCheckManager:
    """Handles system health checks."""

    def __init__(self, config: MaintenanceConfig):
        """Initialize health check manager.

        Args:
            config: Maintenance configuration.
        """
        self.config = config
        self.checks = {
            "disk_space": None,
            "memory": None,
            "dependencies": None,
            "git_status": None
        }
        self.errors = []

    def run_health_check(self) -> dict[str, Any]:
        """Run all health checks.

        Returns:
            Dictionary with health check results.
        """
        logger.info("Starting health checks...")
        start_time = datetime.now(UTC)

        # Check disk space
        self._check_disk_space()

        # Check memory usage
        self._check_memory()

        # Check dependencies
        self._check_dependencies()

        # Check git status
        self._check_git_status()

        duration = (datetime.now(UTC) - start_time).total_seconds()

        all_healthy = all(v in [True, None] for v in self.checks.values())

        logger.info(f"Health check completed: {'HEALTHY' if all_healthy else 'ISSUES FOUND'}")

        return {
            "success": all_healthy,
            "checks": self.checks,
            "errors": self.errors,
            "duration_seconds": duration,
            "timestamp": start_time.isoformat()
        }

    def _check_disk_space(self) -> None:
        """Check available disk space."""
        min_space_gb = self.config.health_check.get("min_disk_space_gb", 5)

        try:
            total, used, free = shutil.disk_usage(Path(__file__).parent.parent)
            free_gb = free / (1024 ** 3)

            self.checks["disk_space"] = {
                "free_gb": round(free_gb, 2),
                "total_gb": round(total / (1024 ** 3), 2),
                "used_percent": round(used / total * 100, 1),
                "healthy": free_gb >= min_space_gb
            }

            if free_gb < min_space_gb:
                self.errors.append(f"Low disk space: {free_gb:.2f} GB (min: {min_space_gb} GB)")
                logger.warning(f"Low disk space: {free_gb:.2f} GB")
            else:
                logger.info(f"Disk space OK: {free_gb:.2f} GB free")

        except Exception as e:
            self.checks["disk_space"] = {"error": str(e), "healthy": False}
            self.errors.append(f"Disk space check failed: {e}")
            logger.error(f"Failed to check disk space: {e}")

    def _check_memory(self) -> None:
        """Check memory usage."""
        max_percent = self.config.health_check.get("max_memory_percent", 90)

        try:
            import psutil
            memory = psutil.virtual_memory()

            self.checks["memory"] = {
                "total_gb": round(memory.total / (1024 ** 3), 2),
                "available_gb": round(memory.available / (1024 ** 3), 2),
                "used_percent": memory.percent,
                "healthy": memory.percent < max_percent
            }

            if memory.percent >= max_percent:
                self.errors.append(f"High memory usage: {memory.percent}% (max: {max_percent}%)")
                logger.warning(f"High memory usage: {memory.percent}%")
            else:
                logger.info(f"Memory usage OK: {memory.percent}%")

        except ImportError:
            # psutil not available, skip memory check
            self.checks["memory"] = {"skipped": "psutil not installed"}
            logger.debug("psutil not available, skipping memory check")
        except Exception as e:
            self.checks["memory"] = {"error": str(e), "healthy": False}
            self.errors.append(f"Memory check failed: {e}")
            logger.error(f"Failed to check memory: {e}")

    def _check_dependencies(self) -> None:
        """Check that required dependencies are installed."""
        if not self.config.health_check.get("check_dependencies", True):
            self.checks["dependencies"] = {"skipped": True}
            return

        required = [
            ("apscheduler", "apscheduler"),
            ("pytest", "pytest"),
        ]

        optional = [
            ("psutil", "psutil"),
            ("networkx", "networkx"),
            ("fastapi", "fastapi"),
        ]

        missing_required = []
        missing_optional = []

        for name, package in required:
            try:
                __import__(package)
            except ImportError:
                missing_required.append(name)

        for name, package in optional:
            try:
                __import__(package)
            except ImportError:
                missing_optional.append(name)

        self.checks["dependencies"] = {
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "healthy": len(missing_required) == 0
        }

        if missing_required:
            self.errors.append(f"Missing required dependencies: {missing_required}")
            logger.error(f"Missing required dependencies: {missing_required}")

        if missing_optional:
            logger.info(f"Optional dependencies not installed: {missing_optional}")

        if not missing_required:
            logger.info("All required dependencies installed")

    def _check_git_status(self) -> None:
        """Check git repository status."""
        if not self.config.health_check.get("check_git_status", True):
            self.checks["git_status"] = {"skipped": True}
            return

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent,
                timeout=30
            )

            changes = result.stdout.strip().split("\n") if result.stdout.strip() else []
            has_changes = len(changes) > 0 and changes[0] != ""

            self.checks["git_status"] = {
                "has_changes": has_changes,
                "changed_files": len(changes) if has_changes else 0,
                "healthy": True
            }

            if has_changes:
                logger.info(f"Git has {len(changes)} uncommitted changes")
            else:
                logger.info("Git working directory clean")

        except subprocess.TimeoutExpired:
            self.checks["git_status"] = {"error": "timeout", "healthy": True}
            logger.warning("Git status check timed out")
        except Exception as e:
            self.checks["git_status"] = {"error": str(e), "healthy": True}
            logger.debug(f"Could not check git status: {e}")


# CLI Commands

def cmd_cleanup(args: argparse.Namespace) -> int:
    """Run cleanup tasks.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    config = MaintenanceConfig()
    manager = CleanupManager(config)
    result = manager.run_cleanup()

    print("\nCleanup Results:")
    print(f"  Files removed: {result['files_removed']}")
    print(f"  Space freed: {result['bytes_freed_mb']:.2f} MB")
    print(f"  Duration: {result['duration_seconds']:.2f}s")

    if result["errors"]:
        print(f"\n  Errors: {len(result['errors'])}")
        for error in result["errors"][:5]:
            print(f"    - {error}")

    return 0 if result["success"] else 1


def cmd_optimize(args: argparse.Namespace) -> int:
    """Run optimization tasks.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    config = MaintenanceConfig()
    manager = OptimizationManager(config)
    result = manager.run_optimization()

    print("\nOptimization Results:")
    print(f"  Databases compacted: {result['databases_compacted']}")
    print(f"  Old runs pruned: {result['runs_pruned']}")
    print(f"  GC collected: {result['gc_collected']}")
    print(f"  Duration: {result['duration_seconds']:.2f}s")

    if result["errors"]:
        print(f"\n  Errors: {len(result['errors'])}")
        for error in result["errors"][:5]:
            print(f"    - {error}")

    return 0 if result["success"] else 1


def cmd_health_check(args: argparse.Namespace) -> int:
    """Run health checks.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    config = MaintenanceConfig()
    manager = HealthCheckManager(config)
    result = manager.run_health_check()

    print("\nHealth Check Results:")

    # Disk space
    if result["checks"]["disk_space"]:
        ds = result["checks"]["disk_space"]
        status = "OK" if ds.get("healthy") else "WARNING"
        print(f"  Disk Space: {status}")
        if "free_gb" in ds:
            print(f"    Free: {ds['free_gb']:.2f} GB / {ds['total_gb']:.2f} GB")
            print(f"    Used: {ds['used_percent']:.1f}%")

    # Memory
    if result["checks"]["memory"]:
        mem = result["checks"]["memory"]
        if mem.get("skipped"):
            print(f"  Memory: SKIPPED ({mem.get('skipped')})")
        else:
            status = "OK" if mem.get("healthy") else "WARNING"
            print(f"  Memory: {status}")
            if "used_percent" in mem:
                print(f"    Used: {mem['used_percent']:.1f}% ({mem['available_gb']:.2f} GB available)")

    # Dependencies
    if result["checks"]["dependencies"]:
        deps = result["checks"]["dependencies"]
        status = "OK" if deps.get("healthy") else "ERROR"
        print(f"  Dependencies: {status}")
        if deps.get("missing_required"):
            print(f"    Missing required: {deps['missing_required']}")
        if deps.get("missing_optional"):
            print(f"    Missing optional: {deps['missing_optional']}")

    # Git status
    if result["checks"]["git_status"]:
        git = result["checks"]["git_status"]
        if git.get("skipped"):
            print("  Git Status: SKIPPED")
        else:
            status = "CLEAN" if not git.get("has_changes") else f"DIRTY ({git.get('changed_files', 0)} changes)"
            print(f"  Git Status: {status}")

    print(f"\n  Duration: {result['duration_seconds']:.2f}s")

    if result["errors"]:
        print(f"\n  Issues Found: {len(result['errors'])}")
        for error in result["errors"]:
            print(f"    - {error}")

    return 0 if result["success"] else 1


def cmd_all(args: argparse.Namespace) -> int:
    """Run all maintenance tasks.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    print("=" * 60)
    print("Running all maintenance tasks...")
    print("=" * 60)

    exit_code = 0

    # Run cleanup
    print("\n[1/3] Cleanup")
    print("-" * 40)
    if cmd_cleanup(args) != 0:
        exit_code = 1

    # Run optimization
    print("\n[2/3] Optimization")
    print("-" * 40)
    if cmd_optimize(args) != 0:
        exit_code = 1

    # Run health check
    print("\n[3/3] Health Check")
    print("-" * 40)
    if cmd_health_check(args) != 0:
        exit_code = 1

    print("\n" + "=" * 60)
    print(f"All maintenance tasks completed (exit code: {exit_code})")
    print("=" * 60)

    return exit_code


def main() -> int:
    """Main entry point for the maintenance CLI.

    Returns:
        Exit code.
    """
    parser = argparse.ArgumentParser(
        description="Maintenance Jobs for Autoflow - Cleanup, Optimization, and Health Checks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 scripts/maintenance.py --cleanup
    python3 scripts/maintenance.py --optimize
    python3 scripts/maintenance.py --health-check
    python3 scripts/maintenance.py --all
        """
    )

    # Main options (mutually exclusive for simplicity)
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--cleanup",
        action="store_true",
        help="Run cleanup tasks (remove old logs, temp files, cache)"
    )
    group.add_argument(
        "--optimize",
        action="store_true",
        help="Run optimization tasks (compact databases, prune old data)"
    )
    group.add_argument(
        "--health-check",
        action="store_true",
        help="Run health checks (disk space, memory, dependencies)"
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Run all maintenance tasks"
    )

    args = parser.parse_args()

    # Default to --all if no option specified
    if not any([args.cleanup, args.optimize, args.health_check, args.all]):
        args.all = True

    if args.cleanup:
        return cmd_cleanup(args)
    elif args.optimize:
        return cmd_optimize(args)
    elif args.health_check:
        return cmd_health_check(args)
    elif args.all:
        return cmd_all(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
