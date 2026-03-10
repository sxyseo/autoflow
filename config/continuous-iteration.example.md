# Continuous Iteration Configuration

## Goal

Define configuration for the continuous iteration loop that turns Autoflow from a manually-invoked harness into a scheduled delivery system. This configuration enables:

- Mapping task roles to specific backend agents
- Configuring agent discovery and fallback behavior
- Setting up verification commands before dispatch
- Managing automatic commit and push behavior
- Controlling retry policy for failed tasks

## File location

`config/continuous-iteration.json` (copy from `config/continuous-iteration.example.json`)

## Configuration structure

### `role_agents`

Map of role names to agent identifiers for explicit role-to-agent assignment.

#### Role name

- **Type:** `string` (key in the role_agents object)
- **Purpose:** Defines which agent handles a specific role in the workflow
- **Example:** `"spec-writer"`, `"implementation-runner"`, `"reviewer"`
- **Used by:** Agent selection logic when dispatching tasks

#### Agent identifier

- **Type:** `string` (value in the role_agents object)
- **Purpose:** References an agent defined in `config/agents.json` or discovered agents
- **Example:** `"codex-spec"`, `"claude-review"`, `"codex-impl"`
- **Resolution:**
  1. First checks `config/agents.json` for exact match
  2. Falls back to discovered agents in `.autoflow/agents.json`
  3. Uses role_preferences if configured agent unavailable
- **Note:** Agent must exist or be discoverable, otherwise dispatch fails

**Common role names:**

- `"spec-writer"`: Agent for writing and updating specs
- `"task-graph-manager"`: Agent for managing task dependencies
- `"implementation-runner"`: Agent for implementing tasks
- `"reviewer"`: Agent for reviewing and QA
- `"maintainer"`: Agent for maintenance tasks

### `agent_selection`

Agent discovery and selection behavior configuration.

#### `agent_selection.sync_before_dispatch`

Whether to sync discovered agents before dispatching.

- **Type:** `boolean`
- **Default:** `true`
- **Purpose:** Update `.autoflow/agents.json` with latest CLI/ACP agents
- **true:** Runs agent discovery before each dispatch
- **false:** Uses cached agent list from previous sync
- **Example:** `true`

#### `agent_selection.overwrite_discovered`

Whether explicit config agents overwrite discovered agents.

- **Type:** `boolean`
- **Default:** `false`
- **Purpose:** Control merge behavior between config and discovered agents
- **true:** Config agents completely replace discovered agents
- **false:** Config agents take precedence, but discovered agents remain available
- **Example:** `false`

#### `agent_selection.role_preferences`

Fallback agent preferences for each role when configured agent unavailable.

- **Type:** `object` (string → array mapping)
- **Purpose:** Define ordered list of preferred agents for each role
- **Role names:** Keys matching role names in `role_agents`
- **Agent lists:** Ordered array of agent identifiers (highest priority first)
- **Example:** `{"reviewer": ["claude-review", "claude"], "implementation-runner": ["codex-impl", "codex", "acp-example"]}`
- **Behavior:**
  - If configured agent unavailable, tries first preference
  - If first unavailable, tries second preference
  - Continues until agent found or list exhausted
- **Used by:** Agent selection fallback logic
- **Note:** Preferences include both explicit agents and discovered agents (e.g., `"codex"`, `"claude"`)

### `verify_commands`

List of shell commands to run before dispatching a task.

- **Type:** `array` of `string`
- **Purpose:** Pre-dispatch verification to ensure system health
- **Execution:** Commands run in order, all must succeed (exit code 0)
- **Failure:** If any command fails, loop stops and reports error
- **Example:** `["bash scripts/ci_check.sh", "python3 scripts/autoflow.py workflow-state --spec {spec}"]`
- **Variables:** `{spec}` is replaced with current spec identifier
- **Common uses:**
  - CI checks (linting, type checking)
  - Workflow state validation
  - Dependency availability checks
  - Repository status checks
- **Note:** Keep these commands lightweight for frequent scheduled runs

### `commit`

Automatic commit and push behavior configuration.

#### `commit.message_prefix`

Prefix for auto-generated commit messages.

