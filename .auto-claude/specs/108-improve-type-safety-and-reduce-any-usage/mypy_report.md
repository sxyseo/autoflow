# MyPy Type Checking Report for Autoflow

**Date:** 2026-03-16
**Package:** autoflow
**MyPy Version:** (via python3 -m mypy)

## Summary

- **Total Errors:** 516
- **Files Checked:** 150 source files
- **Files with Errors:** 72 files
- **Files with No Errors:** 78 files

## Status: ⚠️ ISSUES FOUND

The mypy type checker found 516 errors across 72 files. This report categorizes the issues and provides guidance for resolution.

## Top Files with Most Errors

| File | Error Count | Priority |
|------|-------------|----------|
| `autoflow/core/state.py` | 139 | **HIGH** |
| `autoflow/core/repository.py` | 75 | **HIGH** |
| `autoflow/ci/gates.py` | 32 | **MEDIUM** |
| `autoflow/skills/sharing.py` | 30 | **MEDIUM** |
| `autoflow/intake/linear_client.py` | 21 | **MEDIUM** |
| `autoflow/autoflow_cli.py` | 17 | **HIGH** |
| `autoflow/intake/jobs.py` | 15 | **MEDIUM** |
| `autoflow/analytics/cli.py` | 14 | **LOW** |
| `autoflow/intake/gitlab_client.py` | 12 | **MEDIUM** |
| `autoflow/intake/github_client.py` | 12 | **MEDIUM** |

## Error Categories

### 1. no-any-return (Returning Any from typed functions)

**Count:** ~25+ instances
**Severity:** High
**Impact:** Functions that should return specific types are returning `Any`

**Example Issues:**
```python
autoflow/utils/file_helpers.py:35: Returning Any from function declared to return "dict[str, Any]"
autoflow/core/state.py:417: Returning Any from function declared to return "dict[str, Any] | list[Any] | str | int | float | bool | None | T"
autoflow/rollback/health.py:182: Returning Any from function declared to return "bool"
```

**Root Causes:**
- JSON parsing functions (`json.loads()`, `json.load()`) return `Any`
- Functions calling JSON deserialization without proper type narrowing
- TypeVar functions with insufficient type constraints

**Recommended Fixes:**
- Use `cast()` from `typing` to assert types after JSON parsing
- Implement type guards for runtime type checking
- Use typed JSON helper functions created in earlier subtasks
- Add proper type checking before returning from functions

### 2. union-attr (Item of union has no attribute)

**Count:** ~40+ instances
**Severity:** High
**Impact:** Attempting to access attributes on union types without proper type narrowing

**Example Issues:**
```python
autoflow/core/state.py:675: Item "list[Any]" of "dict[str, Any] | list[Any] | str | int | float | None" has no attribute "get"
autoflow/core/state.py:675: Item "str" of "dict[str, Any] | list[Any] | str | int | float | None" has no attribute "get"
autoflow/core/state.py:782: Item "int" of "dict[str, Any] | list[Any] | str | int | float | None" has no attribute "get"
```

**Root Causes:**
- `StateManager.read_json()` returns overly permissive unions: `dict[str, Any] | list[Any] | str | int | float | None`
- Code assumes dict return type without checking
- Missing isinstance() checks before attribute access

**Recommended Fixes:**
- Add isinstance checks before accessing dict attributes
- Use typed JSON helper functions: `read_json_typed[T]()`
- Narrow return types in StateManager methods
- Consider using TypedDict return types instead of unions

### 3. assignment (Incompatible types in assignment)

**Count:** ~100+ instances
**Severity:** Medium to High
**Impact:** Type mismatches in variable assignments

**Example Issues:**
```python
autoflow/git/operations.py:106: Incompatible types in assignment (expression has type "None", variable has type "list[str]")
autoflow/skills/templates.py:213: Incompatible types in assignment (expression has type "dict[str, Any]", target has type "str")
autoflow/auth/rbac.py:317: Incompatible types in assignment (expression has type "list[dict[str, Any]]", target has type "int | str | None")
```

**Root Causes:**
- Variables initialized with one type, assigned another
- Optional values not properly handled
- API changes without updating type annotations
- Dict keys/values accessed incorrectly

**Recommended Fixes:**
- Fix initialization to match actual usage
- Add proper None checks before assignment
- Update type annotations to match runtime behavior
- Use type: ignore comments only when absolutely necessary

### 4. arg-type (Incompatible argument types)

