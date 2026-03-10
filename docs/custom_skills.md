# Custom Skills Guide

**Autoflow Custom Skills Framework**

Complete guide to creating, validating, sharing, and managing custom skills in Autoflow.

---

## Table of Contents

- [Overview](#overview)
- [Why Custom Skills?](#why-custom-skills)
- [Skill Structure](#skill-structure)
- [Built-in Templates](#built-in-templates)
- [Creating Custom Skills](#creating-custom-skills)
- [Validating Skills](#validating-skills)
- [Sharing Skills](#sharing-skills)
- [Version Management](#version-management)
- [CLI Reference](#cli-reference)
- [Python API](#python-api)
- [Best Practices](#best-practices)
- [Examples](#examples)

---

## Overview

Autoflow's custom skills framework enables teams to create reusable, standardized workflows beyond the built-in roles. Skills define how AI agents should approach specific tasks, ensuring consistency and best practices across your organization.

### What is a Skill?

A **skill** is a structured definition that specifies:

- **Role**: What the agent does (e.g., "review code", "write specs")
- **Workflow**: Step-by-step process for the agent to follow
- **Rules**: Constraints and boundaries for agent behavior
- **Output Format**: Expected artifacts and deliverables
- **Input Requirements**: What context the agent needs

### Key Components

1. **Skill Templates**: Pre-built patterns for common skill types
2. **Skill Builder**: Interactive tool to create skills from templates
3. **Skill Validator**: Ensures skills meet structure and content requirements
4. **Skill Packager**: Export skills for sharing across teams
5. **Version Manager**: Track and manage skill versions

---

## Why Custom Skills?

### Benefits

- **Consistency**: Standardized workflows across your organization
- **Quality**: Enforced best practices and validation
- **Reusability**: Share skills between projects and teams
- **Flexibility**: Adapt Autoflow to your specific workflows
- **Maintainability**: Version tracking and safe updates

### Use Cases

- **Team-specific workflows**: Code review patterns, testing strategies
- **Domain expertise**: Industry-specific compliance checks
- **Tool integration**: Custom tool usage patterns
- **Process automation**: Repetitive task workflows
- **Quality gates**: Custom validation and review steps

---

## Skill Structure

### File Organization

```
skills/
└── my-custom-skill/
    └── SKILL.md
```

### SKILL.md Format

Skills use Markdown with YAML frontmatter:

```markdown
---
name: my-custom-skill
description: Brief description of what this skill does
---

# My Custom Skill

Human-readable title

## Role

Description of the agent's role and responsibilities

## Workflow

1. First step
2. Second step
3. Third step

## Rules

- Rule 1
- Rule 2
- Rule 3

## Output Format

- artifact1.md: Description
- artifact2.json: Description
```

### Required Sections

- **Role**: (Optional) Defines the agent's purpose
- **Workflow**: (Recommended) Step-by-step process
- **Rules**: (Optional) Constraints and boundaries
- **Output Format**: (Optional) Expected deliverables

---

## Built-in Templates

Autoflow includes three built-in templates for common skill patterns:

### 1. Planner Template

**Category**: `planning`

**Purpose**: Skills that analyze, plan, and design solutions

**Variables**:
- `name`: Skill name (uppercase, underscores)

**Use Cases**:
- Specification writers
- Task decomposition
- Architecture planning
- Risk assessment

### 2. Implementer Template

**Category**: `workflow`

**Purpose**: Skills that execute coding and implementation tasks

**Variables**:
- `name`: Skill name (uppercase, underscores)

**Use Cases**:
- Feature implementation
- Bug fixing
- Code refactoring
- Testing implementation

### 3. Reviewer Template

**Category**: `review`

**Purpose**: Skills that review, validate, and provide feedback

**Variables**:
- `name`: Skill name (uppercase, underscores)

**Use Cases**:
- Code review
- Quality assurance
- Security audit
- Performance analysis

---

## Creating Custom Skills

### Method 1: Interactive CLI (Recommended)

```bash
# Create a skill with interactive prompts
autoflow skill create
```

**Interactive Prompts**:
1. Enter skill name (e.g., `security-auditor`)
2. Select template (planner, implementer, reviewer)
3. Provide template variables
4. Confirm and create

**Example Session**:

```bash
$ autoflow skill create

Skill name: security-auditor

Available templates:
1. planner - Planning and specification skills
2. implementer - Implementation and coding skills
3. reviewer - Review and validation skills

Select template (1-3) [2]: 3

Creating skill 'security-auditor' from 'reviewer' template...
✓ Created skills/security-auditor/SKILL.md

Next steps:
1. Edit skills/security-auditor/SKILL.md to customize the skill
2. Validate: autoflow skill validate security-auditor
3. Use in agents.json: "roles": ["security-auditor"]
```

### Method 2: Non-Interactive CLI

```bash
autoflow skill create \
  --name my-custom-skill \
  --template implementer \
  --output-dir skills \
  --variable name=MY_CUSTOM_SKILL
```

**Options**:
- `--name`: Skill name (required)
- `--template`: Template to use (planner, implementer, reviewer)
- `--output-dir`: Output directory (default: skills)
- `--variable`: Template variables (key=value format, can use multiple times)
- `--overwrite`: Overwrite existing skill
- `--json`: JSON output

### Method 3: Python API

```python
from autoflow.skills import SkillBuilder, BuilderConfig

# Configure builder
config = BuilderConfig(
    skills_dir="skills",
    default_template="implementer",
    output_format="markdown"
)

# Create builder
builder = SkillBuilder(config)

# Build skill
result = builder.build(
    skill_name="my-custom-skill",
    template_name="implementer",
    variables={"name": "MY_CUSTOM_SKILL"}
)

# Check result
if result.success:
    print(f"Created: {result.skill_path}")
else:
    print(f"Error: {result.error_message}")
```

### Method 4: Manual Creation

Create the file manually:

```bash
mkdir -p skills/my-custom-skill
cat > skills/my-custom-skill/SKILL.md << 'EOF'
---
name: my-custom-skill
description: Does something specific
---

# My Custom Skill

## Workflow

1. Step one
2. Step two
EOF
```

---

## Validating Skills

### CLI Validation

```bash
# Validate a specific skill
autoflow skill validate my-custom-skill

# Validate with custom skills directory
autoflow skill validate my-custom-skill --skills-dir custom-skills

# Treat warnings as errors
autoflow skill validate my-custom-skill --strict
```

**Output**:

```
✓ Validating skill: my-custom-skill
✓ Structure validation passed
✓ Required sections present
✓ Workflow format valid

Summary:
  Errors: 0
  Warnings: 0
  Status: VALID
```

**Validation Checks**:
- ✓ File exists and is readable
- ✓ YAML frontmatter is valid
- ✓ Markdown structure is correct
- ✓ Required sections are present
- ✓ Workflow uses numbered lists
- ✓ No duplicate sections

### Python API Validation

```python
from autoflow.skills import SkillValidator, create_validator

# Create validator
validator = create_validator()

# Validate skill
result = validator.validate_path("skills/my-custom-skill")

# Check result
if result.is_valid:
    print("Skill is valid!")
else:
    print("Validation errors:")
    for error in result.errors:
        print(f"  - {error.message} (line {error.line})")

# Access validation details
print(f"Sections found: {result.present_sections}")
print(f"Errors: {len(result.errors)}")
print(f"Warnings: {len(result.warnings)}")
```

### Custom Validation Rules

```python
from autoflow.skills import SkillValidator

# Create validator with custom rules
validator = SkillValidator(
    required_sections=["Role", "Workflow", "Rules"],
    optional_sections=["Output Format", "Examples"]
)

# Validate with custom rules
result = validator.validate_path("skills/my-custom-skill")
```

---

## Sharing Skills

### Exporting Skills

**Single Skill Export**:

```bash
# Export to tar.gz (default)
autoflow skill export my-custom-skill

# Export with custom filename
autoflow skill export my-custom-skill \
  --output my-skill-v1.0.tar.gz

# Export with version metadata
autoflow skill export my-custom-skill \
  --version 1.0.0 \
  --description "Initial release"

# Export as directory (no archive)
autoflow skill export my-custom-skill \
  --format dir \
  --output ./dist/my-custom-skill
```

**Multiple Skills Export**:

```python
from autoflow.skills import SkillPackager, SkillRegistry

# Load registry
registry = SkillRegistry()
registry.load_from_directory("skills")

# Export multiple skills
packager = SkillPackager(registry)
package = packager.export_skills(
    skill_names=["skill1", "skill2", "skill3"],
    output_path="team-skills-v1.0.tar.gz",
    metadata={
        "name": "team-skills",
        "version": "1.0.0",
        "description": "Team's standard skills"
    }
)

print(f"Exported: {package.path} ({package.size} bytes)")
```

### Importing Skills

```bash
# Import from package
autoflow skill import team-skills-v1.0.tar.gz

# Import to custom directory
autoflow skill import team-skills-v1.0.tar.gz \
  --target-dir custom-skills

# Import with conflict resolution
autoflow skill import team-skills-v1.0.tar.gz \
  --conflict-resolution backup

# Conflict resolution options:
# - error: Fail on conflicts (default)
# - skip: Skip conflicting skills
# - overwrite: Overwrite existing skills
# - backup: Backup existing, then overwrite
# - rename: Rename imported skill (adds suffix)
```

**Conflict Resolution Strategies**:

1. **error** (default): Fail if any skill exists
2. **skip**: Keep existing, skip new
3. **overwrite**: Replace existing skills
4. **backup**: Backup existing before overwriting
5. **rename**: Add numeric suffix to new skill

### Python API for Sharing

```python
from autoflow.skills import SkillPackager, SkillImporter, ImportConflictResolution

# Export
packager = SkillPackager(registry)
package = packager.export_skill("my-skill", "my-skill-1.0.tar.gz")

# Import with backup
importer = SkillImporter()
result = importer.import_package(
    package_path="my-skill-1.0.tar.gz",
    target_dir="skills",
    conflict_resolution=ImportConflictResolution.BACKUP
)

print(f"Imported: {result.imported}")
print(f"Skipped: {result.skipped}")
print(f"Backups: {result.backup_paths}")
```

---

## Version Management

### Upgrading Skills

```python
from autoflow.skills import VersionManager

# Create version manager
vm = VersionManager(skill_path="skills/my-skill")

# Upgrade to new version
result = vm.upgrade(
    new_content=updated_skill_content,
    new_version="2.0.0",
    create_backup=True
)

if result.success:
    print(f"Upgraded to {result.new_version}")
    print(f"Backup: {result.backup_path}")

# View version history
history = vm.get_version_history()
for entry in history:
    print(f"{entry.timestamp}: {entry.version} ({entry.action})")
```

### Downgrading Skills

```python
# Downgrade to previous version
result = vm.downgrade(
    target_version="1.5.0",
    create_backup=True
)

if result.success:
    print(f"Downgraded to {result.current_version}")
```

### Listing Backups

```python
# List available backups
backups = vm.list_backups()
for backup in backups:
    print(f"{backup['version']}: {backup['path']}")
```

---

## CLI Reference

### `autoflow skill create`

Create a new custom skill from a template.

```bash
autoflow skill create [OPTIONS]
```

**Options**:
- `--name TEXT`: Skill name (required in non-interactive mode)
- `--template [planner|implementer|reviewer]`: Template to use
- `--output-dir PATH`: Output directory (default: skills)
- `--variable TEXT`: Template variables (key=value)
- `--overwrite`: Overwrite existing skill
- `--json`: Output in JSON format

**Examples**:

```bash
# Interactive
autoflow skill create

# Non-interactive
autoflow skill create --name my-skill --template implementer

# With variables
autoflow skill create --name my-skill --template planner \
  --variable name=MY_SKILL --variable author=Team

# JSON output
autoflow skill create --name my-skill --template implementer --json
```

### `autoflow skill validate`

Validate a skill definition.

```bash
autoflow skill validate [OPTIONS] SKILL_NAME
```

**Options**:
- `--skills-dir PATH`: Skills directory (default: skills)
- `--strict`: Treat warnings as errors
- `--json`: Output in JSON format

**Examples**:

```bash
# Validate skill
autoflow skill validate my-skill

# Strict validation
autoflow skill validate my-skill --strict

# Custom skills directory
autoflow skill validate my-skill --skills-dir custom-skills

# JSON output
autoflow skill validate my-skill --json
```

### `autoflow skill template`

Manage skill templates.

```bash
autoflow skill template list [OPTIONS]
autoflow skill template show [OPTIONS] TEMPLATE_NAME
```

**List Options**:
- `--category [workflow|review|planning|validation|custom]`: Filter by category
- `--json`: Output in JSON format

**Show Options**:
- `--json`: Output in JSON format

**Examples**:

```bash
# List all templates
autoflow skill template list

# List by category
autoflow skill template list --category workflow

# Show template details
autoflow skill template show implementer

# JSON output
autoflow skill template list --json
```

### `autoflow skill export`

Export a skill as a distributable package.

```bash
autoflow skill export [OPTIONS] NAME
```

**Options**:
- `--output PATH`: Output package path (default: <name>-<version>.tar.gz)
- `--format [tar.gz|tar|dir]`: Package format
- `--version TEXT`: Package version
- `--description TEXT`: Package description
- `--skills-dir PATH`: Skills directory
- `--json`: Output in JSON format

**Examples**:

```bash
# Export with defaults
autoflow skill export my-skill

# Export with version
autoflow skill export my-skill --version 1.0.0

# Export as directory
autoflow skill export my-skill --format dir --output ./dist

# With metadata
autoflow skill export my-skill \
  --version 2.0.0 \
  --description "Enhanced version with X feature"
```

### `autoflow skill import`

Import a skill from a package.

```bash
autoflow skill import [OPTIONS] PACKAGE
```

**Options**:
- `--target-dir PATH`: Import destination (default: skills)
- `--conflict-resolution [error|skip|overwrite|backup|rename]`: Conflict handling
- `--force`: Alias for --conflict-resolution overwrite
- `--json`: Output in JSON format

**Examples**:

```bash
# Import (fails on conflict)
autoflow skill import my-skill-1.0.tar.gz

# Import with backup
autoflow skill import my-skill-1.0.tar.gz --conflict-resolution backup

# Import and overwrite
autoflow skill import my-skill-1.0.tar.gz --force

# Import to custom directory
autoflow skill import my-skill-1.0.tar.gz --target-dir custom-skills
```

---

## Python API

### Skill Builder

```python
from autoflow.skills import SkillBuilder, BuilderConfig

# Configure
config = BuilderConfig(
    skills_dir="skills",
    default_template="implementer",
    output_format="markdown"
)

# Create builder
builder = SkillBuilder(config)

# Build skill
result = builder.build(
    skill_name="my-skill",
    template_name="implementer",
    variables={"name": "MY_SKILL"}
)

# Check result
if result.success:
    print(f"Created: {result.skill_path}")
    print(f"Warnings: {result.warnings}")
```

### Skill Validator

```python
from autoflow.skills import SkillValidator

# Create validator
validator = SkillValidator()

# Validate from file
result = validator.validate_path("skills/my-skill")

# Validate from string
content = Path("skills/my-skill/SKILL.md").read_text()
result = validator.validate_content(content)

# Check result
if result.is_valid:
    print("Valid!")
else:
    for error in result.errors:
        print(f"Error: {error.message}")
```

### Skill Packager

```python
from autoflow.skills import SkillPackager, SkillRegistry

# Setup
registry = SkillRegistry()
registry.load_from_directory("skills")
packager = SkillPackager(registry)

# Export single skill
package = packager.export_skill(
    skill_name="my-skill",
    output_path="my-skill-1.0.tar.gz",
    version="1.0.0",
    description="First release"
)

# Export multiple skills
package = packager.export_skills(
    skill_names=["skill1", "skill2"],
    output_path="skills-1.0.tar.gz",
    metadata={
        "name": "team-skills",
        "version": "1.0.0"
    }
)
```

### Skill Importer

```python
from autoflow.skills import SkillImporter, ImportConflictResolution

# Create importer
importer = SkillImporter()

# Import package
result = importer.import_package(
    package_path="skills-1.0.tar.gz",
    target_dir="skills",
    conflict_resolution=ImportConflictResolution.BACKUP
)

# Check result
print(f"Imported: {result.imported}")
print(f"Skipped: {result.skipped}")
print(f"Conflicts: {result.conflicts}")
```

### Version Manager

```python
from autoflow.skills import VersionManager

# Create manager
vm = VersionManager(skill_path="skills/my-skill")

# Upgrade
result = vm.upgrade(
    new_content=updated_content,
    new_version="2.0.0",
    create_backup=True
)

# Downgrade
result = vm.downgrade(
    target_version="1.0.0",
    create_backup=True
)

# View history
history = vm.get_version_history()
for entry in history:
    print(f"{entry.version}: {entry.action} at {entry.timestamp}")
```

---

## Best Practices

### 1. Skill Design

- **Keep it focused**: Each skill should have a single, clear purpose
- **Be specific**: Define clear boundaries and constraints
- **Use templates**: Start with built-in templates for consistency
- **Document well**: Clear descriptions and examples
- **Test thoroughly**: Validate before sharing

### 2. Workflow Structure

- **Number steps**: Use numbered lists (1., 2., 3.)
- **Be sequential**: Ensure steps follow logical order
- **Add constraints**: Use Rules section to define boundaries
- **Specify outputs**: Define expected deliverables
- **Handle errors**: Include error handling steps

### 3. Version Management

- **Semantic versioning**: Use MAJOR.MINOR.PATCH (e.g., 1.2.3)
  - MAJOR: Breaking changes
  - MINOR: New features, backward compatible
  - PATCH: Bug fixes
- **Document changes**: Maintain changelog
- **Backup before upgrade**: Always create backups
- **Test after changes**: Validate upgraded skills

### 4. Team Sharing

- **Standardize names**: Use consistent naming conventions
- **Add metadata**: Include version, description, author
- **Package related skills**: Group related skills in one package
- **Document dependencies**: Note required tools or configurations
- **Review before sharing**: Validate and test thoroughly

### 5. Validation

- **Use strict mode**: Treat warnings as errors for production skills
- **Custom rules**: Define team-specific validation rules
- **Automate**: Include validation in CI/CD pipeline
- **Fix warnings**: Address all validation issues
- **Document exceptions**: Note when warnings are acceptable

---

## Examples

### Example 1: Code Review Skill

```markdown
---
name: security-reviewer
description: Performs security-focused code review
---

# Security Reviewer

Review code for security vulnerabilities and best practices.

## Workflow

1. Read the code changes and context
2. Check for common vulnerabilities:
   - SQL injection
   - XSS vulnerabilities
   - Authentication issues
   - Authorization gaps
3. Verify security best practices:
   - Input validation
   - Output encoding
   - Encryption usage
   - Secret management
4. Generate findings with severity levels
5. Provide remediation recommendations

## Rules

- Flag any security issues regardless of severity
- Suggest specific code fixes
- Reference security standards (OWASP, CWE)
- Never approve changes with critical vulnerabilities

## Output Format

- findings.json: Structured security findings
- summary.md: Human-readable review summary
- rating: Security rating (PASS/FAIL/NEEDS_REVIEW)
```

### Example 2: Test Generator Skill

```markdown
---
name: test-generator
description: Generates comprehensive unit tests from code
---

# Test Generator

Generate unit tests for existing code to improve coverage.

## Workflow

1. Analyze the target code structure
2. Identify public functions and methods
3. Determine test cases:
   - Happy path scenarios
   - Edge cases and boundaries
   - Error conditions
4. Generate test code using framework (pytest, jest, etc.)
5. Ensure tests are:
   - Independent (no shared state)
   - Deterministic (same inputs = same outputs)
   - Fast (avoid unnecessary delays)
6. Run tests and verify they pass

## Rules

- Follow testing framework conventions
- Use descriptive test names
- Mock external dependencies
- Aim for high coverage (>80%)
- Include setup and teardown as needed

## Output Format

- test_<module>.py: Generated test file
- coverage_report.txt: Coverage metrics
- test_summary.md: Test documentation
```

### Example 3: Documentation Writer Skill

```markdown
---
name: doc-writer
description: Writes and updates technical documentation
---

# Documentation Writer

Create and maintain technical documentation for code changes.

## Workflow

1. Review code changes and understand intent
2. Identify affected documentation:
   - API docs
   - User guides
   - README files
   - Code comments
3. Update documentation:
   - Add new API endpoints/classes
   - Update examples
   - Fix outdated information
4. Ensure clarity and completeness
5. Verify links and references
6. Check for consistent style and tone

## Rules

- Write for the target audience (developers, users)
- Use clear, concise language
- Include code examples
- Update diagrams if needed
- Follow documentation style guide
- Never document undefined behavior

## Output Format

- updated_docs.md: List of changed documentation
- new_API_docs.md: New API documentation
- examples/: Updated example code
```

---

## Troubleshooting

### Skill Not Found

**Problem**: `Skill not found: my-skill`

**Solutions**:
1. Check skill directory: `ls skills/`
2. Verify skill name matches directory name
3. Check skills directory path: `--skills-dir`
4. Ensure SKILL.md exists in skill directory

### Validation Fails

**Problem**: Validation errors or warnings

**Solutions**:
1. Run with `--json` flag for detailed errors
2. Check YAML frontmatter is valid
3. Ensure required sections exist
4. Verify workflow uses numbered lists
5. Fix duplicate section names

### Import Conflicts

**Problem**: Skill already exists during import

**Solutions**:
1. Use `--conflict-resolution backup` to backup existing
2. Use `--conflict-resolution overwrite` to replace
3. Use `--conflict-resolution rename` to import with new name
4. Manually remove existing skill before import

### Template Not Found

**Problem**: `Template not found: my-template`

**Solutions**:
1. List available templates: `autoflow skill template list`
2. Use built-in template: planner, implementer, reviewer
3. Check template name spelling
4. Verify template category if using filters

---

## Additional Resources

- [Main README](../README.md) - Overview and getting started
- [Architecture Guide](architecture.md) - System architecture
- [Continuous Iteration](continuous-iteration.md) - Autonomous workflows
- [CLI Reference](../README.md#usage) - Command-line usage

---

## Getting Help

- **GitHub Issues**: Report bugs and request features
- **Documentation**: Check main README and other docs
- **Examples**: Review built-in skills in `skills/` directory
- **Community**: Share your custom skills with the community

---

<div align="center">

**[⬆ Back to Top](#custom-skills-guide)**

Made with ❤️ by the Autoflow community

</div>
