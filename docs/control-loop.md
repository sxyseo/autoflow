# Control Loop

## Phase 1: Intake

- collect goal
- generate or update spec
- assign a stable spec slug

## Phase 2: Planning

- derive tasks from spec
- set dependencies
- define acceptance criteria
- choose execution order

## Phase 3: Execution

- select task
- choose role and backend agent
- assemble prompt from spec, task, and skill
- run in `tmux`
- capture logs and outputs

## Phase 4: Review

- run code review role
- run tests and lint
- compare against acceptance criteria
- mark task as passed or failed

## Phase 5: Delivery

- create commit summary
- update task state
- optionally open PR

## Phase 6: Maintenance

- backlog grooming
- dependency updates
- issue triage
- flaky test detection
- recurring refactors

## Required invariants

- every run has a prompt artifact
- every run has metadata and logs
- every task has acceptance criteria
- every merged change has been reviewed by a separate role
