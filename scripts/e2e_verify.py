#!/usr/bin/env python3
"""
End-to-End Verification Script for Autoflow

This script performs comprehensive verification of the Autoflow system:
1. Verifies CLI works with --help
2. Verifies state initialization with 'autoflow init'
3. Verifies state query with 'autoflow status'
4. Runs all tests with pytest
5. Verifies agent adapters can be instantiated
6. Verifies skills can be loaded from registry

Run this script after installing dependencies:
    pip install -e ".[dev]"
    python scripts/e2e_verify.py
"""

import ast
import os
import subprocess
import sys
from pathlib import Path


class VerificationResult:
    """Result of a verification step."""

    def __init__(self, name: str, passed: bool, message: str = "", details: str = ""):
        self.name = name
        self.passed = passed
        self.message = message
        self.details = details

    def __str__(self) -> str:
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status}: {self.name}" + (f" - {self.message}" if self.message else "")


def verify_dependencies() -> VerificationResult:
    """Verify all required dependencies are installed."""
    required = ["click", "pydantic", "json5", "apscheduler", "pytest", "pytest_asyncio"]
    missing = []

    for package in required:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing.append(package)

    if missing:
        return VerificationResult(
            "Dependencies",
            False,
            f"Missing packages: {', '.join(missing)}",
            "Run: pip install -e '.[dev]'"
        )
    return VerificationResult("Dependencies", True, "All required packages installed")


def verify_syntax() -> VerificationResult:
    """Verify Python syntax for all files."""
    errors = []
    file_count = 0

    for directory in ["autoflow", "tests"]:
        for root, dirs, filenames in os.walk(directory):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in filenames:
                if f.endswith(".py"):
                    file_count += 1
                    path = os.path.join(root, f)
                    try:
                        with open(path) as fp:
                            ast.parse(fp.read())
                    except SyntaxError as e:
                        errors.append(f"{path}: {e}")

    if errors:
        return VerificationResult(
            "Python Syntax",
            False,
            f"{len(errors)} files with errors",
            "\n".join(errors)
        )
    return VerificationResult("Python Syntax", True, f"{file_count} files validated")


def verify_imports() -> VerificationResult:
    """Verify all modules can be imported."""
    modules = [
        "autoflow",
        "autoflow.cli",
        "autoflow.core",
        "autoflow.core.config",
        "autoflow.core.state",
        "autoflow.core.orchestrator",
        "autoflow.agents",
        "autoflow.agents.base",
        "autoflow.agents.claude_code",
        "autoflow.agents.codex",
        "autoflow.agents.openclaw",
        "autoflow.tmux",
        "autoflow.tmux.session",
        "autoflow.tmux.manager",
        "autoflow.skills",
        "autoflow.skills.registry",
        "autoflow.skills.executor",
        "autoflow.scheduler",
        "autoflow.scheduler.daemon",
        "autoflow.scheduler.jobs",
        "autoflow.review",
        "autoflow.review.cross_review",
        "autoflow.ci",
        "autoflow.ci.verifier",
        "autoflow.ci.gates",
    ]

    errors = []
    for module in modules:
        try:
            __import__(module)
        except ImportError as e:
            errors.append(f"{module}: {e}")

    if errors:
        return VerificationResult(
            "Module Imports",
            False,
            f"{len(errors)} import errors",
            "\n".join(errors)
        )
    return VerificationResult("Module Imports", True, f"{len(modules)} modules imported")


