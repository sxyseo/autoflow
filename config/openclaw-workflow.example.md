# OpenClaw Workflow Contract

## Goal

Define a declarative workflow contract that external orchestrators (like OpenClaw) can use to drive Autoflow's autonomous execution loop through well-defined commands and structured outputs.

## Contract structure

The workflow contract is a JSON document with the following shape:

```json
{
  "name": "autoflow-openclaw-loop",
  "description": "Example outer-loop contract for OpenClaw-style orchestration around Autoflow state.",
  "steps": [
    {
      "id": "coordination-brief",
      "command": "python3 scripts/autonomy_orchestrator.py coordination-brief --spec <slug> --config config/autonomy.example.json",
      "output": "json"
    },
    {
      "id": "outer-tick",
      "command": "python3 scripts/autonomy_orchestrator.py tick --spec <slug> --config config/autonomy.example.json --dispatch",
      "output": "json"
    }
  ]
}
```

### Top-level fields

- `name` (string): Identifier for this workflow contract
- `description` (string): Human-readable description of the workflow's purpose
- `steps` (array): Ordered list of workflow steps to execute

### Step configuration

Each step in the `steps` array defines:

- `id` (string): Unique identifier for this step (used for logging and tracking)
- `command` (string): Shell command to execute (see interpolation below)
- `output` (string): Expected output format, currently supports:
  - `"json"`: Command emits structured JSON for programmatic consumption
  - `"text"`: Plain text output (for logging or human review)

### Command interpolation

The `<slug>` token in step commands is a placeholder that gets replaced with the current spec identifier at runtime.

Example: If `<slug>` is `openclaw-autonomy`, the command becomes:

```bash
python3 scripts/autonomy_orchestrator.py coordination-brief --spec openclaw-autonomy --config config/autonomy.example.json
```

Common tokens:
- `<slug>`: Spec identifier (e.g., `openclaw-autonomy`, `my-feature-spec`)
- Future tokens may include: `<run-id>`, `<task-id>`, `<role>`

### Output types and coordination flow

#### Step: `coordination-brief`

**Purpose:** Gather context and propose the next action without executing it.

**Output schema:**

```json
{
  "spec": "openclaw-autonomy",
  "workflow_state": {
    "status": "in_progress",
    "active_run_id": "run-001",
    "recommended_next_action": {
      "id": "task-123",
      "owner_role": "implementation-runner",
      "requires_review_approval": false
    }
  },
  "strategy": {
    "playbook": [...],
    "blockers": [],
    "retry_counts": {}
  },
  "health": {
    "status": "ok",
    "binaries": ["codex", "claude", "tmux"],
    "returncode": 0
  },
  "available_agents": ["codex-spec", "codex-impl", "claude-review"],
  "discovered_agents": ["codex", "claude"],
  "proposed_dispatch": {
    "task": "task-123",
    "role": "implementation-runner",
    "agent": "codex-impl",
    "agent_selection": "explicit_config"
  },
  "openclaw": {
    "policy_level": "supervised",
    "max_retries": 3
  }
}
```

**Usage:** The outer orchestrator should:
1. Read `workflow_state.status` to understand current state
2. Check `health.status` before proceeding
3. Review `proposed_dispatch` to validate role/agent assignment against outer policy
4. Inspect `strategy.blockers` for any stop conditions
5. Only proceed to `outer-tick` if all checks pass

#### Step: `outer-tick`

**Purpose:** Execute the next action in the workflow, optionally dispatching work.

**Command flags:**
- `--spec <slug>`: Target spec identifier
- `--config <path>`: Path to autonomy configuration file
- `--dispatch`: Actually dispatch the task (omit for dry-run)
- `--commit-if-dirty`: Commit uncommitted changes before dispatch
- `--push`: Push branch to remote after commit

**Output schema:**

```json
{
  "spec": "openclaw-autonomy",
  "tick_result": "dispatched",
  "dispatch": {
    "task_id": "task-123",
    "role": "implementation-runner",
    "agent": "codex-impl",
    "run_id": "run-002",
    "mode": "background"
  },
  "git": {
    "committed": true,
    "commit_hash": "abc123",
    "pushed": true
  },
  "health": {
    "status": "ok"
  },
  "blockers": []
}
```

**Usage:** The outer orchestrator should:
1. Wait for the background run to complete (check `run_id` status)
2. Call `complete-run` after the task finishes
3. Repeat from `coordination-brief` for the next iteration
4. Stop if `blockers` is non-empty or `tick_result` indicates completion

## Coordination flow

The recommended orchestration loop:

1. **Inspect:** Call `coordination-brief` to get current state
2. **Validate:** Check `health`, `strategy.blockers`, and `proposed_dispatch`
3. **Execute:** If valid, call `outer-tick` with `--dispatch`
4. **Wait:** Monitor the dispatched background run
5. **Finalize:** Call `complete-run` to mark the task done
6. **Repeat:** Return to step 1 until no ready tasks remain

## Safety rules

- Always call `coordination-brief` before `outer-tick` to validate preconditions
- Never dispatch if `health.status` is `"degraded"` or `strategy.blockers` is non-empty
- Respect `review_approval_required` in `workflow_state` before dispatching implementation
- Do not dispatch a new task if `active_run_id` already exists for the spec
- Require `QA_FIX_REQUEST.md` before retrying reviewer-rejected implementation work
- Use `--commit-if-dirty` and `--push` flags cautiously in automation branches
- Prefer one worktree per spec instead of running all tasks from the repo root