- **Type:** `string`
- **Default:** `"autoflow"`
- **Purpose:** Identify commits made by the continuous iteration loop
- **Format:** Messages are `{prefix}: {specific message}`
- **Example:** `"autoflow"` produces commits like `"autoflow: Completed task 1-2"`
- **Note:** Use descriptive prefixes to distinguish automation from manual commits

#### `commit.push`

Whether to push commits to remote repository.

- **Type:** `boolean`
- **Default:** `true`
- **Purpose:** Enable automatic push after commit
- **true:** Commits are pushed to remote branch
- **false:** Commits are local only
- **Example:** `true`
- **Safety:** Consider setting to `false` for testing or when pushing to protected branches

#### `commit.allow_during_active_runs`

Whether to commit while a task run is active.

- **Type:** `boolean`
- **Default:** `false`
- **Purpose:** Control commit timing relative to task execution
- **true:** Can commit even if agent session is running
- **false:** Only commits when no active runs for the spec
- **Example:** `false`
- **Safety:** Setting to `true` risks committing partial/incorrect work
- **Recommendation:** Keep `false` to only commit completed work

### `retry_policy`

Automatic retry behavior for failed tasks.

#### `retry_policy.max_automatic_attempts`

Maximum number of automatic retry attempts.

- **Type:** `integer`
- **Default:** `3`
- **Purpose:** Limit how many times a task can be automatically retried
- **Behavior:** Loop stops and reports retry-limit blocker when exceeded
- **Example:** `3`
- **Note:** Only counts automatic retries, manual retries not limited here
- **Safety:** Prevents infinite retry loops on fundamentally broken tasks

#### `retry_policy.require_fix_request_for_retry`

Whether to require QA_FIX_REQUEST.md for retrying reviewer-rejected tasks.

- **Type:** `boolean`
- **Default:** `true`
- **Purpose:** Enforce human review before retrying rejected implementation work
- **true:** If `review_status.valid` is false, loop stops and waits for QA_FIX_REQUEST.md
- **false:** Can automatically retry even if reviewer rejected the work
- **Example:** `true`
- **Safety:** Setting to `false` may retry work that reviewer has identified as incorrect
- **Recommendation:** Keep `true` for safety, only disable for fully automated workflows

## Usage examples

### Minimal configuration

```json
{
  "role_agents": {
    "implementation-runner": "codex-impl",
    "reviewer": "claude-review"
  },
  "agent_selection": {
    "sync_before_dispatch": true,
    "overwrite_discovered": false,
    "role_preferences": {}
  },
  "verify_commands": [],
  "commit": {
    "message_prefix": "autoflow",
    "push": false,
    "allow_during_active_runs": false
  },
  "retry_policy": {
    "max_automatic_attempts": 3,
    "require_fix_request_for_retry": true
  }
}
```

### Production-ready configuration with full workflow

```json
{
  "role_agents": {
    "spec-writer": "codex-spec",
    "task-graph-manager": "codex-spec",
    "implementation-runner": "codex-impl",
    "reviewer": "claude-review",
    "maintainer": "codex-impl"
  },
  "agent_selection": {
    "sync_before_dispatch": true,
    "overwrite_discovered": false,
    "role_preferences": {
      "reviewer": [
        "claude-review",
        "claude"
      ],
      "implementation-runner": [
        "codex-impl",
        "codex",
        "acp-example"
      ]
    }
  },
  "verify_commands": [
    "bash scripts/ci_check.sh",
    "python3 scripts/autoflow.py workflow-state --spec {spec}"
  ],
  "commit": {
    "message_prefix": "autoflow",
    "push": true,
    "allow_during_active_runs": false
  },
  "retry_policy": {
    "max_automatic_attempts": 3,
    "require_fix_request_for_retry": true
  }
}
```

### Testing configuration (no push, permissive retries)

```json
{
  "role_agents": {
    "implementation-runner": "codex-test",
    "reviewer": "claude-review"
  },
  "agent_selection": {
    "sync_before_dispatch": false,
    "overwrite_discovered": false,
    "role_preferences": {
      "implementation-runner": ["codex-test", "codex"]
    }
  },
  "verify_commands": [
    "python3 scripts/autoflow.py workflow-state --spec {spec}"
  ],
  "commit": {
    "message_prefix": "autoflow-test",
    "push": false,
    "allow_during_active_runs": false
  },
  "retry_policy": {
    "max_automatic_attempts": 5,
    "require_fix_request_for_retry": false
  }
}
```

