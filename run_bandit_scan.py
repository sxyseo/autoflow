#!/usr/bin/env python3
"""Run bandit security scan on continuous_iteration.py"""
import json
import subprocess
import sys

def main():
    result = subprocess.run(
        ['bandit', '-r', 'scripts/continuous_iteration.py', '-f', 'json'],
        capture_output=True,
        text=True
    )

    print("BANDIT SECURITY SCAN RESULTS")
    print("=" * 80)
    print(f"Return code: {result.returncode}")
    print("\nStdout:")
    print(result.stdout)

    if result.stderr:
        print("\nStderr:")
        print(result.stderr)

    # Parse JSON output if available
    if result.stdout:
        try:
            data = json.loads(result.stdout)
            print("\n" + "=" * 80)
            print("SUMMARY")
            print("=" * 80)

            if 'results' in data:
                high_severity = [r for r in data['results'] if r.get('issue_severity') == 'HIGH']
                medium_severity = [r for r in data['results'] if r.get('issue_severity') == 'MEDIUM']
                low_severity = [r for r in data['results'] if r.get('issue_severity') == 'LOW']

                print(f"Total issues: {len(data['results'])}")
                print(f"  HIGH: {len(high_severity)}")
                print(f"  MEDIUM: {len(medium_severity)}")
                print(f"  LOW: {len(low_severity)}")

                if high_severity:
                    print("\nHIGH SEVERITY ISSUES:")
                    for issue in high_severity:
                        print(f"  - {issue.get('test_name')}: {issue.get('text')}")
                        print(f"    Line {issue.get('line_number')}: {issue.get('code')}")

                # Check specifically for shell injection issues
                shell_issues = [r for r in data['results']
                               if 'shell' in r.get('test_name', '').lower()
                               or 'injection' in r.get('test_name', '').lower()]

                if shell_issues:
                    print("\n⚠️  SHELL INJECTION VULNERABILITIES FOUND:")
                    for issue in shell_issues:
                        print(f"  - {issue.get('test_id')}: {issue.get('test_name')}")
                        print(f"    Line {issue.get('line_number')}: {issue.get('text')}")
                else:
                    print("\n✓ NO SHELL INJECTION VULNERABILITIES DETECTED")

            if 'metrics' in data:
                print("\n" + "=" * 80)
                print("METRICS")
                print("=" * 80)
                for key, value in data['metrics'].items():
                    print(f"  {key}: {value}")

        except json.JSONDecodeError:
            print("Could not parse bandit JSON output")

    # Return 0 if no high severity issues, 1 otherwise
    sys.exit(result.returncode)

if __name__ == '__main__':
    main()
