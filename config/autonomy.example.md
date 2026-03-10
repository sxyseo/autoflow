# Autonomy Configuration

## Purpose

The autonomy configuration file (`autonomy.example.json`) controls the outer-loop orchestration layer for automated Autoflow runs. It extends continuous iteration with health monitoring, external task tracking integration, and OpenClaw-style scheduling hooks.

This is the primary configuration for `scripts/autonomy_orchestrator.py`, which provides a stable entry point for scheduled jobs (cron, GitHub Actions, Airflow, etc.).

## Configuration Structure

### `continuous_iteration_config`

Path to the continuous iteration configuration file that contains agent selection, verification commands, and retry policy.

**Type:** `string` (file path)

**Example:** `"config/continuous-iteration.example.json"`

**Notes:**
- Path is relative to the repository root
- Must be a valid JSON file with continuous iteration schema
- This config provides the core dispatch logic that autonomy orchestrator wraps

### `monitoring`

Health check configuration for local coding backends and infrastructure.

#### `monitoring.block_on_missing_binaries`

Whether to stop the loop if required binaries are not available.

**Type:** `boolean`

**Default:** `true`

**Behavior:**
- When `true`: The orchestrator will exit with an error if any required binary is missing
- When `false`: The orchestrator will continue but report degraded status

**Recommended:** Keep as `true` for production automation to prevent silent failures.

#### `monitoring.required_binaries`

List of command-line tools that must be available on the system PATH.

**Type:** `array` of strings

**Supported values:**
- `"codex"` - OpenAI Codex CLI
- `"claude"` - Anthropic Claude CLI
- `"tmux"` - Terminal multiplexer for session management

**Example:**
```json
"required_binaries": ["codex", "claude"]
```

**Health check behavior:**
- Each binary is probed for availability using `which`
- Version information is captured (via `--version` or `-V` flag)
- Capabilities are detected (resume support, model flags, etc.)
- If any required binary is missing and `block_on_missing_binaries` is `true`, the orchestrator exits

### `taskmaster`

External task tracking integration settings for importing/exporting workflow state.

#### `taskmaster.enabled`

Whether to enable taskmaster integration.

**Type:** `boolean`

**Default:** `false`

**Behavior:**
- When `false`: Import/export hooks are skipped
- When `true`: The orchestrator will run import/export commands on each tick

#### `taskmaster.import_file`

Path to a JSON file containing external task state to import into Autoflow.

**Type:** `string` (file path)

**Default:** `""` (empty string = no import)

**Example:** `".autoflow/integrations/taskmaster/openclaw-autonomy.json"`

**Behavior:**
- File is read before dispatch logic runs
- Must be a valid JSON file matching taskmaster import schema
- Path can be relative to repository root or absolute
- If file doesn't exist, import is skipped with a warning

#### `taskmaster.export_file`

Path where current workflow state should be exported for external systems.

**Type:** `string` (file path)

**Default:** `""` (empty string = no export)

**Example:** `".autoflow/integrations/taskmaster/openclaw-autonomy.json"`

**Behavior:**
- File is written after each orchestrator tick completes
- Export includes current workflow state, task statuses, and recommendations
- Parent directories are created if they don't exist
- Useful for external schedulers that need to inspect Autoflow state

### `openclaw`

OpenClaw integration settings for workflow-based orchestration.

#### `openclaw.workflow_contract`

Path to the OpenClaw workflow definition file.

**Type:** `string` (file path)

**Example:** `"config/openclaw-workflow.example.json"`

**Purpose:** Defines the steps and commands that external orchestrators should execute.

**Workflow schema:**
```json
{
  "name": "workflow-name",
  "description": "Human-readable description",
  "steps": [
    {
      "id": "step-name",
      "command": "command with <slug> interpolation",
      "output": "json"
    }
  ]
}
```

#### `openclaw.dispatch_mode`

The orchestration mode for Autoflow dispatch.

**Type:** `string`

**Supported values:**
- `"autoflow-tick"` - Standard Autoflow dispatch (default)
- Future modes may include `"openclaw-managed"` for tighter integration

**Behavior:**
- Controls how tasks are dispatched to backend agents
- `"autoflow-tick"` uses Autoflow's native tmux-based dispatch
- Mode selection affects how coordination brief is structured

#### `openclaw.notes`

Array of informational notes for external orchestrators and operators.

**Type:** `array` of strings

**Example:**
```json
"notes": [
  "Read coordination-brief first.",
  "Honor review and retry gates before dispatching implementation work."
]
```

**Purpose:**
- Documents operational constraints and expectations
- Visible in coordination brief output for external systems
- Used to communicate safety requirements to outer loops

## Usage Examples

### Basic usage with health checks

```bash
python3 scripts/autonomy_orchestrator.py tick \
  --spec openclaw-autonomy \
  --config config/autonomy.example.json \
  --commit-if-dirty \
  --dispatch \
  --push
```

This command:
1. Runs health checks for required binaries (codex, claude, tmux)
2. Commits any dirty worktree changes
3. Imports from taskmaster if configured
4. Dispatches the next ready task
5. Exports to taskmaster if configured
6. Pushes to GitHub if configured in continuous iteration config

### Generate coordination brief for external orchestrator

```bash
python3 scripts/autonomy_orchestrator.py coordination-brief \
  --spec openclaw-autonomy \
  --config config/autonomy.example.json
```

Output includes:
- Current workflow state
- Strategy information
- Health check results
- Available agents
- Proposed next dispatch
- OpenClaw integration notes

### Standalone health check

```bash
python3 scripts/cli_healthcheck.py --require codex --require claude
```

This can be used independently for monitoring alerts.

## Integration with Continuous Iteration

The autonomy config wraps and extends the continuous iteration config:

- **Agent selection** - Delegated to `continuous_iteration_config`
- **Verification commands** - Run from continuous iteration config
- **Retry policy** - Controlled by continuous iteration config
- **Commit/push behavior** - Controlled by continuous iteration config
- **Health monitoring** - Added by autonomy config
- **Taskmaster sync** - Added by autonomy config
- **OpenClaw hooks** - Added by autonomy config

## Safety Considerations

### Health checks
- Always require critical binaries in production automation
- Use monitoring alerts for early detection of degraded infrastructure
- Test health check commands in non-production environments first

### Taskmaster integration
- Use atomic file operations for import/export
- Validate external JSON schemas before importing
- Keep import/export paths outside of repository root when possible
- Consider file locking if multiple processes may access the same files

### OpenClaw workflows
- Keep coordination brief as the source of truth for next actions
- Respect `review_status.valid` gates before dispatching
- Honor retry limits to avoid infinite loops
- Use dedicated automation branches for safety

### Commit behavior
- Prefer pushing to dedicated automation branches first
- Avoid direct commits to `main` without strong verification
- Keep reviewer runs separate from implementation runs
- Never dispatch a new task while another task for the same spec is active