### Single-agent configuration (fallback to discovered agents)

```json
{
  "role_agents": {
    "implementation-runner": "codex",
    "reviewer": "claude"
  },
  "agent_selection": {
    "sync_before_dispatch": true,
    "overwrite_discovered": false,
    "role_preferences": {
      "implementation-runner": ["codex"],
      "reviewer": ["claude"]
    }
  },
  "verify_commands": [],
  "commit": {
    "message_prefix": "autoflow",
    "push": true,
    "allow_during_active_runs": false
  },
  "retry_policy": {
    "max_automatic_attempts": 2,
    "require_fix_request_for_retry": true
  }
}
```

## Field interactions

### Role agents and agent selection

- **Explicit mapping:** `role_agents` defines preferred agent for each role
- **Fallback chain:** If explicit agent unavailable, `agent_selection.role_preferences` is used
- **Discovery sync:** `agent_selection.sync_before_dispatch` ensures latest agents available
- **Merge behavior:** `agent_selection.overwrite_discovered` controls how config and discovery merge

### Verify commands and commit behavior

- **Pre-dispatch check:** `verify_commands` run before any task dispatch
- **Commit timing:** Commit only happens if verify commands pass and worktree is dirty
- **Active runs:** `commit.allow_during_active_runs` controls whether commit can happen during task execution
- **Push behavior:** `commit.push` determines if commits are pushed to remote

### Retry policy and review status

- **Review rejection:** If `review_status.valid` is false and `require_fix_request_for_retry` is true, loop stops
- **Retry limit:** If `max_automatic_attempts` exceeded, loop stops and reports blocker
- **Automatic vs manual:** Retry policy only applies to automatic retries, manual retries not limited
- **Fix request:** QA_FIX_REQUEST.md file signals human-reviewed fixes for retry

### Agent selection and discovered agents

- **Sync process:** When `sync_before_dispatch` is true:
  1. Discovers CLI agents (codex, claude, etc.)
  2. Merges ACP agents from system config registry
  3. Writes to `.autoflow/agents.json`
  4. Uses merged list for agent resolution
- **Fallback behavior:** Role preferences can reference discovered agents
- **Preference order:** First choice is explicit agent, then preferences in order

## Integration with continuous iteration scripts

### `scripts/continuous_iteration.py`

This is the main entry point for scheduled loops.

**Command-line flags:**

- `--config`: Path to this configuration file
- `--commit-if-dirty`: Enable commit behavior (overrides `commit` section)
- `--dispatch`: Enable task dispatch
- `--push`: Enable push behavior (overrides `commit.push`)

**Execution flow:**

1. Load this configuration file
2. Run `verify_commands` from config
3. If `--commit-if-dirty` and worktree dirty, commit with `message_prefix`
4. If `--push` and `commit.push` is true, push to remote
5. Inspect workflow state for next ready task
6. Sync agents if `sync_before_dispatch` is true
7. Resolve agent for next role using `role_agents` and fallbacks
8. Check `retry_policy` before creating retry run
9. If no active run, dispatch task in tmux

### `scripts/autonomy_orchestrator.py`

Outer-loop orchestrator that references this config.

**Integration:**

- Uses `continuous_iteration_config` field in autonomy config to reference this file
- Adds CLI health checks before calling continuous iteration
- Provides Taskmaster integration hooks
- Wraps continuous iteration with additional safety checks

### `scripts/git-auto-commit.sh`

Low-level helper for commit-only behavior (no dispatch).

**When to use:**

- Only want commit and push without task dispatch
- Manual workflow with automated commits
- Testing commit behavior in isolation

## Safety considerations

### Commit and push behavior

- **Branch safety:** Prefer pushing to dedicated automation branch before main
- **Active runs:** Keep `allow_during_active_runs: false` to avoid partial commits
- **Testing:** Set `push: false` when testing to avoid pushing incomplete work
- **Message prefix:** Use clear prefixes to identify automation commits

