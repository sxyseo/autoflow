# Frequently Asked Questions

<div align="center">

**Common Issues and Solutions for Autoflow**

[![Autoflow](https://img.shields.io/badge/Autoflow-FAQ-blue.svg)](README.md)

</div>

---

## Table of Contents

- [Getting Started](#getting-started)
- [Agent Configuration](#agent-configuration)
- [Task Lifecycle](#task-lifecycle)
- [Worktree Management](#worktree-management)
- [Memory and State](#memory-and-state)
- [Review Gates](#review-gates)
- [Continuous Iteration](#continuous-iteration)
- [CLI Issues](#cli-issues)
- [Error Messages](#error-messages)
- [Best Practices](#best-practices)
- [Advanced Scenarios](#advanced-scenarios)

---

## Getting Started

### What is Autoflow and why do I need it?

Autoflow is a control plane for autonomous software delivery. It enables AI agents to run repeatable loops around spec creation, task decomposition, implementation, review, and maintenance. Unlike traditional coding assistants, Autoflow:

- **Tracks all state explicitly**: Every spec, task, run, and decision is recorded
- **Provides deterministic prompts**: Reusable skills ensure consistent agent behavior
- **Supports multiple backends**: Use Claude Code, Codex, or custom agents interchangeably
- **Runs autonomously**: Background execution via tmux without blocking workflows
- **Implements quality gates**: Review, testing, and merge checks prevent bad commits

**Use Autoflow if you need:**
- Repeatable, traceable AI-driven development
- Multi-agent coordination with proper state management
- Autonomous development cycles with safety rails
- Review and quality gates before merging

### What are the minimum requirements?

**System Requirements:**
- Python 3.10 or higher
- Git (for version control)
- tmux (for background agent execution)
- At least one AI agent backend (Claude Code, Codex, or ACP-compatible agent)

**Recommended Setup:**
- 2+ CPU cores for parallel agent execution
- 4GB+ RAM available for agents
- Stable internet connection for AI API calls

### How do I initialize Autoflow for the first time?

```bash
# 1. Clone and setup
git clone https://github.com/your-org/autoflow.git
cd autoflow

# 2. Initialize local state
python3 scripts/autoflow.py init

# 3. Initialize system configuration
python3 scripts/autoflow.py init-system-config

# 4. Configure your agents
cp config/agents.example.json .autoflow/agents.json
# Edit .autoflow/agents.json to add your AI backends

# 5. Discover and sync available agents
python3 scripts/autoflow.py sync-agents
```

For detailed installation instructions, see the [Quick Start](README.md#quick-start) section in README.md.

### How do I create my first spec and start development?

```bash
# 1. Create a new spec
python3 scripts/autoflow.py new-spec \
  --slug my-first-project \
  --title "My First AI Project" \
  --summary "Build an amazing AI-powered application"

# 2. Generate task graph
python3 scripts/autoflow.py init-tasks --spec my-first-project

# 3. View workflow state
python3 scripts/autoflow.py workflow-state --spec my-first-project

# 4. Start continuous iteration
python3 scripts/continuous_iteration.py \
  --spec my-first-project \
  --config config/continuous-iteration.example.json \
  --commit-if-dirty \
  --dispatch \
  --push
```

### How do I migrate from the old CLI to the new CLI?

**Background:** Autoflow has migrated from a Python script-based CLI (`python3 scripts/autoflow.py`) to a modern modular CLI (`autoflow` command).

**Old Command:**
```bash
python3 scripts/autoflow.py init
```

**New Command:**
```bash
autoflow init
```

**Command Migration Guide:**

| Old Command | New Command | Notes |
|------------|-------------|-------|
| `python3 scripts/autoflow.py init` | `autoflow init` | Initialize system |
| `python3 scripts/autoflow.py status` | `autoflow status` | Check system status |
| `python3 scripts/autoflow.py new-spec ...` | `autoflow run "..." --spec ...` | Create specs |
| `python3 scripts/autoflow.py workflow-state` | `autoflow task list` | View workflow state |
| `python3 scripts/autoflow.py show-memory` | `autoflow memory list` | View memory |

**Backward Compatibility:**
The old import path still works for existing scripts:
```python
# This still works
from autoflow.cli import main
main()
```

**When to use old vs. new:**
- **New CLI:** Recommended for all interactive use
- **Old CLI:** Only for backward compatibility with existing scripts
- **Both work:** All functionality is preserved—only the interface has changed

### How do I validate that Autoflow is working correctly?

**Quick Validation:**
```bash
# 1. Check system status
autoflow status

# 2. Verify agents are available
autoflow agent check all

# 3. Validate configuration
autoflow config validate
```

**Runtime Loop Validation:**
```bash
# Command-layer smoke test
python3 scripts/validate_readme_flow.py --agent codex

# Runtime-loop smoke test (uses disposable dummy ACP agent and tmux)
python3 scripts/validate_runtime_loop.py

# Recovery and bounded QA-loop smoke test
python3 scripts/validate_recovery_loop.py
```

**What these validate:**
- **validate_readme_flow.py**: Confirms command-layer functionality works end-to-end
- **validate_runtime_loop.py**: Verifies `continuous_iteration.py --dispatch` creates real background tmux runs and auto-finalizes them
- **validate_recovery_loop.py**: Confirms stale runs can be recovered, reviewer generates fix requests, and the bounded fix/re-review loop advances tasks

**If validation fails:**
```bash
# 1. Check logs for detailed error messages
cat .autoflow/logs/autoflow.log

# 2. Verify tmux is installed and working
tmux -V

# 3. Check agent availability
autoflow agent check all

# 4. Reinitialize if needed
autoflow init --force
```

---

## Agent Configuration

### Why do I get "agent not found" errors?

**Problem:**
```
Error: Agent 'claude-impl' not found in registry
```

**Causes:**
1. Agent not defined in `.autoflow/agents.json`
2. Agent configuration has syntax errors
3. Agent CLI not installed or not in PATH
4. Agent not synced after configuration

**Solutions:**

```bash
# 1. Verify agent configuration exists
cat .autoflow/agents.json | jq '.agents'

# 2. Validate configuration
python3 scripts/autoflow.py validate-config

# 3. Test specific agent
python3 scripts/autoflow.py test-agent --agent claude-impl

# 4. Sync discovered agents
python3 scripts/autoflow.py sync-agents --overwrite

# 5. Check if CLI is available
which claude
which codex
```

**Prevention:**
- Always run `sync-agents` after modifying `agents.json`
- Use `validate-config` before starting work
- Keep agent CLIs updated and in PATH

### How do I configure multiple agents for the same role?

**Problem:** You want to use multiple AI backends (e.g., Claude and Codex) for implementation tasks.

**Solution:**

```json
{
  "agents": {
    "claude-impl-1": {
      "name": "Claude Implementation Agent 1",
      "protocol": "cli",
      "command": "claude",
      "args": ["--full-auto"],
      "model_profile": "implementation",
      "roles": ["implementation-runner"],
      "max_concurrent": 3
    },
    "claude-impl-2": {
      "name": "Claude Implementation Agent 2",
      "protocol": "cli",
      "command": "claude",
      "args": ["--full-auto"],
      "model_profile": "implementation",
      "roles": ["implementation-runner"],
      "max_concurrent": 3
    },
    "codex-impl": {
      "name": "Codex Implementation Agent",
      "protocol": "cli",
      "command": "codex",
      "args": ["--full-auto"],
      "model_profile": "implementation",
      "roles": ["implementation-runner"],
      "max_concurrent": 2
    }
  }
}
```

Autoflow will automatically distribute tasks across available agents respecting `max_concurrent` limits.

### How do I set up native continuation for agents?

**Problem:** You want agents to resume from where they left off after interruption.

**Solution:** Configure the `resume` field in `agents.json`:

```json
{
  "agents": {
    "claude-impl": {
      "resume": {
        "mode": "subcommand",
        "subcommand": "resume",
        "args": ["--last"]
      }
    },
    "codex-spec": {
      "resume": {
        "mode": "session",
        "session_file": ".codex_session"
      }
    }
  }
}
```

**Modes:**
- `subcommand`: Agent supports resume via CLI flag
- `session`: Agent maintains session file
- `none`: No native continuation (will restart from scratch)

### Why are my agents not using the correct model?

**Problem:** Agent is using default model instead of configured one.

**Solution:** Check model profile configuration in `.autoflow/system.json`:

```json
{
  "model_profiles": {
    "implementation": {
      "model": "claude-sonnet-4-6",
      "temperature": 0.3,
      "max_tokens": 16384
    },
    "spec": {
      "model": "claude-opus-4-6",
      "temperature": 0.7,
      "max_tokens": 8192
    }
  }
}
```

Ensure your agent configuration references the correct profile:
```json
{
  "model_profile": "implementation"
}
```

### How do I add custom ACP (Agent Communication Protocol) agents?

**Solution:**

1. **Install ACP agent** to discovery path:
```bash
# Default discovery paths
/usr/local/bin/acp-agents/
~/.local/share/acp-agents/
```

2. **Configure in agents.json**:
```json
{
  "agents": {
    "my-acp-agent": {
      "name": "My Custom ACP Agent",
      "protocol": "acp",
      "transport": {
        "type": "stdio",
        "command": "my-agent",
        "args": ["--mode", "autoflow"]
      },
      "prompt_mode": "argv",
      "roles": ["implementation-runner"],
      "max_concurrent": 2
    }
  }
}
```

3. **Sync agents**:
```bash
python3 scripts/autoflow.py sync-agents
```

---

## Task Lifecycle

### Why is my task stuck in "needs_changes" status?

**Problem:** Task is stuck and not progressing despite fixes.

**Causes:**
1. Reviewer rejected implementation, and no fix request was generated
2. Fix request exists but implementation hash changed
3. Review gate is blocking re-dispatch
4. Task exceeded retry limit

**Solutions:**

```bash
# 1. Check if fix request exists
python3 scripts/autoflow.py show-fix-request --spec <spec-slug>

# 2. View review state
cat .autoflow/specs/<slug>/review_state.json

# 3. Check task history for retry count
python3 scripts/autoflow.py task-history --spec <spec> --task <task-id>

# 4. If fix request exists but hash changed, update review approval
python3 scripts/autoflow.py update-review \
  --spec <spec> \
  --approve-implementation \
  --force

# 5. If exceeded retry limit, manually reset task
python3 scripts/autoflow.py update-task \
  --spec <spec> \
  --task <task-id> \
  --status todo
```

**Prevention:**
- Always address all reviewer findings before re-dispatch
- Don't modify implementation between review and fix
- Set appropriate retry limits in config

### How do I unblock a task in "blocked" status?

**Problem:** Task is blocked on dependencies and not progressing.

**Solution:**

```bash
# 1. Check task dependencies
python3 scripts/autoflow.py show-task --spec <spec> --task <task-id>

# 2. View workflow state to see dependency chain
python3 scripts/autoflow.py workflow-state --spec <spec>

# 3. Check if dependencies are done
python3 scripts/autoflow.py list-tasks --spec <spec> --status done

# 4. If dependency is stuck, investigate that task first
# Dependencies auto-unblock when upstream tasks complete

# 5. Manual override (use with caution)
python3 scripts/autoflow.py update-task \
  --spec <spec> \
  --task <task-id> \
  --status todo \
  --force
```

**Note:** Manual override can break task dependencies. Only use if you're sure dependency is satisfied.

### Why are tasks not being dispatched automatically?

**Problem:** Continuous iteration is running but not dispatching tasks.

**Causes:**
1. No ready tasks available
2. Active run already exists for the spec
3. All agents at max_concurrent limit
4. Review gate blocking (review_status.valid = false)
5. Verification commands failing

**Solutions:**

```bash
# 1. Check workflow state for ready tasks
python3 scripts/autoflow.py workflow-state --spec <spec>

# 2. Check for active runs
python3 scripts/autoflow.py list-runs --spec <spec> --status in_progress

# 3. Check agent capacity
python3 scripts/autoflow.py show-agents --status running

# 4. Check review gate status
cat .autoflow/specs/<slug>/review_state.json

# 5. Test verification commands manually
# (from config/continuous-iteration.json verify_commands)
python3 -m pytest tests/ -v

# 6. Check continuous iteration logs
tail -f .autoflow/logs/continuous_iteration.log
```

### How do I retry a failed task?

**Solution:**

```bash
# 1. Check why it failed
python3 scripts/autoflow.py show-run --run <run-id>

# 2. View task history
python3 scripts/autoflow.py task-history --spec <spec> --task <task-id>

# 3. If fix request exists, it will be used automatically
python3 scripts/autoflow.py show-fix-request --spec <spec>

# 4. Create new run for retry
python3 scripts/autoflow.py new-run \
  --spec <spec> \
  --role implementation-runner \
  --task <task-id> \
  --agent <agent-name>

# 5. Launch the run
scripts/tmux-start.sh .autoflow/runs/<run-id>/run.sh
```

**Automatic Retry:**
If continuous iteration is enabled, it will automatically retry failed tasks up to `max_attempts` limit (default: 3).

### How do I skip or cancel a task?

**Solution:**

```bash
# 1. Mark task as done (skipped)
python3 scripts/autoflow.py update-task \
  --spec <spec> \
  --task <task-id> \
  --status done \
  --note "Task skipped - not required"

# 2. Or mark as blocked if you want to revisit later
python3 scripts/autoflow.py update-task \
  --spec <spec> \
  --task <task-id> \
  --status blocked \
  --note "Deferred - waiting for X"
```

---

## Worktree Management

### Why is my worktree not being created?

**Problem:** Worktree creation fails with errors.

**Causes:**
1. Git worktree already exists
2. Branch doesn't exist in main repo
3. Insufficient permissions
4. Disk space issues

**Solutions:**

```bash
# 1. Check existing worktrees
git worktree list

# 2. Remove old worktree if needed
git worktree remove .autoflow/worktrees/<spec-slug>

# 3. Check if target branch exists
git branch -a | grep <spec-slug>

# 4. Create worktree with force
python3 scripts/autoflow.py create-worktree \
  --spec <spec> \
  --force

# 5. Check disk space
df -h
```

### How do I switch worktrees or work from the main repo?

**Problem:** You want to work from the main repository instead of a worktree.

**Solution:**

```bash
# 1. Worktrees are per-spec, check current location
pwd
# Should be: /path/to/main/repo/.autoflow/worktrees/<spec-slug>

# 2. To work from main repo, cd to it
cd /path/to/main/repo

# 3. Note: This is NOT recommended for autonomous development
# Worktrees provide isolation and prevent conflicts

# 4. If you must work from main repo, disable worktree creation
# In continuous-iteration.json:
{
  "worktree": {
    "enabled": false
  }
}
```

**Warning:** Working from the main repo bypasses isolation and can lead to conflicts between autonomous runs and manual work.

### Why are changes not appearing in the main repository?

**Problem:** Worktree changes are not visible in the main branch.

**Explanation:**
Worktrees are isolated Git working trees. Changes stay in the worktree until:

1. **Committed in worktree** → Changes become part of worktree branch
2. **Merged to main** → Changes integrated into main branch

**Solution:**

```bash
# 1. Check worktree status
cd .autoflow/worktrees/<spec-slug>
git status

# 2. View worktree branch
git branch

# 3. Merge worktree branch to main
# From main repository:
git merge <spec-slug>-branch

# 4. Or use Autoflow's merge command
python3 scripts/autoflow.py merge-worktree \
  --spec <spec> \
  --target main
```

### How do I clean up old worktrees?

**Solution:**

```bash
# 1. List all worktrees
git worktree list

# 2. Remove specific worktree
git worktree remove .autoflow/worktrees/<spec-slug>

# 3. Remove all Autoflow worktrees for completed specs
python3 scripts/autoflow.py cleanup-worktrees --completed-only

# 4. Force remove all worktrees (use with caution)
python3 scripts/autoflow.py cleanup-worktrees --all --force
```

---

## Memory and State

### How does Autoflow memory work?

Autoflow captures and uses three types of memory:

**1. Global Memory:**
- Cross-spec lessons and patterns
- Location: `.autoflow/memory/global.md`
- Scope: Available to all agents with `"memory_scopes": ["global"]`

**2. Spec Memory:**
- Per-spec context and history
- Location: `.autoflow/memory/specs/<slug>.md`
- Scope: Available only to agents working on that spec

**3. Strategy Memory:**
- Playbooks for repeated blockers
- Location: `.autoflow/memory/strategy/*.md`
- Scope: Used by iteration-manager and task-graph-manager

**How to use:**

```bash
# View memory
python3 scripts/autoflow.py show-memory --scope global
python3 scripts/autoflow.py show-memory --scope spec --spec <slug>

# Add memory manually
python3 scripts/autoflow.py add-memory \
  --scope global \
  --note "Lesson: Always validate JWT tokens before use"

# Capture memory from completed run
python3 scripts/autoflow.py capture-memory --run <run-id>
```

### Why is memory not being used by agents?

**Problem:** Memory exists but agents aren't using it.

**Causes:**
1. Agent configuration doesn't include memory scopes
2. Memory file is empty or malformed
3. Memory not synced to agent prompt

**Solutions:**

```bash
# 1. Check agent memory configuration
cat .autoflow/agents.json | jq '.agents["<agent-name>"].memory_scopes'

# 2. Should include memory scopes:
# "memory_scopes": ["global", "spec"]

# 3. View memory contents
python3 scripts/autoflow.py show-memory --scope global

# 4. If empty, add some memory
python3 scripts/autoflow.py add-memory \
  --scope global \
  --note "Key patterns discovered..."

# 5. Verify system config has memory enabled
cat .autoflow/system.json | jq '.memory'
# Should show: "enabled": true
```

### How do I reset corrupted state?

**Problem:** System state is inconsistent or corrupted.

**Solutions (in order of severity):**

```bash
# 1. Reset specific task
python3 scripts/autoflow.py reset-task --spec <spec> --task <task-id>

# 2. Clear stuck runs for a spec
python3 scripts/autoflow.py cleanup-runs --spec <spec>

# 3. Rebuild worktree
python3 scripts/autoflow.py create-worktree --spec <spec> --force

# 4. Reset spec state (preserves spec content)
python3 scripts/autoflow.py reset-spec --spec <spec>

# 5. Last resort: Reinitialize entire system
# WARNING: This clears all state!
rm -rf .autoflow/
python3 scripts/autoflow.py init
```

**Prevention:**
- Always stop continuous iteration before manual state changes
- Use `validate-config` before making changes
- Keep backups of `.autoflow/` directory

### How do I back up and restore Autoflow state?

**Backup:**

```bash
# 1. Backup entire .autoflow directory
tar -czf autoflow-state-backup-$(date +%Y%m%d).tar.gz .autoflow/

# 2. Or backup specific spec
tar -czf spec-backup-<slug>-$(date +%Y%m%d).tar.gz \
  .autoflow/specs/<slug>/ \
  .autoflow/memory/specs/<slug>.md
```

**Restore:**

```bash
# 1. Stop all Autoflow processes
pkill -f continuous_iteration
tmux kill-session -a -t autoflow

# 2. Extract backup
tar -xzf autoflow-state-backup-20240310.tar.gz

# 3. Verify integrity
python3 scripts/autoflow.py validate-config
```

---

## Review Gates

### Why is implementation blocked by review gate?

**Problem:** Implementation task cannot be dispatched after review changes.

**Explanation:** Autoflow uses hash-based review approval. If the spec or task graph changes after review but before implementation fix, the hash mismatches and the gate blocks.

**Solutions:**

```bash
# 1. Check review state
cat .autoflow/specs/<slug>/review_state.json

# 2. View review gate status
python3 scripts/autoflow.py show-review-gate --spec <spec>

# 3. If planning changed, re-run review
python3 scripts/autoflow.py new-run \
  --spec <spec> \
  --role reviewer \
  --task <task-id>

# 4. Force approve (use only if you're sure changes are safe)
python3 scripts/autoflow.py update-review \
  --spec <spec> \
  --approve-implementation \
  --force

# 5. Or reset planning to match review
python3 scripts/autoflow.py reset-tasks --spec <spec> \
  --from-review <review-run-id>
```

### How do I interpret reviewer findings?

**Problem:** Reviewer generated QA_FIX_REQUEST.md/json but you don't understand how to fix.

**Solution:**

```bash
# 1. View findings in markdown (human-readable)
python3 scripts/autoflow.py show-fix-request --spec <spec>

# 2. View structured findings (machine-readable)
cat .autoflow/specs/<slug>/QA_FIX_REQUEST.json

# 3. Findings structure:
{
  "findings": [
    {
      "file": "src/auth.py",
      "line": 42,
      "end_line": 45,
      "severity": "error",  // error, warning, info
      "category": "security",
      "title": "Missing input validation",
      "body": "JWT token not validated before use",
      "suggested_fix": "Add validation: validate_jwt(token)",
      "source_run": "20260307T123456Z-reviewer-feature-auth-T3"
    }
  ]
}

# 4. When you create a fix run, findings are automatically injected
# into the agent prompt with file locations and suggested fixes
```

**Severity Levels:**
- `error`: Must fix before approval
- `warning`: Should fix, optional
- `info`: Nice to have, no action required

### How do I override a reviewer rejection?

**Problem:** You disagree with reviewer findings and want to proceed anyway.

**Solution:**

```bash
# 1. Review the findings carefully
python3 scripts/autoflow.py show-fix-request --spec <spec>

# 2. Document why you're overriding
python3 scripts/autoflow.py add-planner-note \
  --spec <spec> \
  --note "Override reviewer finding X because: reason"

# 3. Approve implementation despite review
python3 scripts/autoflow.py update-review \
  --spec <spec> \
  --approve-implementation \
  --override \
  --reason "Findings X, Y don't apply because..."
```

**Warning:** Overriding reviewer gates bypasses quality checks. Only do this if you're certain the findings are incorrect.

---

## Continuous Iteration

### Why is continuous iteration not committing changes?

**Problem:** Worktree is dirty but changes aren't being committed.

**Causes:**
1. `commit.enabled` is false in config
2. Verification commands failing
3. No active run to attribute commit to
4. Git commit hooks failing

**Solutions:**

```bash
# 1. Check continuous iteration config
cat config/continuous-iteration.json | jq '.commit'

# 2. Should show:
{
  "enabled": true,
  "message_prefix": "autoflow:",
  "push": true,
  "require_active_run": false
}

# 3. Run verification commands manually
python3 -m pytest tests/ -v
python3 scripts/ci_check.sh

# 4. Check if active run exists
python3 scripts/autoflow.py list-runs --status in_progress

# 5. Manual commit
python3 scripts/git-auto-commit.sh \
  --spec <spec> \
  --prefix "manual:"

# 6. Check logs
tail -f .autoflow/logs/continuous_iteration.log
```

### How often should I run continuous iteration?

**Recommendation:** Start with every 6 hours.

**Rationale:**
- Gives agents time to complete work
- Reduces noisy commits
- Allows time for review cycles
- Prevents API rate limiting

**Configuration:**

```json
{
  "schedule": {
    "enabled": true,
    "interval_seconds": 21600,  // 6 hours
    "require_active_run": false
  }
}
```

**Cron Example:**
```bash
# Run every 6 hours
0 */6 * * * cd /path/to/autoflow && python3 scripts/continuous_iteration.py --spec my-project --config config/continuous-iteration.json --commit-if-dirty --dispatch --push
```

### Why is continuous iteration stopping unexpectedly?

**Problem:** Continuous iteration exits after one cycle instead of looping.

**Causes:**
1. Review gate blocking (review_status.valid = false)
2. Task exceeded retry limit
3. No ready tasks available
4. Unhandled exception

**Solutions:**

```bash
# 1. Check review gate status
cat .autoflow/specs/<slug>/review_state.json

# 2. If review_status.valid is false, re-approve
python3 scripts/autoflow.py update-review \
  --spec <spec> \
  --approve-implementation

# 3. Check task retry status
python3 scripts/autoflow.py workflow-state --spec <spec>

# 4. View logs for errors
tail -100 .autoflow/logs/continuous_iteration.log

# 5. Run with verbose logging
python3 scripts/continuous_iteration.py \
  --spec <spec> \
  --config config/continuous-iteration.json \
  --verbose \
  2>&1 | tee /tmp/autoflow-debug.log
```

### How do I temporarily disable continuous iteration?

**Solution:**

```bash
# 1. Stop the process
pkill -f continuous_iteration

# 2. Or disable in config temporarily
{
  "dispatch": {
    "enabled": false  // Set to false
  }
}

# 3. Or use scheduler pause
# If using cron, comment out the line
crontab -e
```

### Why is the scheduler not running tasks?

**Problem:** Scheduler is running but not dispatching tasks.

**Causes:**
1. Scheduler not configured for the correct spec
2. Job not enabled in scheduler configuration
3. Cron schedule incorrect
4. Scheduler process not running

**Solutions:**

```bash
# 1. Check scheduler status
autoflow scheduler status

# 2. Verify scheduler configuration
cat .autoflow/scheduler.json | jq .

# 3. Check if continuous_iteration job is enabled
cat .autoflow/scheduler.json | jq '.jobs.continuous_iteration.enabled'

# 4. Verify job configuration includes spec
cat .autoflow/scheduler.json | jq '.jobs.continuous_iteration.args.spec'

# 5. Check scheduler logs
tail -f .autoflow/logs/scheduler.log
```

**Expected Scheduler Configuration:**
```json
{
  "jobs": {
    "continuous_iteration": {
      "enabled": true,
      "cron": "*/5 * * * *",
      "args": {
        "spec": "my-project",
        "config": "config/continuous-iteration.example.json",
        "dispatch": true,
        "commit_if_dirty": false,
        "push": false
      }
    }
  }
}
```

### How do I configure scheduler for multiple specs?

**Problem:** You want to run continuous iteration for multiple specs.

**Solution:**

```bash
# 1. Create separate scheduler jobs for each spec
cat > .autoflow/scheduler.json << 'EOF'
{
  "jobs": {
    "continuous_iteration_spec1": {
      "enabled": true,
      "cron": "*/5 * * * *",
      "args": {
        "spec": "spec-1",
        "config": "config/continuous-iteration.example.json",
        "dispatch": true
      }
    },
    "continuous_iteration_spec2": {
      "enabled": true,
      "cron": "*/10 * * * *",
      "args": {
        "spec": "spec-2",
        "config": "config/continuous-iteration.example.json",
        "dispatch": true
      }
    }
  }
}
EOF

# 2. Restart scheduler to pick up new configuration
autoflow scheduler stop
autoflow scheduler start

# 3. Verify both jobs are running
autoflow scheduler status
```

**Best Practices:**
- Use different cron schedules to avoid resource contention
- Monitor logs for each spec separately
- Set appropriate max_concurrent per spec

---

## Error Messages

### "Spec not found" error

**Problem:**
```
Error: Spec 'my-project' not found
```

**Solution:**
```bash
# 1. List available specs
python3 scripts/autoflow.py list-specs

# 2. Check spec slug (case-sensitive)
python3 scripts/autoflow.py show-spec --slug my-project

# 3. Create spec if it doesn't exist
python3 scripts/autoflow.py new-spec \
  --slug my-project \
  --title "My Project"
```

### "Task not found" error

**Problem:**
```
Error: Task 'task-1' not found in spec 'my-project'
```

**Solution:**
```bash
# 1. List tasks for the spec
python3 scripts/autoflow.py list-tasks --spec my-project

# 2. Initialize tasks if not done
python3 scripts/autoflow.py init-tasks --spec my-project

# 3. Check task ID format (usually: phase-N-task-M)
python3 scripts/autoflow.py show-task --spec my-project --task phase-1-task-1
```

### "Run creation failed" error

**Problem:**
```
Error: Failed to create run: Cannot dispatch task - no available agents
```

**Solution:**
```bash
# 1. Check available agents
python3 scripts/autoflow.py show-agents

# 2. Check if agents support required role
cat .autoflow/agents.json | jq '.agents[] | select(.roles[] == "implementation-runner")'

# 3. Check agent capacity
python3 scripts/autoflow.py show-agents --status running

# 4. Sync agents
python3 scripts/autoflow.py sync-agents

# 5. Test specific agent
python3 scripts/autoflow.py test-agent --agent claude-impl
```

### "Worktree creation failed" error

**Problem:**
```
Error: Failed to create worktree: Branch 'feature-X' does not exist
```

**Solution:**
```bash
# 1. Check if branch exists in main repo
cd /path/to/main/repo
git branch -a | grep feature-X

# 2. If branch doesn't exist, create it
git checkout -b feature-X

# 3. Or let Autoflow create branch automatically
python3 scripts/autoflow.py create-worktree \
  --spec my-project \
  --create-branch

# 4. Force rebuild worktree
python3 scripts/autoflow.py create-worktree \
  --spec my-project \
  --force
```

### "Permission denied" errors

**Problem:**
```
Error: Permission denied: .autoflow/runs/...
```

**Solution:**
```bash
# 1. Check .autoflow directory permissions
ls -la .autoflow/

# 2. Fix permissions if needed
chmod -R 755 .autoflow/

# 3. Check ownership
ls -l .autoflow/
# Should be owned by your user

# 4. If wrong user, fix ownership
sudo chown -R $USER:$USER .autoflow/

# 5. Check disk space
df -h .autoflow/
```

---

## CLI Issues

### Why is the Autoflow CLI not found?

**Problem:**
```bash
autoflow: command not found
```

**Causes:**
1. Autoflow not installed in editable mode
2. Virtual environment not activated
3. Installation failed silently
4. PATH not configured correctly

**Solutions:**

```bash
# 1. Verify installation
pip show autoflow

# 2. If not installed, install in editable mode
cd /path/to/autoflow
pip install -e .

# 3. If virtual environment exists, activate it
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows

# 4. Verify installation again
which autoflow  # Should show path to autoflow executable
autoflow --version  # Should show version number
```

**Prevention:**
- Always use `pip install -e .` when setting up Autoflow
- Keep virtual environment active during development
- Add `source .venv/bin/activate` to your shell startup script

### How do I verify CLI installation?

```bash
# 1. Check CLI version
autoflow --version

# 2. Verify CLI installation
python -c "from autoflow.cli import main; print('OK')"

# 3. Test basic commands
autoflow --help
autoflow status --help

# 4. Run system status check
autoflow status
```

**Expected Output:**
- `autoflow --version`: Should show version number (e.g., `Autoflow v0.1.0`)
- Python import test: Should print `OK` without errors
- Help commands: Should display usage information
- Status check: Should show system health

### Why are CLI commands failing with import errors?

**Problem:**
```bash
ImportError: No module named 'autoflow.cli'
```

**Causes:**
1. Installation in development mode without dependencies
2. Wrong Python environment
3. Corrupted installation

**Solutions:**

```bash
# 1. Reinstall with all dependencies
pip install -e .[dev]

# 2. Verify Python path
which python
python --version

# 3. Uninstall and reinstall
pip uninstall autoflow
pip install -e .

# 4. Check for conflicting installations
pip list | grep autoflow
```

### How do I switch between old and new CLI?

**Scenario:** You have scripts using the old CLI and want to use the new CLI.

**Solution:**

```bash
# Old CLI (still works for backward compatibility)
python3 scripts/autoflow.py init

# New CLI (recommended)
autoflow init
```

**Migration Script:**
```bash
# Create a helper script for migration
cat > migrate_to_new_cli.sh << 'EOF'
#!/bin/bash
# Replace old CLI invocations with new CLI
find . -name "*.sh" -type f -exec sed -i '' 's/python3 scripts\/autoflow\.py/autoflow/g' {} +
echo "Migration complete!"
EOF

chmod +x migrate_to_new_cli.sh
./migrate_to_new_cli.sh
```

**Note:** The old Python import path still works:
```python
# Old import (still works)
from autoflow.cli import main
main()

# New usage (recommended)
import subprocess
subprocess.run(["autoflow", "status"])
```

---

## Best Practices

### How should I structure my specs for best results?

**Recommendations:**

1. **Start Small:**
   - Break large features into smaller specs
   - Each spec should be completable in 1-2 weeks
   - Focus on one feature area per spec

2. **Clear Requirements:**
   - Define acceptance criteria explicitly
   - Include constraints and dependencies
   - Provide examples and edge cases

3. **Incremental Development:**
   - Start with MVP, then iterate
   - Use task dependencies to enforce order
   - Test each task before moving to next

**Example:**
```markdown
# User Authentication

## Requirements
- User registration with email verification
- Secure password storage (bcrypt)
- JWT-based session management
- Password reset flow

## Constraints
- Must use existing email service
- Password requirements: 12+ chars, mixed case
- Session timeout: 24 hours

## Acceptance Criteria
- [ ] Users can register with email
- [ ] Email verification required before login
- [ ] Sessions expire after 24 hours
- [ ] Password reset completes within 5 minutes
```

### What's the recommended team workflow?

**Small Team (1-3 developers):**

1. **Single Main Branch**
   - All work done via Autoflow specs
   - Human reviews before merge to main
   - Continuous iteration every 6 hours

2. **Role Distribution**
   - One person owns spec creation
   - AI handles implementation and review
   - Human approves final merge

**Large Team (4+ developers):**

1. **Feature Branches**
   - Each spec gets isolated worktree
   - Multiple specs can run in parallel
   - Separate integration spec for merges

2. **Role Specialization**
   - Tech lead owns spec-writer role
   - Senior devs handle review tasks
   - Junior devs monitor autonomous runs

### How do I measure Autoflow effectiveness?

**Key Metrics:**

```bash
# 1. Task completion rate
python3 scripts/autoflow.py workflow-state --spec <spec> | grep "done"

# 2. Average task duration
python3 scripts/autoflow.py task-history --spec <spec> --task <task-id>

# 3. Review pass rate
cat .autoflow/specs/<slug>/review_state.json | jq '.pass_rate'

# 4. Agent utilization
python3 scripts/autoflow.py show-agents --stats

# 5. Iteration frequency
git log --oneline --since="1 week ago" | grep "autoflow:" | wc -l
```

**Target Metrics:**
- Task completion rate: >80%
- Review pass rate: >70%
- Agent utilization: >60%
- Iteration frequency: 10-20 per day

### How do I handle security and credentials?

**Best Practices:**

1. **Never Commit Secrets:**
   ```bash
   # Add to .gitignore
   .env
   .autoflow/agents.json
   config/secrets.json
   ```

2. **Use Environment Variables:**
   ```json
   {
     "agents": {
       "claude-impl": {
         "env": {
           "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}"
         }
       }
     }
   }
   ```

3. **Encrypt Sensitive Data:**
   ```bash
   # Use git-crypt for secrets
   git-crypt init
   echo "*.key filter=git-crypt diff=git-crypt" >> .gitattributes
   ```

4. **Audit Access:**
   ```bash
   # Review who has access
   ls -la .autoflow/
   whoami
   ```

---

## Advanced Scenarios

### How do I set up multi-repo development?

**Problem:** Your project spans multiple Git repositories.

**Solution:**

1. **Configure repo mappings:**
   ```json
   {
     "repos": {
       "main": "https://github.com/org/main-repo.git",
       "services": "https://github.com/org/services-repo.git",
       "frontend": "https://github.com/org/frontend-repo.git"
     }
   }
   ```

2. **Create worktrees for each repo:**
   ```bash
   python3 scripts/autoflow.py create-worktree \
     --spec my-spec \
     --repo main \
     --branch feature-main

   python3 scripts/autoflow.py create-worktree \
     --spec my-spec \
     --repo services \
     --branch feature-services
   ```

3. **Configure agent to work across repos:**
   ```json
   {
     "agents": {
       "multi-repo-impl": {
         "worktree_map": {
           "main": ".autoflow/worktrees/main-my-spec",
           "services": ".autoflow/worktrees/services-my-spec"
         }
       }
     }
   }
   ```

### How do I integrate with external CI/CD?

**Solution:**

1. **Autoflow triggers CI:**
   ```bash
   # In continuous-iteration.json
   {
     "ci": {
       "enabled": true,
       "command": "gh workflow run ci.yml",
       "wait_for_completion": true
     }
   }
   ```

2. **CI gates Autoflow:**
   ```yaml
   # .github/workflows/autoflow-gate.yml
   name: Autoflow Gate
   on: push
   jobs:
     gate:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v3
         - name: Run tests
           run: python3 -m pytest tests/
         - name: Approve Autoflow
           if: success()
           run: |
             python3 scripts/autoflow.py update-review \
               --spec ${{ github.ref_name }} \
               --approve-ci
   ```

3. **Autoflow deploys after CI:**
   ```json
   {
     "deploy": {
       "enabled": true,
       "condition": "ci_passed AND review_approved",
       "command": "kubectl apply -f k8s/"
     }
   }
   ```

### How do I create custom skills?

**Problem:** You need a custom workflow beyond built-in skills.

**Solution:**

1. **Create skill directory:**
   ```bash
   mkdir -p skills/my-custom-skill
   ```

2. **Write SKILL.md:**
   ```markdown
   # Performance Optimizer

   ## Description
   Analyzes code for performance bottlenecks and applies optimizations.

   ## Workflow
   1. Profile code execution
   2. Identify bottlenecks (top 5 by time)
   3. Research optimization strategies
   4. Implement optimizations
   5. Verify improvements with benchmarks

   ## Rules
   - Never change API signatures
   - Always add benchmarks before and after
   - Document performance improvements
   - Run tests after each optimization

   ## Output Format
   - benchmark_results.json: Before/after metrics
   - optimization_notes.md: What was changed and why
   ```

3. **Create role template:**
   ```bash
   mkdir -p skills/my-custom-skill/role_templates
   cat > skills/my-custom-skill/role_templates/optimizer.md << 'EOF'
   You are a Performance Optimization Specialist.
   Your goal is to identify and fix performance bottlenecks.
   You measure everything and prove improvements with data.
   EOF
   ```

4. **Use in agents.json:**
   ```json
   {
     "agents": {
       "performance-optimizer": {
         "roles": ["my-custom-skill"],
         "skill_path": "skills/my-custom-skill/SKILL.md"
       }
     }
   }
   ```

### How do I debug agent behavior?

**Solution:**

1. **Enable verbose logging:**
   ```bash
   # In agents.json
   {
     "agents": {
       "claude-impl": {
         "debug": true,
         "log_level": "verbose"
       }
     }
   }
   ```

2. **Capture agent prompts:**
   ```bash
   # Prompts are stored in run directories
   cat .autoflow/runs/<run-id>/prompt.md
   ```

3. **Attach to running tmux session:**
   ```bash
   tmux attach -t autoflow-run-<timestamp>
   # See agent output in real-time
   ```

4. **Review agent summary:**
   ```bash
   cat .autoflow/runs/<run-id>/summary.md
   ```

5. **Check run metadata:**
   ```bash
   cat .autoflow/runs/<run-id>/metadata.json | jq .
   ```

---

## Still Need Help?

- **Documentation:** See [README.md](README.md) for detailed guides
- **Architecture:** See [docs/architecture.md](docs/architecture.md) for system design
- **Continuous Iteration:** See [docs/continuous-iteration.md](docs/continuous-iteration.md) for automation setup
- **Troubleshooting:** See the [Troubleshooting](README.md#troubleshooting) section in README.md
- **Issues:** Report bugs or request features at [GitHub Issues](https://github.com/your-org/autoflow/issues)

---

<div align="center">

**[⬆ Back to Top](#frequently-asked-questions)**

Made with ❤️ by the Autoflow community

</div>
