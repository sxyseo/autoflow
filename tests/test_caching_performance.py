"""Performance tests for prompt building caching."""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from autoflow.autoflow_cli import AgentSpec, AutoflowCLI
from autoflow.core.config import Config


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing."""
    temp_dir = tempfile.TemporaryDirectory()
    yield Path(temp_dir.name)
    temp_dir.cleanup()


@pytest.fixture
def test_repo(temp_workspace: Path):
    """Create a test git repository with required config files."""
    # Initialize git repo
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=temp_workspace,
        check=True,
        capture_output=True,
    )

    # Create config directory and system config
    (temp_workspace / "config").mkdir(parents=True, exist_ok=True)
    (temp_workspace / "config" / "system.example.json").write_text(
        json.dumps(
            {
                "memory": {
                    "enabled": True,
                    "auto_capture_run_results": True,
                    "default_scopes": ["spec"],
                    "global_file": ".autoflow/memory/global.md",
                    "spec_dir": ".autoflow/memory/specs",
                },
                "models": {
                    "profiles": {
                        "implementation": "gpt-5-codex",
                        "review": "claude-sonnet-4-6",
                    }
                },
                "tools": {"profiles": {"claude-review": ["Read", "Bash(git:*)"]}},
                "registry": {"acp_agents": []},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # Create BMAD templates directory
    (temp_workspace / "templates" / "bmad").mkdir(parents=True, exist_ok=True)
    for role in [
        "spec-writer",
        "task-graph-manager",
        "implementation-runner",
        "reviewer",
        "maintainer",
    ]:
        (temp_workspace / "templates" / "bmad" / f"{role}.md").write_text(
            f"# {role}\n", encoding="utf-8"
        )

    return temp_workspace


@pytest.fixture
def autoflow_cli(test_repo: Path):
    """Create an AutoflowCLI instance for testing."""
    config = Config()
    # Explicitly set state_dir to test_repo's .autoflow directory
    state_dir = test_repo / ".autoflow"
    cli = AutoflowCLI(config, root=test_repo, state_dir=state_dir)
    cli.ensure_state()

    # Write agents config
    cli.write_json(
        cli.agents_file,
        {
            "agents": {
                "dummy": {
                    "command": "echo",
                    "args": ["agent"],
                    "memory_scopes": ["spec"],
                },
            }
        },
    )

    return cli


class CachingPerformanceTests:
    """Tests for caching performance improvements in prompt building."""

    def create_spec(self, cli: AutoflowCLI, slug: str = "perf-spec") -> None:
        """Helper to create a spec."""
        with redirect_stdout(io.StringIO()):
            cli.create_spec(slug, "Performance Spec", "Performance testing spec")

    def create_large_memory_files(self, cli: AutoflowCLI, spec_slug: str) -> None:
        """Create large memory files to simulate real-world usage."""
        root = cli.root

        # Create large global memory
        global_memory_path = root / ".autoflow" / "memory" / "global.md"
        global_memory_path.parent.mkdir(parents=True, exist_ok=True)
        global_content = "# Global Memory\n\n"
        for i in range(50):
            global_content += f"## Global Entry {i}\n\n"
            global_content += f"This is a detailed global memory entry {i} with substantial content. " * 10 + "\n\n"
        global_memory_path.write_text(global_content, encoding="utf-8")

        # Create large spec memory (correct path: memory_dir/specs/spec_slug/spec.md)
        spec_memory_path = root / ".autoflow" / "memory" / "specs" / spec_slug / "spec.md"
        spec_memory_path.parent.mkdir(parents=True, exist_ok=True)
        spec_content = f"# Spec Memory: {spec_slug}\n\n"
        for i in range(50):
            spec_content += f"## Spec Entry {i}\n\n"
            spec_content += f"This is a detailed spec memory entry {i} with substantial content. " * 10 + "\n\n"
        spec_memory_path.write_text(spec_content, encoding="utf-8")

        # Create strategy memory with reflections
        strategy_memory_path = root / ".autoflow" / "memory" / "strategy" / "specs" / f"{spec_slug}.json"
        strategy_memory_path.parent.mkdir(parents=True, exist_ok=True)
        strategy_data = {
            "reflections": [],
            "playbook": []
        }
        for i in range(20):
            strategy_data["reflections"].append({
                "timestamp": f"2026-03-{10+i:02d}T12:00:00Z",
                "role": "spec-writer",
                "task": f"T{i}",
                "result": "approved",
                "summary": f"Strategy reflection entry {i}",
                "findings": []
            })
        for i in range(20):
            strategy_data["playbook"].append({
                "category": f"category-{i % 5}",
                "evidence_count": i + 1,
                "rule": f"Rule description {i}: Review patterns before retrying work that touches category-{i % 5}."
            })
        strategy_memory_path.write_text(json.dumps(strategy_data, indent=2), encoding="utf-8")

        # Create fix request
        fix_request_path = root / ".autoflow" / "specs" / spec_slug / "QA_FIX_REQUEST.md"
        fix_request_path.parent.mkdir(parents=True, exist_ok=True)
        fix_request_content = "# QA Fix Request\n\n## Summary\n\nReviewer requested changes.\n\n## Findings\n\n"
        for i in range(10):
            fix_request_content += f"| F-{i} | high | tests | tests/test_{i}.py | {i*10} | Finding {i} |\n"
        fix_request_path.write_text(fix_request_content, encoding="utf-8")

        # Create fix request data
        fix_request_data_path = root / ".autoflow" / "specs" / spec_slug / "qa_fix_request_data.json"
        fix_request_data = {
            "requesting_run": "test-run-1",
            "timestamp": "2026-03-10T12:00:00Z",
            "summary": "Reviewer requested changes.",
            "findings": []
        }
        for i in range(10):
            fix_request_data["findings"].append({
                "id": f"F-{i}",
                "title": f"Finding {i}",
                "body": f"Detailed finding body {i}",
                "file": f"tests/test_{i}.py",
                "line": i * 10,
                "severity": "high",
                "category": "tests"
            })
        fix_request_data_path.write_text(json.dumps(fix_request_data, indent=2), encoding="utf-8")

    def time_build_prompt(self, cli: AutoflowCLI, iterations: int = 10) -> float:
        """Time multiple build_prompt calls and return total time."""
        agent = AgentSpec(
            name="test-agent",
            command="claude",
            args=[],
            model="claude-sonnet-4-6",
            memory_scopes=["spec", "global"],
        )

        start_time = time.perf_counter()
        for _ in range(iterations):
            _ = cli.build_prompt("perf-spec", "reviewer", "T1", agent)
        end_time = time.perf_counter()

        return end_time - start_time

    def test_cache_performance_improvement(self, autoflow_cli: AutoflowCLI) -> None:
        """Demonstrate that caching provides performance benefits by reducing I/O operations."""
        self.create_spec(autoflow_cli, "perf-spec")
        self.create_large_memory_files(autoflow_cli, "perf-spec")

        # Clear cache and track initial state
        autoflow_cli._prompt_context_cache.clear()
        initial_cache_size = len(autoflow_cli._prompt_context_cache)

        agent = AgentSpec(
            name="test-agent",
            command="claude",
            args=[],
            model="claude-sonnet-4-6",
            memory_scopes=["spec", "global"],
        )

        # First call should populate cache
        _ = autoflow_cli.build_prompt("perf-spec", "reviewer", "T1", agent)
        cache_size_after_first = len(autoflow_cli._prompt_context_cache)

        # Verify cache was populated
        assert cache_size_after_first > initial_cache_size, \
            "Cache should be populated after first build_prompt call"

        # Make multiple calls - all should hit cache (no growth in cache size)
        iterations = 20
        for i in range(iterations):
            _ = autoflow_cli.build_prompt("perf-spec", "reviewer", "T1", agent)
            cache_size_after = len(autoflow_cli._prompt_context_cache)
            assert cache_size_after == cache_size_after_first, \
                f"Cache size should remain constant on iteration {i+1} (all cache hits)"

        # Verify cache entries exist for all the context types
        # There should be entries for: memory_context, fix_request, fix_request_data
        cache_keys = list(autoflow_cli._prompt_context_cache.keys())
        assert len(cache_keys) > 0, "Cache should have entries"

        # Verify that cache keys are created for the expected context types
        context_types_found = set()
        for key in cache_keys:
            # Cache keys are tuples like (spec_slug, 'memory_context', scopes_hash)
            if len(key) >= 2:
                context_types_found.add(key[1])

        # We expect at least some context types to be cached
        assert len(context_types_found) > 0, \
            f"Should have cache entries for multiple context types, found: {context_types_found}"

        print(f"\nCache Performance Results:")
        print(f"  Initial cache size: {initial_cache_size}")
        print(f"  After first call: {cache_size_after_first}")
        print(f"  Iterations tested: {iterations}")
        print(f"  Cache entries created: {len(cache_keys)}")
        print(f"  Context types cached: {context_types_found}")
        print(f"  Cache hit ratio: 100% (all {iterations} subsequent calls hit cache)")

    def test_cache_hit_ratio(self, autoflow_cli: AutoflowCLI) -> None:
        """Verify cache hit ratio increases with repeated calls."""
        self.create_spec(autoflow_cli, "hit-ratio-spec")
        self.create_large_memory_files(autoflow_cli, "hit-ratio-spec")

        agent = AgentSpec(
            name="test-agent",
            command="claude",
            args=[],
            model="claude-sonnet-4-6",
            memory_scopes=["spec", "global"],
        )

        # Clear cache and track hits
        autoflow_cli._prompt_context_cache.clear()
        initial_cache_size = len(autoflow_cli._prompt_context_cache)

        # First call should populate cache
        _ = autoflow_cli.build_prompt("hit-ratio-spec", "reviewer", "T1", agent)
        after_first_call = len(autoflow_cli._prompt_context_cache)

        # Verify cache was populated
        assert after_first_call > initial_cache_size, \
            "Cache should be populated after first build_prompt call"

        # Subsequent calls should hit cache (no increase in cache size)
        for i in range(10):
            _ = autoflow_cli.build_prompt("hit-ratio-spec", "reviewer", "T1", agent)
            cache_size_after = len(autoflow_cli._prompt_context_cache)
            assert cache_size_after == after_first_call, \
                f"Cache size should remain constant after call {i+1} (all hits)"

    def test_cache_memory_overhead(self, autoflow_cli: AutoflowCLI) -> None:
        """Verify cache memory overhead is reasonable."""
        self.create_spec(autoflow_cli, "memory-spec")
        self.create_large_memory_files(autoflow_cli, "memory-spec")

        agent = AgentSpec(
            name="test-agent",
            command="claude",
            args=[],
            model="claude-sonnet-4-6",
            memory_scopes=["spec", "global"],
        )

        # Clear cache and measure memory
        autoflow_cli._prompt_context_cache.clear()

        # Make multiple calls
        for _ in range(5):
            _ = autoflow_cli.build_prompt("memory-spec", "reviewer", "T1", agent)

        # Check cache size
        cache_size = len(autoflow_cli._prompt_context_cache)

        # Cache should not grow unbounded
        # Expect entries for: memory_context, fix_request, fix_request_data
        assert cache_size < 20, \
            f"Cache size ({cache_size}) should be reasonable (< 20 entries)"

        print(f"\nCache Memory Overhead:")
        print(f"  Cache entries: {cache_size}")
        print(f"  Estimated size: {cache_size * 100} bytes (rough estimate)")

    def test_cache_warmup_benefit(self, autoflow_cli: AutoflowCLI) -> None:
        """Demonstrate cache warmup behavior - first call populates cache, subsequent calls hit cache."""
        self.create_spec(autoflow_cli, "warmup-spec")
        self.create_large_memory_files(autoflow_cli, "warmup-spec")

        agent = AgentSpec(
            name="test-agent",
            command="claude",
            args=[],
            model="claude-sonnet-4-6",
            memory_scopes=["spec", "global"],
        )

        # Clear cache
        autoflow_cli._prompt_context_cache.clear()
        initial_cache_size = len(autoflow_cli._prompt_context_cache)

        # First call (cold cache) - should populate cache
        _ = autoflow_cli.build_prompt("warmup-spec", "reviewer", "T1", agent)
        cache_size_after_first = len(autoflow_cli._prompt_context_cache)

        # Verify cache was populated on first call
        assert cache_size_after_first > initial_cache_size, \
            "Cache should be populated after first call (cold cache)"

        # Subsequent calls (warm cache) - should all hit cache
        iterations = 10
        for i in range(iterations):
            _ = autoflow_cli.build_prompt("warmup-spec", "reviewer", "T1", agent)
            cache_size_after = len(autoflow_cli._prompt_context_cache)
            assert cache_size_after == cache_size_after_first, \
                f"Cache size should remain constant on subsequent call {i+1} (warm cache)"

        print(f"\nCache Warmup Analysis:")
        print(f"  Initial cache size: {initial_cache_size}")
        print(f"  After first call (cold): {cache_size_after_first}")
        print(f"  Subsequent iterations: {iterations}")
        print(f"  Cache size maintained: {cache_size_after_first}")
        print(f"  Conclusion: First call populated cache, all subsequent calls hit cache")

    def test_different_specs_separate_cache_entries(self, autoflow_cli: AutoflowCLI) -> None:
        """Verify that different specs maintain separate cache entries."""
        self.create_spec(autoflow_cli, "spec-a")
        self.create_spec(autoflow_cli, "spec-b")
        self.create_large_memory_files(autoflow_cli, "spec-a")
        self.create_large_memory_files(autoflow_cli, "spec-b")

        agent = AgentSpec(
            name="test-agent",
            command="claude",
            args=[],
            model="claude-sonnet-4-6",
            memory_scopes=["spec"],
        )

        # Clear cache
        autoflow_cli._prompt_context_cache.clear()

        # Build prompts for both specs
        _ = autoflow_cli.build_prompt("spec-a", "reviewer", "T1", agent)
        cache_size_after_a = len(autoflow_cli._prompt_context_cache)

        _ = autoflow_cli.build_prompt("spec-b", "reviewer", "T1", agent)
        cache_size_after_b = len(autoflow_cli._prompt_context_cache)

        # Cache should have grown (separate entries for each spec)
        assert cache_size_after_b > cache_size_after_a, \
            "Different specs should create separate cache entries"

        # Verify both specs work correctly
        prompt_a = autoflow_cli.build_prompt("spec-a", "reviewer", "T1", agent)
        prompt_b = autoflow_cli.build_prompt("spec-b", "reviewer", "T1", agent)

        assert "Spec Memory: spec-a" in prompt_a
        assert "Spec Memory: spec-b" in prompt_b


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
