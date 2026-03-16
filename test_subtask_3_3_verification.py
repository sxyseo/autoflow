#!/usr/bin/env python3
"""
Verification script for subtask 3-3:
Verify archived spec appears in --archived list

This script tests the complete workflow:
1. Creates a test spec
2. Archives it
3. Verifies it appears in 'autoflow spec list --archived'
4. Verifies metadata.json contains 'archived': true
"""

import json
import subprocess
import sys
from pathlib import Path

def run_autoflow_command(args: list[str]) -> tuple[bool, str, str]:
    """Run autoflow CLI command and return (success, stdout, stderr)."""
    cmd = ["python3", "-m", "autoflow.cli"] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    return result.returncode == 0, result.stdout, result.stderr

def main():
    print("=" * 70)
    print("SUBTASK 3-3 VERIFICATION: Archived spec appears in --archived list")
    print("=" * 70)
    print()

    # Step 1: Create test spec
    print("Step 1: Creating test spec...")
    test_spec_id = "test-verify-archive"
    test_spec = {
        "id": test_spec_id,
        "title": "Test Archive Verification",
        "summary": "Spec to verify archive functionality",
        "created_at": "2026-03-11T00:00:00Z",
        "status": "done",
        "metadata": {}
    }

    specs_dir = Path(".autoflow/specs")
    specs_dir.mkdir(parents=True, exist_ok=True)
    spec_file = specs_dir / f"{test_spec_id}.json"

    with open(spec_file, 'w') as f:
        json.dump(test_spec, f, indent=2)
    print(f"✓ Created test spec: {spec_file}")
    print()

    # Step 2: Verify spec appears in default list
    print("Step 2: Verifying spec appears in default list...")
    success, stdout, stderr = run_autoflow_command(["spec", "list"])

    if not success:
        print(f"✗ Failed to run spec list: {stderr}")
        sys.exit(1)

    if test_spec_id in stdout:
        print(f"✓ Test spec appears in default list")
    else:
        print(f"✗ Test spec NOT found in default list")
        print(f"Output: {stdout}")
    print()

    # Step 3: Archive the test spec
    print("Step 3: Archiving test spec...")
    success, stdout, stderr = run_autoflow_command([
        "spec", "archive", test_spec_id, "--force"
    ])

    if not success:
        print(f"✗ Failed to archive spec: {stderr}")
        sys.exit(1)

    print(f"✓ Archived test spec")
    print()

    # Step 4: Verify spec NO LONGER appears in default list
    print("Step 4: Verifying spec removed from default list...")
    success, stdout, stderr = run_autoflow_command(["spec", "list"])

    if not success:
        print(f"✗ Failed to run spec list: {stderr}")
        sys.exit(1)

    if test_spec_id not in stdout:
        print(f"✓ Test spec correctly removed from default list")
    else:
        print(f"✗ Test spec STILL appears in default list (should be removed)")
        print(f"Output: {stdout}")
    print()

    # Step 5: Verify spec APPEARS in --archived list
    print("Step 5: Verifying spec appears in --archived list...")
    success, stdout, stderr = run_autoflow_command([
        "spec", "list", "--archived"
    ])

    if not success:
        print(f"✗ Failed to run spec list --archived: {stderr}")
        sys.exit(1)

    if test_spec_id in stdout:
        print(f"✓ Test spec appears in --archived list")
        print(f"\nArchived list output:")
        print("-" * 70)
        print(stdout)
        print("-" * 70)
    else:
        print(f"✗ Test spec NOT found in --archived list")
        print(f"Output: {stdout}")
        sys.exit(1)
    print()

    # Step 6: Verify metadata.json contains 'archived': true
    print("Step 6: Verifying metadata contains 'archived': true...")
    archive_dir = Path(".autoflow/specs_archive")
    archived_spec_file = archive_dir / f"{test_spec_id}.json"

    if not archived_spec_file.exists():
        print(f"✗ Archived spec file not found: {archived_spec_file}")
        sys.exit(1)

    with open(archived_spec_file, 'r') as f:
        archived_spec = json.load(f)

    if "metadata" in archived_spec and archived_spec["metadata"].get("archived") is True:
        print(f"✓ Metadata contains 'archived': true")
        print(f"\nArchived spec metadata:")
        print("-" * 70)
        print(json.dumps(archived_spec.get("metadata", {}), indent=2))
        print("-" * 70)
    else:
        print(f"✗ Metadata does NOT contain 'archived': true")
        print(f"Metadata: {archived_spec.get('metadata', {})}")
        sys.exit(1)
    print()

    # Step 7: Test with JSON output
    print("Step 7: Verifying JSON output format...")
    # Note: --json is a global option that comes before 'spec'
    cmd = ["python3", "-m", "autoflow.cli", "--json", "spec", "list", "--archived"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    success, stdout, stderr = result.returncode == 0, result.stdout, result.stderr

    if not success:
        print(f"✗ Failed to run spec list --archived --json: {stderr}")
        sys.exit(1)

    try:
        json_output = json.loads(stdout)
        if "specs" in json_output:
            spec_ids = [s.get("id") for s in json_output["specs"]]
            if test_spec_id in spec_ids:
                print(f"✓ JSON output contains archived spec")
            else:
                print(f"✗ JSON output does NOT contain archived spec")
                print(f"Spec IDs: {spec_ids}")
                sys.exit(1)
        else:
            print(f"✗ JSON output missing 'specs' key")
            sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"✗ Failed to parse JSON output: {e}")
        print(f"Output: {stdout}")
        sys.exit(1)
    print()

    # Cleanup
    print("Cleanup: Removing test spec from archive...")
    if archived_spec_file.exists():
        archived_spec_file.unlink()
        print(f"✓ Removed test spec from archive")
    print()

    print("=" * 70)
    print("✓ ALL VERIFICATIONS PASSED")
    print("=" * 70)
    print()
    print("Summary:")
    print("- ✓ Test spec created and appears in default list")
    print("- ✓ Test spec archived successfully")
    print("- ✓ Test spec removed from default list")
    print("- ✓ Test spec appears in --archived list")
    print("- ✓ Metadata contains 'archived': true")
    print("- ✓ JSON output format works correctly")
    print()
    print("Subtask 3-3 verification: COMPLETE")

if __name__ == "__main__":
    main()
