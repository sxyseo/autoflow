"""
Autoflow Autonomy Orchestration Module

Provides autonomous workflow coordination functionality extracted from
scripts/autonomy_orchestrator.py and scripts/cli_healthcheck.py.

This module makes business logic testable through dependency injection
of configuration instead of module-level constants.

Usage:
    from autoflow.core.config import Config
    from autoflow.orchestration.autonomy import AutonomyOrchestrator

    config = Config()
    orchestrator = AutonomyOrchestrator(config)
    brief = orchestrator.coordination_brief("my-spec", "config/continuous.json")

    # Or use standalone functions with explicit dependencies
    from autoflow.orchestration.autonomy import coordination_brief, probe_binary

    brief = coordination_brief(spec, continuous_config, config, root)
    status = probe_binary("codex")
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autoflow.core.config import Config, get_state_dir


def now_stamp() -> str:
    """
    Get current UTC timestamp as a string.

    Returns:
        Timestamp in format YYYYMMDDTHHMMSSZ
    """
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def run_cmd(
    args: list[str],
    root: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """
    Run a command as a subprocess.

    Args:
        args: Command arguments
        root: Working directory
        check: Whether to raise exception on non-zero exit

    Returns:
        Completed process result
    """
    return subprocess.run(
        args,
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
    )


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Load JSON from a file, returning default if not found.

    Args:
        path: Path to JSON file
        default: Default value if file doesn't exist

    Returns:
        Parsed JSON data or default value
    """
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_config_from_path(root: Path, config_path: str) -> dict[str, Any]:
    """
    Load configuration from a path relative to root.

    Args:
        root: Project root directory
        config_path: Path to config file (relative or absolute)

    Returns:
        Parsed JSON configuration
    """
    path = (
        root / config_path if not Path(config_path).is_absolute() else Path(config_path)
    )
    return json.loads(path.read_text(encoding="utf-8"))


