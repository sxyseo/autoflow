# System Configuration

## Goal

Define global system-wide settings that affect how Autoflow manages memory, model selection, tool access, and agent discovery. This configuration enables:

- Centralized model and tool profile definitions
- Persistent memory management across tasks and specs
- ACP agent registration for discovery
- Default behaviors for all agents and workflows

## File location

`config/system.json` (copy from `config/system.example.json`)

## Configuration structure

### `memory`

Global memory system configuration that controls how Autoflow stores and retrieves contextual information across tasks and spec runs.

#### `memory.enabled`

Whether the memory system is active.

- **Type:** `boolean`
- **Default:** `true`
- **Purpose:** Master switch for memory functionality
- **true:** Memory system captures and retrieves context
- **false:** All memory functions return early with minimal state
- **Example:** `true`

#### `memory.auto_capture_run_results`

Whether to automatically capture task run results to memory.

- **Type:** `boolean`
- **Default:** `true`
- **Purpose:** Automatically store execution outcomes without explicit calls
- **true:** Run results are written to spec memory after each task
- **false:** Memory must be manually updated via explicit calls
- **Example:** `true`

#### `memory.default_scopes`

Default memory scopes to use when loading context.

- **Type:** `array` of `string`
- **Default:** `["spec"]`
- **Valid values:** Combination of `"global"`, `"spec"`, `"task"`, `"run"`
- **Purpose:** Controls which memory layers are loaded by default
- **Scopes:**
  - `"global"`: Cross-spec discoveries, patterns, and learnings
  - `"spec"`: Spec-specific context, decisions, and task history
  - `"task"`: Individual task notes and implementation details
  - `"run"`: Single execution run (ephemeral, rarely persisted)
- **Example:** `["global", "spec"]` for agents that need broad context
- **Note:** Agents can override this with their own `memory_scopes` configuration

#### `memory.global_file`

Path to the global memory file.

- **Type:** `string`
- **Default:** `".autoflow/memory/global.md"`
- **Purpose:** Stores cross-spec discoveries and reusable patterns
- **Valid values:** Relative or absolute file path
- **Example:** `".autoflow/memory/global.md"`
- **Note:** Directory will be created if it doesn't exist

#### `memory.spec_dir`

Path to the directory containing spec-specific memory files.

- **Type:** `string`
- **Default:** `".autoflow/memory/specs"`
- **Purpose:** Directory where individual spec memory files are stored
- **Valid values:** Relative or absolute directory path
- **Example:** `".autoflow/memory/specs"`
- **File naming:** Each spec gets a file named `{spec_slug}.md`
- **Note:** Directory will be created if it doesn't exist

### `models`

Model profile definitions that map logical profile names to concrete model identifiers.

#### `models.profiles`

Map of profile names to model identifiers.

- **Type:** `object` (string → string mapping)
- **Purpose:** Define reusable model configurations by role
- **Profile names:** Logical identifiers (e.g., `"spec"`, `"implementation"`, `"review"`)
- **Model identifiers:** Backend-specific model names (e.g., `"gpt-5"`, `"claude-sonnet-4-6"`)
- **Example:** `{"spec": "gpt-5", "implementation": "gpt-5-codex", "review": "claude-sonnet-4-6"}`
- **Used by:** Agent configurations via `model_profile` field
- **Resolution:** When an agent specifies `model_profile`, the corresponding model ID is looked up here

**Common profile names:**

- `"spec"`: Model for writing specs and planning (balanced creativity/precision)
- `"implementation"`: Model for coding tasks (fast, decisive)
- `"review"`: Model for verification and QA (thorough, careful)
- `"planning"`: Model for architectural decisions (high reasoning)
- `"testing"`: Model for test generation (detail-oriented)

**Model identifier examples:**

- `"gpt-5"`: Generic GPT-5 model
- `"gpt-5-codex"`: GPT-5 optimized for code
- `"claude-sonnet-4-6"`: Anthropic Claude Sonnet 4.6
- `"claude-opus-4"`: Anthropic Claude Opus 4
- `"o3-preview"`: OpenAI o3-preview

