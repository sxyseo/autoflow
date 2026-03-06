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
  system.example.json
docs/
  auto-claude-lessons.md
  architecture.md
  method-stack.md
  control-loop.md
  continuous-iteration.md
  openclaw-integration.md
  phase4-plan.md
scripts/
  agent_runner.py
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

3. Initialize the local system config for memory, model profiles, tool profiles, and ACP registry entries.

```bash
python3 scripts/autoflow.py init-system-config
```

4. Discover local/ACP agents and materialize them into `.autoflow/agents.json` when needed.

```bash
python3 scripts/autoflow.py sync-agents
```

5. Create a spec and seed tasks.

```bash
python3 scripts/autoflow.py new-spec \
  --slug openclaw-autonomy \
  --title "OpenClaw autonomous development system" \
  --summary "Build a multi-agent autonomous development harness with skills, task graph, review gates, and background execution."
```

6. Generate a run prompt for a role.

```bash
python3 scripts/autoflow.py new-run \
  --spec openclaw-autonomy \
  --role spec-writer \
  --agent codex-spec \
  --task T1
```

7. Launch the run in `tmux`.

```bash
scripts/tmux-start.sh .autoflow/runs/<run-id>/run.sh
```

8. Inspect the workflow state.

```bash
python3 scripts/autoflow.py workflow-state --spec openclaw-autonomy
```

9. Close a finished run and advance task state.

```bash
python3 scripts/autoflow.py complete-run \
  --run <run-id> \
  --result success \
  --summary "Implementation finished and is ready for review."
```

10. Run one scheduled iteration tick.

```bash
python3 scripts/continuous_iteration.py \
  --spec openclaw-autonomy \
  --config config/continuous-iteration.example.json \
  --commit-if-dirty \
  --dispatch \
  --push
```

11. Inspect structured reviewer findings or stored memory.

```bash
python3 scripts/autoflow.py show-fix-request --spec openclaw-autonomy
python3 scripts/autoflow.py show-memory --scope spec --spec openclaw-autonomy
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
- reviewer-generated `QA_FIX_REQUEST.md` and `QA_FIX_REQUEST.json` artifacts with structured findings
- structured findings in prompt context with `file`, `line`, `severity`, `category`, `suggested_fix`, and `source_run`
- system-level memory configuration with scoped memory capture and prompt injection
- central model/tool profiles resolved from `config/system.example.json`
- CLI and ACP agent discovery plus `sync-agents` to materialize runnable local catalogs
- dynamic fallback agent selection during scheduled dispatch
- codex/claude native continuation wired through the agent runner

It still does not integrate directly with Taskmaster AI or Symphony APIs. BMAD is currently used as a prompt-template layer, not yet as a richer handoff framework.

## System configuration

Autoflow now has two configuration layers:

- `.autoflow/agents.json`: runnable agent catalog, role bindings, protocol details, and backend-specific resume behavior
- `.autoflow/system.json`: local memory settings, model profiles, tool profiles, and ACP registry entries

Use `model_profile` and `tool_profile` in agent entries when you want a shared system-level configuration, and override with concrete `model` or `tools` on a per-agent basis when needed.

## Structured QA findings

Reviewer failures now produce both markdown and JSON artifacts:

- `.autoflow/specs/<slug>/QA_FIX_REQUEST.md`
- `.autoflow/specs/<slug>/QA_FIX_REQUEST.json`

Each finding is machine-readable and can carry:

- `file`
- `line`
- `end_line`
- `severity`
- `category`
- `title`
- `body`
- `suggested_fix`
- `source_run`

Those findings are injected back into the next implementation prompt so retries can be task-driven instead of summary-driven.
