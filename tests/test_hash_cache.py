"""Unit tests for cached file hashing in scripts/autoflow.py."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import ModuleType


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
    module.clear_hash_cache()


class HashCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "config").mkdir(parents=True, exist_ok=True)
        (self.root / "config" / "system.example.json").write_text("{}\n", encoding="utf-8")
        (self.root / "templates" / "bmad").mkdir(parents=True, exist_ok=True)
        self.autoflow = load_module(
            self.repo_root / "scripts" / "autoflow.py",
            "autoflow_hash_cache_test",
        )
        configure_autoflow_module(self.autoflow, self.root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_compute_file_hash_uses_cache_until_mtime_changes(self) -> None:
        test_file = self.root / "spec.md"
        test_file.write_text("version-one", encoding="utf-8")

        first_hash = self.autoflow.compute_file_hash(test_file)
        self.assertEqual(len(self.autoflow._file_hash_cache), 1)
        self.assertIn(test_file, self.autoflow._file_mtime_cache)

        second_hash = self.autoflow.compute_file_hash(test_file)
        self.assertEqual(first_hash, second_hash)
        self.assertEqual(len(self.autoflow._file_hash_cache), 1)

        test_file.write_text("version-two", encoding="utf-8")
        bumped_mtime = time.time() + 5
        os.utime(test_file, (bumped_mtime, bumped_mtime))

        updated_hash = self.autoflow.compute_file_hash(test_file)
        self.assertNotEqual(first_hash, updated_hash)
        self.assertEqual(self.autoflow._file_hash_cache[test_file], updated_hash)

    def test_clear_hash_cache_empties_hash_and_mtime_caches(self) -> None:
        test_file = self.root / "contract.json"
        test_file.write_text('{"task": "T1"}', encoding="utf-8")

        self.autoflow.compute_file_hash(test_file)
        self.assertTrue(self.autoflow._file_hash_cache)
        self.assertTrue(self.autoflow._file_mtime_cache)

        self.autoflow.clear_hash_cache()
        self.assertEqual(self.autoflow._file_hash_cache, {})
        self.assertEqual(self.autoflow._file_mtime_cache, {})
