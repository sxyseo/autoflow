---
name: task-graph-manager
description: Build and maintain the task graph for Autoflow. Use when a spec must be decomposed into executable tasks, dependencies, priorities, and acceptance criteria in a stable machine-readable format.
---

# Task Graph Manager

Manage `.autoflow/tasks/<spec-slug>.json`.

## Workflow

1. Read the spec and current tasks.
2. Split work into small execution slices that can be completed and reviewed independently.
3. Add dependencies only when required.
4. Each task must include:
   - `id`
   - `title`
   - `status`
   - `depends_on`
   - `acceptance_criteria`
   - `owner_role`
5. Prefer vertical slices over layer-only tasks.

## Rules

- Do not create tasks that have no testable exit condition.
- Do not create tasks larger than one review cycle.
- Re-open blocked tasks instead of duplicating them.
