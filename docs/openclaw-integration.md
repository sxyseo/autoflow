# OpenClaw Integration

## Goal

Use OpenClaw as the outer agent host and let Autoflow provide the persistent workflow state.

## Contract

OpenClaw should not own long-lived project state directly. Instead it should call Autoflow commands and read Autoflow artifacts.

### State owned by Autoflow

- `.autoflow/specs/<slug>/spec.md`
- `.autoflow/tasks/<slug>.json`
- `.autoflow/specs/<slug>/handoffs/*.md`
- `.autoflow/runs/<run-id>/`

### Decisions owned by OpenClaw

- which role to run next
- which concrete backend to assign
- whether to retry, escalate, or stop

## Suggested loop

1. Call `python3 scripts/autoflow.py workflow-state --spec <slug>`
2. Pick `recommended_next_action`
3. Map `owner_role` to an agent backend
4. Call `scripts/workflow-dispatch.sh <slug> <role> <agent> <task-id>`
5. Wait for the background run to finish
6. Call `python3 scripts/autoflow.py complete-run ...`
7. Repeat until no ready tasks remain

## Role to backend mapping

Suggested starting map:

- `spec-writer` -> `codex-spec`
- `task-graph-manager` -> `codex-spec`
- `implementation-runner` -> `codex-impl`
- `reviewer` -> `claude-review`
- `maintainer` -> `codex-impl`

## Important rule

Do not let the implementation role mark its own task `done`. A reviewer or maintainer step must close the task.
