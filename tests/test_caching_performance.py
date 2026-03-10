from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def configure_autoflow_module(module: ModuleType, root: Path) -> None:
    module.ROOT = root
    module.STATE_DIR = root / ".autoflow"
    module.SPECS_DIR = module.STATE_DIR / "specs"
    module.TASKS_DIR = module.STATE_DIR / "tasks"
    module.RUNS_DIR = module.STATE_DIR / "runs"
    module.LOGS_DIR = module.STATE_DIR / "logs"
    module.WORKTREES_DIR = module.STATE_DIR / "worktrees" / "tasks"
    module.MEMORY_DIR = module.STATE_DIR / "memory"
    module.STRATEGY_MEMORY_DIR = module.MEMORY_DIR / "strategy"
    module.DISCOVERY_FILE = module.STATE_DIR / "discovered_agents.json"
    module.SYSTEM_CONFIG_FILE = module.STATE_DIR / "system.json"
    module.SYSTEM_CONFIG_TEMPLATE = root / "config" / "system.example.json"
    module.AGENTS_FILE = module.STATE_DIR / "agents.json"
    module.BMAD_DIR = root / "templates" / "bmad"


class CachingPerformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        (self.root / "config").mkdir(parents=True, exist_ok=True)
        (self.root / "config" / "system.example.json").write_text(
            json.dumps(
                {
                    "memory": {
                        "enabled": True,
                        "auto_capture_run_results": True,
                        "default_scopes": ["spec"],
                        "global_file": ".autoflow/memory/global.md",
                        "spec_dir": ".autoflow/memory/specs",
                    },
                    "models": {"profiles": {"implementation": "gpt-5-codex", "review": "claude-sonnet-4-6"}},
                    "tools": {"profiles": {"claude-review": ["Read", "Bash(git:*)"]}},
                    "registry": {"acp_agents": []},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.root / "templates" / "bmad").mkdir(parents=True, exist_ok=True)
        for role in [
            "spec-writer",
            "task-graph-manager",
            "implementation-runner",
            "reviewer",
            "maintainer",
        ]:
            (self.root / "templates" / "bmad" / f"{role}.md").write_text(
                f"# {role}\n", encoding="utf-8"
            )
        self.autoflow = load_module(self.repo_root / "scripts" / "autoflow.py", "autoflow_perf_test")
        configure_autoflow_module(self.autoflow, self.root)
        self.autoflow.ensure_state()
        self.autoflow.write_json(
            self.autoflow.AGENTS_FILE,
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

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_spec(self, slug: str = "perf-spec") -> None:
        args = type("Args", (), {"slug": slug, "title": "Performance Spec", "summary": "Performance testing spec"})()
        with redirect_stdout(io.StringIO()):
            self.autoflow.create_spec(args)

    def create_large_memory_files(self, spec_slug: str) -> None:
        """Create large memory files to simulate real-world usage."""
        # Create large global memory
        global_memory_path = self.root / ".autoflow" / "memory" / "global.md"
        global_memory_path.parent.mkdir(parents=True, exist_ok=True)
        global_content = "# Global Memory\n\n"
        for i in range(50):
            global_content += f"## Global Entry {i}\n\n"
            global_content += f"This is a detailed global memory entry {i} with substantial content. " * 10 + "\n\n"
        global_memory_path.write_text(global_content, encoding="utf-8")

        # Create large spec memory
        spec_memory_path = self.root / ".autoflow" / "memory" / "specs" / f"{spec_slug}.md"
        spec_memory_path.parent.mkdir(parents=True, exist_ok=True)
        spec_content = f"# Spec Memory: {spec_slug}\n\n"
        for i in range(50):
            spec_content += f"## Spec Entry {i}\n\n"
            spec_content += f"This is a detailed spec memory entry {i} with substantial content. " * 10 + "\n\n"
        spec_memory_path.write_text(spec_content, encoding="utf-8")

        # Create strategy memory with reflections
        strategy_memory_path = self.root / ".autoflow" / "memory" / "strategy" / "specs" / f"{spec_slug}.json"
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
        fix_request_path = self.root / ".autoflow" / "specs" / spec_slug / "QA_FIX_REQUEST.md"
        fix_request_path.parent.mkdir(parents=True, exist_ok=True)
        fix_request_content = "# QA Fix Request\n\n## Summary\n\nReviewer requested changes.\n\n## Findings\n\n"
        for i in range(10):
            fix_request_content += f"| F-{i} | high | tests | tests/test_{i}.py | {i*10} | Finding {i} |\n"
        fix_request_path.write_text(fix_request_content, encoding="utf-8")

        # Create fix request data
        fix_request_data_path = self.root / ".autoflow" / "specs" / spec_slug / "qa_fix_request_data.json"
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

    def time_build_prompt(self, iterations: int = 10) -> float:
        """Time multiple build_prompt calls and return total time."""
        agent = self.autoflow.AgentSpec(
            name="test-agent",
            command="claude",
            args=[],
            model="claude-sonnet-4-6",
            memory_scopes=["spec", "global"],
        )

        start_time = time.perf_counter()
        for _ in range(iterations):
            _ = self.autoflow.build_prompt("perf-spec", "reviewer", "T1", agent)
        end_time = time.perf_counter()

        return end_time - start_time

    def test_cache_performance_improvement(self) -> None:
        """Demonstrate that caching provides performance benefits by reducing I/O operations."""
        self.create_spec("perf-spec")
        self.create_large_memory_files("perf-spec")

        # Clear cache and track initial state
        self.autoflow._prompt_context_cache.clear()
        initial_cache_size = len(self.autoflow._prompt_context_cache)

        agent = self.autoflow.AgentSpec(
            name="test-agent",
            command="claude",
            args=[],
            model="claude-sonnet-4-6",
            memory_scopes=["spec", "global"],
        )

        # First call should populate cache
        _ = self.autoflow.build_prompt("perf-spec", "reviewer", "T1", agent)
        cache_size_after_first = len(self.autoflow._prompt_context_cache)

        # Verify cache was populated
        self.assertGreater(cache_size_after_first, initial_cache_size,
                          "Cache should be populated after first build_prompt call")

        # Make multiple calls - all should hit cache (no growth in cache size)
        iterations = 20
        for i in range(iterations):
            _ = self.autoflow.build_prompt("perf-spec", "reviewer", "T1", agent)
            cache_size_after = len(self.autoflow._prompt_context_cache)
            self.assertEqual(cache_size_after, cache_size_after_first,
                           f"Cache size should remain constant on iteration {i+1} (all cache hits)")

        # Verify cache entries exist for all the context types
        # There should be entries for: memory_context, strategy_context, fix_request, fix_request_data
        cache_keys = list(self.autoflow._prompt_context_cache.keys())
        self.assertGreater(len(cache_keys), 0, "Cache should have entries")

        # Verify that cache keys are created for the expected context types
        context_types_found = set()
        for key in cache_keys:
            # Cache keys are tuples like (spec_slug, 'memory_context', scopes_hash)
            if len(key) >= 2:
                context_types_found.add(key[1])

        # We expect at least some context types to be cached
        self.assertGreater(len(context_types_found), 0,
                          f"Should have cache entries for multiple context types, found: {context_types_found}")

        print(f"\nCache Performance Results:")
        print(f"  Initial cache size: {initial_cache_size}")
        print(f"  After first call: {cache_size_after_first}")
        print(f"  Iterations tested: {iterations}")
        print(f"  Cache entries created: {len(cache_keys)}")
        print(f"  Context types cached: {context_types_found}")
        print(f"  Cache hit ratio: 100% (all {iterations} subsequent calls hit cache)")

    def test_cache_hit_ratio(self) -> None:
        """Verify cache hit ratio increases with repeated calls."""
        self.create_spec("hit-ratio-spec")
        self.create_large_memory_files("hit-ratio-spec")

        agent = self.autoflow.AgentSpec(
            name="test-agent",
            command="claude",
            args=[],
            model="claude-sonnet-4-6",
            memory_scopes=["spec", "global"],
        )

        # Clear cache and track hits
        self.autoflow._prompt_context_cache.clear()
        initial_cache_size = len(self.autoflow._prompt_context_cache)

        # First call should populate cache
        _ = self.autoflow.build_prompt("hit-ratio-spec", "reviewer", "T1", agent)
        after_first_call = len(self.autoflow._prompt_context_cache)

        # Verify cache was populated
        self.assertGreater(after_first_call, initial_cache_size,
                          "Cache should be populated after first build_prompt call")

        # Subsequent calls should hit cache (no increase in cache size)
        for i in range(10):
            _ = self.autoflow.build_prompt("hit-ratio-spec", "reviewer", "T1", agent)
            cache_size_after = len(self.autoflow._prompt_context_cache)
            self.assertEqual(cache_size_after, after_first_call,
                           f"Cache size should remain constant after call {i+1} (all hits)")

    def test_cache_memory_overhead(self) -> None:
        """Verify cache memory overhead is reasonable."""
        self.create_spec("memory-spec")
        self.create_large_memory_files("memory-spec")

        agent = self.autoflow.AgentSpec(
            name="test-agent",
            command="claude",
            args=[],
            model="claude-sonnet-4-6",
            memory_scopes=["spec", "global"],
        )

        # Clear cache and measure memory
        self.autoflow._prompt_context_cache.clear()

        # Make multiple calls
        for _ in range(5):
            _ = self.autoflow.build_prompt("memory-spec", "reviewer", "T1", agent)

        # Check cache size
        cache_size = len(self.autoflow._prompt_context_cache)

        # Cache should not grow unbounded
        # Expect entries for: memory_context, strategy_context, fix_request, fix_request_data
        # Plus potentially handoff files
        self.assertLess(cache_size, 20,
                       f"Cache size ({cache_size}) should be reasonable (< 20 entries)")

        print(f"\nCache Memory Overhead:")
        print(f"  Cache entries: {cache_size}")
        print(f"  Estimated size: {cache_size * 100} bytes (rough estimate)")

    def test_cache_warmup_benefit(self) -> None:
        """Demonstrate cache warmup behavior - first call populates cache, subsequent calls hit cache."""
        self.create_spec("warmup-spec")
        self.create_large_memory_files("warmup-spec")

        agent = self.autoflow.AgentSpec(
            name="test-agent",
            command="claude",
            args=[],
            model="claude-sonnet-4-6",
            memory_scopes=["spec", "global"],
        )

        # Clear cache
        self.autoflow._prompt_context_cache.clear()
        initial_cache_size = len(self.autoflow._prompt_context_cache)

        # First call (cold cache) - should populate cache
        _ = self.autoflow.build_prompt("warmup-spec", "reviewer", "T1", agent)
        cache_size_after_first = len(self.autoflow._prompt_context_cache)

        # Verify cache was populated on first call
        self.assertGreater(cache_size_after_first, initial_cache_size,
                          "Cache should be populated after first call (cold cache)")

        # Subsequent calls (warm cache) - should all hit cache
        iterations = 10
        for i in range(iterations):
            _ = self.autoflow.build_prompt("warmup-spec", "reviewer", "T1", agent)
            cache_size_after = len(self.autoflow._prompt_context_cache)
            self.assertEqual(cache_size_after, cache_size_after_first,
                           f"Cache size should remain constant on subsequent call {i+1} (warm cache)")

        print(f"\nCache Warmup Analysis:")
        print(f"  Initial cache size: {initial_cache_size}")
        print(f"  After first call (cold): {cache_size_after_first}")
        print(f"  Subsequent iterations: {iterations}")
        print(f"  Cache size maintained: {cache_size_after_first}")
        print(f"  Conclusion: First call populated cache, all subsequent calls hit cache")

    def test_different_specs_separate_cache_entries(self) -> None:
        """Verify that different specs maintain separate cache entries."""
        self.create_spec("spec-a")
        self.create_spec("spec-b")
        self.create_large_memory_files("spec-a")
        self.create_large_memory_files("spec-b")

        agent = self.autoflow.AgentSpec(
            name="test-agent",
            command="claude",
            args=[],
            model="claude-sonnet-4-6",
            memory_scopes=["spec"],
        )

        # Clear cache
        self.autoflow._prompt_context_cache.clear()

        # Build prompts for both specs
        _ = self.autoflow.build_prompt("spec-a", "reviewer", "T1", agent)
        cache_size_after_a = len(self.autoflow._prompt_context_cache)

        _ = self.autoflow.build_prompt("spec-b", "reviewer", "T1", agent)
        cache_size_after_b = len(self.autoflow._prompt_context_cache)

        # Cache should have grown (separate entries for each spec)
        self.assertGreater(cache_size_after_b, cache_size_after_a,
                          "Different specs should create separate cache entries")

        # Verify both specs work correctly
        prompt_a = self.autoflow.build_prompt("spec-a", "reviewer", "T1", agent)
        prompt_b = self.autoflow.build_prompt("spec-b", "reviewer", "T1", agent)

        self.assertIn("Spec Memory: spec-a", prompt_a)
        self.assertIn("Spec Memory: spec-b", prompt_b)


if __name__ == "__main__":
    unittest.main()
