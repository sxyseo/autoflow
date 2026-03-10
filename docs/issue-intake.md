# Issue Intake System

## Goal

Ingest issues from external sources (GitHub Issues, GitLab, Linear) and automatically convert them into Autoflow specs and tasks. Provide bidirectional synchronization so external issue trackers reflect the current state of work in Autoflow.

## Architecture

The intake system consists of several layered components:

### Data Models (`autoflow/intake/models.py`)

- **IssueSource**: Represents an external issue source (GitHub repo, GitLab project, Linear workspace)
- **Issue**: Normalized issue model that abstracts differences between source systems
- **Enums**: `SourceType`, `IssueStatus`, `IssuePriority` for consistent representation

### Label Mapping (`autoflow/intake/mapping.py`)

- **LabelMapping**: Maps source labels to Autoflow priorities and categories
- **IssueTransformer**: Converts source-specific issue data to normalized `Issue` objects
  - `from_github()`: GitHub issue → Issue
  - `from_gitlab()`: GitLab issue → Issue
  - `from_linear()`: Linear issue → Issue

### API Clients (`autoflow/intake/client.py`, `*_client.py`)

- **IssueClient** (base): Abstract interface for fetching and updating issues
- **GitHubClient**: GitHub API integration
- **GitLabClient**: GitLab API integration
- **LinearClient**: Linear API integration

### Ingestion Pipeline (`autoflow/intake/pipeline.py`)

- **IntakePipeline**: Orchestrates fetching, transforming, converting, and storing issues
  - `ingest_all()`: Process all configured sources
  - `ingest_from_source()`: Process single source
  - `process_webhook()`: Handle webhook events

### Issue Converter (`autoflow/intake/converter.py`)

- **IssueConverter**: Transforms normalized Issues into Autoflow Specs and Tasks
  - Preserves issue metadata as task properties
  - Extracts priority and category from labels
  - Maintains source URL for traceability

### Sync Manager (`autoflow/intake/sync.py`)

- **SyncManager**: Bidirectional synchronization between Autoflow and external sources
  - Tracks task-issue mappings
  - Pushes task status updates back to sources
  - Pulls issue updates into tasks
  - Maintains sync history and statistics

## Workflow

### Initial Ingestion

1. Configure issue sources in `config/intake.json5`
2. Run import: `autoflow intake import --mode full`
3. Pipeline fetches issues from all enabled sources
4. Issues are transformed to normalized `Issue` objects
5. Converter creates Specs and Tasks from issues
6. Sync manager tracks mappings between tasks and external issues

### Webhook Processing

1. Configure webhook URL in external source settings
2. Start webhook server: `autoflow intake webhook`
3. External source sends webhook on issue events
4. Pipeline validates signature and processes event
5. Corresponding task is updated or created

### Bidirectional Sync

1. Run sync: `autoflow intake sync --direction push`
2. Sync manager reads task state changes
3. Updates are pushed to external issues (status, comments)
4. Optionally pull external changes back to tasks
5. Sync mappings and history are updated

## Configuration

Create `config/intake.json5` based on `config/intake.example.json5`:

```json5
{
  sources: [
    {
      id: "github-main",
      type: "github",
      name: "owner/repo",
      url: "https://github.com/owner/repo",
      enabled: true,
      config: {
        token: "ghp_xxx",
        // Optional: webhook secret for signature verification
        webhook_secret: "webhook_secret_value",
      }
    },
    {
      id: "gitlab-project",
      type: "gitlab",
      name: "group/project",
      url: "https://gitlab.com/group/project",
      enabled: true,
      config: {
        token: "glpat-xxx",
      }
    },
    {
      id: "linear-workspace",
      type: "linear",
      name: "My Workspace",
      url: "https://linear.app/workspace",
      enabled: true,
      config: {
        token: "lin_api_xxx",
      }
    }
  ],

  // Global settings
  sync: {
    auto_sync: false,
    sync_comments: true,
    sync_status: true,
    sync_labels: true,
    direction: "push",  // "push", "pull", or "bidirectional"
  },

  pipeline: {
    create_specs: true,
    create_tasks: true,
    filter_closed: false,
    filter_labels: ["bug", "feature"],  // Only ingest issues with these labels
  }
}
```

## Label Mapping

Configure custom label mappings by setting environment variables or extending the default mapping:

```python
from autoflow.intake.mapping import LabelMapping, LabelRule
from autoflow.intake.models import IssuePriority

mapping = LabelMapping(
    priority_rules=[
        LabelRule(pattern="p0", priority=IssuePriority.URGENT),
        LabelRule(pattern="p1", priority=IssuePriority.HIGH),
        LabelRule(pattern="p2", priority=IssuePriority.MEDIUM),
    ],
    category_rules=[
        LabelRule(pattern="feat.*", category="feature", is_regex=true),
        LabelRule(pattern="fix.*", category="bug", is_regex=true),
    ]
)
```

## CLI Commands

### Import Issues

```bash
# Import all issues from all sources
autoflow intake import

# Import only from specific sources
autoflow intake import --sources github-main,gitlab-project

# Import mode: full (all), incremental (new/updated since last), since-last
autoflow intake import --mode incremental

# Dry run (don't actually create specs/tasks)
autoflow intake import --dry-run

# JSON output for automation
autoflow intake import --json
```

