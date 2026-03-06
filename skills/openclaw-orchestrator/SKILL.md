---
name: openclaw-orchestrator
description: Orchestrate the Autoflow control loop from OpenClaw or another outer agent host. Use when the system must inspect workflow state, choose the next role, dispatch a background run, and close the loop after execution.
---

# OpenClaw Orchestrator

Use Autoflow as the persistent state layer.

## Workflow

1. Call `python3 scripts/autoflow.py workflow-state --spec <slug>`.
2. Select the next ready task.
3. Check review status and active runs.
4. Map the task role to a configured agent backend.
5. Ensure the spec worktree exists.
6. Call `scripts/workflow-dispatch.sh <slug> <role> <agent> <task-id>`.
7. When the run finishes, record the result with `python3 scripts/autoflow.py complete-run ...`.

## Rules

- Do not let a coding role mark itself `done`.
- Always preserve run metadata, prompt artifacts, and handoffs.
- Prefer one active implementation run at a time until review gates are proven stable.
