# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Autoflow is a thin control plane for autonomous software delivery, inspired by OpenAI's "Harness Engineering" philosophy and Peter Steinberger's AI-driven development workflow. It implements a harness model where the system owns state, sequencing, verification, and recovery, while individual model CLIs execute bounded jobs.

**Core Philosophy**: Like Peter's 627-commit day, Autoflow enables AI to self-complete loops:发现问题→自动修复→自动测试→自动提交. Humans define goals and boundaries; AI handles execution and verification.

The architecture treats autonomous development as a multi-layer system with explicit state and swappable agent backends, supporting OpenClaw, Claude Code, Codex, and custom agents through unified protocols.

## Python Module Structure

The `autoflow/` directory contains the main Python package with the following architecture:

### Core Modules (`autoflow/core/`)
- **config.py**: Configuration management for agents, system settings, and profiles
- **orchestrator.py**: Main orchestration logic for agent execution and workflow coordination
- **state.py**: State management for specs, tasks, runs, and workflow status

### Agent System (`autoflow/agents/`)
- **base.py**: Base agent interface and common functionality
- **claude_code.py**: Claude Code agent implementation
- **codex.py**: Codex agent implementation
- **openclaw.py**: OpenClaw agent implementation

### CI/CD System (`autoflow/ci/`)
- Gates, health checks, and verification logic
- Pre-commit and pre-merge validation
- Automated quality assurance

### Self-Healing (`autoflow/healing/`)
- Automatic error detection and recovery
- Rollback mechanisms
- Retry strategies with exponential backoff

### Quality Prediction (`autoflow/prediction/`)
- ML-based quality prediction using scikit-learn
- Success probability estimation for tasks
- Risk assessment and mitigation recommendations

### Review System (`autoflow/review/`)
- Cross-review implementation
- Structured findings generation
- Review state management and approval tracking

