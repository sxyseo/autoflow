#!/usr/bin/env python3
"""
Manual Verification Test for Agent Config Redaction

This script simulates the build_prompt() function to verify that
sensitive fields in agent configurations are properly redacted
when output as JSON.

Run this script to verify that:
1. Agent model configs are redacted
2. Transport configs are redacted
3. API keys and secrets are redacted
4. Non-sensitive fields remain intact
"""

import json
import sys
from pathlib import Path

# Add the parent directory to the path so we can import autoflow modules
sys.path.insert(0, str(Path(__file__).parent))

from autoflow.core.sanitization import sanitize_dict, DEFAULT_REDACTED


def create_test_agent_config():
    """
    Create a test agent configuration with sensitive fields
    similar to what build_prompt() uses.
    """
    return {
        "agent": "claude-code",
        "protocol": "acp",
        "command": "acp-agent",
        "model": "claude-3-5-sonnet-20241022",  # Should be redacted
        "model_profile": "implementation",  # Should be redacted
        "tools": ["bash", "editor", "file_search"],
        "tool_profile": "claude-code",  # Should be redacted
        "memory_scopes": ["global", "spec"],  # Should be redacted
        "native_resume_supported": True,
        "transport": {  # Should be redacted
            "type": "stdio",
            "command": "acp-agent",
            "args": [],
            "env": {
                "API_KEY": "sk-ant-secret123",  # Should be redacted
                "SECRET_TOKEN": "token-xyz-789",  # Should be redacted
            },
        },
        "api_key": "sk-proj-abc123def456",  # Should be redacted
        "endpoint": "https://api.example.com",  # Should NOT be redacted
    }


def verify_redaction(original: dict, sanitized: dict) -> tuple[bool, list[str]]:
    """
    Verify that sensitive fields are properly redacted.

    Returns:
        (success, list of failure messages)
    """
    failures = []

    # Check that model is redacted
    if sanitized.get("model") == original.get("model"):
        failures.append("FAIL: 'model' field was NOT redacted")

    # Check that model_profile is redacted
    if sanitized.get("model_profile") == original.get("model_profile"):
        failures.append("FAIL: 'model_profile' field was NOT redacted")

    # Check that tool_profile is redacted
    if sanitized.get("tool_profile") == original.get("tool_profile"):
        failures.append("FAIL: 'tool_profile' field was NOT redacted")

    # Check that memory_scopes is redacted
    if sanitized.get("memory_scopes") == original.get("memory_scopes"):
        failures.append("FAIL: 'memory_scopes' field was NOT redacted")

    # Check that transport is redacted
    if sanitized.get("transport") == original.get("transport"):
        failures.append("FAIL: 'transport' field was NOT redacted")

    # Check that api_key is redacted
    if sanitized.get("api_key") == original.get("api_key"):
        failures.append("FAIL: 'api_key' field was NOT redacted")

    # Check that non-sensitive fields are preserved
    if sanitized.get("agent") != original.get("agent"):
        failures.append("FAIL: 'agent' field should NOT be redacted")

    if sanitized.get("protocol") != original.get("protocol"):
        failures.append("FAIL: 'protocol' field should NOT be redacted")

    if sanitized.get("endpoint") != original.get("endpoint"):
        failures.append("FAIL: 'endpoint' field should NOT be redacted")

    # Check that tools list is preserved
    if sanitized.get("tools") != original.get("tools"):
        failures.append("FAIL: 'tools' field should NOT be redacted")

    # Check boolean values are preserved
    if sanitized.get("native_resume_supported") != original.get("native_resume_supported"):
        failures.append("FAIL: 'native_resume_supported' field should NOT be redacted")

    return len(failures) == 0, failures


def main():
    """Run the manual verification test."""
    print("=" * 80)
    print("MANUAL VERIFICATION TEST: Agent Config Redaction")
    print("=" * 80)
    print()

    # Create test agent config
    print("1. Creating test agent configuration with sensitive fields...")
    original_config = create_test_agent_config()
    print("   ✓ Test configuration created")
    print()

    # Display original config
    print("2. Original configuration (with sensitive data):")
    print("-" * 80)
    print(json.dumps(original_config, indent=2, ensure_ascii=True))
    print("-" * 80)
    print()

    # Sanitize the config
    print("3. Sanitizing configuration...")
    sanitized_config = sanitize_dict(original_config)
    print("   ✓ Configuration sanitized")
    print()

    # Display sanitized config
    print("4. Sanitized configuration (sensitive data redacted):")
    print("-" * 80)
    print(json.dumps(sanitized_config, indent=2, ensure_ascii=True))
    print("-" * 80)
    print()

    # Verify redaction
    print("5. Verifying redaction...")
    success, failures = verify_redaction(original_config, sanitized_config)

    if success:
        print("   ✓ ALL CHECKS PASSED")
        print()
        print("   Sensitive fields properly redacted:")
        print("   - model: ***REDACTED***")
        print("   - model_profile: ***REDACTED***")
        print("   - tool_profile: ***REDACTED***")
        print("   - memory_scopes: ***REDACTED***")
        print("   - transport: ***REDACTED***")
        print("   - api_key: ***REDACTED***")
        print()
        print("   Non-sensitive fields preserved:")
        print(f"   - agent: {sanitized_config['agent']}")
        print(f"   - protocol: {sanitized_config['protocol']}")
        print(f"   - endpoint: {sanitized_config['endpoint']}")
        print()
        print("=" * 80)
        print("VERIFICATION RESULT: ✓ PASSED")
        print("=" * 80)
        return 0
    else:
        print("   ✗ VERIFICATION FAILED")
        print()
        print("   Failures:")
        for failure in failures:
            print(f"   - {failure}")
        print()
        print("=" * 80)
        print("VERIFICATION RESULT: ✗ FAILED")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())
