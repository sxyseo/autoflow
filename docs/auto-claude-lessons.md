# Lessons From Auto-Claude

This document records the parts of Auto-Claude that are worth extracting into Autoflow without importing its full product surface.

## What Auto-Claude gets right

### 1. Per-spec isolation

The strongest idea is not "more agents". It is `spec -> worktree -> branch` isolation. That prevents one autonomous task from polluting another.

### 2. Review approval invalidation

Approval should be tied to a hash of planning artifacts. If the spec or task contract changes, the approval must become invalid.

### 3. Recovery-aware prompts

Retries should not start from a blank slate. Prompts should include recent failed attempts and their summaries so the next run can try a different approach.

### 4. Persistent event logging

Long-running autonomy needs durable events, not just transient terminal output. Event logs make recovery, audit, and automation summaries much easier.

### 5. Prompt minimalism

Auto-Claude's prompt generator keeps prompts focused on one task, one environment, and one recovery context. This is more robust than a giant reusable prompt.

## What not to copy directly

- Desktop UI complexity
- Large monorepo structure
- Provider-specific account systems
- Full semantic merge machinery

Autoflow should stay smaller. It only needs the reliability primitives.

## Autoflow translation

These lessons map to Autoflow as:

- `create-worktree`, `remove-worktree`, `list-worktrees`
- hash-based `review-status` and `approve-spec`
- recovery context inside generated run prompts
- per-spec `events.jsonl`
