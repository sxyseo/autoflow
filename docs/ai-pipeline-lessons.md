# AI Pipeline Lessons

## Source synthesis

This summary is based on the provided article excerpt about OpenClaw-style development loops, plus the Harness Engineering framing already used in this repository.

## The useful parts

### 1. Tiny commits are a safety primitive

The article's core observation is not "one person can type fast." It is that an AI loop can make many very small, independently validated changes.

Useful implication for Autoflow:

- prefer task slices that can be validated in minutes
- commit after a narrow testable change, not after a long interactive session
- keep retries small enough that revert and blame stay cheap

### 2. The real loop is detect -> fix -> validate -> commit

The useful pattern is a closed loop:

1. detect a concrete issue
2. write or refine the task contract
3. apply the fix
4. run the relevant checks
5. retry if needed
6. commit only after the gate passes

Useful implication for Autoflow:

- reviewer findings must be structured and machine-readable
- scheduled loops must refuse to push when validation fails
- strategy memory must preserve what failed and what worked

### 3. Humans should define boundaries, not micromanage each attempt

The article argues that the human contribution is goal-setting, boundaries, and gates. The agents handle execution.

Useful implication for Autoflow:

- keep approval, retry, and CI gates explicit
- route implementation through reviewer/maintainer closure
- preserve enough durable state that the loop can continue after a pause or crash

### 4. Automation without tests is just faster damage

High-frequency commits only work if the loop has strong validation.

Useful implication for Autoflow:

- every scheduled iteration should run the same narrow CI contract
- retry policies need fix-request context before another implementation attempt
- health checks for CLI agents and tmux workers should run independently from feature work

### 5. Queueing and orchestration matter more than prompt cleverness

The article's examples point to a pipeline with background workers, queueing, and continuous validation.

Useful implication for Autoflow:

- outer-loop orchestration should decide what to run next
- inner-loop run records should stay deterministic and resumable
- strategy memory should feed future planning and retries
