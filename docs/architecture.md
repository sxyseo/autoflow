# Architecture

## Core principle

Treat the autonomous dev system as a harness, not a single agent. The harness owns state, sequencing, verification, and recovery. Individual model CLIs only execute bounded jobs.

## Layers

### 1. Control plane

Files under `.autoflow/` are the source of truth:

- `specs/`: product intent and constraints
- `tasks/`: backlog, dependencies, status, and acceptance criteria
- `runs/`: per-execution prompts, logs, outputs, and metadata
- `agents.json`: logical role to CLI mapping

### 2. Role layer

Roles are implemented as skills:

- `spec-writer`: convert intent into spec artifacts
- `task-graph-manager`: derive and refine execution graph
- `implementation-runner`: execute coding slices
- `reviewer`: run review, regression, and merge checks
- `maintainer`: do issue triage, dependency bumps, and cleanup

These skills should be invoked by OpenClaw or any outer orchestrator.

### 3. Execution layer

Each run binds:

- one spec
- one role
- one concrete agent backend
- one prompt
- one writable workspace

The execution layer must be restartable. `tmux` is enough for the first version.

### 4. Governance layer

The system should gate all autonomous changes through:

- task acceptance criteria
- repository tests and lint
- review summary
- branch and commit policy

## Recommended first delivery path

1. Single repository
2. Single branch per task slice
3. One active coding agent at a time
4. One review agent after each coding run
5. Human approval before merge

After that works reliably, add:

- multiple parallel implementation agents
- issue intake
- scheduled maintenance
- automatic PR refresh
- automatic rollback policy