**Count:** ~30+ instances
**Severity:** Medium
**Impact:** Passing wrong types to function parameters

**Example Issues:**
```python
autoflow/intake/pipeline.py:667: Argument "issue_data" has incompatible type "dict[str, Any] | None"; expected "dict[str, Any]"
autoflow/auth/middleware.py:241: Argument 2 to "_authenticate_request" has incompatible type "Coroutine[Any, Any, str | None]"; expected "str | None"
autoflow/intake/jobs.py:291: Missing named argument "success" for "JobResult"
```

**Root Causes:**
- Missing await on coroutines
- Optional values not unwrapped before use
- Dataclass/TypedDict missing required fields
- API signature mismatches

**Recommended Fixes:**
- Add `await` keywords for coroutines
- Add None checks or provide default values
- Ensure all required fields are present when constructing objects
- Update function signatures to match actual usage

### 5. attr-defined (Module has no attribute)

**Count:** ~15+ instances
**Severity:** Medium
**Impact:** Accessing attributes that don't exist on modules/classes

**Example Issues:**
```python
autoflow/intake/pipeline.py:765: "StateManager" has no attribute "create_spec"
autoflow/intake/pipeline.py:769: "StateManager" has no attribute "create_task"
autoflow/api/main.py:148: Module "autoflow.db" has no attribute "close_db"
```

**Root Causes:**
- Methods/attributes removed or renamed
- Import errors (wrong module imported)
- Missing method implementations
- Incompatible API versions

**Recommended Fixes:**
- Verify correct method/attribute names
- Check for typos in attribute names
- Ensure all required methods are implemented
- Update imports if accessing wrong module

### 6. no-untyped-def (Missing type annotations)

**Count:** ~10+ instances
**Severity:** Low to Medium
**Impact:** Functions missing return type or parameter type annotations

**Example Issues:**
```python
autoflow/auth/middleware.py:187: Function is missing a type annotation for one or more arguments
autoflow/auth/middleware.py:213: Function is missing a return type annotation
autoflow/auth/middleware.py:213: Function is missing a type annotation for one or more arguments
```

**Root Causes:**
- Legacy code without type annotations
- Complex types that are difficult to annotate
- Callback functions with dynamic signatures

**Recommended Fixes:**
- Add proper type annotations to all function signatures
- Use `# type: ignore` only for truly untypable code
- Consider Protocol types for complex callbacks
- Use TypeVar for generic function signatures

### 7. call-overload (No overload variant matches)

**Count:** ~5+ instances
**Severity:** Medium
**Impact:** Function calls don't match any overload signature

**Example Issues:**
```python
autoflow/review/coverage.py:207: No overload variant of "field" matches argument type "str"
autoflow/review/coverage.py:207: Possible overload variants show field() expects specific parameter types
```

**Root Causes:**
- Wrong parameter types passed to dataclass field()
- Incorrect usage of overloaded functions
- Version mismatches in library APIs

**Recommended Fixes:**
- Review function signature documentation
- Fix parameter types to match overload
- Use correct factory functions for defaults

### 8. operator (Unsupported operand types)

**Count:** ~10+ instances
**Severity:** Medium
**Impact:** Operations between incompatible types

**Example Issues:**
```python
autoflow/intake/jobs.py:445: Unsupported operand types for + ("None" and "int")
autoflow/intake/jobs.py:461: Unsupported operand types for > ("int" and "None")
```

**Root Causes:**
- None values used in arithmetic operations
- Missing None checks before operations
- Optional types not properly handled

**Recommended Fixes:**
- Add None checks before operations
- Provide default values for None cases
- Use proper type guards

## Analysis by Module

### Core Modules (HIGH PRIORITY)

#### autoflow/core/state.py (139 errors)
- **Primary Issue:** Union type handling (union-attr)
- **Root Cause:** `read_json()` returns permissive unions, code assumes dict
- **Impact:** State management is core to all operations
- **Fix Strategy:**
  1. Migrate to `read_json_typed[T]()` methods
  2. Add isinstance checks before dict operations
  3. Narrow return types where possible

#### autoflow/core/repository.py (75 errors)
- **Primary Issue:** Type mismatches in repository operations
- **Impact:** Affects dependency management
- **Fix Strategy:** Review and update type annotations for repository methods

### Collaboration Module (MEDIUM PRIORITY)

#### autoflow/collaboration/activity.py (5 errors)
- **Status:** Recently updated with typed metadata
- **Remaining Issues:** Minor type narrowing needed
- **Fix Strategy:** Add type guards for metadata access

