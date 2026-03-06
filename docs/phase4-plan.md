# Phase 4 Plan

## Objective

Evolve Autoflow from a prompt-and-run harness into a safer autonomous delivery loop with isolation, approval tracking, recovery context, and durable execution history.

## Plan

### Phase 4A

- add per-spec git worktrees
- route runs into spec worktrees
- add worktree safety context to prompts

### Phase 4B

- add hash-based review approval state
- invalidate approval when spec or task contract changes
- expose review status in workflow state

### Phase 4C

- add task recovery context from prior failed runs
- add per-spec event logs
- expose task history and recent events in CLI

### Phase 4D

- add QA fix-request artifacts
- add retry policy for scheduled iteration
- add worktree-aware automation branch policy

## Delivered in this iteration

- Phase 4A
- Phase 4B
- Phase 4C

## Next candidates

1. Create a `QA_FIX_REQUEST.md` style artifact for reviewer failures.
2. Add resumable run sessions tied to previous task attempts.
3. Add more explicit human input and pause files.
