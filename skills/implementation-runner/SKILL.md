---
name: implementation-runner
description: Execute a bounded coding task in the Autoflow harness. Use when a specific task has a defined scope, acceptance criteria, and repository context and needs code changes from Codex, Claude Code, or another coding CLI.
---

# Implementation Runner

Execute one task at a time.

## Workflow

1. Read the spec, the selected task, and the latest reviewer handoff.
2. Work only inside the task scope.
3. Make the smallest set of changes that satisfies acceptance criteria.
4. Run local verification where possible.
5. Produce:
   - code changes
   - a run summary
   - unresolved risks

## Rules

- Do not expand scope on your own.
- If the task is underspecified, write back the blocker instead of improvising a redesign.
- Leave the repository in a runnable state.
