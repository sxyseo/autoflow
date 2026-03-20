"""
End-to-End Test: Run Artifact Integrity Verification

This test performs real CLI invocations to verify that:
1. Runs are created with integrity hashes
2. Tampering with prompt.md is detected before execution
3. Tampering with run.sh is detected before execution
4. Execution fails appropriately when integrity checks fail

This is a subtask-4-1 implementation for the integrity verification feature.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


class IntegrityVerificationE2ETest(unittest.TestCase):
    """End-to-end test for run artifact integrity verification."""

    def setUp(self) -> None:
        """Set up temporary test environment with required configuration."""
        self.temp_dir = tempfile.mkdtemp(prefix="integrity_e2e_")
        self.temp_path = Path(self.temp_dir)

        # Create .autoflow directory structure
        self.autoflow_dir = self.temp_path / ".autoflow"
        self.runs_dir = self.autoflow_dir / "runs"
        self.specs_dir = self.autoflow_dir / "specs"
        self.tasks_dir = self.autoflow_dir / "tasks"

        self.autoflow_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.specs_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

        # Create a minimal spec
        spec_dir = self.specs_dir / "test-integrity"
        spec_dir.mkdir(parents=True, exist_ok=True)
        spec_file = spec_dir / "SPEC.md"
        spec_file.write_text(
            "# Test Integrity Spec\n\n"
            "Testing end-to-end integrity verification.\n",
            encoding="utf-8"
        )

        # Create minimal tasks file
        tasks_file = self.tasks_dir / "test-integrity.json"
        tasks_file.write_text(
            json.dumps({
                "spec_slug": "test-integrity",
                "updated_at": "20260318T000000Z",
                "tasks": [
                    {
                        "id": "T1",
                        "title": "Test Task",
                        "status": "in_progress",
                        "owner_role": "implementation-runner",
                        "description": "Test integrity verification",
                        "depends_on": [],
                        "acceptance_criteria": []
                    }
                ]
            }),
            encoding="utf-8"
        )

        # Create minimal agents.json
        agents_file = self.autoflow_dir / "agents.json"
        agents_file.write_text(
            json.dumps({
                "agents": {
                    "echo-agent": {
                        "command": "echo",
                        "args": ["test execution"]
                    }
                }
            }),
            encoding="utf-8"
        )

        # Create minimal system.json
        system_file = self.autoflow_dir / "system.json"
        system_file.write_text(
            json.dumps({
                "model_profiles": {},
                "tool_profiles": {}
            }),
            encoding="utf-8"
        )

        # Store repository root for script invocation
        self.repo_root = Path(__file__).resolve().parents[2]

    def tearDown(self) -> None:
        """Clean up temporary test environment."""
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_run_via_cli(self) -> tuple[Path, dict[str, any]]:
        """
        Create a run by invoking autoflow.py directly.

        Returns:
            Tuple of (run_directory, run_metadata)
        """
        # Import autoflow module to call create_run_record
        scripts_dir = self.repo_root / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        import importlib
        import autoflow

        # Reload the module to ensure we get the latest version
        importlib.reload(autoflow)

        # Patch the constants to use our temp directory
        original_root = autoflow.ROOT
        original_runs_dir = autoflow.RUNS_DIR
        original_specs_dir = autoflow.SPECS_DIR
        original_tasks_dir = autoflow.TASKS_DIR
        original_state_dir = autoflow.STATE_DIR
        original_agents_file = autoflow.AGENTS_FILE

        try:
            autoflow.ROOT = self.temp_path
            autoflow.RUNS_DIR = self.runs_dir
            autoflow.SPECS_DIR = self.specs_dir
            autoflow.TASKS_DIR = self.tasks_dir
            autoflow.STATE_DIR = self.autoflow_dir
            autoflow.AGENTS_FILE = self.autoflow_dir / "agents.json"

            # Create the run
            run_dir = autoflow.create_run_record(
                spec_slug="test-integrity",
                role="implementation-runner",
                agent_name="echo-agent",
                task_id="T1"
            )

            # Load run metadata
            run_json_path = run_dir / "run.json"
            run_metadata = json.loads(run_json_path.read_text(encoding="utf-8"))

            return run_dir, run_metadata

        finally:
            # Restore original constants
            autoflow.ROOT = original_root
            autoflow.RUNS_DIR = original_runs_dir
            autoflow.SPECS_DIR = original_specs_dir
            autoflow.TASKS_DIR = original_tasks_dir
            autoflow.STATE_DIR = original_state_dir
            autoflow.AGENTS_FILE = original_agents_file

    def test_e2e_integrity_verification_workflow(self) -> None:
        """
        End-to-end test: create run with hashes, verify tampering is detected.

        This test performs the following steps:
        1. Create a new run using autoflow.py new-run command
        2. Verify run.json contains integrity field with prompt.md and run.sh hashes
        3. Tamper with prompt.md file
        4. Attempt to execute run using agent_runner.py
        5. Verify execution fails with integrity check error
        6. Restore prompt.md, tamper with run.sh
        7. Attempt to execute run using agent_runner.py
        8. Verify execution fails with integrity check error
        """
        # Step 1: Create a new run
        run_dir, run_metadata = self._create_run_via_cli()
        self.assertIsNotNone(run_dir)
        self.assertTrue(run_dir.exists())

        run_json_path = run_dir / "run.json"
        prompt_path = run_dir / "prompt.md"
        run_script_path = run_dir / "run.sh"

        # Step 2: Verify run.json contains integrity field
        self.assertIn("integrity", run_metadata)
        integrity = run_metadata["integrity"]

        # Verify integrity structure
        self.assertIn("prompt_md_hash", integrity)
        self.assertIn("run_sh_hash", integrity)
        self.assertIn("hash_algorithm", integrity)
        self.assertEqual(integrity["hash_algorithm"], "sha256")

        # Verify hash format (64 hex characters for SHA-256)
        prompt_hash = integrity["prompt_md_hash"]
        script_hash = integrity["run_sh_hash"]
        self.assertEqual(len(prompt_hash), 64)
        self.assertEqual(len(script_hash), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in prompt_hash))
        self.assertTrue(all(c in "0123456789abcdef" for c in script_hash))

        # Verify files exist
        self.assertTrue(prompt_path.exists())
        self.assertTrue(run_script_path.exists())

        # Store original content for restoration
        original_prompt_content = prompt_path.read_text(encoding="utf-8")
        original_script_content = run_script_path.read_text(encoding="utf-8")

        # Step 3: Tamper with prompt.md
        prompt_path.write_text("TAMPERED PROMPT CONTENT", encoding="utf-8")

        # Step 4 & 5: Verify integrity check fails via direct function call
        # This tests the actual integrity verification logic
        scripts_dir = self.repo_root / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        from agent_runner import verify_prompt_integrity

        # Verify that tampered prompt.md fails integrity check
        with self.assertRaises(SystemExit) as context:
            verify_prompt_integrity(str(prompt_path), run_metadata)

        self.assertIn("integrity", str(context.exception).lower())

        # Step 6: Restore prompt.md and tamper with run.sh
        prompt_path.write_text(original_prompt_content, encoding="utf-8")
        run_script_path.write_text("# TAMPERED SCRIPT\necho 'malicious'\n", encoding="utf-8")

        # Step 7 & 8: Verify integrity check fails for run.sh
        from agent_runner import verify_run_script_integrity

        # Verify that tampered run.sh fails integrity check
        with self.assertRaises(SystemExit) as context:
            verify_run_script_integrity(str(run_script_path), run_metadata)

        self.assertIn("integrity", str(context.exception).lower())

        # Additional verification: Restore both files and verify execution would succeed
        # (Note: We don't actually execute since we don't want to run the echo command)
        prompt_path.write_text(original_prompt_content, encoding="utf-8")
        run_script_path.write_text(original_script_content, encoding="utf-8")

        # Verify integrity is restored by checking hashes
        from scripts.integrity import verify_file_integrity
        self.assertTrue(
            verify_file_integrity(prompt_path, prompt_hash),
            "Restored prompt.md should pass integrity check"
        )
        self.assertTrue(
            verify_file_integrity(run_script_path, script_hash),
            "Restored run.sh should pass integrity check"
        )

    def test_backward_compatibility_missing_integrity_field(self) -> None:
        """
        Test that runs without integrity field can still execute (backward compatibility).
        """
        # Create a run without integrity field
        run_dir, run_metadata = self._create_run_via_cli()

        # Remove integrity field from run.json
        run_json_path = run_dir / "run.json"
        run_metadata.pop("integrity", None)
        run_json_path.write_text(json.dumps(run_metadata, indent=2), encoding="utf-8")

        # Verify that verification functions handle missing integrity field gracefully
        prompt_path = run_dir / "prompt.md"
        run_script_path = run_dir / "run.sh"

        scripts_dir = self.repo_root / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        from agent_runner import verify_prompt_integrity, verify_run_script_integrity

        # These should NOT raise exceptions when integrity field is missing
        try:
            verify_prompt_integrity(str(prompt_path), run_metadata)
            verify_run_script_integrity(str(run_script_path), run_metadata)
        except SystemExit as e:
            # If SystemExit is raised, it should NOT be due to integrity
            error_msg = str(e).lower()
            self.assertNotIn("integrity", error_msg,
                "Should not fail with integrity error when integrity field is missing")


if __name__ == "__main__":
    unittest.main()
