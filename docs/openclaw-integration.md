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

1. Call `python3 scripts/autonomy_orchestrator.py coordination-brief --spec <slug>`
2. Read `workflow_state`, `strategy`, `health`, and `proposed_dispatch`
3. If a task is ready, ensure the role/agent selection still satisfies your outer policy
4. Call `python3 scripts/autonomy_orchestrator.py tick --spec <slug> --dispatch`
5. Wait for the background run to finish
6. Call `python3 scripts/autoflow.py complete-run ...`
7. Repeat until no ready tasks remain

If `workflow-state` reports `review_approval_required`, do not dispatch implementation. Re-approve the spec first.
If the retry policy blocks a task, stop and surface the blocker instead of silently re-running the same task.
If a retry run exists, let the configured backend use its native continuation mode instead of starting a brand-new session blindly.
If the strategy playbook shows recurring blockers, feed that back into planning instead of continuing blind retries.

## Role to backend mapping

Suggested starting map:

- `spec-writer` -> `codex-spec`
- `task-graph-manager` -> `codex-spec`
- `implementation-runner` -> `codex-impl`
- `reviewer` -> `claude-review`
- `maintainer` -> `codex-impl`

## Important rule

Do not let the implementation role mark its own task `done`. A reviewer or maintainer step must close the task.