### `tools`

Tool profile definitions that map logical profile names to tool access lists.

#### `tools.profiles`

Map of profile names to tool configurations.

- **Type:** `object` (string → array mapping)
- **Purpose:** Define reusable tool access patterns by role
- **Profile names:** Logical identifiers (e.g., `"codex-default"`, `"claude-review"`)
- **Tool configurations:** Array of tool names or tool patterns
- **Example:** `{"codex-default": [], "claude-review": ["Read", "Bash(git:*)"]}`
- **Used by:** Agent configurations via `tool_profile` field
- **Resolution:** When an agent specifies `tool_profile`, the corresponding tool list is used

**Tool format:**

- **Simple tool name:** `"Read"` grants access to that tool
- **Pattern restriction:** `"Bash(git:*)"` restricts Bash tool to git commands only
- **Full access:** Empty array `[]` means no restrictions (all tools available)

**Common profile names:**

- `"codex-default"`: Default tool access for codex agents (usually unrestricted)
- `"claude-review"`: Read-only tools for review (no write access)
- `"full-access"`: All tools enabled
- `"read-only"`: Only read operations (Read, Grep, Glob)
- `"testing"`: Tools for test generation and execution

**Tool examples:**

```json
["Read", "Grep", "Glob"]           // Read-only access
["Read", "Write", "Edit"]          // File modification
["Bash(git:*)", "Read"]            // Git commands + read
[]                                 // All tools (unrestricted)
```

### `registry`

Agent discovery registry for ACP (Agent Communication Protocol) agents.

#### `registry.acp_agents`

List of ACP agent definitions for discovery and registration.

- **Type:** `array` of `object`
- **Purpose:** Register custom ACP agents for automatic discovery
- **Discovery:** These agents are merged with CLI-discovered agents in `.autoflow/agents.json`
- **Fallback:** Used when no explicit agent configuration matches a role
- **Example:** See below

##### Agent object

Each agent in the `acp_agents` array defines an ACP agent for discovery.

###### `name`

- **Type:** `string`
- **Purpose:** Unique identifier for this agent
- **Example:** `"example-acp-agent"`, `"my-custom-processor"`
- **Used by:** Agent discovery to identify and reference the agent

###### `transport`

Transport configuration defining how to communicate with the agent.

- **Type:** `object`
- **Purpose:** Specifies communication mechanism and connection details
- **Required:** Yes

###### `transport.type`

Transport mechanism type.

- **Type:** `string`
- **Valid values:** `"stdio"`, `"http"`, `"websocket"`
- **Purpose:** Communication channel protocol
- **stdio:** Standard input/output (most common for local agents)
- **http:** REST API over HTTP
- **websocket:** WebSocket connection
- **Default:** None (required field)
- **Example:** `"stdio"`

###### `transport.command`

Command to invoke for stdio transport.

- **Type:** `string`
- **Purpose:** Executable that speaks ACP protocol
- **Example:** `"acp-agent"`, `"python -m my_agent"`, `"/usr/local/bin/custom-agent"`
- **Default:** None (required for stdio transport)
- **Note:** For http/websocket, this would be the base URL

###### `transport.args`

Arguments for the transport command.

- **Type:** `array` of `string`
- **Purpose:** Additional parameters for the transport command
- **Example:** `["--port", "8080"]`, `["--config", "agent.yaml"]`, `["--debug"]`
- **Default:** `[]` (empty array)

###### `transport.prompt_mode`

How prompts are delivered to the agent.

- **Type:** `string`
- **Valid values:** `"argv"`, `"stdin"`, `"file"`
- **Purpose:** Method for sending the initial task prompt
- **argv:** Prompt passed as command-line argument
- **stdin:** Prompt written to standard input
- **file:** Prompt written to a temporary file, path passed as argument
- **Default:** `"argv"`

###### `capabilities`

Agent capability flags.

- **Type:** `object`
- **Purpose:** Declare agent features for discovery and matching
- **Optional:** Yes (defaults to empty object)

###### `capabilities.resume`

