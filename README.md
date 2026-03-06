# Autoflow

Autoflow is a thin control plane for autonomous software delivery. It is designed to let OpenClaw or other agent hosts run a repeatable loop around spec creation, task decomposition, implementation, review, and maintenance while delegating concrete coding work to `codex`, `claude`, or other CLI agents.

The initial goal is not full autonomy. The initial goal is a reliable harness:

- explicit specs and task state
- deterministic prompt assembly
- swappable agent backends
- background execution via `tmux`
- review and merge gates
- resumable runs with logs

## Why this shape

OpenAI's Harness Engineering article argues that strong agents come from a strong harness: evaluation, orchestration, checkpoints, and clear contracts around tool use. This repository applies that idea to software development:

- `spec` defines intent
- `tasks` define work units and dependencies
- `skills` define reusable workflows
- `runs` store concrete executions
- `agents.json` maps logical roles to concrete CLIs

## Proposed stack

Use OpenClaw as the outer orchestrator. Use this repository as the workflow contract that OpenClaw executes. Use other methods as focused subsystems rather than one merged meta-framework:

- Taskmaster AI: task graph and execution backlog
- BMAD: role framing and delivery checkpoints
- Spec Driven Development: spec-first artifact flow
- Symphony: optional future orchestrator for structured multi-agent workflows

Recommendation: start with OpenClaw + spec-driven artifacts + Taskmaster-style task graph. Add BMAD role prompts next. Add Symphony only after the single-node harness is stable.

## Repository layout

```text
config/
  agents.example.json
docs/
  auto-claude-lessons.md
  architecture.md
  method-stack.md
  control-loop.md
  continuous-iteration.md
  openclaw-integration.md
  phase4-plan.md
scripts/
  autoflow.py
  continuous_iteration.py
  git-auto-commit.sh
  git-prepare-branch.sh
  run-agent.sh
  tmux-start.sh
  workflow-dispatch.sh
skills/
  iteration-manager/
  openclaw-orchestrator/
  spec-writer/
  task-graph-manager/
  implementation-runner/
  reviewer/
  maintainer/
templates/
  bmad/
.autoflow/
  specs/
  tasks/
  runs/
  logs/
```

## Quick start

1. Copy the agent config.

```bash
cp config/agents.example.json .autoflow/agents.json
```

2. Create the local state directories.

```bash
python3 scripts/autoflow.py init
```

3. Create a spec and seed tasks.

```bash
python3 scripts/autoflow.py new-spec \
  --slug openclaw-autonomy \
  --title "OpenClaw autonomous development system" \
  --summary "Build a multi-agent autonomous development harness with skills, task graph, review gates, and background execution."
```

4. Generate a run prompt for a role.

```bash
python3 scripts/autoflow.py new-run \
  --spec openclaw-autonomy \
  --role spec-writer \
  --agent codex-spec \
  --task T1
```

5. Launch the run in `tmux`.

```bash
scripts/tmux-start.sh .autoflow/runs/<run-id>/run.sh
```

6. Inspect the workflow state.

```bash
python3 scripts/autoflow.py workflow-state --spec openclaw-autonomy
```

7. Close a finished run and advance task state.

```bash
python3 scripts/autoflow.py complete-run \
  --run <run-id> \
  --result success \
  --summary "Implementation finished and is ready for review."
```

8. Run one scheduled iteration tick.

```bash
python3 scripts/continuous_iteration.py \
  --spec openclaw-autonomy \
  --config config/continuous-iteration.example.json \
  --commit-if-dirty \
  --dispatch \
  --push
```

## What is implemented now

This repository now provides a minimal autonomous workflow harness:

- repository structure and docs
- reusable skill definitions
- agent mapping config
- a Python control-plane CLI with task lifecycle support
- shell wrappers for local agent execution, branch prep, auto-commit, and `tmux`
- handoff artifacts and a review gate
- an OpenClaw-oriented dispatch contract
- BMAD role templates injected into prompts
- a phase 3 continuous iteration loop for scheduled commit and dispatch
- per-spec worktree support inspired by Auto-Claude
- hash-based review approval and invalidation
- recovery-aware prompts and per-spec event logs
- review-gated implementation dispatch after planning changes
- reviewer-generated `QA_FIX_REQUEST.md` artifacts and resumable retry runs

It still does not integrate directly with Taskmaster AI or Symphony APIs. BMAD is currently used as a prompt-template layer, not yet as a richer handoff framework.
