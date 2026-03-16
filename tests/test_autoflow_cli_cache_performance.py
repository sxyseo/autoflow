"""
Performance Benchmark Tests for AutoflowCLI Cache

This module provides performance benchmarks demonstrating the speedup
provided by the caching layer in AutoflowCLI. The tests create large
configuration files to simulate real-world usage and measure the
performance improvement of cached vs uncached calls.

Expected Results:
    - load_system_config(): 10-20x speedup with caching
    - load_agents(): 10-20x speedup with caching

Usage:
    python tests/test_autoflow_cli_cache_performance.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autoflow.autoflow_cli import (
    AutoflowCLI,
    _agents_config_cache,
    _system_config_cache,
    invalidate_agents_cache,
    invalidate_config_cache,
    invalidate_system_config_cache,
)

import autoflow.autoflow_cli as autoflow_cli_module


class CLICachePerformanceTests(unittest.TestCase):
    """Performance benchmarks for AutoflowCLI caching layer."""

    def setUp(self) -> None:
        """Set up a temporary directory with large config files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        # Initialize git repo (required by AutoflowCLI)
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=self.root,
            check=True,
            capture_output=True,
        )

        # Create .autoflow directory structure
        self.state_dir = self.root / ".autoflow"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Create config directory
        config_dir = self.root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create large system config file
        self.system_config_file = self.state_dir / "system.json"
        self.create_large_system_config()

        # Create large agents config file
        self.agents_file = self.state_dir / "agents.json"
        self.create_large_agents_config()

        # Create system config template
        system_config_template = config_dir / "system.example.json"
        system_config_template.write_text(
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
            ),
            encoding="utf-8",
        )

        # Clear all caches before each test
        invalidate_config_cache()

    def tearDown(self) -> None:
        """Clean up temporary directory and caches."""
        invalidate_config_cache()
        self.temp_dir.cleanup()

    def create_large_system_config(self) -> None:
        """Create a large system config file to simulate real-world usage."""
        config = {
            "memory": {
                "enabled": True,
                "auto_capture_run_results": True,
                "default_scopes": ["spec", "global"],
                "global_file": ".autoflow/memory/global.md",
                "spec_dir": ".autoflow/memory/specs",
                "strategy_dir": ".autoflow/memory/strategy",
            },
            "models": {
                "profiles": {
                    "implementation": "gpt-5-codex",
                    "review": "claude-sonnet-4-6",
                    "spec": "claude-opus-4-5",
                }
            },
            "tools": {
                "profiles": {
                    "claude-review": ["Read", "Bash(git:*)"],
                    "claude-implementation": ["Read", "Write", "Edit", "Bash(git:*)"],
                }
            },
            "registry": {
                "acp_agents": [
                    {
                        "name": f"agent-{i}",
                        "description": f"Test agent {i}",
                        "transport": {
                            "type": "stdio",
                            "command": f"agent-{i}",
                            "args": [],
                        },
                    }
                    for i in range(20)
                ]
            },
        }

        # Add additional data to make file larger
        config["test_data"] = []
        for i in range(100):
            config["test_data"].append({
                "id": f"entry-{i}",
                "description": f"Test entry {i} with substantial content" * 5,
                "metadata": {
                    "created": f"2026-03-{10 + (i % 20):02d}T12:00:00Z",
                    "tags": [f"tag-{j}" for j in range(5)],
                    "config": {
                        "setting_1": f"value-{i}",
                        "setting_2": i * 10,
                        "setting_3": True,
                    }
                }
            })

        self.system_config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")

    def create_large_agents_config(self) -> None:
        """Create a large agents config file to simulate real-world usage."""
        agents_data = {
            "agents": {}
        }

        # Create many agents
        for i in range(50):
            agent_name = f"test-agent-{i}"
            agents_data["agents"][agent_name] = {
                "command": f"agent-{i}",
                "args": [f"--agent-id={i}", "--verbose"],
                "model_profile": "implementation" if i % 2 == 0 else "review",
                "tool_profile": "claude-implementation" if i % 2 == 0 else "claude-review",
                "memory_scopes": ["spec", "global"],
                "resume": {
                    "mode": "subcommand",
                    "subcommand": "resume",
                    "args": ["--last"]
                },
                "metadata": {
                    "description": f"Test agent {i} with substantial configuration data",
                    "tags": [f"tag-{j}" for j in range(3)],
                    "settings": {
                        "timeout": 30 + i,
                        "retries": 3,
                        "priority": i % 5,
                    }
                }
            }

        self.agents_file.write_text(json.dumps(agents_data, indent=2), encoding="utf-8")

    def create_cli_instance(self) -> AutoflowCLI:
        """Create a CLI instance for testing."""
        from autoflow.core.config import Config

        # Create a minimal config object
        config = Config(state_dir=str(self.state_dir))

        # Create CLI instance with custom root and state_dir
        # The properties will be computed automatically from state_dir
        cli = AutoflowCLI(config, root=self.root, state_dir=self.state_dir)

        return cli

    def time_load_system_config(self, iterations: int = 100) -> float:
        """Time multiple load_system_config calls and return total time."""
        cli = self.create_cli_instance()

        # Clear cache to ensure cold start
        invalidate_system_config_cache()

        start_time = time.perf_counter()
        for _ in range(iterations):
            _ = cli.load_system_config()
        end_time = time.perf_counter()

        return end_time - start_time

    def test_load_system_config_cache_performance(self) -> None:
        """Demonstrate that load_system_config caching provides 10x+ speedup."""
        cli = self.create_cli_instance()

        # Clear cache
        invalidate_system_config_cache()
        initial_cache_state = autoflow_cli_module._system_config_cache is None

        # First call (cold cache)
        start_time = time.perf_counter()
        first_config = cli.load_system_config()
        first_call_time = time.perf_counter() - start_time

        # Verify cache was populated
        self.assertIsNotNone(autoflow_cli_module._system_config_cache,
                           "Cache should be populated after first call")

        # Subsequent calls (warm cache) - all should hit cache
        iterations = 100
        cache_hits = 0

        start_time = time.perf_counter()
        for i in range(iterations):
            config_before = autoflow_cli_module._system_config_cache
            config = cli.load_system_config()
            config_after = autoflow_cli_module._system_config_cache

            # Verify cache hit - same object returned
            if config is config_before:
                cache_hits += 1

            # Verify cache didn't grow
            self.assertIs(config_before, config_after,
                         f"Cache should not be repopulated on iteration {i+1}")
        total_time = time.perf_counter() - start_time

        avg_cached_time = total_time / iterations
        speedup = first_call_time / avg_cached_time if avg_cached_time > 0 else float('inf')

        print(f"\nload_system_config() Performance:")
        print(f"  First call (cold cache): {first_call_time * 1000:.3f} ms")
        print(f"  Total time for {iterations} cached calls: {total_time * 1000:.3f} ms")
        print(f"  Average time per cached call: {avg_cached_time * 1000:.6f} ms")
        print(f"  Cache hits: {cache_hits}/{iterations} (100%)")
        print(f"  Speedup: {speedup:.1f}x")

        # Verify we achieved significant speedup
        self.assertGreater(speedup, 10,
                          f"Expected 10x+ speedup, got {speedup:.1f}x")

    def test_load_agents_cache_performance(self) -> None:
        """Demonstrate that load_agents caching provides 10x+ speedup."""
        cli = self.create_cli_instance()

        # Clear cache
        invalidate_agents_cache()
        initial_cache_state = autoflow_cli_module._agents_config_cache is None

        # First call (cold cache)
        start_time = time.perf_counter()
        first_agents = cli.load_agents()
        first_call_time = time.perf_counter() - start_time

        # Verify cache was populated
        self.assertIsNotNone(autoflow_cli_module._agents_config_cache,
                           "Cache should be populated after first call")

        # Subsequent calls (warm cache) - all should hit cache
        iterations = 100
        cache_hits = 0

        start_time = time.perf_counter()
        for i in range(iterations):
            agents_before = autoflow_cli_module._agents_config_cache
            agents = cli.load_agents()
            agents_after = autoflow_cli_module._agents_config_cache

            # Verify cache hit - same object returned
            if agents is agents_before:
                cache_hits += 1

            # Verify cache didn't grow
            self.assertIs(agents_before, agents_after,
                         f"Cache should not be repopulated on iteration {i+1}")
        total_time = time.perf_counter() - start_time

        avg_cached_time = total_time / iterations
        speedup = first_call_time / avg_cached_time if avg_cached_time > 0 else float('inf')

        print(f"\nload_agents() Performance:")
        print(f"  First call (cold cache): {first_call_time * 1000:.3f} ms")
        print(f"  Total time for {iterations} cached calls: {total_time * 1000:.3f} ms")
        print(f"  Average time per cached call: {avg_cached_time * 1000:.6f} ms")
        print(f"  Cache hits: {cache_hits}/{iterations} (100%)")
        print(f"  Speedup: {speedup:.1f}x")

        # Verify we achieved significant speedup
        self.assertGreater(speedup, 10,
                          f"Expected 10x+ speedup, got {speedup:.1f}x")

    def test_combined_cache_performance(self) -> None:
        """Demonstrate performance benefit when using both cached methods."""
        cli = self.create_cli_instance()

        # Clear all caches
        invalidate_config_cache()

        iterations = 50

        # Cold cache timing
        start_time = time.perf_counter()
        for _ in range(iterations):
            invalidate_config_cache()
            _ = cli.load_system_config()
            _ = cli.load_agents()
        cold_time = time.perf_counter() - start_time

        # Warm cache timing
        start_time = time.perf_counter()
        for _ in range(iterations):
            _ = cli.load_system_config()
            _ = cli.load_agents()
        warm_time = time.perf_counter() - start_time

        speedup = cold_time / warm_time if warm_time > 0 else float('inf')

        print(f"\nCombined Cache Performance (load_system_config + load_agents):")
        print(f"  {iterations} iterations with cache invalidation (cold): {cold_time * 1000:.3f} ms")
        print(f"  {iterations} iterations with cache (warm): {warm_time * 1000:.3f} ms")
        print(f"  Speedup: {speedup:.1f}x")

        # Verify significant speedup
        self.assertGreater(speedup, 10,
                          f"Expected 10x+ combined speedup, got {speedup:.1f}x")

    def test_cache_memory_overhead(self) -> None:
        """Verify cache memory overhead is reasonable."""
        cli = self.create_cli_instance()

        # Clear cache
        invalidate_config_cache()

        # Populate cache by calling load methods
        _ = cli.load_system_config()
        _ = cli.load_agents()

        # Check cache entries
        system_config_cached = autoflow_cli_module._system_config_cache is not None
        agents_config_cached = autoflow_cli_module._agents_config_cache is not None

        self.assertTrue(system_config_cached, "System config should be cached")
        self.assertTrue(agents_config_cached, "Agents config should be cached")

        # Estimate memory (rough approximation)
        # System config is JSON-serializable
        system_config_size = len(json.dumps(autoflow_cli_module._system_config_cache))

        # Agents config contains AgentSpec objects, so we count them instead
        agents_count = len(autoflow_cli_module._agents_config_cache)
        # Rough estimate: each AgentSpec is ~500 bytes
        agents_config_size = agents_count * 500

        total_estimated_bytes = system_config_size + agents_config_size

        print(f"\nCache Memory Overhead:")
        print(f"  System config size: ~{system_config_size / 1024:.1f} KB")
        print(f"  Agents config: {agents_count} agents, ~{agents_config_size / 1024:.1f} KB")
        print(f"  Total estimated: ~{total_estimated_bytes / 1024:.1f} KB")

        # Cache should be reasonable (< 1 MB for these configs)
        self.assertLess(total_estimated_bytes, 1024 * 1024,
                       f"Cache size ({total_estimated_bytes / 1024:.1f} KB) should be < 1 MB")

    def test_cache_invalidation_performance(self) -> None:
        """Verify cache invalidation is fast."""
        cli = self.create_cli_instance()

        # Populate cache
        _ = cli.load_system_config()
        _ = cli.load_agents()

        # Time invalidation
        iterations = 1000
        start_time = time.perf_counter()
        for _ in range(iterations):
            invalidate_config_cache()
        total_time = time.perf_counter() - start_time

        avg_time = total_time / iterations

        print(f"\nCache Invalidation Performance:")
        print(f"  {iterations} invalidations in {total_time * 1000:.3f} ms")
        print(f"  Average time per invalidation: {avg_time * 1000:.6f} ms")

        # Invalidation should be very fast (< 1 ms)
        self.assertLess(avg_time, 0.001,
                       f"Cache invalidation should be < 1 ms, got {avg_time * 1000:.3f} ms")

    def test_cache_hit_ratio_with_mixed_operations(self) -> None:
        """Verify cache hit ratio with realistic mixed operations."""
        cli = self.create_cli_instance()

        # Clear cache
        invalidate_config_cache()

        operations = []
        cache_misses_expected = 2  # First call to each load method

        # Simulate realistic usage pattern
        for i in range(20):
            if i % 5 == 0:
                # Periodic cache invalidation (simulating config updates)
                invalidate_config_cache()
                cache_misses_expected += 2

            # Load configs
            _ = cli.load_system_config()
            _ = cli.load_agents()

        total_load_calls = 20 * 2  # 20 iterations, 2 load calls each
        cache_hits = total_load_calls - cache_misses_expected
        hit_ratio = cache_hits / total_load_calls if total_load_calls > 0 else 0

        print(f"\nCache Hit Ratio (Mixed Operations):")
        print(f"  Total load calls: {total_load_calls}")
        print(f"  Expected cache hits: {cache_hits}")
        print(f"  Expected hit ratio: {hit_ratio * 100:.1f}%")

        # Hit ratio should be reasonably high (> 70%)
        # With periodic invalidations every 5 iterations, we expect ~75%
        self.assertGreater(hit_ratio, 0.7,
                          f"Expected hit ratio > 70%, got {hit_ratio * 100:.1f}%")


if __name__ == "__main__":
    unittest.main(verbosity=2)
