# Agents Configuration

## Goal

Define backend AI agents that can be dispatched for different roles in the Autoflow workflow. This configuration enables:

- Mapping task roles to specific AI backends (codex, claude, acp agents, etc.)
- Configuring agent capabilities (write access, background execution)
- Setting up resume/continuation behavior for interrupted tasks
- Managing memory scopes across tasks
- Providing agent discovery for dynamic role resolution

## File location

`config/agents.json` (copy from `config/agents.example.json`)

## Configuration structure

### `defaults`

Default settings that apply to all agents unless overridden.

#### `workspace`

Default working directory for agent execution.

- **Type:** `string`
- **Default:** `"."`
- **Valid values:** Relative or absolute path
- **Purpose:** Specifies where commands will run
- **Example:** `"."` (current directory) or `"./worktrees/spec-name"`

#### `shell`

Default shell for executing commands.

- **Type:** `string`
- **Default:** `"bash"`
- **Valid values:** `"bash"`, `"zsh"`, `"sh"`, or any available shell
- **Purpose:** Shell used to run agent commands
- **Example:** `"bash"`

### `agents`

Map of agent identifiers to their configurations. Each agent represents a backend AI service that can be dispatched for tasks.

#### Agent identifier

- **Type:** `string` (key in the agents object)
- **Purpose:** Unique name for this agent configuration
- **Example:** `"codex-spec"`, `"claude-review"`, `"acp-example"`
- **Note:** Used in role mapping and agent selection

#### `protocol`

Communication protocol for the agent.

- **Type:** `string`
- **Valid values:** `"cli"` (command-line interface) or `"acp"` (Agent Communication Protocol)
- **Purpose:** Determines how Autoflow interacts with the agent
- **CLI agents:** Invoked as shell commands with arguments
- **ACP agents:** Communicate via ACP transport (stdio, HTTP, etc.)
- **Default:** None (required field)

#### `command`

Shell command to invoke the agent.

- **Type:** `string`
- **Purpose:** Executable or script to run
- **Example:** `"codex"`, `"claude"`, `"acp-agent"`
- **Default:** None (required field)

#### `args`

Command-line arguments passed to the agent.

- **Type:** `array` of `string`
- **Purpose:** Additional flags or parameters for the agent command
- **Example:** `["--full-auto"]`, `["--model", "gpt-4"]`
- **Default:** `[]` (empty array)
- **Note:** Arguments are appended to the base command

#### `model_profile`

Agent behavior profile for model selection and settings.

- **Type:** `string`
- **Valid values:** `"implementation"`, `"review"`, `"planning"`, or custom profiles
- **Purpose:** Influences model choice, temperature, and other generation parameters
- **Implementation:** Faster, more decisive models for coding tasks
- **Review:** More careful, thorough models for verification
- **Default:** None (optional field)
- **Note:** Maps to model profiles in your backend configuration

#### `tool_profile`

Tool usage profile for agents with tool restrictions or preferences.

- **Type:** `string`
- **Purpose:** Specifies which tool sets the agent can use
- **Example:** `"claude-review"` (read-only tools), `"full-access"` (all tools)
- **Default:** None (optional field)
- **Note:** Used to restrict or customize tool access for security or role-specific needs

#### `memory_scopes`

Memory scopes that this agent can access and update.

- **Type:** `array` of `string`
- **Valid values:** `"global"`, `"spec"`, `"task"`, `"run"`
- **Purpose:** Controls which shared memory contexts the agent can read/write
- **Scopes:**
  - `"global"`: Cross-spec memory (discoveries, patterns)
  - `"spec"`: Spec-specific memory (task context, decisions)
  - `"task"`: Task-specific memory (implementation notes)
  - `"run"`: Single execution run (ephemeral)
- **Default:** `[]` (no memory access)
- **Example:** `["global", "spec"]` for agents that need context across tasks

#### `resume`

Configuration for resuming interrupted or continued sessions.

- **Type:** `object`
- **Purpose:** Defines how to reconnect to an existing agent session
- **Note:** Optional but highly recommended for robust task execution

##### `resume.mode`

Resume strategy type.

- **Type:** `string`
- **Valid values:** `"subcommand"`, `"args"`, `"none"`
- **Purpose:** How to construct the resume command
- **Subcommand:** Uses a separate subcommand (e.g., `codex resume --last`)
- **Args:** Appends resume arguments to the base command
- **None:** No resume capability (agent starts fresh each time)
- **Default:** `"none"`

##### `resume.subcommand`

Subcommand for resume when `mode` is `"subcommand"`.

- **Type:** `string`
- **Purpose:** Subcommand name for resuming
- **Example:** `"resume"` (for `codex resume --last`)
- **Default:** None (required when `mode` is `"subcommand"`)

##### `resume.args`

Arguments for resume command.

- **Type:** `array` of `string`
- **Purpose:** Arguments passed to the resume command or appended to base command
- **Example:** `["--last"]`, `["--continue"]`, `["--session", "12345"]`
- **Default:** `[]`

#### `transport` (ACP protocol only)

Transport configuration for ACP agents.

