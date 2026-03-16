#!/usr/bin/env python3
"""
Verification script for subtask-3-2: Archive test spec and verify it's moved
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from autoflow.core.state import StateManager
from autoflow.core.config import get_state_dir, load_config


def main():
    print("=" * 80)
    print("SUBTASK 3-2 VERIFICATION: Archive Test Spec")
    print("=" * 80)

    # Load config
    config = load_config()
    state_dir = get_state_dir(config)

    print(f"\nState directory: {state_dir}")

    # Initialize state manager
    state = StateManager(state_dir)

    # Step 1: Verify test-spec exists before archiving
    print("\n--- Step 1: Verify test-spec exists ---")
    specs_before = state.list_specs()
    print(f"Active specs before archive: {[s['id'] for s in specs_before]}")

    test_spec = state.load_spec("test-spec")
    if test_spec:
        print(f"✓ test-spec found: {test_spec['title']}")
    else:
        print("✗ test-spec not found!")
        return False

    # Step 2: Archive the test spec
    print("\n--- Step 2: Archive test-spec ---")
    success = state.archive_spec("test-spec")
    if success:
        print("✓ Successfully archived test-spec")
    else:
        print("✗ Failed to archive test-spec")
        return False

    # Step 3: Verify test-spec no longer in active list
    print("\n--- Step 3: Verify test-spec removed from active enumeration ---")
    specs_after = state.list_specs()
    print(f"Active specs after archive: {[s['id'] for s in specs_after]}")

    test_spec_in_active = any(s['id'] == 'test-spec' for s in specs_after)
    if test_spec_in_active:
        print("✗ test-spec still appears in active list!")
        return False
    else:
        print("✓ test-spec no longer in active list")

    # Step 4: Verify archive directory exists and contains test-spec
    print("\n--- Step 4: Verify archive directory contains test-spec ---")
    archive_dir = state.archive_dir
    print(f"Archive directory: {archive_dir}")

    if not archive_dir.exists():
        print("✗ Archive directory does not exist!")
        return False

    archived_specs = state.list_archived_specs()
    print(f"Archived specs: {[s['id'] for s in archived_specs]}")

    test_spec_archived = any(s['id'] == 'test-spec' for s in archived_specs)
    if test_spec_archived:
        print("✓ test-spec found in archive")
    else:
        print("✗ test-spec not found in archive!")
        return False

    # Step 5: Verify original spec file no longer exists
    print("\n--- Step 5: Verify original spec file removed ---")
    original_spec_path = state.specs_dir / "test-spec.json"
    if original_spec_path.exists():
        print(f"✗ Original spec file still exists: {original_spec_path}")
        return False
    else:
        print("✓ Original spec file removed")

    # Step 6: Verify archived spec file exists
    print("\n--- Step 6: Verify archived spec file exists ---")
    archived_spec_path = archive_dir / "test-spec.json"
    if archived_spec_path.exists():
        print(f"✓ Archived spec file exists: {archived_spec_path}")
        # Load and verify content
        archived_spec = state.read_json(archived_spec_path)
        print(f"  Archived spec title: {archived_spec.get('title', 'N/A')}")
        print(f"  Archived spec status: {archived_spec.get('status', 'N/A')}")
    else:
        print(f"✗ Archived spec file not found: {archived_spec_path}")
        return False

    print("\n" + "=" * 80)
    print("✓ ALL VERIFICATIONS PASSED")
    print("=" * 80)
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Error during verification: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
