# Manual Code Review Findings
## Task 029: Agent Configuration Input Validation

**Review Date:** 2026-03-09
**Reviewer:** Manual Security Code Review
**Files Reviewed:**
- `scripts/agent_validation.py` (522 lines)
- `scripts/agent_runner.py` (104 lines)

---

## Executive Summary

**Overall Assessment: ⚠️ MODERATE RISK - ISSUES FOUND**

The validation logic demonstrates strong security practices with comprehensive allowlist validation, shell metacharacter detection, and path traversal prevention. However, **several security issues were identified** that should be addressed before production deployment.

### Severity Breakdown
- 🔴 **1 CRITICAL** - requires immediate fix
- 🟠 **2 HIGH** - requires fixes
- 🟡 **2 MEDIUM** - recommended for fixes
- 🟢 **3 LOW** - optional improvements

---

## Critical Issues

### 🔴 CRITICAL: Unvalidated File Paths Allow Arbitrary File Reads

**Location:** `agent_runner.py` lines 78-80, 83-84

**Issue:** The `agents_file`, `prompt_file`, and `run_json` paths are taken directly from command-line arguments without any validation.

```python
agents_file = Path(sys.argv[1])  # No validation
prompt_file = sys.argv[3]        # No validation
data = read_json(agents_file)    # Used directly
```

**Impact:** An attacker can read **any file** on the filesystem by supplying arbitrary paths.

**Recommendation:** Add path validation using `validate_path()` for all file inputs:

```python
# In agent_runner.py main()
from scripts.agent_validation import validate_path

# Validate agents_file
try:
    validated_agents_path = validate_path(
        str(agents_file),
        base_dir="./agents",
        allow_absolute=False
    )
except ValidationError as e:
    raise SystemExit(f"Invalid agents file path: {e}") from e

# Validate prompt_file
try:
    validated_prompt_path = validate_path(
        prompt_file,
        base_dir="./prompts",
        allow_absolute=False
    )
except ValidationError as e:
    raise SystemExit(f"Invalid prompt file path: {e}") from e
```

---

## High Severity Issues

### 🟠 HIGH: Unvalidated agent_name Parameter

**Location:** `agent_runner.py` line 84

**Issue:** The `agent_name` parameter is used directly as a dictionary key without format validation.

**Impact:** Violates secure coding principles; could cause issues with special characters.

**Recommendation:** Add format validation:

```python
agent_name = sys.argv[2]
if not re.match(r"^[a-zA-Z0-9_-]+$", agent_name):
    raise SystemExit(f"Invalid agent name: {agent_name}")
```

### 🟠 HIGH: Missing Validation for run_json Path

**Location:** `agent_runner.py` lines 81, 87

**Issue:** The optional `run_json` file path is not validated before use.

**Impact:** Allows reading arbitrary files (same as agents_file issue).

**Recommendation:** Add path validation for `run_json` (same as above).

---

## Medium Severity Issues

### 🟡 MEDIUM: Error Messages Leak Information to Attackers

**Location:** `agent_validation.py` lines 262-265, 445-447

**Issue:** Error messages include specific details about what was detected.

```python
# Current (leaks information)
f"{field_name} contains shell metacharacters: {', '.join(found)}."
f"Path '{path}' resolves to '{resolved}' which is outside the base directory '{base}'."
```

**Impact:** Helps attackers refine their attacks through trial and error.

**Recommendation:** Use generic error messages:

```python
# Improved (generic)
f"{field_name} contains invalid characters. This could indicate a command injection attempt."
f"Path '{path}' is outside the allowed base directory."
```

### 🟡 MEDIUM: Missing Shell Metacharacters

**Location:** `agent_validation.py` lines 42-55

**Issue:** Some shell metacharacters are missing from detection.

**Missing:** `!`, `{`, `}`, `[`, `]`, `*`, `?`

**Recommendation:** Add to `SHELL_METACHARACTERS`:

