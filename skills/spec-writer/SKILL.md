---
name: spec-writer
description: Create or update product specs for Autoflow-style autonomous development. Use when the system needs a scoped implementation spec, interfaces, constraints, risks, or acceptance criteria before task decomposition or coding.
---

# Spec Writer

Create or update `.autoflow/specs/<slug>/spec.md`.

## Workflow

1. Read the product goal and existing spec directory if present.
2. Produce a concise spec with:
   - problem statement
   - target outcomes
   - non-goals
   - architecture constraints
   - interfaces and dependencies
   - acceptance criteria
   - open risks
3. Keep the spec implementation-oriented. Avoid marketing language.
4. If the request is ambiguous, record assumptions explicitly in the spec instead of hiding them.

## Output contract

- Update `spec.md`
- Update `metadata.json`
- Leave a short summary in `handoff.md` for the next role
