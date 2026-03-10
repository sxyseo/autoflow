# OpenClaw autonomous development system

## Summary

Build an autonomous software delivery harness with skills, task graph, review gates, and swappable coding agents.

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

## Acceptance Criteria

- A spec-driven task graph exists.
- Runs can be created from roles and agent mappings.
- Review is a separate step from implementation.
