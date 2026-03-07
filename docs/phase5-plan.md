# Phase 5 Plan

## Objective

Move Autoflow from a resilient run harness into a task-driven autonomous pipeline with:

- cumulative planner/reflection memory
- OpenClaw-facing outer orchestration
- Taskmaster-compatible task import/export
- scheduled health checks and CI gates

## Phase 5A

- add strategy memory that aggregates reflections across runs
- inject strategy playbook context into future prompts
- keep planner notes separate from execution reflections

## Phase 5B

- add Taskmaster import/export adapters
- expose a coordination brief for outer orchestrators
- preserve recommended dispatch decisions outside the run prompt

## Phase 5C

- add CLI health monitoring for `codex`, `claude`, and `tmux`
- add a single outer-loop script that scheduled jobs can call
- strengthen repo CI so automated commits use the same checks as pull requests

## Delivered in this iteration

- strategy memory with reflection aggregation and playbook generation
- planner note support
- Taskmaster import/export commands
- outer-loop autonomy orchestrator
- CLI healthcheck script
- CI check script and GitHub Actions workflow