def probe_binary(name: str) -> dict[str, Any]:
    """
    Probe a binary to check availability and capabilities.

    Args:
        name: Binary name to probe

    Returns:
        Dictionary with availability status, path, version, and capabilities
    """
    path = shutil.which(name)
    if not path:
        return {
            "name": name,
            "available": False,
            "path": "",
            "status": "missing",
            "version": "",
            "capabilities": {},
        }

    # Get version
    version_cmd = [name, "--version"]
    if name == "tmux":
        version_cmd = [name, "-V"]
    version_result = subprocess.run(
        version_cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    help_result = subprocess.run(
        [name, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    version_text = (version_result.stdout or version_result.stderr).strip()
    help_text = (help_result.stdout or "") + (help_result.stderr or "")

    capabilities = {
        "resume": "resume" in help_text.lower() or "--continue" in help_text,
        "model_flag": "--model" in help_text or " -m," in help_text,
    }

    return {
        "name": name,
        "available": True,
        "path": path,
        "status": "ok",
        "version": version_text.splitlines()[0] if version_text else "",
        "capabilities": capabilities,
    }


def tmux_sessions() -> list[dict[str, Any]]:
    """
    Get list of active tmux sessions.

    Returns:
        List of session dictionaries with name, windows, and attached status
    """
    if not shutil.which("tmux"):
        return []

    result = subprocess.run(
        [
            "tmux",
            "list-sessions",
            "-F",
            "#{session_name}:#{session_windows}:#{session_attached}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return []

    sessions = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(":")
        if len(parts) < 3:
            continue
        name, windows, attached = parts[0], parts[1], parts[2]
        sessions.append(
            {
                "name": name,
                "windows": int(windows) if windows.isdigit() else 0,
                "attached": bool(int(attached)) if attached.isdigit() else False,
            }
        )

    return sessions


def build_report() -> dict[str, Any]:
    """
    Build a health report for system binaries.

    Returns:
        Dictionary with checked timestamp, binary status, and tmux sessions
    """
    binaries = [probe_binary("codex"), probe_binary("claude"), probe_binary("tmux")]
    return {
        "checked_at": now_stamp(),
        "binaries": binaries,
        "tmux_sessions": tmux_sessions(),
    }


def health_report(
    root: Path,
    required: list[str] | None = None,
) -> dict[str, Any]:
    """
    Generate a health report with optional requirements checking.

    Args:
        root: Project root directory
        required: Optional list of required binary names

    Returns:
        Health report dictionary with status and binary information
    """
    cmd = ["python3", "scripts/cli_healthcheck.py"]
    for item in required or []:
        cmd.extend(["--require", item])

    result = subprocess.run(
        cmd,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )

    payload = (
        json.loads(result.stdout)
        if result.stdout.strip()
        else {"binaries": [], "tmux_sessions": []}
    )
    payload["status"] = "ok" if result.returncode == 0 else "degraded"
    payload["returncode"] = result.returncode

    return payload


def autoflow_json(root: Path, *args: str) -> dict[str, Any]:
    """
    Run autoflow CLI command and return JSON output.

    Args:
        root: Project root directory
        *args: Arguments to pass to autoflow.py

    Returns:
        Parsed JSON output from command
    """
    result = subprocess.run(
        ["python3", "scripts/autoflow.py", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def taskmaster_sync(
    root: Path,
    spec: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """
    Synchronize taskmaster import/export if enabled.

    Args:
        root: Project root directory
        spec: Spec identifier
        config: Autonomy configuration dictionary

    Returns:
        Taskmaster sync status dictionary
    """
    tm_cfg = config.get("taskmaster", {})
    if not tm_cfg.get("enabled", False):
        return {"enabled": False}

    payload: dict[str, Any] = {"enabled": True}

    # Import taskmaster state
    import_file = tm_cfg.get("import_file", "")
    if import_file:
        input_path = (
            root / import_file
            if not Path(import_file).is_absolute()
            else Path(import_file)
        )
        if input_path.exists():
            result = autoflow_json(
                root, "import-taskmaster", "--spec", spec, "--input", str(input_path)
            )
            payload["import"] = result
        else:
            payload["import"] = {"missing": str(input_path)}

    # Export taskmaster state
    export_file = tm_cfg.get("export_file", "")
    if export_file:
        output_path = (
            root / export_file
            if not Path(export_file).is_absolute()
            else Path(export_file)
        )
        subprocess.run(
            [
                "python3",
                "scripts/autoflow.py",
                "export-taskmaster",
                "--spec",
                spec,
                "--output",
                str(output_path),
            ],
            cwd=root,
            check=True,
            capture_output=True,
        )
        payload["export_file"] = str(output_path)

    return payload


def coordination_brief(
    root: Path,
    state_dir: Path,
    spec: str,
    continuous_config: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a coordination brief for autonomous workflow.

    Args:
        root: Project root directory
        state_dir: State directory path
        spec: Spec identifier
        continuous_config: Path to continuous iteration config
        config: Autonomy configuration dictionary

    Returns:
        Coordination brief with workflow state, strategy, health, and proposed dispatch
    """
    import continuous_iteration

    ci_config = load_config_from_path(root, continuous_config)
    workflow = autoflow_json(root, "workflow-state", "--spec", spec)
    strategy = autoflow_json(root, "show-strategy", "--spec", spec)
    health = health_report(
        root, config.get("monitoring", {}).get("required_binaries", [])
    )

    agents_file = state_dir / "agents.json"
    discovered_file = state_dir / "discovered_agents.json"

    agents_catalog = load_json(agents_file, default={"agents": {}}).get("agents", {})
    discovered = load_json(discovered_file, default={}).get("agents", [])

    next_action = workflow.get("recommended_next_action")
    proposed_dispatch: dict[str, Any] | None = None

    if next_action:
        agent, source = continuous_iteration.select_agent_for_role(
            ci_config,
            next_action["owner_role"],
            agents_catalog,
        )
        proposed_dispatch = {
            "task": next_action["id"],
            "role": next_action["owner_role"],
            "agent": agent,
            "agent_selection": source,
        }

    return {
        "spec": spec,
        "workflow_state": workflow,
        "strategy": strategy,
        "health": health,
        "available_agents": sorted(agents_catalog.keys()),
        "discovered_agents": discovered,
        "proposed_dispatch": proposed_dispatch,
        "openclaw": config.get("openclaw", {}),
    }


def run_tick(
    root: Path,
    state_dir: Path,
    spec: str,
    autonomy_config: str,
    dispatch: bool = False,
    commit_if_dirty: bool = False,
    push: bool = False,
) -> dict[str, Any]:
    """
    Run a single autonomy orchestration tick.

    Args:
        root: Project root directory
        state_dir: State directory path
        spec: Spec identifier
        autonomy_config: Path to autonomy configuration
        dispatch: Whether to dispatch agents
        commit_if_dirty: Whether to commit if working directory is dirty
        push: Whether to push changes

    Returns:
        Tick execution result with taskmaster, coordination brief, and iteration info
    """
    config = load_config_from_path(root, autonomy_config)
    continuous_config = config.get(
        "continuous_iteration_config", "config/continuous-iteration.example.json"
    )

    taskmaster = taskmaster_sync(root, spec, config)
    brief = coordination_brief(root, state_dir, spec, continuous_config, config)

    monitoring_cfg = config.get("monitoring", {})
    if brief["health"].get("returncode", 0) != 0 and monitoring_cfg.get(
        "block_on_missing_binaries", True
    ):
        return {
            "spec": spec,
            "taskmaster": taskmaster,
            "coordination_brief": brief,
            "blocked": "binary_healthcheck_failed",
        }

    cmd = [
        "python3",
        "scripts/continuous_iteration.py",
        "--spec",
        spec,
        "--config",
        continuous_config,
    ]
    if dispatch:
        cmd.append("--dispatch")
    if commit_if_dirty:
        cmd.append("--commit-if-dirty")
    if push:
        cmd.append("--push")

    result = subprocess.run(
        cmd,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    iteration = json.loads(result.stdout)

    return {
        "spec": spec,
        "taskmaster": taskmaster,
        "coordination_brief": brief,
        "iteration": iteration,
    }


class AutonomyOrchestrator:
    """
    Autonomy orchestration functionality.

    This class encapsulates autonomous workflow coordination logic,
    making it testable through dependency injection of configuration.

    Attributes:
        config: Autoflow configuration object
        root: Root directory of the project
        state_dir: State directory for storing workflow data

    Example:
        >>> from autoflow.core.config import load_config
        >>> from autoflow.orchestration.autonomy import AutonomyOrchestrator
        >>>
        >>> config = load_config()
        >>> orchestrator = AutonomyOrchestrator(config)
        >>> brief = orchestrator.coordination_brief("my-spec", "config/continuous.json")
    """

    def __init__(
        self,
        config: Config,
        root: str | Path | None = None,
        state_dir: str | Path | None = None,
    ):
        """
        Initialize the AutonomyOrchestrator.

        Args:
            config: Autoflow configuration object
            root: Project root directory (defaults to current working directory)
            state_dir: State directory (defaults to config.state_dir or .autoflow)
        """
        self.config = config

        # Resolve root directory
        if root is None:
            root = Path.cwd()
        self.root = Path(root).resolve()

        # Resolve state directory
        if state_dir is None:
            state_dir = get_state_dir(config)
        self.state_dir = Path(state_dir).resolve()

    @property
    def agents_file(self) -> Path:
        """Path to agents configuration file."""
        return self.state_dir / "agents.json"

    @property
    def discovery_file(self) -> Path:
        """Path to discovered agents registry file."""
        return self.state_dir / "discovered_agents.json"

    # === Utility Methods ===

    def now_utc(self) -> datetime:
        """
        Get current datetime in UTC.

        Returns:
            Current datetime in UTC
        """
        return datetime.now(UTC)

    def now_stamp(self) -> str:
        """
        Get current UTC timestamp as a string.

        Returns:
            Timestamp in format YYYYMMDDTHHMMSSZ
        """
        return now_stamp()

    def run_cmd(
        self,
        args: list[str],
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """
        Run a command as a subprocess.

        Args:
            args: Command arguments
            check: Whether to raise exception on non-zero exit

        Returns:
            Completed process result
        """
        return run_cmd(args, self.root, check)

    def load_json(
        self, path: Path, default: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Load JSON from a file, returning default if not found.

        Args:
            path: Path to JSON file
            default: Default value if file doesn't exist

        Returns:
            Parsed JSON data or default value
        """
        return load_json(path, default)

    def load_config_from_path(self, config_path: str) -> dict[str, Any]:
        """
        Load configuration from a path relative to root.

        Args:
            config_path: Path to config file (relative or absolute)

        Returns:
            Parsed JSON configuration
        """
        return load_config_from_path(self.root, config_path)

    # === Health Check Methods ===

    def probe_binary(self, name: str) -> dict[str, Any]:
        """
        Probe a binary to check availability and capabilities.

        Args:
            name: Binary name to probe

        Returns:
            Dictionary with availability status, path, version, and capabilities
        """
        return probe_binary(name)

    def tmux_sessions(self) -> list[dict[str, Any]]:
        """
        Get list of active tmux sessions.

        Returns:
            List of session dictionaries with name, windows, and attached status
        """
        return tmux_sessions()

    def build_report(self) -> dict[str, Any]:
        """
        Build a health report for system binaries.

        Returns:
            Dictionary with checked timestamp, binary status, and tmux sessions
        """
        return build_report()

    def health_report(self, required: list[str] | None = None) -> dict[str, Any]:
        """
        Generate a health report with optional requirements checking.

        Args:
            required: Optional list of required binary names

        Returns:
            Health report dictionary with status and binary information
        """
        return health_report(self.root, required)

    # === Taskmaster Methods ===

    def taskmaster_sync(self, spec: str, config: dict[str, Any]) -> dict[str, Any]:
        """
        Synchronize taskmaster import/export if enabled.

        Args:
            spec: Spec identifier
            config: Autonomy configuration dictionary

        Returns:
            Taskmaster sync status dictionary
        """
        return taskmaster_sync(self.root, spec, config)

    # === Coordination Methods ===

    def autoflow_json(self, *args: str) -> dict[str, Any]:
        """
        Run autoflow CLI command and return JSON output.

        Args:
            *args: Arguments to pass to autoflow.py

        Returns:
            Parsed JSON output from command
        """
        return autoflow_json(self.root, *args)

    def coordination_brief(
        self,
        spec: str,
        continuous_config: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build a coordination brief for autonomous workflow.

        Args:
            spec: Spec identifier
            continuous_config: Path to continuous iteration config
            config: Autonomy configuration dictionary

        Returns:
            Coordination brief with workflow state, strategy, health, and proposed dispatch
        """
        return coordination_brief(
            self.root, self.state_dir, spec, continuous_config, config
        )

    # === Orchestration Methods ===

    def run_tick(
        self,
        spec: str,
        autonomy_config: str,
        dispatch: bool = False,
        commit_if_dirty: bool = False,
        push: bool = False,
    ) -> dict[str, Any]:
        """
        Run a single autonomy orchestration tick.

        Args:
            spec: Spec identifier
            autonomy_config: Path to autonomy configuration
            dispatch: Whether to dispatch agents
            commit_if_dirty: Whether to commit if working directory is dirty
            push: Whether to push changes

        Returns:
            Tick execution result with taskmaster, coordination brief, and iteration info
        """
        return run_tick(
            self.root,
            self.state_dir,
            spec,
            autonomy_config,
            dispatch,
            commit_if_dirty,
            push,
        )
