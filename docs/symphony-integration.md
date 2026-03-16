# Symphony Framework Integration

## Overview

**Symphony** is a decentralized multi-agent orchestration framework for scalable collective intelligence. Autoflow provides optional integration with Symphony, enabling you to add Symphony's multi-agent coordination capabilities to your Autoflow workflows while maintaining Autoflow's review gates and state management.

### Key Benefits

- **Multi-Agent Coordination**: Orchestrate multiple specialized AI agents working collaboratively
- **Checkpoint-Based Recovery**: Symphony's checkpoint system integrates with Autoflow's state management
- **Review Gate Integration**: Pause multi-agent workflows at review checkpoints for approval
- **Flexible Orchestration**: Choose between simple single-agent workflows or complex multi-agent coordination
- **State Synchronization**: Automatic bidirectional sync between Symphony checkpoints and Autoflow runs

## What is Symphony?

Symphony is a multi-agent framework (described in [arXiv:2508.20019](https://arxiv.org/abs/2508.20019)) that enables:

- **Role-based agent collaboration**: Multiple agents with different roles working together
- **Fault tolerance and recovery**: Checkpoint-based state management for resilience
- **Distributed task execution**: Parallel execution across multiple agent instances
- **Workflow orchestration**: Structured multi-agent workflows with dependencies

## Integration Architecture

The Autoflow-Symphony integration consists of four layers:

### 1. Agent Adapter (`autoflow/agents/symphony.py`)

Implements the `AgentAdapter` interface for Symphony:

```python
from autoflow.agents.symphony import SymphonyAdapter
from autoflow.agents.base import AgentConfig

adapter = SymphonyAdapter()
result = await adapter.execute(
    prompt="Fix the bug in app.py",
    workdir="/path/to/project",
    config=AgentConfig(command="symphony")
)
```

**Key Features:**
- Native session resume via session IDs
- Result coordination across multiple agents
- Configurable runtime (Claude or generic)
- Health checking and timeout management

### 2. Orchestrator Integration (`autoflow/core/orchestrator.py`)

The orchestrator can run Symphony workflows directly:

```python
from autoflow.core.orchestrator import AutoflowOrchestrator

orchestrator = AutoflowOrchestrator()
result = await orchestrator.run_symphony_workflow(
    workflow_name="multi-agent-analysis",
    task="Analyze the codebase architecture",
    workdir="/path/to/project"
)
```

**New Orchestrator Status:**
- `SYMPHONY_WORKFLOW`: Orchestrator is executing a Symphony workflow

### 3. Symphony Bridge (`autoflow/skills/symphony_bridge.py`)

Bidirectional integration between Symphony workflows and Autoflow skills:

```python
from autoflow.skills.symphony_bridge import SymphonyBridge
from autoflow.skills.registry import SkillRegistry

bridge = SymphonyBridge(registry=SkillRegistry())

# Register Symphony workflow as a skill
bridge.register_workflow_as_skill(
    workflow_name="code-review",
    skill_name="CODE_REVIEW"
)

# Execute workflow as skill
result = await bridge.execute_workflow_skill(
    workflow_name="code-review",
    task="Review the PR changes",
    context={"pr_number": 123}
)
```

**Bridge Capabilities:**
- **Workflow → Skill**: Invoke Symphony workflows as Autoflow skills
- **Skill → Workflow**: Execute Autoflow skills within Symphony workflows
- **State Synchronization**: Bidirectional sync between checkpoints and runs
- **Checkpoint Management**: Create, query, approve, and reject checkpoints

### 4. Review Gate Integration (`autoflow/ci/gates.py`)

Integrates Autoflow's CI review gates with Symphony checkpoints:

```python
from autoflow.ci.gates import SymphonyCheckpointGate, TestGate

# Wrap any gate with checkpoint awareness
gate = SymphonyCheckpointGate(
    wrapped_gate=TestGate(),
    checkpoint_name="pre-test-checkpoint",
    require_approval=True
)

result = gate.check(workdir="/path/to/project")
# Creates Symphony checkpoint, waits for approval if required
```

**Checkpoint Flow:**
1. Symphony workflow reaches review gate
2. `SymphonyCheckpointGate` creates checkpoint
3. Workflow pauses at checkpoint
4. Human or automated approval/rejection
5. Workflow resumes or terminates based on decision

## Configuration

### Enabling Symphony

Create `config/symphony.json5` from the example:

```bash
cp config/symphony.example.json5 config/symphony.json5
```

Edit `config/symphony.json5`:

```json5
{
  // Enable Symphony integration
  enabled: true,

  // Symphony API endpoint
  api_url: "http://localhost:8080",

  // Agent configuration
  agent: {
    command: "symphony",
    args: ["agent", "run"],
    timeout_seconds: 300,
    runtime: "claude",  // or "generic"
  },

  // Workflow configuration
  workflows: {
    workflow_dir: ".autoflow/symphony/workflows",
    checkpoint_dir: ".autoflow/symphony/checkpoints",
    enabled_workflows: [],
    auto_resume: true,
  },

  // Checkpoint integration
  checkpoints: {
    enabled: true,
    sync_with_review_gates: true,
    checkpoint_interval_seconds: 60,
    max_checkpoints: 10,
  },
}
```

### Configuration Options

#### `enabled` (boolean)
- **Default**: `false`
- **Description**: Enable or disable Symphony integration
- **Note**: When disabled, Symphony features are unavailable but Autoflow works normally

#### `api_url` (string)
- **Default**: `"http://localhost:8080"`
- **Description**: Symphony API server endpoint
- **Note**: Must match your Symphony deployment

#### `agent.command` (string)
- **Default**: `"symphony"`
- **Description**: Command to invoke Symphony CLI
- **Example**: Use full path if Symphony not in PATH: `"/usr/local/bin/symphony"`

#### `agent.args` (list of strings)
- **Default**: `["agent", "run"]`
- **Description**: Default arguments for Symphony agent execution
- **Example**: `["workflow", "execute", "--parallel"]` for workflow execution

#### `agent.timeout_seconds` (integer)
- **Default**: `300`
- **Description**: Default execution timeout in seconds
- **Range**: 60-3600 recommended

#### `agent.runtime` (string)
- **Default**: `"claude"`
- **Options**: `"claude"` or `"generic"`
- **Description**: Runtime type for Symphony agent execution

#### `workflows.workflow_dir` (string)
- **Default**: `".autoflow/symphony/workflows"`
- **Description**: Directory for Symphony workflow definitions
- **Note**: Can be absolute or relative path

#### `workflows.checkpoint_dir` (string)
- **Default**: `".autoflow/symphony/checkpoints"`
- **Description**: Directory for workflow checkpoints
- **Note**: Used for state management and recovery

#### `workflows.enabled_workflows` (list of strings)
- **Default**: `[]` (all workflows enabled)
- **Description**: Whitelist of workflow IDs to enable
- **Example**: `["code-review", "multi-agent-debug"]`

#### `workflows.auto_resume` (boolean)
- **Default**: `true`
- **Description**: Automatically resume interrupted workflows from checkpoints
- **Note**: Requires checkpoint sync enabled

#### `checkpoints.enabled` (boolean)
- **Default**: `true`
- **Description**: Enable checkpoint creation and management
- **Note**: Required for state recovery

#### `checkpoints.sync_with_review_gates` (boolean)
- **Default**: `true`
- **Description**: Create checkpoints at review gate boundaries
- **Note**: Enables pause-and-resume workflows

#### `checkpoints.checkpoint_interval_seconds` (integer)
- **Default**: `60`
- **Description**: How often to create automatic checkpoints
- **Range**: 30-600 recommended

#### `checkpoints.max_checkpoints` (integer)
- **Default**: `10`
- **Description**: Maximum number of checkpoints to retain
- **Note**: Older checkpoints are automatically cleaned up

## Usage Patterns

### Pattern 1: Simple Symphony Agent

Use Symphony as a drop-in replacement for other agents:

```python
from autoflow.agents.symphony import SymphonyAdapter
from autoflow.agents.base import AgentConfig

adapter = SymphonyAdapter()
result = await adapter.execute(
    prompt="Implement the user authentication feature",
    workdir="/path/to/project",
    config=AgentConfig(
        command="symphony",
        args=["agent", "run"],
        timeout_seconds=600
    )
)

if result.success:
    print(f"Session ID: {result.session_id}")
    print(f"Output: {result.output}")
```

### Pattern 2: Multi-Agent Workflow

Run a coordinated multi-agent workflow:

```python
from autoflow.core.orchestrator import AutoflowOrchestrator

orchestrator = AutoflowOrchestrator()

# Symphony orchestrates multiple agents internally
result = await orchestrator.run_symphony_workflow(
    workflow_name="distributed-testing",
    task="Run tests across multiple environments",
    workdir="/path/to/project",
    metadata={
        "environments": ["python3.8", "python3.9", "python3.10"],
        "parallel": True
    }
)
```

### Pattern 3: Workflow as Skill

Register Symphony workflows as reusable skills:

```python
from autoflow.skills.symphony_bridge import SymphonyBridge
from autoflow.skills.registry import SkillRegistry

registry = SkillRegistry()
bridge = SymphonyBridge(registry=registry)

# Register workflow as skill
bridge.register_workflow_as_skill(
    workflow_name="security-scan",
    skill_name="SECURITY_SCAN"
)

# Now available as a skill
skill = registry.get_skill("SECURITY_SCAN")
result = await bridge.execute_workflow_skill(
    workflow_name="security-scan",
    task="Scan for vulnerabilities",
    context={"target": "src/auth"}
)
```

### Pattern 4: Review Gate Checkpoints

Add approval checkpoints to multi-agent workflows:

```python
from autoflow.ci.gates import SymphonyCheckpointGate, TestGate, LintGate
from autoflow.ci.verifier import GateRunner

# Create checkpoint-aware gates
test_gate = SymphonyCheckpointGate(
    wrapped_gate=TestGate(),
    checkpoint_name="pre-test-checkpoint",
    require_approval=True
)

lint_gate = SymphonyCheckpointGate(
    wrapped_gate=LintGate(),
    checkpoint_name="pre-lint-checkpoint",
    require_approval=False  # Auto-approve if tests pass
)

# Runner creates checkpoints, waits for approval
runner = GateRunner(gates=[test_gate, lint_gate])
result = runner.run(workdir="/path/to/project")
```

### Pattern 5: State Synchronization

Query checkpoint status and sync with runs:

```python
from autoflow.skills.symphony_bridge import SymphonyBridge

bridge = SymphonyBridge(state_dir=".autoflow")

# Create checkpoint at gate
checkpoint_id = bridge.create_gate_checkpoint(
    gate_name="Tests",
    gate_type="test",
    workdir="/path/to/project",
    require_approval=True
)

# Wait for approval (blocking)
approved = bridge.wait_for_gate_checkpoint_approval(
    checkpoint_id=checkpoint_id,
    timeout_seconds=300
)

# Approve or reject
if approved:
    bridge.approve_gate_checkpoint(
        checkpoint_id=checkpoint_id,
        approver="human-reviewer",
        notes="All tests passed"
    )
else:
    bridge.reject_gate_checkpoint(
        checkpoint_id=checkpoint_id,
        reason="Critical tests failed",
        rejecter="human-reviewer"
    )

# Sync checkpoint to run
bridge.sync_checkpoint_to_run(
    checkpoint_id=checkpoint_id,
    run_id="run-123",
    state_dir=".autoflow"
)
```

## State Synchronization

The bridge provides bidirectional state sync:

### Checkpoint → Run

```python
# Map Symphony checkpoint to Autoflow run
bridge.sync_checkpoint_to_run(
    checkpoint_id="ckpt-abc123",
    run_id="run-456",
    state_dir=".autoflow"
)
# Stores checkpoint metadata in run.metadata["symphony_checkpoint"]
```

### Run → Checkpoint

```python
# Format run state for Symphony checkpoint
checkpoint_data = bridge.sync_run_to_checkpoint(
    run_id="run-456",
    state_dir=".autoflow"
)
# Returns dict with status, agent, timestamps, output
```

### Discovery

```python
# Find run by checkpoint ID
run = bridge.get_run_from_checkpoint(
    checkpoint_id="ckpt-abc123",
    state_dir=".autoflow"
)

# Find checkpoint by run ID
checkpoint = bridge.get_checkpoint_from_run(
    run_id="run-456",
    state_dir=".autoflow"
)
```

## Approval Flow Integration

Symphony checkpoints integrate with Autoflow's approval system:

```python
from autoflow.review.approval import ApprovalGate
from autoflow.skills.symphony_bridge import SymphonyBridge

gate = ApprovalGate()
bridge = SymphonyBridge()

# Load checkpoint for approval
checkpoint_data = bridge.load_checkpoint_for_approval(
    checkpoint_id="ckpt-abc123"
)

# Grant approval from checkpoint
token = gate.grant_approval_from_checkpoint(
    checkpoint_id="ckpt-abc123",
    bridge=bridge,
    approver="human-reviewer",
    notes="Checkpoint approved"
)

# Verify checkpoint-based approval
is_valid = gate.verify_checkpoint_approval(
    checkpoint_id="ckpt-abc123",
    token=token,
    bridge=bridge
)
```

## Checkpoint Management

### Creating Checkpoints

```python
checkpoint_id = bridge.create_gate_checkpoint(
    gate_name="Tests",
    gate_type="test",
    workdir="/path/to/project",
    require_approval=True,
    metadata={"test_suite": "pytest"}
)
```

### Querying Status

```python
status = bridge.get_gate_checkpoint_status(
    checkpoint_id="ckpt-abc123"
)
# Returns: pending, approved, or rejected
```

### Listing Checkpoints

```python
# List all checkpoints
checkpoints = bridge.list_gate_checkpoints(
    workdir="/path/to/project"
)

# Filter by gate type
test_checkpoints = bridge.list_gate_checkpoints(
    workdir="/path/to/project",
    gate_type="test"
)

# Filter by status
pending_checkpoints = bridge.list_gate_checkpoints(
    workdir="/path/to/project",
    status="pending"
)
```

### Approval/Rejection

```python
# Approve
bridge.approve_gate_checkpoint(
    checkpoint_id="ckpt-abc123",
    approver="human-reviewer",
    notes="Approved after manual review"
)

# Reject
bridge.reject_gate_checkpoint(
    checkpoint_id="ckpt-abc123",
    reason="Security vulnerability detected",
    rejecter="human-reviewer"
)
```

## When to Use Symphony

### Use Symphony When:

- **Complex Multi-Agent Tasks**: Multiple specialized agents need to collaborate
- **Fault Tolerance Required**: Checkpoint-based recovery is critical
- **Distributed Execution**: Tasks need to run across multiple environments
- **Review Gates Integration**: Want to pause workflows for approval at checkpoints
- **Stateful Workflows**: Long-running workflows with intermediate state

### Use Standard Agents When:

- **Simple Single-Agent Tasks**: One agent can complete the task
- **Fast Iteration**: Overhead of Symphony orchestration isn't needed
- **Existing Workflows**: Current agent setup works well
- **No Multi-Agent Coordination**: Task doesn't require multiple agents

## Troubleshooting

### Symphony Command Not Found

**Error**: `Command not found: symphony`

**Solution**:
1. Install Symphony CLI: `pip install symphony-framework`
2. Or set full path in config: `agent.command = "/usr/local/bin/symphony"`

### Checkpoints Not Created

**Symptom**: Checkpoints not appearing at review gates

**Solutions**:
1. Verify checkpoint sync enabled: `checkpoints.sync_with_review_gates: true`
2. Check checkpoint directory permissions
3. Verify state_dir is set in SymphonyBridge initialization

### Session Resume Fails

**Error**: `Session ID not found`

**Solutions**:
1. Verify session_id is from a previous successful execution
2. Check that workdir hasn't been deleted
3. Ensure auto_resume is enabled in config

### Approval Timeout

**Symptom**: Workflow hangs waiting for approval

**Solutions**:
1. Check checkpoint status: `bridge.get_gate_checkpoint_status(checkpoint_id)`
2. Approve manually: `bridge.approve_gate_checkpoint(checkpoint_id, ...)`
3. Increase timeout in `wait_for_gate_checkpoint_approval()`

## Advanced Topics

### Custom Workflow Definitions

Create custom Symphony workflows in `.autoflow/symphony/workflows/`:

```yaml
# .autoflow/symphony/workflows/code-review.yaml
name: code-review
agents:
  - role: reviewer
    agent: claude-code
    tasks:
      - review code for bugs
      - check style compliance
  - role: security-reviewer
    agent: symphony-security
    tasks:
      - scan for vulnerabilities
      - check dependency security
```

### Runtime Selection

Choose between Claude and generic runtimes:

```json5
{
  agent: {
    runtime: "claude",  // Best for code tasks
    // or
    runtime: "generic",  // For general-purpose agents
  }
}
```

### Parallel Execution

Configure parallel agent execution:

```python
result = await orchestrator.run_symphony_workflow(
    workflow_name="parallel-analysis",
    task="Analyze codebase",
    metadata={
        "parallel": True,
        "max_parallel_agents": 5
    }
)
```

## See Also

- [Symphony Framework Documentation](https://symphonyframework.dev)
- [Agent Adapter Reference](../autoflow/agents/symphony.py)
- [Configuration Examples](./config/symphony.example.json5)
- [Review Gate Integration](../autoflow/ci/gates.py)
- [State Management](../autoflow/core/state.py)