- **Type:** `object`
- **Purpose:** Defines how to communicate with ACP agents
- **Required for:** `protocol: "acp"`

##### `transport.type`

Transport mechanism.

- **Type:** `string`
- **Valid values:** `"stdio"`, `"http"`, `"websocket"`
- **Purpose:** Communication channel type
- **Stdio:** Standard input/output (most common for local agents)
- **Http:** REST API over HTTP
- **Websocket:** WebSocket connection
- **Default:** None (required for ACP agents)

##### `transport.command`

Command to invoke for stdio transport.

- **Type:** `string`
- **Purpose:** Executable that speaks ACP protocol
- **Example:** `"acp-agent"`, `"python -m my_agent"`
- **Default:** None (required for stdio transport)

##### `transport.args`

Arguments for the transport command.

- **Type:** `array` of `string`
- **Purpose:** Additional parameters for the transport command
- **Example:** `["--port", "8080"]`, `["--config", "agent.yaml"]`
- **Default:** `[]`

##### `transport.prompt_mode`

How prompts are delivered to the agent.

- **Type:** `string`
- **Valid values:** `"argv"`, `"stdin"`, `"file"`
- **Purpose:** Method for sending the initial task prompt
- **Argv:** Prompt passed as command-line argument
- **Stdin:** Prompt written to standard input
- **File:** Prompt written to a temporary file, path passed as argument
- **Default:** `"argv"`

#### `supports_write`

Whether the agent can modify files.

- **Type:** `boolean`
- **Purpose:** Indicates if agent has write access to the workspace
- **true:** Agent can read and write files
- **false:** Agent is read-only (suitable for review tasks)
- **Default:** `false`
- **Note:** Used for safety checks and role assignment

#### `supports_background`

Whether the agent can run in background mode.

- **Type:** `boolean`
- **Purpose:** Indicates if agent supports asynchronous execution
- **true:** Agent can be started and checked later
- **false:** Agent requires synchronous, blocking execution
- **Default:** `false`
- **Note:** Affects dispatch strategy in continuous iteration loops

## Usage examples

### Basic CLI agent with resume capability

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
      },
      "supports_write": true,
      "supports_background": true
    }
  }
}
```

### Read-only review agent

```json
{
  "agents": {
    "claude-review": {
      "protocol": "cli",
      "command": "claude",
      "args": [],
      "model_profile": "review",
      "tool_profile": "claude-review",
      "memory_scopes": ["spec"],
      "resume": {
        "mode": "args",
        "args": ["--continue"]
      },
      "supports_write": false,
      "supports_background": true
    }
  }
}
```

### ACP agent with stdio transport

```json
{
  "agents": {
    "acp-example": {
      "protocol": "acp",
      "command": "acp-agent",
      "args": [],
      "transport": {
        "type": "stdio",
        "command": "acp-agent",
        "args": [],
        "prompt_mode": "argv"
      },
      "supports_write": true,
      "supports_background": true
    }
  }
}
```

### Minimal agent configuration

```json
{
  "agents": {
    "simple-runner": {
      "protocol": "cli",
      "command": "python",
      "args": ["-m", "my_agent"],
      "supports_write": true,
      "supports_background": false
    }
  }
}
```

## Field interactions

### Resume and protocol

- **CLI agents:** Use `resume.mode` to define continuation strategy
- **ACP agents:** Resume handled by protocol itself, `resume` config may be ignored

### Memory scopes and roles

- **Spec-level roles** (spec writer, impl lead): Use `["global", "spec"]` for cross-task context
- **Task-level roles** (implementer, tester): Use `["spec", "task"]` for task isolation
- **Review roles:** Use `["spec"]` to access task context without modifying it

### Model and tool profiles

- **model_profile** affects generation behavior (creativity, verbosity)
- **tool_profile** affects available capabilities (file access, API calls)
- Combine to create specialized agents:
  - High creativity + full tools = Brainstorming agent
  - Low creativity + read-only tools = Verification agent
  - Medium creativity + write tools = Implementation agent

### Supports flags and dispatch

- `supports_background: true` enables async dispatch in continuous iteration
- `supports_write: false` prevents assignment to implementation roles
- Both flags are checked during role-agent matching

## Agent discovery

Autoflow can automatically discover CLI agents from your environment:

1. Checks for `codex`, `claude`, and other known commands
2. Merges discovered agents with explicit config (config takes precedence)
3. Discovered agents use conservative defaults (no write, no background)
4. Synchronized to `.autoflow/agents.json` for inspection

Discovered agents act as fallbacks when explicit agents are unavailable, following `agent_selection.role_preferences` in continuous iteration config.

## Best practices

- **Use descriptive agent IDs** that indicate role (e.g., `codex-impl`, `claude-review`)
- **Enable resume capability** for all long-running agents
- **Restrict write access** for review and planning roles
- **Enable background mode** for agents used in scheduled loops
- **Set appropriate memory scopes** based on role context needs
- **Test resume behavior** before using in production workflows
- **Document custom model profiles** in your backend configuration
- **Use tool profiles** to enforce role-based access control
- **Keep agent commands simple** (wrapper scripts work better than complex command chains)
- **Verify agent availability** before referencing in role configurations
