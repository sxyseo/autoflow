# Agent Validation System

## Overview

Autoflow's agent validation system prevents command injection attacks through comprehensive input validation and sanitization. The system uses a multi-layered security approach to ensure that only safe commands and arguments are executed when launching AI agents.

**Key Principle:** All agent configuration is validated before execution, using allowlists, pattern matching, and strict type checking to block malicious inputs.

## Why Validation Matters

Autoflow executes agents based on configuration in `.autoflow/agents.json`. If an attacker can modify this configuration, they could inject malicious commands. The validation system prevents this by:

1. **Allowlist enforcement** - Only explicitly permitted commands can execute
2. **Shell injection prevention** - Detects and blocks shell metacharacters
3. **Code execution prevention** - Detects dangerous flags that could execute code
4. **Path traversal prevention** - Blocks attempts to escape the workspace directory

## Architecture

The validation system is implemented in `scripts/agent_validation.py` and consists of three layers:

### Layer 1: Command Allowlist

**Location:** `ALLOWED_COMMANDS` constant

Only these commands are permitted to execute:
- `claude` - Claude Code CLI
- `codex` - Codex CLI
- `acp-agent` - ACP protocol agents

**Security Property:** Deny-by-default approach using an immutable `frozenset`

### Layer 2: Pattern Detection

**Shell Metacharacters Detection (20 characters):**

