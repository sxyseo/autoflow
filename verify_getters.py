#!/usr/bin/env python3
"""Verification script for pattern store getter methods."""

from autoflow.healing.pattern_store import PatternStore

def main():
    store = PatternStore()
    getter_methods = [m for m in dir(store) if 'get' in m.lower()]

    print(f'Has {len(getter_methods)} getter methods')
    print('\nGetter methods:')
    for method in sorted(getter_methods):
        print(f'  - {method}')

    # Expected methods
    expected = [
        'get_pattern',
        'get_attempt',
        'get_strategy',
        'find_by_error_pattern',
        'get_strategies_for_error',
        'get_success_rate',
    ]

    print(f'\nExpected {len(expected)} methods, found {len(getter_methods)}')

    # Check if all expected methods exist
    missing = []
    for method in expected:
        if not hasattr(store, method):
            missing.append(method)

    if missing:
        print(f'Missing methods: {missing}')
        return False
    else:
        print('All expected methods present!')
        return True

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
