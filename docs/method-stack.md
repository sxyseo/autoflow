# Method Stack

## Summary

These methods help, but they should not all be peers in the same layer.

## Recommended layering

### OpenClaw

Use as the outer runtime and skill host. It should decide which skill to run next and which backend agent to invoke.

### Spec Driven Development

Use as the backbone. All work starts from a spec artifact with scope, constraints, interfaces, and acceptance criteria.

### Taskmaster AI

Use for turning specs into a task graph. Its main value is decomposition, dependency tracking, and execution visibility.

### BMAD

Use as prompt discipline rather than as the state model. BMAD is useful for role framing, checkpoints, and better handoffs. It should shape prompts and review templates.

### Symphony

Use later if you need more formal workflow orchestration, retries, state machines, and agent collaboration patterns. It is not the first dependency to adopt.

## What to avoid

- Do not let each framework own task state.
- Do not let each agent invent its own directory structure.
- Do not start with fully parallel coding agents before you have strong review gates.
- Do not couple the system to a single model vendor.

## Practical conclusion

The shortest path is:

1. OpenClaw for orchestration
2. Spec-driven artifacts for source of truth
3. Taskmaster-style task graph for execution
4. BMAD role prompts for consistency
5. Symphony later for advanced orchestration
