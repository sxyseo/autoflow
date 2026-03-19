# Test Spec

## Summary

Test spec for list-runs

## Problem

Describe the problem this system is solving.

## Goals

- Build a reliable autonomous development harness.
- Keep orchestration separate from model-specific execution.
- Make every run resumable and auditable.

## Non-goals

- Fully unsupervised production deploys in v1.
- Vendor lock-in to a single coding model.

## Constraints

- Use explicit specs and task artifacts.
- Support `codex` and `claude` style CLIs.
- Support background execution with `tmux`.
- Require review before marking coding work complete.
- Prefer isolated git worktrees for implementation runs.

## Acceptance Criteria

- A spec-driven task graph exists.
- Runs can be created from roles and agent mappings.
- Review is a separate step from implementation.
- Git workflow hooks can prepare isolated task branches.