### Additional Systems
- **rollback/**: Automatic rollback and recovery mechanisms
- **scheduler/**: Task scheduling and dependency management
- **skills/**: Skill system for role-based workflows
- **tmux/**: Tmux session management for background agent execution

## Core Architecture

The system is organized into four layers:

1. **Control Plane** (`.autoflow/`): Source of truth for specs, tasks, runs, and agent configuration
2. **Role Layer** (`skills/`): Reusable role implementations (spec-writer, task-graph-manager, implementation-runner, reviewer, maintainer)
3. **Execution Layer**: Each run binds one spec, one role, one agent backend, one prompt, and one workspace
4. **Governance Layer**: Gates through task acceptance criteria, tests, review, and branch policy

### State Hierarchy

- `specs/`: Product intent and constraints (per-spec directories with SPEC.md, acceptance criteria, QA artifacts)
- `tasks/`: Backlog, dependencies, status, acceptance criteria (TASKS.json with task objects)
- `runs/`: Per-execution prompts, logs, outputs, metadata (timestamped run directories)
- `memory/`: Scoped memory capture (global.md and per-spec memory)
- `worktrees/`: Per-spec git worktrees for isolated execution
- `agents.json`: Agent configuration and protocol settings
- `system.json`: Model profiles, tool profiles, memory configuration

### Configuration Files

**`.autoflow/agents.json`**: Agent catalog and configuration
- Defines available agents (codex, claude, openclaw, custom)
- Specifies protocol type (cli, acp)
- Maps roles to agents
- Configures model and tool profiles
- Sets resume behavior per agent

**`.autoflow/system.json`**: System-level configuration
- Model profiles (spec, implementation, review models)
- Tool profiles (allowed tools per profile)
- Memory configuration (scopes, file paths)
- ACP agent registry for local discovery

**`config/continuous-iteration.example.json`**: Continuous iteration settings
- Role-to-agent mappings
- Agent selection preferences
- Pre-commit verification commands
- Commit message prefixing and push behavior
- Retry policies and fix request handling

### Task Status Workflow

Valid task statuses: `todo` → `in_progress` → `in_review` → `done` or `needs_changes` or `blocked`

Valid run results: `success`, `needs_changes`, `blocked`, `failed`

## Configuration System

Autoflow uses two configuration layers:

### `.autoflow/agents.json`
- Runnable agent catalog with CLI/ACP protocol support
- Role bindings (which agent handles which role)
- Model and tool profile references
- Resume behavior for each agent (native continuation vs re-prompting)

### `.autoflow/system.json`
- Model profiles (spec, implementation, review models)
- Tool profiles (allowed tools per profile)
- Memory configuration (enabled/disabled, scopes, file paths)
- ACP agent registry for local agent discovery

### Agent Configuration Pattern

Agents can reference system-level profiles or override with concrete values:

```json
{
  "agents": {
    "codex-spec": {
      "protocol": "cli",
      "command": "codex",
      "args": ["--full-auto"],
      "model_profile": "implementation",
      "memory_scopes": ["global", "spec"],
      "resume": {
        "mode": "subcommand",
        "subcommand": "resume",
        "args": ["--last"]
      }
    }
  }
}
```

## Common Development Commands

### Initialization

```bash
# Setup local state directories
python3 scripts/autoflow.py init

# Initialize system config from template
python3 scripts/autoflow.py init-system-config

# Copy and customize agent configuration
cp config/agents.example.json .autoflow/agents.json

# Discover and sync local/ACP agents
python3 scripts/autoflow.py sync-agents [--overwrite]
```

### Spec and Task Management

```bash
# Create a new spec
python3 scripts/autoflow.py new-spec \
  --slug <spec-slug> \
  --title "<title>" \
  --summary "<summary>"

# Update spec from existing spec
python3 scripts/autoflow.py update-spec --slug <spec-slug>

# Initialize tasks for a spec
python3 scripts/autoflow.py init-tasks --spec <spec-slug>

# Show workflow state
python3 scripts/autoflow.py workflow-state --spec <spec-slug>
```

### Running and Managing Work

```bash
# Create a new run (returns run directory path)
python3 scripts/autoflow.py new-run \
  --spec <spec-slug> \
  --role <role> \
  --agent <agent-name> \
  --task <task-id>

# Launch run in tmux
scripts/tmux-start.sh .autoflow/runs/<run-id>/run.sh

# Complete a run and advance task state
python3 scripts/autoflow.py complete-run \
  --run <run-id> \
  --result <success|needs_changes|blocked|failed> \
  --summary "<summary>"

# Show fix request from reviewer
python3 scripts/autoflow.py show-fix-request --spec <spec-slug>
```

### Continuous Iteration

```bash
# Run one iteration tick (commit and/or dispatch)
python3 scripts/continuous_iteration.py \
  --spec <spec-slug> \
  --config config/continuous-iteration.example.json \
  --commit-if-dirty \
  --dispatch \
  --push
```

### Memory and State

```bash
# Show scoped memory
python3 scripts/autoflow.py show-memory --scope <global|spec> [--spec <spec-slug>]

# Capture memory from a completed run
python3 scripts/autoflow.py capture-memory --run <run-id>

# Show task history
python3 scripts/autoflow.py task-history --spec <spec-slug> --task <task-id>
```

### Worktree Management

```bash
# Create or refresh per-spec worktree
python3 scripts/autoflow.py create-worktree --spec <spec-slug>
```

## Key Scripts and Their Purposes

- `autoflow.py`: Main control-plane CLI (spec/task/run lifecycle, state queries, memory management)
- `continuous_iteration.py`: Scheduled iteration loop with commit, verify, dispatch logic
- `agent_runner.py`: Agent execution wrapper (handles resume protocols, ACP vs CLI)
- `workflow-dispatch.sh`: End-to-end dispatch (worktree creation → run generation → tmux launch)
- `tmux-start.sh`: Background execution wrapper
- `git-auto-commit.sh`: Auto-commit with prefixed messages
- `git-prepare-branch.sh`: Branch preparation for tasks

## Skills and Roles

Skills in `skills/<role>/SKILL.md` define reusable workflows. The system includes:

- **spec-writer**: Convert intent into spec artifacts
- **task-graph-manager**: Derive and refine execution graph
- **implementation-runner**: Execute coding slices with bounded scope
- **reviewer**: Run review, regression, and merge checks
- **maintainer**: Issue triage, dependency bumps, cleanup

Each skill includes a workflow description and rules. BMAD role templates in `templates/bmad/` are injected into prompts for role framing.

## Review and QA System

### Review Artifacts

Reviewer failures produce structured artifacts:
- `.autoflow/specs/<slug>/QA_FIX_REQUEST.md`: Human-readable findings
- `.autoflow/specs/<slug>/QA_FIX_REQUEST.json`: Machine-readable structured findings

### Finding Schema

Each finding includes:
- `file`, `line`, `end_line`: Location
- `severity`: Issue severity
- `category`: Type of issue
- `title`, `body`: Description
- `suggested_fix`: Proposed fix
- `source_run`: Originating run

### Review Approval

Uses hash-based approval:
- Approved implementations are hashed in `review_state.json`
- Reviewer can invalidate approval by removing hash
- System gates implementation dispatch until review approval present

## Agent Protocols

### CLI Protocol (codex, claude)
- `command` + `args` base command
- Optional `resume` configuration for native continuation
- `model_profile` or concrete `model` override
- `tool_profile` or concrete `tools` list

### ACP Protocol (acp-agent)
- `transport.type`: "stdio"
- `transport.command` + `transport.args`: Agent command
- `transport.prompt_mode`: "argv" for prompt via argument

## Memory System

Memory is scoped and automatically captured:
- **Global memory**: `.autoflow/memory/global.md` (cross-spec lessons)
- **Spec memory**: `.autoflow/memory/specs/<slug>.md` (per-spec context)
- **Auto-capture**: Enabled by default for successful runs
- **Prompt injection**: Memory is injected based on agent's `memory_scopes` config

## Development Commands

### Testing

```bash
# Run all tests
python3 -m pytest tests/

# Run specific test file
python3 -m pytest tests/test_agent_runner.py

# Run tests with coverage
python3 -m pytest tests/ --cov=autoflow --cov-report=html

# Run with verbose output
python3 -m pytest tests/ -v

# Run specific test function
python3 -m pytest tests/test_state.py::test_task_state_transitions -v

# Run performance benchmarks
python3 benchmark_results.py
```

### Test Organization

Tests are organized by component:
- **test_state.py**: State management and workflow transitions
- **test_orchestrator.py**: Main orchestration logic
- **test_agent_runner.py**: Agent execution and protocol handling
- **test_codex_adapter.py**: Codex agent integration
- **test_claude_code_adapter.py**: Claude Code agent integration
- **test_ci_gates.py**: Quality gates and verification
- **test_cross_review.py**: Review system and approval workflow
- **test_tmux_manager.py**: Tmux session management
- **test_scheduler.py**: Task scheduling and dependency resolution
- **test_skill_registry.py**: Skill system functionality
- **test_run_metadata_performance.py**: Performance optimization validation
- **test_run_cache_integration.py**: Caching strategy verification

### Code Quality

```bash
# Run linting (ruff)
ruff check autoflow/ tests/

# Format code
ruff format autoflow/ tests/

# Type checking
mypy autoflow/

# Security checks
bandit -r autoflow/

# Run all quality checks
ruff check autoflow/ tests/ && mypy autoflow/ && bandit -r autoflow/
```

### CLI Usage

```bash
# Show help
autoflow --help

# Initialize Autoflow state
autoflow init

# Create a new spec
autoflow new-spec --slug my-feature --title "My Feature" --summary "Description"

# Initialize tasks for a spec
autoflow init-tasks --spec my-feature

# Show workflow state
autoflow workflow-state --spec my-feature

# Create and run a new run
autoflow new-run --spec my-feature --role implementation-runner --agent codex --task T1
```

## Peter's AI Development Principles

Based on Peter Steinberger's workflow (627 commits in one day), Autoflow implements:

### 1. Automated Testing is Prerequisite
- Every commit must pass tests before merging
- Failed tests trigger automatic fixes, not human intervention
- CI runs on every iteration, not just on PR

### 2. AI Self-Completion Loops
- AI discovers problems → AI fixes → AI tests → AI commits
- Humans set rules (CI gates, security checks), AI handles execution
- Each cycle takes 1-2 minutes, enabling rapid iteration

### 3. Fine-Grained Commits for Safety
- Small, focused changes (few lines, not thousands)
- Easy rollback when issues occur
- Precise problem identification and quick recovery

### 4. Human-in-the-Loop for Rules, Not Execution
- Humans define goals, boundaries, and acceptance criteria
- AI operates autonomously within those constraints
- Manual intervention only for rule violations or strategic decisions

## Important Architectural Invariants

1. Every run has a prompt artifact and metadata/logs
2. Every task has acceptance criteria
3. Every merged change has been reviewed by a separate role
4. State is the source of truth; agent CLIs are ephemeral
5. Worktrees provide isolation; main repo remains clean
6. Review gates prevent implementation after planning changes
7. Structured findings enable task-driven retries (not summary-driven)
8. **Every commit passes automated tests before merging**
9. **AI operates autonomously within human-defined boundaries**
10. **Fine-grained changes enable rapid recovery from failures**

## Continuous Iteration Configuration

The continuous iteration system in `config/continuous-iteration.example.json` controls:

- `role_agents`: Explicit agent per role
- `agent_selection`: Fallback preferences, sync behavior
- `verify_commands`: Pre-commit verification (supports `{spec}` placeholder)
- `commit`: Message prefix, push behavior, active run gating
- `retry_policy`: Max attempts, fix request requirements

## OpenClaw Integration

The `skills/openclaw-orchestrator/` skill defines the contract for OpenClaw as outer orchestrator. OpenClaw executes Autoflow skills and manages the control loop while Autoflow provides state management and workflow contracts.

## Complete AI-Driven Development Workflow

### Phase 1: Setup and Initialization
```bash
# 1. Initialize the repository
python3 scripts/autoflow.py init
python3 scripts/autoflow.py init-system-config
cp config/agents.example.json .autoflow/agents.json

# 2. Create a new spec from high-level goal
python3 scripts/autoflow.py new-spec \
  --slug ai-project \
  --title "AI-Powered Web Service" \
  --summary "Build a scalable web service using AI-driven development"

# 3. Let AI decompose into tasks
python3 scripts/autoflow.py init-tasks --spec ai-project
```

### Phase 2: Autonomous Development Loop
```bash
# 4. Start continuous iteration (this is where the magic happens)
# This single command enables AI to self-complete loops like Peter's workflow
python3 scripts/continuous_iteration.py \
  --spec ai-project \
  --config config/continuous-iteration.example.json \
  --commit-if-dirty \
  --dispatch \
  --push

# Behind the scenes, this will:
# - Check workflow state
# - Find next ready task
# - Create appropriate run (implementation/review/planning)
# - Launch agent in tmux background
# - Agent completes work autonomously
# - Run completes and updates task status
# - If tests pass, auto-commit with descriptive message
# - Push to remote
# - Repeat every 2-5 minutes
```

### Phase 3: Monitoring and Intervention
```bash
# 5. Monitor AI progress (humans should check periodically, not constantly)
python3 scripts/autoflow.py workflow-state --spec ai-project

# 6. If AI gets stuck, provide guidance
python3 scripts/autoflow.py show-fix-request --spec ai-project

# 7. View task history to understand iteration patterns
python3 scripts/autoflow.py task-history --spec ai-project --task T3
```

### Example: One AI Development Cycle
```
16:05 - AI discovers issue in authentication module
16:06 - AI creates fix task and generates implementation
16:08 - AI writes tests for the fix
16:09 - AI runs tests (fails initially)
16:11 - AI refines fix based on test output
16:12 - AI runs tests again (passes)
16:13 - AI creates review run
16:15 - Reviewer approves (automated checks pass)
16:16 - System auto-commits: "fix(auth): resolve JWT validation edge case"
16:17 - Changes pushed to main branch
```

## Scheduled Automation Setup

To achieve Peter-style continuous development, setup cron jobs:

```bash
# Add to crontab (crontab -e)
# Run continuous iteration every 5 minutes
*/5 * * * * cd /path/to/autoflow && python3 scripts/continuous_iteration.py --spec ai-project --config config/continuous-iteration.example.json --commit-if-dirty --dispatch --push >> .autoflow/logs/cron.log 2>&1

