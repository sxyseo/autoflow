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
5. Sync discovered CLI/ACP agents into `.autoflow/agents.json`
6. Resolve the best backend agent for the next role from explicit config plus fallback preferences
7. Ensure the spec has an isolated worktree before dispatch
8. If no active run exists, dispatch the next ready task in `tmux`

If `review_status.valid` is false for an implementation or maintenance task, the loop must stop and wait for re-approval.
If a task has already failed the configured number of automatic retries, the loop must stop and report the retry-limit blocker.
If a retry run is created, the agent runner will prefer the backend's native continuation mode when configured.
If a configured role agent is unavailable, the loop can fall back to a discovered `codex`, `claude`, or ACP-backed agent according to `agent_selection.role_preferences`.

### `scripts/autonomy_orchestrator.py`

This is the outer-loop entry point for OpenClaw-style scheduling or timed automation.

Example:

```bash
python3 scripts/autonomy_orchestrator.py tick \
  --spec openclaw-autonomy \
  --config config/autonomy.example.json \
  --commit-if-dirty \
  --dispatch \
  --push
```

It adds:

- CLI health checks for `codex`, `claude`, and `tmux`
- Taskmaster import/export hooks
- a coordination brief for outer orchestrators
- one stable command for scheduled jobs to call

### `scripts/cli_healthcheck.py`

Use this for scheduled monitoring of local coding backends.

Example:

```bash
python3 scripts/cli_healthcheck.py --require codex --require claude
```

### `scripts/git-auto-commit.sh`

This is a low-level helper when you only want commit and push behavior without dispatch logic.

## Safety rules

- Prefer pushing to a dedicated automation branch first.
- Prefer one worktree per spec instead of running all tasks from the repo root.
- Keep reviewer runs separate from implementation runs.
- Do not dispatch a new task while another task for the same spec is still active.
- Require `QA_FIX_REQUEST.md` before retrying reviewer-rejected implementation work.
- Add stronger verification commands before allowing direct push to `main`.