### Agent selection

- **Fallback risk:** Role preferences can fallback to less-capable agents
- **Discovery:** Enable `sync_before_dispatch` for latest agent availability
- **Overwrite:** Keep `overwrite_discovered: false` to preserve fallback options
- **Validation:** Test role_preferences chain before production use

### Retry policy

- **Infinite loops:** `max_automatic_attempts` prevents endless retries
- **Review rejection:** `require_fix_request_for_retry` ensures human oversight
- **Fix requests:** QA_FIX_REQUEST.md file enables manual retry approval
- **Task blocking:** Reviewer rejection stops loop until fix request provided

### Verify commands

- **Performance:** Keep commands lightweight for scheduled runs (every 6 hours recommended)
- **Fail-fast:** All commands must pass for dispatch to proceed
- **Workflow state:** Include workflow-state check to detect blocked tasks
- **CI integration:** Use existing CI scripts for verification consistency

### Scheduled execution

- **Cadence:** Start with every 6 hours, not every few minutes
- **Worktree isolation:** Use one worktree per spec, not repo root
- **Reviewer separation:** Keep reviewer runs separate from implementation runs
- **Active tasks:** Never dispatch new task while another task for same spec is active

## Best practices

### Configuration setup

- **Map all roles:** Define agents for all roles used in your workflow
- **Set preferences:** Configure role_preferences for all critical roles
- **Enable sync:** Keep `sync_before_dispatch: true` for agent availability
- **Verify commands:** Include at minimum a workflow-state check
- **Test locally:** Run continuous iteration manually before scheduling

### Commit behavior

- **Clear prefixes:** Use descriptive `message_prefix` values
- **Push safety:** Set `push: false` for testing, `true` for production
- **Active runs:** Keep `allow_during_active_runs: false` for safety
- **Branch strategy:** Push to feature branches, not directly to main

### Retry policy

- **Conservative limits:** Start with `max_automatic_attempts: 2` or `3`
- **Review oversight:** Keep `require_fix_request_for_retry: true`
- **Manual intervention:** Use QA_FIX_REQUEST.md for human-guided fixes
- **Monitor blockers:** Check workflow-state when loop stops

### Agent selection

- **Explicit agents:** Define agents in agents.json for reliability
- **Fallback chain:** Order role_preferences by capability and reliability
- **Discovery sync:** Enable to catch agent availability changes
- **Test fallbacks:** Verify each preference in the chain works

### Verification commands

- **Quick checks:** Use fast-running commands for scheduled execution
- **CI integration:** Reuse existing CI/check scripts
- **State validation:** Always check workflow-state
- **Dependency checks:** Verify required tools and binaries available

### Scheduled execution

- **Conservative cadence:** Every 6 hours recommended starting point
- **Worktree isolation:** One worktree per spec for safety
- **Monitoring:** Set up alerts for loop failures
- **Manual review:** Review automation commits regularly
- **Rollback plan:** Keep ability to disable automation quickly

## Troubleshooting

### Agent not found

- Check agent identifier in `role_agents` matches `agents.json`
- Verify `sync_before_dispatch` is enabled
- Review role_preferences fallback chain
- Check `.autoflow/agents.json` for discovered agents

### Verify commands failing

- Run commands manually to test
- Check command paths are correct
- Verify variables like `{spec}` are properly replaced
- Review command exit codes and error output

### Commits not pushing

- Verify `commit.push` is `true`
- Check git remote is configured
- Verify branch tracking is set up
- Review git push permissions for remote

### Retries not happening

- Check `retry_policy.max_automatic_attempts` not exceeded
- Verify `review_status.valid` if `require_fix_request_for_retry` is true
- Look for retry-limit blocker in workflow state
- Review task run history for failed attempts

### Loop stopping unexpectedly

- Check workflow-state for blockers
- Review verify commands for failures
- Verify agent availability
- Check retry policy limits
- Look for reviewer rejection requiring fix request

### Agent selection not using preferences

- Verify `sync_before_dispatch` is true
- Check configured agent is actually unavailable
- Review role_preferences array order
- Test discovered agents in `.autoflow/agents.json`
