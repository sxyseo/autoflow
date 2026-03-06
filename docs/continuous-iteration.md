# Continuous Iteration

## Goal

Turn Autoflow from a manually-invoked harness into a scheduled delivery loop that can:

- inspect the next ready task
- dispatch the correct role to the correct backend agent
- commit repository changes if the worktree is dirty
- push the current branch to GitHub

## Recommended cadence

Start with every 6 hours, not every few minutes. That gives runs time to finish and reduces noisy commits.

## Scripts

### `scripts/continuous_iteration.py`

This is the phase 3 entry point for a scheduled loop.

Example:

```bash
python3 scripts/continuous_iteration.py \
  --spec openclaw-autonomy \
  --config config/continuous-iteration.example.json \
  --commit-if-dirty \
  --dispatch \
  --push
```

Behavior:

1. Run lightweight verification commands from config
2. If the worktree is dirty, commit all changes
3. Push the current branch to GitHub if enabled
4. Inspect `workflow-state`
5. Ensure the spec has an isolated worktree before dispatch
6. If no active run exists, dispatch the next ready task in `tmux`

If `review_status.valid` is false for an implementation or maintenance task, the loop must stop and wait for re-approval.

### `scripts/git-auto-commit.sh`

This is a low-level helper when you only want commit and push behavior without dispatch logic.

## Safety rules

- Prefer pushing to a dedicated automation branch first.
- Prefer one worktree per spec instead of running all tasks from the repo root.
- Keep reviewer runs separate from implementation runs.
- Do not dispatch a new task while another task for the same spec is still active.
- Add stronger verification commands before allowing direct push to `main`.