Whether the agent supports resuming interrupted sessions.

- **Type:** `boolean`
- **Purpose:** Indicates if agent can reconnect to existing sessions
- **true:** Agent can resume from previous state
- **false:** Agent starts fresh each time
- **Default:** `false`
- **Note:** Affects whether resume logic is attempted

###### `capabilities.task_driven`

Whether the agent uses task-driven execution.

- **Type:** `boolean`
- **Purpose:** Indicates if agent expects task-based prompts
- **true:** Agent designed for task-oriented workflows
- **false:** Agent uses conversational interaction
- **Default:** `true`

## Usage examples

### Minimal system configuration

```json
{
  "memory": {
    "enabled": true,
    "auto_capture_run_results": true,
    "default_scopes": ["spec"],
    "global_file": ".autoflow/memory/global.md",
    "spec_dir": ".autoflow/memory/specs"
  },
  "models": {
    "profiles": {
      "implementation": "gpt-5-codex",
      "review": "claude-sonnet-4-6"
    }
  },
  "tools": {
    "profiles": {
      "codex-default": [],
      "claude-review": ["Read", "Bash(git:*)"]
    }
  },
  "registry": {
    "acp_agents": []
  }
}
```

### Production-ready configuration with custom ACP agents

```json
{
  "memory": {
    "enabled": true,
    "auto_capture_run_results": true,
    "default_scopes": ["global", "spec"],
    "global_file": ".autoflow/memory/global.md",
    "spec_dir": ".autoflow/memory/specs"
  },
  "models": {
    "profiles": {
      "spec": "gpt-5",
      "implementation": "gpt-5-codex",
      "review": "claude-sonnet-4-6",
      "planning": "o3-preview",
      "testing": "gpt-5"
    }
  },
  "tools": {
    "profiles": {
      "codex-default": [],
      "claude-review": ["Read", "Bash(git:*)"],
      "read-only": ["Read", "Grep", "Glob"],
      "full-access": []
    }
  },
  "registry": {
    "acp_agents": [
      {
        "name": "custom-processor",
        "transport": {
          "type": "stdio",
          "command": "python",
          "args": ["-m", "my_agent.agent"],
          "prompt_mode": "argv"
        },
        "capabilities": {
          "resume": true,
          "task_driven": true
        }
      },
      {
        "name": "http-agent",
        "transport": {
          "type": "http",
          "command": "http://localhost:8080",
          "args": [],
          "prompt_mode": "argv"
        },
        "capabilities": {
          "resume": false,
          "task_driven": true
        }
      }
    ]
  }
}
```

### Memory-disabled configuration

```json
{
  "memory": {
    "enabled": false,
    "auto_capture_run_results": false,
    "default_scopes": ["spec"],
    "global_file": ".autoflow/memory/global.md",
    "spec_dir": ".autoflow/memory/specs"
  },
  "models": {
    "profiles": {
      "implementation": "gpt-5-codex"
    }
  },
  "tools": {
    "profiles": {}
  },
  "registry": {
    "acp_agents": []
  }
}
```

## Field interactions

### Memory scopes and agent configuration

- **System defaults:** `memory.default_scopes` provides fallback when agent doesn't specify scopes
- **Agent override:** Agent `memory_scopes` takes precedence over system defaults
- **Context loading:** `load_memory_context()` merges requested scopes in order (global, spec, task, run)
- **Isolation:** Different scopes enable different isolation levels for security and context separation

### Model profiles and agent configuration

- **Resolution flow:**
  1. Agent specifies `model_profile: "implementation"`
  2. System looks up `models.profiles.implementation`
  3. Returns model ID (e.g., `"gpt-5-codex"`)
  4. Model ID is passed to backend agent
- **Fallback:** If profile not found, empty string is returned (backend uses default)
- **Backend-specific:** Model IDs are passed directly to the agent backend (codex, claude, etc.)
- **Centralization:** Define once in system config, reference from many agents

### Tool profiles and agent configuration