def verify_cli_help() -> VerificationResult:
    """Verify CLI --help works."""
    try:
        result = subprocess.run(
            ["python", "-m", "autoflow.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0 and "Usage:" in result.stdout:
            return VerificationResult("CLI --help", True, "CLI responds to --help")
        return VerificationResult(
            "CLI --help",
            False,
            "Unexpected output",
            result.stdout + result.stderr
        )
    except subprocess.TimeoutExpired:
        return VerificationResult("CLI --help", False, "Timeout")
    except Exception as e:
        return VerificationResult("CLI --help", False, str(e))


def verify_init() -> VerificationResult:
    """Verify 'autoflow init' creates state directory."""
    state_dir = Path(".autoflow")

    # Clean up any existing state
    if state_dir.exists():
        import shutil
        shutil.rmtree(state_dir)

    try:
        result = subprocess.run(
            ["python", "-m", "autoflow.cli", "init"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if state_dir.exists():
            subdirs = [d.name for d in state_dir.iterdir() if d.is_dir()]
            return VerificationResult(
                "autoflow init",
                True,
                f"Created .autoflow/ with: {', '.join(subdirs)}"
            )
        return VerificationResult(
            "autoflow init",
            False,
            "State directory not created",
            result.stdout + result.stderr
        )
    except subprocess.TimeoutExpired:
        return VerificationResult("autoflow init", False, "Timeout")
    except Exception as e:
        return VerificationResult("autoflow init", False, str(e))


def verify_status() -> VerificationResult:
    """Verify 'autoflow status' works."""
    try:
        result = subprocess.run(
            ["python", "-m", "autoflow.cli", "status"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return VerificationResult("autoflow status", True, "Status command works")
        return VerificationResult(
            "autoflow status",
            False,
            f"Exit code: {result.returncode}",
            result.stdout + result.stderr
        )
    except subprocess.TimeoutExpired:
        return VerificationResult("autoflow status", False, "Timeout")
    except Exception as e:
        return VerificationResult("autoflow status", False, str(e))


def verify_tests() -> VerificationResult:
    """Verify all tests pass."""
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=300
        )

        # Parse output for summary
        lines = result.stdout.split("\n")
        summary_line = ""
        for line in lines:
            if "passed" in line or "failed" in line:
                summary_line = line

        if result.returncode == 0:
            return VerificationResult("pytest tests/", True, summary_line)
        return VerificationResult(
            "pytest tests/",
            False,
            "Some tests failed",
            summary_line
        )
    except subprocess.TimeoutExpired:
        return VerificationResult("pytest tests/", False, "Timeout (5 min)")
    except Exception as e:
        return VerificationResult("pytest tests/", False, str(e))


def verify_agent_adapters() -> VerificationResult:
    """Verify agent adapters can be instantiated."""
    try:
        from autoflow.agents.base import ResumeMode
        from autoflow.agents.claude_code import ClaudeCodeAdapter
        from autoflow.agents.codex import CodexAdapter
        from autoflow.agents.openclaw import OpenClawAdapter

        adapters = []

        # ClaudeCodeAdapter
        claude = ClaudeCodeAdapter()
        adapters.append("ClaudeCodeAdapter")
        assert claude.get_resume_mode() == ResumeMode.NATIVE

        # CodexAdapter
        codex = CodexAdapter()
        adapters.append("CodexAdapter")
        assert codex.get_resume_mode() == ResumeMode.REPROMPT

        # OpenClawAdapter
        openclaw = OpenClawAdapter()
        adapters.append("OpenClawAdapter")
        assert openclaw.get_resume_mode() == ResumeMode.NATIVE

        return VerificationResult(
            "Agent Adapters",
            True,
            f"All adapters instantiated: {', '.join(adapters)}"
        )
    except ImportError as e:
        return VerificationResult("Agent Adapters", False, f"Import error: {e}")
    except AssertionError as e:
        return VerificationResult("Agent Adapters", False, f"Assertion error: {e}")
    except Exception as e:
        return VerificationResult("Agent Adapters", False, str(e))


def verify_skill_registry() -> VerificationResult:
    """Verify skills can be loaded from registry."""
    try:
        from autoflow.skills.registry import SkillRegistry

        registry = SkillRegistry()

        # Check that we can discover skills
        skills_dir = Path("skills")
        if skills_dir.exists():
            skill_count = len(list(skills_dir.glob("*/SKILL.md")))
        else:
            skill_count = 0

        # List loaded skills
        loaded_skills = registry.list_skills()

        return VerificationResult(
            "Skill Registry",
            True,
            f"Registry initialized, {skill_count} skill dirs, {len(loaded_skills)} loaded"
        )
    except ImportError as e:
        return VerificationResult("Skill Registry", False, f"Import error: {e}")
    except Exception as e:
        return VerificationResult("Skill Registry", False, str(e))


def verify_file_structure() -> VerificationResult:
    """Verify expected file structure exists."""
    expected = [
        "autoflow/__init__.py",
        "autoflow/cli.py",
        "autoflow/core/__init__.py",
        "autoflow/core/config.py",
        "autoflow/core/state.py",
        "autoflow/core/orchestrator.py",
        "autoflow/agents/__init__.py",
        "autoflow/agents/base.py",
        "autoflow/agents/claude_code.py",
        "autoflow/agents/codex.py",
        "autoflow/agents/openclaw.py",
        "autoflow/tmux/__init__.py",
        "autoflow/tmux/session.py",
        "autoflow/tmux/manager.py",
        "autoflow/skills/__init__.py",
        "autoflow/skills/registry.py",
        "autoflow/skills/executor.py",
        "autoflow/scheduler/__init__.py",
        "autoflow/scheduler/daemon.py",
        "autoflow/scheduler/jobs.py",
        "autoflow/review/__init__.py",
        "autoflow/review/cross_review.py",
        "autoflow/ci/__init__.py",
        "autoflow/ci/verifier.py",
        "autoflow/ci/gates.py",
        "config/settings.example.json5",
        "pyproject.toml",
    ]

    missing = [f for f in expected if not Path(f).exists()]

    if missing:
        return VerificationResult(
            "File Structure",
            False,
            f"Missing {len(missing)} files",
            "\n".join(missing[:10])  # Show first 10
        )
    return VerificationResult("File Structure", True, f"All {len(expected)} expected files exist")


def run_all_verifications() -> list[VerificationResult]:
    """Run all verification steps."""
    results = []

    # Static checks (no dependencies needed)
    print("Running static checks...")
    results.append(verify_syntax())
    results.append(verify_file_structure())

    # Dependency check
    print("Checking dependencies...")
    dep_result = verify_dependencies()
    results.append(dep_result)

    if not dep_result.passed:
        print("\nDependencies missing. Please install them first:")
        print("  pip install -e '.[dev]'")
        return results

    # Import checks
    print("Verifying imports...")
    results.append(verify_imports())

    # CLI checks
    print("Testing CLI...")
    results.append(verify_cli_help())
    results.append(verify_init())
    results.append(verify_status())

    # Component checks
    print("Verifying components...")
    results.append(verify_agent_adapters())
    results.append(verify_skill_registry())

    # Test checks
    print("Running tests...")
    results.append(verify_tests())

    return results


def main():
    """Run all verifications and print results."""
    print("=" * 60)
    print("Autoflow End-to-End Verification")
    print("=" * 60)
    print()

    results = run_all_verifications()

    print()
    print("=" * 60)
    print("Results Summary")
    print("=" * 60)

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    for r in results:
        print(f"  {r}")

    print()
    print(f"Total: {passed} passed, {failed} failed")

    if failed > 0:
        print()
        print("Details for failed checks:")
        for r in results:
            if not r.passed and r.details:
                print(f"\n{r.name}:")
                print(f"  {r.details}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
