---
name: iteration-manager
description: Run Autoflow as a continuous delivery loop. Use when the system should inspect workflow state, commit dirty changes, push to GitHub, and dispatch the next ready role on a schedule.
---

# Iteration Manager

Use `scripts/continuous_iteration.py` as the entry point.

## Workflow

1. Check whether the repository has uncommitted changes.
2. Run configured verification commands.
3. Commit and optionally push if the worktree is dirty.
4. Read `workflow-state`.
5. If there is no active run, dispatch the next ready task.

## Rules

- Prefer a dedicated automation branch unless the repository already has strong protections.
- Do not dispatch multiple implementation tasks concurrently by default.
- If verification fails, stop before commit or push.