- **Resolution flow:**
  1. Agent specifies `tool_profile: "claude-review"`
  2. System looks up `tools.profiles.claude-review`
  3. Returns tool list (e.g., `["Read", "Bash(git:*)"]`)
  4. Tool list is passed to backend agent
- **Fallback:** If profile not found, empty array is returned (all tools available)
- **Security:** Use restrictive profiles for review or planning roles
- **Flexibility:** Define different tool sets for different workflow phases

### Registry and agent discovery

- **Discovery process:**
  1. CLI agents (codex, claude) are auto-discovered
  2. ACP agents from `registry.acp_agents` are added
  3. All agents written to `.autoflow/agents.json`
  4. Agent selection uses discovered agents as fallbacks
- **Capabilities:** Resume and task_driven flags affect selection logic
- **Fallback:** Discovered agents used when explicit agents unavailable
- **Synchronization:** Registry is synced on each continuous iteration loop

### Auto-capture and workflow

- **When enabled:** Run results automatically stored after task completion
- **When disabled:** Must manually call memory append functions
- **Integration:** Works with continuous iteration loop's commit behavior
- **Scope:** Uses spec-level memory for run results

## File paths and defaults

### Memory file paths

| Component | Default | Override location |
|-----------|---------|-------------------|
| Global file | `.autoflow/memory/global.md` | `memory.global_file` |
| Spec directory | `.autoflow/memory/specs` | `memory.spec_dir` |
| Spec files | `{spec_dir}/{spec_slug}.md` | Automatic |

### Profile resolution

| Profile type | Default if not found | Used by |
|--------------|---------------------|---------|
| Model | Empty string (backend default) | Agent `model_profile` |
| Tools | Empty array (all tools) | Agent `tool_profile` |

## Best practices

### Memory configuration

- **Enable memory for production** to accumulate learnings across tasks
- **Use global scope sparingly** for truly reusable discoveries
- **Prefer spec scope** for most context to keep specs self-contained
- **Set appropriate default_scopes** based on your typical workflow
- **Keep auto_capture enabled** unless you need manual control over what's stored

### Model profiles

- **Name profiles by role** not by model (e.g., "implementation" not "gpt-5")
- **Create separate profiles for different workflow phases**
- **Match model capabilities to role requirements** (creativity for planning, precision for review)
- **Document backend-specific model names** in comments
- **Use consistent profile names** across agents and specs

### Tool profiles

- **Create restrictive profiles for review roles** (read-only)
- **Use pattern restrictions** for sensitive operations (e.g., `Bash(git:*)`)
- **Empty array means unrestricted** (use carefully)
- **Test tool profiles** with actual agent before production use
- **Document permission boundaries** clearly in profile names

### Registry and ACP agents

- **Register custom agents** that aren't discoverable via CLI
- **Use capabilities flags** to help agent selection logic
- **Test transport configuration** before adding to registry
- **Document agent purpose** in the name field
- **Keep args minimal** (prefer config files over complex command lines)

### General configuration

- **Version control your system.json** to track configuration changes
- **Document custom profiles** in comments (convert to .md for notes)
- **Test configuration changes** in isolation before production
- **Use descriptive profile names** that indicate purpose
- **Keep backups of working configurations** before major changes
- **Review default_scopes** when workflow patterns change

## Troubleshooting

### Memory not working

- Check `memory.enabled` is `true`
- Verify file paths are writable
- Check directory permissions for `.autoflow/memory/`
- Confirm agent has appropriate `memory_scopes` configured

### Model not recognized

- Verify model ID is valid for your backend
- Check profile name in agent config matches system config
- Ensure system.json is loaded (no syntax errors)
- Test model ID directly with backend CLI

### Tool access denied

- Review tool profile for syntax errors
- Check if tool names match backend's available tools
- Verify pattern restrictions (e.g., `Bash(git:*)`) are correct
- Test agent with unrestricted profile first

### ACP agent not discovered

- Verify transport command is executable
- Check prompt_mode matches agent's expectations
- Test agent manually with example prompt
- Review `.autoflow/agents.json` for discovery errors
- Check agent logs for protocol errors