```python
SHELL_METACHARACTERS = frozenset({
    "|", "&", ";", "$", "`", "\n", "\r", "(", ")", "<", ">", "\\",
    "!", "{", "}", "[", "]", "*", "?",  # Additional metacharacters
})
```

---

## Low Severity Issues

### 🟢 LOW: Missing Dangerous Flags for Python Code Execution

**Missing patterns:** `__import__`, `subprocess`, `pickle`, `yaml.load`

**Recommendation:** Add to `DANGEROUS_FLAGS` set (defense-in-depth).

### 🟢 LOW: validate_path Error Message Leaks Resolved Path

**Issue:** Error message includes full resolved path, leaking directory structure.

**Recommendation:** Remove resolved path from error message.

### 🟢 LOW: No Validation of Prompt File Content

**Issue:** Prompt file content is not validated before being passed as an argument.

**Assessment:** Acceptable - prompt content is trusted data and outside the scope of command injection prevention.

---

## Positive Findings

### ✅ Command Allowlist
- Strict allowlist of permitted commands (`claude`, `codex`, `acp-agent`)
- Uses frozenset for immutability
- Clear denylist-by-default approach

### ✅ Shell Metacharacter Detection
- Comprehensive detection of command injection vectors
- Applied consistently across all argument fields

### ✅ Dangerous Flag Detection
- Detects execution flags (`--exec`, `--eval`, `-e`, `-c`, `-x`)
- Detects shell command patterns (`/bin/sh`, `bash -c`)
- Detects Python execution patterns (`exec(`, `eval(`, `system(`)

### ✅ Path Traversal Prevention
- Proper path resolution to handle `..` components
- Validation against base directory
- Prevention of absolute paths and home directory expansion

### ✅ Double Validation Pattern
- Validation in `build_command()` (line 36-39)
- Final validation in `main()` before `os.execvp()` (line 94-97)
- Provides defense-in-depth

---

## Attack Vector Coverage

| Attack Vector | Coverage | Status |
|--------------|----------|--------|
| Command Injection | Well Covered | ✅ |
| Path Traversal | Well Covered | ✅ |
| Arbitrary File Read | Poorly Covered | ⚠️ **CRITICAL ISSUE** |
| Configuration Tampering | Well Covered | ✅ |
| Supply Chain Attacks | Well Covered | ✅ |

---

## Bypass Techniques Analysis

| Attempted Bypass | Result |
|-----------------|--------|
| Unicode homograph attacks | ✅ BLOCKED |
| Argument injection via newlines | ✅ BLOCKED |
| Command chaining via semicolon | ✅ BLOCKED |
| Path traversal via symlinks | ⚠️ PARTIAL |
| Arbitrary file read | ❌ **NOT BLOCKED** |

---

## Recommendations Summary

### Must Fix (Before Production)
1. ✅ Add path validation for `agents_file`, `prompt_file`, and `run_json`
2. ✅ Add format validation for `agent_name`
3. ✅ Make error messages generic to prevent information disclosure

### Should Fix (Soon)
4. ✅ Add missing shell metacharacters (`!`, `{`, `}`, `[`, `]`, `*`, `?`)
5. ✅ Remove resolved paths from error messages

### Nice to Have (Future)
6. ⚠️ Add additional dangerous flag patterns
7. ⚠️ Make command allowlist configurable

---

## Conclusion

The agent validation logic demonstrates **strong security fundamentals** with comprehensive allowlist validation, shell metacharacter detection, and path traversal prevention. However, **critical gaps exist** that must be addressed:

**Overall Risk Level:**
- Before fixes: ⚠️ **MODERATE**
- After recommended fixes: ✅ **LOW**

**Status:** ⚠️ **REQUIRES FIXES BEFORE PRODUCTION USE**

The core validation mechanisms are well-designed and effective. Once the critical and high-severity issues are addressed, the system will have strong security posture suitable for production deployment.

---

**Reviewed by:** Manual Security Code Review
**Date:** 2026-03-09
**Next Review:** After implementing recommended fixes