### Sync Issues

```bash
# Push task updates to external sources
autoflow intake sync --direction push

# Pull external changes into tasks
autoflow intake sync --direction pull

# Bidirectional sync
autoflow intake sync --direction bidirectional

# Sync specific tasks
autoflow intake sync --tasks task-001,task-002

# Dry run
autoflow intake sync --dry-run
```

### Webhook Server

```bash
# Start webhook server (default: localhost:8000/webhooks)
autoflow intake webhook

# Custom host and port
autoflow intake webhook --host 0.0.0.0 --port 3000

# Custom path
autoflow intake webhook --path /issue-events

# Disable signature verification (not recommended for production)
autoflow intake webhook --no-verify
```

### Status and Diagnostics

```bash
# Show intake status and statistics
autoflow intake status

# Show details for specific source
autoflow intake status --source github-main

# JSON output
autoflow intake status --json
```

## Data Flow

```
External Source (GitHub/GitLab/Linear)
    ↓
API Client (fetch_issue, list_issues)
    ↓
IssueTransformer (normalize to Issue model)
    ↓
IssueConverter (Issue → Spec + Task)
    ↓
StateManager (persist specs/tasks)
    ↓
SyncManager (track mappings)
    ↓
External Source (update_issue, create_comment)
```

## State Storage

The intake system maintains state in `.auto-claude/state/`:

- `sync_mappings.json`: Task-to-issue mappings
- `sync_history/`: Sync operation history
- Issue metadata is stored in task `metadata` field:
  - `source_id`: External issue ID
  - `source_type`: github, gitlab, or linear
  - `source_url`: Link to external issue
  - `last_sync_at`: Timestamp of last sync

## Label to Status/Priority Mapping

### GitHub Labels

- `urgent`, `critical` → URGENT priority
- `high`, `priority:high` → HIGH priority
- `medium`, `priority:medium` → MEDIUM priority
- `low`, `priority:low` → LOW priority
- `bug`, `bug:*` → Category: bug
- `feature`, `enhancement` → Category: feature
- `docs`, `documentation` → Category: documentation

### GitLab Labels

Same as GitHub, uses comma-separated label array

### Linear Priorities

- `urgent` → URGENT priority
- `high` → HIGH priority
- `medium` → MEDIUM priority
- `low` → LOW priority
- `none` → NO_PRIORITY priority

## Webhook Configuration

### GitHub

1. Go to repo Settings → Webhooks → Add webhook
2. Payload URL: `https://your-domain.com/webhooks`
3. Content type: `application/json`
4. Secret: Set webhook secret in source config
5. Events: Issues, Issue comments

### GitLab

1. Go to project Settings → Webhooks
2. URL: `https://your-domain.com/webhooks`
3. Secret token: Set webhook secret in source config
4. Trigger: Issues events

### Linear

1. Go to workspace Settings → API → Webhooks
2. URL: `https://your-domain.com/webhooks`
3. Events: Issue created, Issue updated

## Important Rules

### Do Not Duplicate Work

Check if an issue has already been ingested by examining the `source_id` in task metadata. The pipeline should be idempotent - running import multiple times should not create duplicate tasks.

### Preserve Source Context

Always maintain the `source_url` in task metadata so users can navigate back to the original issue. Include issue comments in task context to preserve discussion history.

### Sync Direction Matters

- **Push mode**: Autoflow is the source of truth. Task changes update external issues.
- **Pull mode**: External tracker is source of truth. Issue updates modify tasks.
- **Bidirectional**: Both systems can make changes. Last write wins on conflicts.

### Handle Rate Limiting

API clients respect rate limits and retry with exponential backoff. Configure `retry_attempts` and `retry_delay_seconds` in source config to adjust behavior.

### Webhook Security

Always verify webhook signatures in production. Use `webhook_secret` in source config to validate incoming requests.

### Error Recovery

The pipeline continues processing even if individual issues fail. Failed issues are logged in the result errors array. Check logs and retry failed syncs individually.

## Testing

```bash
# Run intake tests
pytest tests/test_intake_models.py -v
pytest tests/test_intake_mapping.py -v
pytest tests/test_intake_converter.py -v
pytest tests/test_intake_clients.py -v
pytest tests/test_intake_sync.py -v

# Test with dry-run first
autoflow intake import --dry-run --json
```

## Troubleshooting

### Import creates no tasks

- Check source is `enabled: true`
- Verify API token has read permissions
- Check filter labels don't exclude all issues
- Use `--dry-run --json` to see what would be imported

### Sync fails to update external issues

- Verify token has write permissions
- Check webhook secret matches (if using webhooks)
- Test with `autoflow intake sync --dry-run`
- Review sync errors in status output

### Webhook not processing

- Verify webhook URL is accessible from external service
- Check signature verification (disable with `--no-verify` for testing)
- Review webhook server logs for errors
- Test webhook payload manually

### Duplicate tasks created

- Check if `source_id` is being set correctly
- Ensure incremental mode is working (last_sync_at in metadata)
- Review converter logic for deduplication