The system scans all arguments for shell metacharacters that could enable command injection:
```
| & ; $ ` \n \r ( ) < > \ ! { } [ ] * ?
```

**Attack Vectors Prevented:**
- Pipe injection: `argument | malicious_command`
- Command chaining: `valid_argument && malicious_command`
- Command substitution: `argument $(malicious_command)`
- Redirect attacks: `argument > /etc/passwd`

**Dangerous Flags Detection (13 patterns):**

The system blocks arguments containing dangerous execution flags:
```
--exec, --execute, --eval, --evaluate, -e, -c, -x
/bin/sh, /bin/bash, sh -c, bash -c
exec(, eval(, system(
```

**Attack Vectors Prevented:**
- Flag injection: `--exec "rm -rf /"`
- Code execution: `--eval "__import__('os').system('evil')"`

### Layer 3: Path Validation

**Function:** `validate_path()`

Prevents directory traversal attacks by:
- Expanding `~` and environment variables safely
- Resolving `..` components and symlinks
- Enforcing base directory containment
- Rejecting absolute paths (unless explicitly allowed)

**Attack Vectors Prevented:**
- Directory traversal: `../../../etc/passwd`
- Symlink attacks: Using symlinks to escape workspace
- Absolute path injection: `/etc/passwd`
- Tilde expansion: `~root/.ssh`

## Usage

### For Agent Configuration

When defining agents in `.autoflow/agents.json`:

```json
{
  "agents": {
    "my-claude": {
      "protocol": "cli",
      "command": "claude",
      "args": ["--print", "prompt.md"],
      "model": "claude-3-5-sonnet-20241022"
    }
  }
}
```

The validation system automatically:
- Verifies `command` is in the allowlist
- Scans all `args` for shell metacharacters
- Checks for dangerous flags
- Validates format of `model` identifier

### For Custom Agents

**To add a custom agent to the allowlist:**

1. Edit `scripts/agent_validation.py`
2. Add your command to the `ALLOWED_COMMANDS` frozenset:

```python
ALLOWED_COMMANDS = frozenset({
    "claude",
    "codex",
    "acp-agent",
    "my-custom-agent",  # Add your agent here
})
```

3. Deploy the updated validation module

**Important:** Only add commands that you trust completely. Any command in the allowlist can be executed with user-supplied arguments (subject to metacharacter and dangerous flag validation).

## Examples

### Safe Configuration

```json
{
  "agents": {
    "claude-default": {
      "protocol": "cli",
      "command": "claude",
      "args": ["--model", "claude-3-5-sonnet-20241022"],
      "model": "claude-3-5-sonnet-20241022"
    },
    "codex-full-auto": {
      "protocol": "cli",
      "command": "codex",
      "args": ["--full-auto"],
      "model_profile": "implementation"
    }
  }
}
```

✅ All commands are in the allowlist
✅ No shell metacharacters in arguments
✅ No dangerous flags
✅ Valid format for model identifiers

### Unsafe Configuration (Blocked)

```json
{
  "agents": {
    "malicious-example": {
      "protocol": "cli",
      "command": "rm",
      "args": ["-rf", "/"]
    },
    "injection-example": {
      "protocol": "cli",
      "command": "claude",
      "args": ["--print", "prompt.md; rm -rf /"]
    },
    "flag-example": {
      "protocol": "cli",
      "command": "claude",
      "args": ["--eval", "__import__('os').system('evil')"]
    }
  }
}
```

❌ `rm` is not in the allowlist
❌ `;` is a shell metacharacter
❌ `--eval` is a dangerous flag
❌ All would be rejected by validation

## ACP Protocol Agents

For agents using the ACP protocol, the `transport.command` field is also validated:

```json
{
  "agents": {
    "my-acp-agent": {
      "protocol": "acp",
      "transport": {
        "type": "stdio",
        "command": "acp-agent",
        "args": ["--agent-id", "my-agent"]
      }
    }
  }
}
```

The `transport.command` must also be in the `ALLOWED_COMMANDS` allowlist, and `transport.args` are validated for shell metacharacters and dangerous flags.

## Security Properties

### Validation Guarantees

✅ **Allowlist enforcement** - Only explicitly permitted commands execute
✅ **Defense in depth** - Multiple validation layers
✅ **Fail-safe** - Validation errors block execution
✅ **Minimal error messages** - Prevents information leakage
✅ **Immutable security constants** - frozenset for allowlists

### OWASP Compliance

| OWASP Category | Status | Implementation |
|----------------|--------|----------------|
| Command Injection | ✅ Prevented | Allowlist + metacharacter detection |
| Input Validation | ✅ Enforced | Multi-layer validation |
| Path Traversal | ✅ Prevented | validate_path() function |
| Whitelist Validation | ✅ Used | ALLOWED_COMMANDS frozenset |

## Validation in Code

### Using the Validation Module

```python
from scripts.agent_validation import validate_agent_spec, ValidationError

try:
    # Validate agent specification
    spec = {
        "command": "claude",
        "args": ["--print", "prompt.md"],
        "model": "claude-3-5-sonnet-20241022"
    }
    validator = validate_agent_spec(spec, validate_all_fields=True)
    print("Validation passed")
except ValidationError as e:
    print(f"Security validation failed: {e}")
```

### Path Validation

```python
from scripts.agent_validation import validate_path, ValidationError

try:
    # Validate path is within workspace
    safe_path = validate_path("prompts/task.md", base_dir="/workspace")
    print(f"Safe path: {safe_path}")
except ValidationError as e:
    print(f"Path validation failed: {e}")
```

## Integration Points

The validation system is integrated at two critical points:

### 1. Build-Time Validation

In `scripts/agent_runner.py` (line 73-76):
```python
# Security: Validate agent specification before building command
try:
    validate_agent_spec(agent_spec, validate_all_fields=True)
except (ValidationError, ValueError) as e:
    raise SystemExit(f"Invalid agent specification: {e}") from e
```

### 2. Pre-Execution Validation

In `scripts/agent_runner.py` (line 191-194):
```python
# Security: Final validation before executing command
try:
    validate_agent_spec(resolved_spec, validate_all_fields=True)
except (ValidationError, ValueError) as e:
    raise SystemExit(f"Invalid agent configuration: {e}") from e

os.execvp(command[0], command)
```

This defense-in-depth approach ensures validation happens both during command construction and immediately before execution.

## Limitations and Considerations

### Current Limitations

1. **Hardcoded allowlist** - Adding custom agents requires code changes
2. **False positives** - Legitimate arguments with special characters may be rejected
3. **No config-based allowlist** - Cannot configure allowlist via system.json

### Mitigation Strategies

- Users can modify `ALLOWED_COMMANDS` in code (requires deployment)
- Consider making allowlist configurable via `system.json` for extensibility
- Document validation requirements for custom agent development

## Best Practices

### When Configuring Agents

1. **Use only allowed commands** - Stick to `claude`, `codex`, and `acp-agent`
2. **Avoid special characters** - Don't use shell metacharacters in arguments
3. **Validate paths** - Ensure file paths are within the workspace
4. **Test configuration** - Run validation before deploying

### When Extending the System

1. **Review security implications** - Understand why a command should be allowed
2. **Update documentation** - Document why new commands were added
3. **Add tests** - Cover new commands in test suite
4. **Consider alternatives** - Use ACP protocol for custom agents when possible

## Testing

The validation system is covered by comprehensive tests in `tests/test_agent_runner.py`:

- Shell metacharacter rejection tests
- Dangerous flag rejection tests
- Allowlist enforcement tests
- Path traversal prevention tests
- File integrity verification tests

Run tests with:
```bash
python3 -m pytest tests/test_agent_runner.py -v
```

## Further Reading

- **Implementation details:** See `.auto-claude/specs/092-add-input-validation-and-sanitization-for-agent-co/VALIDATION_MECHANISMS.md`
- **Investigation findings:** See `.auto-claude/specs/092-add-input-validation-and-sanitization-for-agent-co/INVESTIGATION_FINDINGS.md`
- **Source code:** `scripts/agent_validation.py`
- **Tests:** `tests/test_agent_runner.py`
