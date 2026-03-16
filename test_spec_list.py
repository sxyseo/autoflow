#!/usr/bin/env python3
"""Test script to verify spec list functionality."""

import sys
import os
import json
from pathlib import Path

def test_spec_exists():
    """Test that test spec file exists and is valid."""
    spec_path = Path(".autoflow/specs/test-spec.json")

    print("Checking test spec file...")
    print(f"  Path: {spec_path.absolute()}")
    print(f"  Exists: {spec_path.exists()}")

    if not spec_path.exists():
        print("✗ Test spec file does not exist")
        return False

    # Load and validate the spec
    with open(spec_path, 'r') as f:
        spec_data = json.load(f)

    print(f"  ID: {spec_data.get('id')}")
    print(f"  Title: {spec_data.get('title')}")
    print(f"  Status: {spec_data.get('status')}")

    if spec_data.get('id') != 'test-spec':
        print("✗ Spec ID mismatch")
        return False

    print("✓ Test spec file is valid")
    return True

def test_state_manager():
    """Test StateManager can list specs."""
    # Import StateManager directly without going through __init__.py
    sys.path.insert(0, str(Path(__file__).parent))
    import importlib.util
    spec = importlib.util.spec_from_file_location("state", "autoflow/core/state.py")
    state_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(state_module)
    StateManager = state_module.StateManager

    print("\nTesting StateManager...")

    # Create StateManager instance
    sm = StateManager(".autoflow")
    sm.initialize()

    # List specs
    specs = sm.list_specs()

    print(f"  Found {len(specs)} spec(s)")
    for spec in specs:
        print(f"    - {spec.get('id')}: {spec.get('title')}")

    # Check if test-spec is in the list
    test_spec_found = any(spec.get('id') == 'test-spec' for spec in specs)

    if test_spec_found:
        print("✓ test-spec found in StateManager.list_specs()")
    else:
        print("✗ test-spec NOT found in StateManager.list_specs()")
        return False

    # Check archive directory doesn't contain test-spec yet
    archived_specs = sm.list_archived_specs()
    test_spec_archived = any(spec.get('id') == 'test-spec' for spec in archived_specs)

    if test_spec_archived:
        print("✗ test-spec found in archived list (should not be there yet)")
        return False
    else:
        print("✓ test-spec not in archived list (as expected)")

    # Verify archive directory exists but is empty
    archive_dir = sm.archive_dir
    print(f"\n  Archive directory: {archive_dir.absolute()}")
    print(f"  Archive exists: {archive_dir.exists()}")

    if archive_dir.exists():
        archived_files = list(archive_dir.glob("*.json"))
        print(f"  Archived files: {len(archived_files)}")
        if len(archived_files) == 0:
            print("✓ Archive directory is empty (as expected)")
        else:
            print(f"  Files: {[f.name for f in archived_files]}")

    return True

if __name__ == "__main__":
    try:
        success1 = test_spec_exists()
        success2 = test_state_manager()
        success = success1 and success2
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
