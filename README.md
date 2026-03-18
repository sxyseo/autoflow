# Autoflow

<div align="center">

**Autonomous Software Delivery Control Plane**

Inspired by OpenAI's "Harness Engineering" philosophy and AI-driven development workflows

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**[English](README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [Español](README.es.md)**

</div>

---

## Table of Contents

- [Overview](#overview)
- [Philosophy](#philosophy)
- [Key Concepts](#key-concepts)
- [Architecture](#architecture)
- [Features](#features)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
- [Advanced Topics](#advanced-topics)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Additional Documentation

- [**Custom Skills Guide**](docs/custom_skills.md) - Create, validate, and share custom skills

## Overview

**Autoflow** is a thin control plane for autonomous software delivery. It enables AI agents to run repeatable loops around spec creation, task decomposition, implementation, review, and maintenance while delegating concrete coding work to various AI agent backends.

### What Makes Autoflow Different

Unlike traditional development tools, Autoflow is built from the ground up for **AI-driven development**:

- **State as Source of Truth**: Every spec, task, run, and decision is explicitly tracked
- **Deterministic Prompts**: Reusable skills and templates ensure consistent agent behavior
- **Swappable Backends**: Use OpenClaw, Claude Code, Codex, or custom agents interchangeably
- **Background Execution**: Agents run autonomously via `tmux` without blocking workflows
- **Automated Gates**: Review, testing, and merge checks prevent bad commits
- **Full Recovery**: Every run is logged and resumable for transparency and debugging

### The Goal: Reliable AI Autonomy

The initial goal is **not** full autonomy—it's a **reliable harness** where:

- Humans define goals, boundaries, and acceptance criteria
- AI operates autonomously within those constraints
- Every change is tested, reviewed, and committed atomically
- Failed iterations automatically trigger fixes, not human intervention

## Philosophy

### Harness Engineering

Autoflow is inspired by [OpenAI's Harness Engineering](https://openai.com/index/harness-engineering/) philosophy: **strong agents come from strong harnesses**.

A harness provides:
- **Evaluation**: Clear metrics for success and failure
- **Orchestration**: Coordinated multi-agent workflows
- **Checkpoints**: Recoverable state and rollback capability
- **Contracts**: Well-defined interfaces for tool use

### AI Self-Completion Loops

Autoflow enables autonomous development cycles:

```
Traditional AI Coding:
Human discovers issue → Human writes prompt → AI writes code → Human verifies → (repeat)

Autoflow Workflow:
AI discovers issue → AI fixes → AI tests → AI commits → (loop every 1-2 minutes)
```

**Key insights**:
1. **Automated testing is prerequisite**: Every commit must pass tests
2. **AI self-completion loops**: AI discovers, fixes, tests, and commits autonomously
3. **Fine-grained commits**: Small changes (few lines) enable safe, fast iteration
4. **Human-in-the-loop for rules, not execution**: Humans set boundaries; AI handles execution

### Spec-Driven Development

Autoflow applies spec-driven development principles:

- **Spec** defines intent, constraints, and acceptance criteria
- **Tasks** define work units with dependencies and status
- **Skills** define reusable workflows for each role
- **Runs** store concrete executions with full context
- **Agents** map logical roles to concrete AI backends

## Key Concepts

### State Hierarchy

```
.autoflow/
├── specs/           # Product intent and constraints
│   └── <slug>/
│       ├── SPEC.md              # Requirements and constraints
│       ├── TASKS.json           # Task graph and status
│       ├── QA_FIX_REQUEST.md    # Review findings (markdown)
│       ├── QA_FIX_REQUEST.json  # Review findings (structured)
│       └── events.jsonl         # Event log
├── tasks/           # Task definitions and status
├── runs/            # Per-execution prompts, logs, outputs
│   └── <timestamp>-<role>-<spec>-<task>/
│       ├── prompt.md            # Full prompt sent to agent
│       ├── summary.md           # Agent's summary
│       ├── run.sh               # Execution script
│       └── metadata.json        # Run metadata
├── memory/          # Scoped memory capture
│   ├── global.md                # Cross-spec lessons
│   └── specs/
│       └── <slug>.md            # Per-spec context
├── worktrees/       # Per-spec git worktrees
└── logs/            # Execution logs
```

### Task Status Workflow

```
todo → in_progress → in_review → done
                   ↓           ↑
              needs_changes    |
                   ↓           |
                blocked ←─────┘
                   ↓
                  todo
```

**Valid statuses**:
- `todo`: Ready to start
- `in_progress`: Currently being executed
- `in_review`: Awaiting review
- `done`: Completed and approved
- `needs_changes`: Review found issues
- `blocked`: Waiting on dependencies

### Run Results

**Valid results**:
- `success`: Task completed successfully
- `needs_changes`: Completed but requires fixes
- `blocked`: Cannot proceed due to dependencies
- `failed`: Execution failed

### Skills and Roles

Autoflow defines **skills** as reusable workflows:

| Skill | Role | Description |
|-------|------|-------------|
| `spec-writer` | Planner | Convert intent into structured specs |
| `task-graph-manager` | Architect | Derive and refine execution graph |
| `implementation-runner` | Implementer | Execute coding slices with bounded scope |
| `reviewer` | Quality Assurance | Run review, regression, and merge checks |
| `maintainer` | Operator | Issue triage, dependency bumps, cleanup |

Each skill includes:
- **Workflow description**: Step-by-step process
- **Role framing**: Templates for consistent agent behavior
- **Rules and constraints**: What the agent can and cannot do
- **Output format**: Expected artifacts and handoffs

### Agent Protocols

Autoflow supports multiple agent protocols:

#### CLI Protocol (codex, claude)

```json
{
  "protocol": "cli",
  "command": "claude",
  "args": ["--full-auto"],
  "model_profile": "implementation",
  "memory_scopes": ["global", "spec"],
  "resume": {
    "mode": "subcommand",
    "subcommand": "resume",
    "args": ["--last"]
  }
}
```

#### ACP Protocol (acp-agent)

```json
{
  "protocol": "acp",
  "transport": {
    "type": "stdio",
    "command": "my-agent",
    "args": []
  },
  "prompt_mode": "argv"
}
```

## Architecture

### Four-Layer System

```
┌─────────────────────────────────────────────────────────────┐
│                  Layer 4: Governance                         │
│              Review Gates, CI/CD, Branch Policy              │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                  Layer 3: Execution                          │
│           Spec, Role, Agent, Prompt, Workspace               │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                  Layer 2: Roles (Skills)                     │
│    Spec-Writer, Task-Graph-Manager, Implementation-Runner,   │
│              Reviewer, Maintainer, Iteration-Manager         │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                  Layer 1: Control Plane                      │
│              State, Config, Memory, Discovery                │
└─────────────────────────────────────────────────────────────┘
```

### Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                      External Orchestrator                    │
│                    (Cron / Human / Custom)                    │
└─────────────────────────────┬────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    Autoflow Control Plane                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Specs   │  │  Tasks   │  │   Runs   │  │  Memory  │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │             │             │             │           │
│       └─────────────┴─────────────┴─────────────┘           │
│                           │                                 │
│  ┌────────────────────────┴────────────────────────────┐    │
│  │                    Skill System                     │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐           │    │
│  │  │ Spec     │ │ Task     │ │Implement │           │    │
│  │  │ Writer   │ │ Graph    │ │ Runner   │           │    │
│  │  └──────────┘ └──────────┘ └──────────┘           │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐           │    │
│  │  │ Reviewer │ │Maintainer│ │Iteration │           │    │
│  │  └──────────┘ └──────────┘ └──────────┘           │    │
│  └────────────────────────┬────────────────────────────┘    │
│                           │                                 │
│  ┌────────────────────────┴────────────────────────────┐    │
│  │                 Agent Registry                      │    │
│  │  CLI (claude, codex) │ ACP (custom) │ Orchestrate   │    │
│  └────────────────────────┬────────────────────────────┘    │
└───────────────────────────┼─────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                      Execution Layer                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  tmux    │  │  Agent   │  │  Git     │  │  Worktree│  │
│  │ Sessions │  │  Runner  │  │  Operations│  │ Isolation│  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## CLI Architecture

Autoflow features a **modular CLI architecture** that separates concerns into focused command groups. This design makes the codebase maintainable, testable, and easy to extend.

### Modular Structure

```
autoflow/cli/
├── __init__.py           # Package initialization
├── main.py               # Main Click group and entry point
├── utils.py              # Shared utility functions
├── init.py               # Initialization commands
├── status.py             # System status commands
├── run.py                # Task execution commands
├── agent.py              # Agent management commands
├── skill.py              # Skill management commands
├── task.py               # Task lifecycle commands
├── scheduler.py          # Scheduler control commands
├── ci.py                 # CI/CD verification commands
├── review.py             # Review and QA commands
├── config.py             # Configuration management
└── memory.py             # Memory and learning commands
```

### Command Groups

The CLI is organized into logical command groups:

| Command Group | Purpose | Example Commands |
|--------------|---------|------------------|
| **init** | System initialization | `autoflow init`, `autoflow init --config` |
| **status** | System health checks | `autoflow status`, `autoflow status --json` |
| **run** | Execute tasks | `autoflow run "Fix bug"`, `autoflow run --agent codex` |
| **agent** | Manage AI agents | `autoflow agent list`, `autoflow agent check all` |
| **skill** | Manage skills | `autoflow skill list`, `autoflow skill show SPEC_WRITER` |
| **task** | Task lifecycle | `autoflow task list`, `autoflow task show <id>` |
| **scheduler** | Control scheduler | `autoflow scheduler start`, `autoflow scheduler status` |
| **ci** | CI/CD operations | `autoflow ci verify --all`, `autoflow ci verify --fix` |
| **review** | Code review | `autoflow review run`, `autoflow review run --agent claude-code` |
| **config** | Configuration | `autoflow config show`, `autoflow config validate` |
| **memory** | Learning system | `autoflow memory list`, `autoflow memory get <key>` |

### Design Principles

The modular CLI follows these principles:

1. **Single Responsibility**: Each module handles one command group
2. **Shared Utilities**: Common functions in `cli/utils.py`
3. **Context Management**: Click context passes config and state
4. **Backward Compatibility**: Old import paths still work
5. **Type Safety**: Full type annotations with mypy
6. **Testability**: Each module tested independently

### Extending the CLI

Adding a new command group is straightforward:

#### 1. Create the Module

Create a new file in `autoflow/cli/`:

```python
"""autoflow/cli/mygroup.py

Autoflow CLI - My Command Group

Manage custom operations.

Usage:
    autoflow mygroup list
    autoflow mygroup run <name>
"""

from __future__ import annotations

import click

@click.group()
def mygroup() -> None:
    """Manage custom operations."""
    pass

@mygroup.command("list")
@click.pass_context
def mygroup_list(ctx: click.Context) -> None:
    """List all items."""
    # Your implementation here
    pass

@mygroup.command("run")
@click.argument("name", type=str)
@click.pass_context
def mygroup_run(ctx: click.Context, name: str) -> None:
    """Run a specific item."""
    # Your implementation here
    pass
```

#### 2. Register in Main

Import and register in `autoflow/cli/main.py`:

```python
from autoflow.cli.mygroup import mygroup

# Add to the main group
main.add_command(mygroup)
```

#### 3. Add Tests

Create tests in `tests/test_cli_mygroup.py`:

```python
"""Tests for mygroup CLI commands."""

from click.testing import CliRunner

def test_mygroup_list(cli_runner):
    """Test 'autoflow mygroup list' command."""
    result = cli_runner.invoke(["mygroup", "list"])
    assert result.exit_code == 0
```

### Backward Compatibility

The old monolithic `autoflow/cli.py` is maintained as a thin wrapper for backward compatibility:

```python
# Old import path still works
from autoflow.cli import main

# Old script invocation still works
python3 -m autoflow.cli --help
```

This ensures existing scripts and integrations continue to work without modification.

## Features

### 1. Explicit State Management

Every aspect of the development process is explicitly tracked:

- **Specs**: Intent, requirements, constraints, acceptance criteria
- **Tasks**: Work units with dependencies, status, and assignments
- **Runs**: Complete execution history with prompts, outputs, and metadata
- **Memory**: Scoped learning capture across specs and runs
- **Events**: Per-spec event logs for audit and recovery

### 2. Deterministic Prompt Assembly

Autoflow ensures consistent agent behavior through:

- **Skill definitions**: Reusable workflows with clear steps
- **Role templates**: Role-framing for consistent agent personas
- **Context injection**: Automated inclusion of relevant state, memory, and findings
- **Prompt versioning**: Full prompt stored with each run for reproducibility

### 3. Swappable Agent Backends

Support for multiple AI backends through unified protocols:

- **CLI Protocol**: For command-line agents (claude, codex)
- **ACP Protocol**: For Agent Communication Protocol agents
- **Native continuation**: Agent-specific resume mechanisms
- **Dynamic fallback**: Automatic agent selection on failures

### 4. Background Execution

Autonomous operation via `tmux`:

- **Non-blocking**: Runs execute in background without disrupting workflows
- **Attachable**: Monitor runs in real-time or review logs later
- **Resumable**: Native continuation support for interrupted runs
- **Resource-managed**: Concurrent run limits per agent and spec

### 5. Review and Merge Gates

Automated quality checks prevent bad commits:

- **Structured findings**: Machine-readable QA artifacts with location, severity, and fixes
- **Hash-based approval**: Implementation hash must match approved review
- **Gate enforcement**: System blocks implementation after planning changes
- **Task-driven retries**: Structured findings injected into fix prompts

### 6. Memory and Learning

Accumulated wisdom across runs:

- **Global memory**: Cross-spec lessons and patterns
- **Spec memory**: Per-spec context and history
- **Strategy memory**: Playbooks for repeated blockers
- **Auto-capture**: Memory extracted from successful runs
- **Prompt injection**: Context automatically included based on agent config

### 7. Worktree Isolation

Safe parallel development:

- **Per-spec worktrees**: Isolated git working trees
- **Clean main repo**: Main branch remains pristine
- **Atomic merges**: Changes merged only after approval
- **Easy rollback**: Revert worktree on failure

### 8. Continuous Iteration

Scheduled autonomous development:

- **Tick-based loop**: Check, commit, dispatch, push
- **Auto-commit**: Descriptive commits with prefixed messages
- **Verification**: Pre-commit tests and checks
- **Progress tracking**: Automatic task state advancement

## Quick Start

### Prerequisites

- Python 3.10 or higher
- Git
- tmux
- An AI agent backend (Claude Code, Codex, or custom)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/autoflow.git
cd autoflow

# (Optional) Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in editable mode (includes CLI entry point)
pip install -e .
```

### Migration from Old CLI

If you're upgrading from the old monolithic CLI:

**Old Command:**
```bash
python3 scripts/autoflow.py init
```

**New Command:**
```bash
autoflow init
```

**Backward Compatibility:**
The old import path still works for existing scripts:
```python
# This still works
from autoflow.cli import main
main()
```

All existing functionality is preserved—only the interface has changed. See the [CLI Architecture](#cli-architecture) section for details.

### Initialization

```bash
# Recommended today: use the script-based control plane
python3 scripts/doctor.py
python3 scripts/autoflow.py init
python3 scripts/autoflow.py init-system-config
python3 scripts/autoflow.py sync-agents

# Check overall status
python3 scripts/autoflow.py status
```

### Create Your First Spec

```bash
# Create a new spec and inspect the generated task graph
python3 scripts/autoflow.py new-spec \
  --slug my-first-project \
  --title "My First AI Project" \
  --summary "Build an AI-driven application"
python3 scripts/autoflow.py init-tasks --spec my-first-project
python3 scripts/autoflow.py workflow-state --spec my-first-project
```

### Start Autonomous Development

```bash
# Start with a single safe tick. Do not commit/push on first run.
python3 scripts/continuous_iteration.py \
  --spec my-first-project \
  --config config/continuous-iteration.example.json \
  --dispatch

# Then let scheduler drive the same job definition
python3 scripts/scheduler.py run-once \
  --job-type continuous_iteration \
  --config config/scheduler_config.json \
  --verbose
```

Recommended order:
1. Run `scripts/doctor.py` first.
2. Use `continuous_iteration.py` as a single-pass smoke test.
3. Only after that, use `scheduler.py` for repeated execution.

Important:
- `continuous_iteration.py` is a single tick, not a long-running daemon
- repeated execution comes from `scheduler.py`
- avoid `--commit-if-dirty` and `--push` until the smoke path is green

### Validate the Runtime Loop

```bash
# Read-only environment and dependency check
python3 scripts/doctor.py

# Command-layer smoke test
python3 scripts/validate_readme_flow.py --agent codex

# Runtime-loop smoke test (uses a disposable dummy ACP agent and tmux)
python3 scripts/validate_runtime_loop.py

# Long-running scheduler smoke test (launch, wait, SIGTERM, clean shutdown)
python3 scripts/validate_scheduler_start.py

# Recovery and bounded QA-loop smoke test
python3 scripts/validate_recovery_loop.py
```

The runtime validation confirms that:
- `continuous_iteration.py --dispatch` creates a real background tmux run and auto-finalizes it after the agent writes `agent_result.json`
- `scheduler.py run-once --job-type continuous_iteration` can drive the same path from scheduler config
- Autoflow advances state into reviewer handoff instead of leaving a dangling active run

The scheduler-start validation confirms that:
- `scheduler.py start` reaches a stable running state with both idle and enabled-job configurations
- the process handles `SIGTERM` cleanly instead of hanging
- repeated start/stop cycles do not leave a lingering scheduler process behind

The recovery validation confirms that:
- stale runs can be recovered into retry runs
- reviewer `needs_changes` generates a fix request and hands work back to implementation
- the bounded fix and re-review loop advances the task into the next stage

## Configuration

### Agent Configuration (`.autoflow/agents.json`)

```json
{
  "agents": {
    "claude-impl": {
      "name": "Claude Implementation Agent",
      "protocol": "cli",
      "command": "claude",
      "args": ["--full-auto"],
      "model_profile": "implementation",
      "tool_profile": "default",
      "memory_scopes": ["global", "spec"],
      "roles": ["implementation-runner", "maintainer"],
      "max_concurrent": 3,
      "resume": {
        "mode": "subcommand",
        "subcommand": "resume",
        "args": ["--last"]
      }
    },
    "codex-spec": {
      "name": "Codex Specification Agent",
      "protocol": "cli",
      "command": "codex",
      "args": ["--full-auto"],
      "model_profile": "spec",
      "tool_profile": "spec-tools",
      "memory_scopes": ["global"],
      "roles": ["spec-writer", "task-graph-manager"],
      "max_concurrent": 2
    }
  }
}
```

### System Configuration (`.autoflow/system.json`)

```json
{
  "memory": {
    "enabled": true,
    "scopes": ["global", "spec", "strategy"],
    "auto_capture": true,
    "global_memory_path": ".autoflow/memory/global.md",
    "spec_memory_dir": ".autoflow/memory/specs",
    "strategy_memory_dir": ".autoflow/memory/strategy"
  },
  "model_profiles": {
    "spec": {
      "model": "claude-sonnet-4-6",
      "temperature": 0.7,
      "max_tokens": 8192
    },
    "implementation": {
      "model": "claude-sonnet-4-6",
      "temperature": 0.3,
      "max_tokens": 16384
    },
    "review": {
      "model": "claude-opus-4-6",
      "temperature": 0.2,
      "max_tokens": 16384
    }
  },
  "tool_profiles": {
    "default": {
      "allowed_tools": ["read", "write", "edit", "bash", "search"],
      "denied_tools": []
    },
    "spec-tools": {
      "allowed_tools": ["read", "write", "edit", "search"],
      "denied_tools": ["bash"]
    }
  },
  "acp_registry": {
    "enabled": true,
    "discovery_paths": [
      "/usr/local/bin/acp-agents/*",
      "~/.local/share/acp-agents/*"
    ]
  }
}
```

### Continuous Iteration Configuration

```json
{
  "spec": "my-first-project",
  "role_agents": {
    "spec-writer": "codex-spec",
    "task-graph-manager": "codex-spec",
    "implementation-runner": "claude-impl",
    "reviewer": "claude-review",
    "maintainer": "claude-impl"
  },
  "verify_commands": [
    "python3 -m pytest tests/ -v",
    "python3 scripts/ci_check.sh"
  ],
  "commit": {
    "enabled": true,
    "message_prefix": "autoflow:",
    "push": true,
    "require_active_run": false
  },
  "dispatch": {
    "enabled": true,
    "max_concurrent_runs": 5,
    "dispatch_interval_seconds": 120
  },
  "retry_policy": {
    "max_attempts": 3,
    "require_fix_request": true,
    "backoff_multiplier": 2
  }
}
```

### Scheduler Configuration

The scheduler's `continuous_iteration` job must declare which spec it should drive:

```json
{
  "jobs": {
    "continuous_iteration": {
      "enabled": true,
      "cron": "*/5 * * * *",
      "args": {
        "spec": "my-first-project",
        "config": "config/continuous-iteration.example.json",
        "dispatch": true,
        "commit_if_dirty": false,
        "push": false
      }
    }
  }
}
```

### Sanitization Configuration

Autoflow includes built-in data sanitization to prevent sensitive information from appearing in logs and JSON output. This protects against information disclosure (CWE-200) by automatically redacting API keys, secrets, passwords, tokens, and other sensitive data.

#### Default Sanitization Behavior

By default, Autoflow automatically redacts fields matching these patterns:

- **Credentials**: `api_key`, `apikey`, `secret`, `password`, `passwd`, `token`, `auth`, `credential`, `private_key`, `access_token`, `refresh_token`, `session_key`, `csrf`, `bearer`
- **Configuration**: `model`, `model_profile`, `tool_profile`, `memory_scope`, `transport`

Values are replaced with `***REDACTED***` in all JSON file writes and stdout output.

#### Configuration Options

Create or edit `config/settings.json5` to customize sanitization:

```json5
{
  // ... other config ...

  sanitization: {
    // Enable or disable sanitization globally
    enabled: true,

    // Custom redaction marker
    redacted_marker: "***REDACTED***",

    // Partial redaction (show first/last N chars) for some fields
    partial_redaction: false,
    partial_chars: 4,

    // Additional fields to treat as sensitive
    custom_sensitive_fields: ["custom_field", "internal_id"],

    // Fields to exclude from sanitization (whitelist)
    excluded_fields: ["model_name", "display_model"],

    // Recursively sanitize nested structures
    recursive: true
  }
}
```

#### Programmatic Usage

You can also use sanitization functions directly in your code:

```python
from autoflow.core.sanitization import sanitize_dict, sanitize_value, create_sanitize_config

# Basic usage - sanitize a dictionary
data = {
    "api_key": "sk-1234567890",
    "username": "user@example.com",
    "model": "gpt-4",
    "public_id": "abc-123"
}
clean_data = sanitize_dict(data)
# Result: {
#   "api_key": "***REDACTED***",
#   "username": "user@example.com",
#   "model": "***REDACTED***",
#   "public_id": "abc-123"
# }

# With custom configuration
config = create_sanitize_config(
    partial_redaction=True,
    partial_chars=4,
    excluded_fields=["model"]
)
clean_data = sanitize_dict(data, config)
# Result: {
#   "api_key": "***REDACTED***",
#   "username": "user@example.com",
#   "model": "gpt-4",
#   "public_id": "abc-123"
# }

# Sanitize nested structures
nested = {
    "database": {
        "host": "localhost",
        "password": "secret123",
        "credentials": {
            "api_key": "key-456"
        }
    }
}
clean_nested = sanitize_dict(nested)
# Result: {
#   "database": {
#     "host": "localhost",
#     "password": "***REDACTED***",
#     "credentials": {
#       "api_key": "***REDACTED***"
#     }
#   }
# }
```

#### Automatic Sanitization Points

Autoflow automatically sanitizes data at these points:

1. **JSON File Writes**: All `write_json()` calls in StateManager
2. **Agent Configuration**: Agent configs in prompts and CLI output
3. **Run Metadata**: Metadata saved to run directories
4. **CLI Output**: JSON output from all CLI commands

This ensures sensitive data is protected regardless of how it's output.

#### Security Best Practices

1. **Never disable sanitization in production**: Keep `enabled: true` at all times
2. **Review custom exclusions carefully**: Only exclude fields that are truly non-sensitive
3. **Use partial redaction for debugging**: Enable `partial_redaction` during development to see enough info for debugging without exposing full values
4. **Audit logs regularly**: Check `.autoflow/logs/` and run directories to ensure sanitization is working

## Usage

### Basic Commands

#### System Commands

```bash
# Initialize Autoflow
autoflow init [--config /path/to/config.yaml]

# Check system status
autoflow status [--json] [--verbose]

# Run a task
autoflow run "Task description" \
  --spec <spec-slug> \
  --agent <agent-name> \
  --skill <skill-name>
```

#### Agent Management

```bash
# List available agents
autoflow agent list

# Check agent availability
autoflow agent check claude-code
autoflow agent check codex
autoflow agent check all
```

#### Skill Management

```bash
# List available skills
autoflow skill list

# Show skill details
autoflow skill show SPEC_WRITER
autoflow skill show CONTINUOUS_ITERATOR
```

#### Task Management

```bash
# List tasks
autoflow task list \
  --status pending \
  --agent claude-code \
  --limit 20

# Show task details
autoflow task show <task-id>

# Update task status
autoflow task update <task-id> --status <status>
```

#### Scheduler Control

```bash
# Start scheduler
autoflow scheduler start \
  --spec <spec-slug> \
  --max-concurrent 3

# Stop scheduler
autoflow scheduler stop

# Check scheduler status
autoflow scheduler status
```

#### CI/CD Operations

```bash
# Run verification
autoflow ci verify --all

# Verify and auto-fix
autoflow ci verify --fix --agent claude-code
```

#### Code Review

```bash
# Run review
autoflow review run \
  --spec <spec-slug> \
  --agent claude-code

# Run with strategy
autoflow review run \
  --strategy comprehensive \
  --category security
```

#### Configuration

```bash
# Show configuration
autoflow config show

# Validate configuration
autoflow config validate
```

#### Memory and Learning

```bash
# List memory entries
autoflow memory list [--scope global|spec|strategy]

# Get memory value
autoflow memory get <key> [--scope global]

# Set memory value
autoflow memory set <key> <value> [--scope global]

# Delete memory entry
autoflow memory delete <key> [--scope global]
```

### Common Patterns

#### Quick Task Execution

```bash
# Run a quick task with defaults
autoflow run "Fix login bug"

# Run with specific agent and skill
autoflow run "Add user profile" \
  --agent claude-code \
  --skill FEATURE_DEVELOPER
```

#### Monitoring Autonomous Development

```bash
# Start scheduler in background
autoflow scheduler start --spec my-project &

# Monitor status
watch -n 5 "autoflow task list --status in_progress"

# View scheduler status
autoflow scheduler status
```

#### Debugging Failed Tasks

```bash
# Show failed tasks
autoflow task list --status failed

# View task details
autoflow task show <task-id>

# Review findings
autoflow review run --spec <spec> --strategy diagnostic
```

## Advanced Topics

### CLI Architecture Deep Dive

Autoflow's CLI is built on **Click**, a Python package for creating beautiful command-line interfaces. The modular architecture provides:

#### Module Organization

Each command group is a separate Python module:

```python
# autoflow/cli/agent.py
@click.group()
def agent() -> None:
    """Manage AI agents."""
    pass

@agent.command("list")
@click.pass_context
def agent_list(ctx: click.Context) -> None:
    """List available agents."""
    config = ctx.obj.get("config")
    # Implementation...
```

#### Context Management

Configuration and state are passed through Click context:

```python
# Main group sets up context
@click.group()
@click.pass_context
def main(ctx: click.Context) -> None:
    config = load_config()
    ctx.obj["config"] = config
    ctx.obj["verbose"] = verbose

# Subcommands access context
@agent.command("check")
@click.pass_context
def agent_check(ctx: click.Context, name: str) -> None:
    config = ctx.obj.get("config")
    # Use config...
```

#### Shared Utilities

Common functions in `cli/utils.py`:

```python
# State management
def _get_state_manager(config: Config) -> StateManager:
    """Get initialized state manager from config."""
    return StateManager(config.state_dir)

# Output formatting
def _print_json(data: dict) -> None:
    """Print data as JSON."""
    click.echo(json.dumps(data, indent=2))

# Async handling
def _run_async(coro: Coroutine) -> Any:
    """Run async coroutine in sync context."""
    return asyncio.run(coro)
```

#### Testing Infrastructure

Each CLI module has comprehensive tests:

```python
# tests/test_cli_agent.py
class TestAgentCommands:
    def test_agent_list(self, cli_runner):
        result = cli_runner.invoke(["agent", "list"])
        assert result.exit_code == 0

    def test_agent_check(self, cli_runner):
        result = cli_runner.invoke(["agent", "check", "all"])
        assert "claude-code" in result.output
```

### Review Gate System

Autoflow implements hash-based review approval:

```bash
# Reviewer generates findings
autoflow review run --spec <spec-slug>

# Implementation hash stored in review_state.json
# System gates implementation until review approves
cat .autoflow/specs/<slug>/review_state.json
```

### Structured Findings

Reviewer findings are machine-readable:

```json
{
  "findings": [
    {
      "file": "src/auth.py",
      "line": 42,
      "end_line": 45,
      "severity": "error",
      "category": "security",
      "title": "Missing input validation",
      "body": "JWT token not validated before use",
      "suggested_fix": "Add validation: validate_jwt(token)",
      "source_run": "20260307T123456Z-reviewer-feature-auth-T3"
    }
  ]
}
```

Findings are automatically injected into fix prompts for task-driven retries.

### Native Continuation

Agents with native continuation support resume seamlessly:

```bash
# Codex resumes with --last flag
"resume": {
  "mode": "subcommand",
  "subcommand": "resume",
  "args": ["--last"]
}

# Claude uses session-based continuation
"resume": {
  "mode": "session",
  "session_file": ".claude_session"
}
```

### Multi-Agent Orchestration

Run multiple agents in parallel:

```bash
# Configure multiple implementation agents
# In .autoflow/agents.json:
{
  "agents": {
    "claude-impl-1": {"max_concurrent": 3},
    "claude-impl-2": {"max_concurrent": 3},
    "codex-impl": {"max_concurrent": 2}
  }
}

# System will dispatch tasks to available agents
# respecting max_concurrent limits
```

### Custom Skills

Autoflow includes a comprehensive framework for creating, validating, and sharing custom skills beyond the built-in roles.

#### Quick Example

```bash
# Create a custom skill interactively
autoflow skill create

# Or create non-interactively
autoflow skill create --name my-custom-skill --template implementer

# Validate your skill
autoflow skill validate my-custom-skill

# Export to share with your team
autoflow skill export my-custom-skill --version 1.0.0

# Import skills from your team
autoflow skill import team-skills.tar.gz
```

#### Key Features

- **Skill Templates**: Built-in templates for common patterns (planner, implementer, reviewer)
- **Interactive Builder**: Guided skill creation with prompts and validation
- **Validation System**: Ensure skills meet structure and content requirements
- **Sharing & Versioning**: Export/import skills with version tracking and conflict resolution
- **CLI & Python API**: Use from command line or programmatically

#### Documentation

For comprehensive documentation on creating and managing custom skills, see [**Custom Skills Guide**](docs/custom_skills.md).

Topics covered:
- Creating skills from templates
- Validating skill structure
- Sharing skills across teams
- Version management
- CLI reference and Python API
- Best practices and examples

## Best Practices

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

## Troubleshooting

### Agent Runs Stall or Hang

```bash
# Check active tmux sessions
tmux ls

# Attach to specific session to debug
tmux attach -t autoflow-run-<timestamp>

# Kill stuck session
tmux kill-session -t autoflow-run-<timestamp>

# Check scheduler status
autoflow scheduler status
```

### Tasks Keep Failing

```bash
# Examine task details
autoflow task show <task-id>

# List failed tasks
autoflow task list --status failed

# Check for fix requests
autoflow review run --spec <spec> --strategy diagnostic

# Update task status manually
autoflow task update <task-id> --status todo
```

### Configuration Issues

```bash
# Validate configuration
autoflow config validate

# Show current configuration
autoflow config show

# Test agent availability
autoflow agent check all

# Check system status
autoflow status --verbose
```

### Memory and State Issues

```bash
# Check memory state
autoflow memory list --scope global

# Clear specific memory entry
autoflow memory delete <key> --scope global

# Reinitialize system
autoflow init --force
```

### CLI Issues

```bash
# Check CLI version
autoflow --version

# Verify CLI installation
python -c "from autoflow.cli import main; print('OK')"

# Test basic commands
autoflow --help
autoflow status --help
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) file for details

---

<div align="center">

**[⬆ Back to Top](#autoflow)**

Made with ❤️ by the Autoflow community

</div>