# Nightly maintenance and optimization
0 2 * * * cd /path/to/autoflow && python3 scripts/autoflow.py maintainer --spec ai-project --agent claude-review

# Weekly memory consolidation and learning
0 3 * * 0 cd /path/to/autoflow && python3 scripts/autoflow.py consolidate-memory --global
```

## Key Architectural Patterns

### Agent Protocol Abstraction

The system uses a unified agent protocol that abstracts different AI backends:
- **CLI Protocol** (codex, claude): Command-line tools with optional resume support
- **ACP Protocol** (acp-agent): stdio-based communication with prompt via argv
- **Agent Registry**: Dynamic discovery and sync of local agents

All agents implement the same interface defined in `autoflow/agents/base.py`, enabling seamless swapping of backends without changing workflow logic.

### State-Driven Execution

Autoflow is fundamentally state-driven:
1. **State is source of truth**: All workflow decisions derive from `.autoflow/` state
2. **Immutable runs**: Completed runs never change; new runs create new state
3. **Deterministic state transitions**: Task statuses follow strict workflows
4. **Reproducible artifacts**: Every run has prompt, logs, output, and metadata

### Multi-Layer Isolation

- **Spec isolation**: Each spec has its own directory in `.autoflow/specs/`
- **Task isolation**: Tasks track dependencies and block/unlock appropriately
- **Execution isolation**: Runs execute in per-spec worktrees (`.autoflow/worktrees/`)
- **Agent isolation**: Agents run in tmux sessions with separate processes

### Quality Gates

The system implements multiple quality gates:
1. **Acceptance criteria**: Every task has defined acceptance criteria
2. **Pre-commit verification**: Tests, linting, and security checks before commit
3. **Cross-review**: Separate reviewer role validates implementation
4. **Review approval**: Hash-based approval system prevents unreviewed code from dispatching

### Scripts Directory Structure

The `scripts/` directory contains essential automation:

- **autoflow.py**: Main control-plane CLI (85KB, comprehensive state management)
- **continuous_iteration.py**: Scheduled iteration loop with commit, verify, dispatch logic
- **agent_runner.py**: Agent execution wrapper handling resume protocols
- **workflow-dispatch.sh**: End-to-end dispatch pipeline
- **tmux-start.sh**: Background execution wrapper
- **e2e_verify.py**: End-to-end verification testing
- **generate_fix_tasks.py**: Automatic fix task generation from review findings
- **maintenance.py**: System maintenance and cleanup operations

## Important Architectural Invariants

### Agent Runs Stall or Hang
```bash
# Check active tmux sessions
tmux ls