### Intake Module (MEDIUM PRIORITY)

#### autoflow/intake/jobs.py (15 errors)
- **Primary Issue:** JobResult missing fields, None handling
- **Impact:** Job processing failures
- **Fix Strategy:** Ensure all JobResult fields are provided, handle None values

### Auth Module (MEDIUM PRIORITY)

#### autoflow/auth/middleware.py (7 errors)
- **Primary Issue:** Missing type annotations, await issues
- **Impact:** Authentication type safety
- **Fix Strategy:** Add complete type annotations, fix coroutine handling

## Recommendations

### Immediate Actions (HIGH PRIORITY)

1. **Fix StateManager Union Types** (autoflow/core/state.py)
   - Migrate from `read_json()` to `read_json_typed[T]()`
   - Add isinstance checks for union type narrowing
   - **Estimated Effort:** 4-6 hours
   - **Impact:** Eliminates ~100+ errors

2. **Fix Repository Type Issues** (autoflow/core/repository.py)
   - Review all method signatures
   - Add proper type annotations
   - **Estimated Effort:** 2-3 hours
   - **Impact:** Eliminates ~75 errors

3. **Fix no-any-return Issues**
   - Add type assertions after JSON parsing
   - Use cast() where runtime checks aren't feasible
   - **Estimated Effort:** 3-4 hours
   - **Impact:** Eliminates ~25 errors

### Short-term Actions (MEDIUM PRIORITY)

4. **Fix JobResult Construction** (autoflow/intake/jobs.py)
   - Ensure all required fields are provided
   - Add proper None handling
   - **Estimated Effort:** 1-2 hours

5. **Add Missing Type Annotations** (auth/middleware.py)
   - Complete function signatures
   - Add return type annotations
   - **Estimated Effort:** 1-2 hours

### Long-term Actions (LOW PRIORITY)

6. **Fix Client API Types**
   - Update github_client, gitlab_client, linear_client
   - **Estimated Effort:** 2-3 hours per client

7. **Add Type Tests**
   - Create mypy test suite for critical paths
   - **Estimated Effort:** 4-6 hours

## Progress Tracking

### Type Safety Improvements from This Spec

**Completed Work:**
- ✅ Created TypedDict definitions in `autoflow/core/types.py`
- ✅ Added typed JSON helpers in `autoflow/utils/file_helpers.py`
- ✅ Migrated autoflow_cli.py to use TasksFile, ReviewState, StrategyMemory
- ✅ Updated collaboration module to use ActivityMetadata, NotificationMetadata
- ✅ Updated core/config.py and core/dependency.py to use TypedDict
- ✅ Updated core/repository.py RepositoryDependency to use typed metadata

**Remaining Work:**
- ⚠️ Fix StateManager union type issues (139 errors)
- ⚠️ Complete migration to typed JSON helpers
- ⚠️ Fix remaining no-any-return issues
- ⚠️ Add missing type annotations
- ⚠️ Fix client API type mismatches

## MyPy Configuration

To run mypy with specific error codes filtered:
```bash
# Check only specific error categories
python3 -m mypy autoflow/ --disable-error-code=no-any-return
python3 -m mypy autoflow/ --disable-error-code=union-attr

# Generate HTML report
python3 -m mypy autoflow/ --html-report ./mypy-report

# Check specific files
python3 -m mypy autoflow/core/state.py autoflow/core/repository.py
```

## Conclusion

The mypy type checker found **516 errors** across the autoflow codebase. The majority of issues stem from:

1. **Union type handling** in StateManager (~40% of errors)
2. **Type assertion issues** after JSON parsing (~15% of errors)
3. **Missing type annotations** (~10% of errors)
4. **Optional/None handling** (~10% of errors)

**Good News:**
- The TypedDict infrastructure is in place
- Typed JSON helper functions are available
- Many core modules have been updated (collaboration, config, dependency)
- The errors are concentrated in specific files, making them tractable

**Next Steps:**
1. Prioritize fixing StateManager union issues (highest impact)
2. Migrate remaining code to typed JSON helpers
3. Add type guards and isinstance checks
4. Complete missing type annotations
5. Re-run mypy to verify improvements

**Estimated Total Effort:** 15-20 hours to resolve all high and medium priority issues

---

**Report Generated:** 2026-03-16
**Command:** `python3 -m mypy autoflow/`
**Full Output:** See `mypy_report.txt` for complete error listing