# Attach to specific session to debug
tmux attach -t autoflow-run-<timestamp>

# Kill stuck session
tmux kill-session -t autoflow-run-<timestamp>
```

### Tasks Keep Failing
```bash
# Examine task history for patterns
python3 scripts/autoflow.py task-history --spec <spec> --task <task-id>

# Check if fix request exists
python3 scripts/autoflow.py show-fix-request --spec <spec>

# View recent runs for the task
ls -lt .autoflow/runs/ | grep <task-id>

# Manually advance blocked task
python3 scripts/autoflow.py update-task --spec <spec> --task <task-id> --status todo
```

### Configuration Issues
```bash
# Validate agent configuration
python3 scripts/autoflow.py validate-config

# Test agent availability
python3 scripts/autoflow.py test-agent --agent <agent-name>

# Sync discovered agents
python3 scripts/autoflow.py sync-agents --overwrite
```

### Memory and State Corruption
```bash
# Reset specific task state
python3 scripts/autoflow.py reset-task --spec <spec> --task <task-id>

# Clear stuck runs
python3 scripts/autoflow.py cleanup-runs --spec <spec>

# Rebuild worktree
python3 scripts/autoflow.py create-worktree --spec <spec> --force
```

## Common Development Patterns

### Adding New Agent Types

When adding a new agent backend:
1. Create a new class in `autoflow/agents/` inheriting from `BaseAgent`
2. Implement the required methods: `execute()`, `supports_resume()`, `cleanup()`
3. Add agent configuration to `.autoflow/agents.json`
4. Add tests in `tests/test_<agent>_adapter.py`

### Modifying Workflow State

When working with workflow state:
1. Always use the state management functions in `autoflow/core/state.py`
2. Never manually edit `.autoflow/specs/*/TASKS.json` - use the CLI
3. Task status transitions must follow valid workflows
4. State changes should be atomic - use transactions when possible

### Testing Strategy

The project uses a comprehensive testing approach:
- **Unit tests**: Individual component testing
- **Integration tests**: Multi-component interaction testing
- **E2E tests**: Full workflow testing with `e2e_verify.py`
- **Performance tests**: Benchmark and optimization validation
- **Security tests**: Bandit scanning for vulnerabilities

When adding new features:
1. Write tests first (TDD approach)
2. Ensure all tests pass before committing
3. Add coverage for new code paths
4. Run security scans on changes to agent execution or file handling

### Error Handling

The system implements comprehensive error handling:
- **Structured errors**: All errors are logged with context
- **Recovery patterns**: Automatic retry with exponential backoff
- **Rollback support**: Failed runs can be rolled back
- **Human escalation**: Unrecoverable errors trigger human notification

## Performance Optimization

### Parallel Execution
Edit `.autoflow/agents.json` to enable concurrent agents:
```json
{
  "agents": {
    "codex-impl-1": {"command": "codex", "max_concurrent": 3},
    "codex-impl-2": {"command": "codex", "max_concurrent": 3}
  }
}
```

### Resource Management
```bash
# Monitor resource usage
python3 scripts/autoflow.py monitor-resources --spec <spec>

# Limit concurrent runs per spec
python3 scripts/autoflow.py set-config --spec <spec> --max-concurrent-runs 5
```

### Caching and Incremental Development
```bash
# Enable caching for faster iterations
python3 scripts/autoflow.py set-config --enable-cache true

# Clear cache when needed
python3 scripts/autoflow.py clear-cache --spec <spec>
```

## Best Practices for AI-Driven Development

### 1. Start with Strong Foundations
- Invest in comprehensive test coverage upfront
- Define clear acceptance criteria for every task
- Set up CI/CD gates before autonomous operation

### 2. Define Clear Boundaries
- Specify what AI can and cannot do autonomously
- Set resource limits (time, memory, API calls)
- Define escalation triggers for human intervention

### 3. Trust but Verify
- Let AI operate autonomously within bounds
- Monitor outputs periodically, not constantly
- Intervene only when boundaries are violated

### 4. Embrace Rapid Iteration
- Small, focused changes > large PRs
- Fast feedback loops > perfect planning
- Automated recovery > manual debugging

### 5. Learn and Adapt
- Review AI decisions weekly
- Update boundaries based on patterns
- Consolidate learned lessons into memory
