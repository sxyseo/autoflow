# Contributing to Autoflow

<div align="center">

**Thank you for your interest in contributing!**

This document provides guidelines and instructions for contributing to the Autoflow project.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

</div>

---

## Contributing

Welcome to the Autoflow contributing guide! This document contains comprehensive guidelines to help you contribute effectively to the Autoflow project.

We welcome contributions from everyone, whether you're fixing bugs, adding features, improving documentation, or simply reporting issues. This guide will walk you through everything you need to know.

---

## Table of Contents

- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Submitting Changes](#submitting-changes)
- [Reporting Issues](#reporting-issues)
- [Community Guidelines](#community-guidelines)

## Getting Started

### Prerequisites

Before contributing, ensure you have the following installed:

- **Python 3.10 or higher**: Required for running Autoflow
- **Git**: For version control
- **tmux**: For background agent execution
- **AI Agent Backend**: At least one of Claude Code, Codex, or a custom ACP-compatible agent

### Setting Up Your Development Environment

```bash
# 1. Fork the repository on GitHub
#    Click the "Fork" button in the top-right corner

# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/autoflow.git
cd autoflow

# 3. Add the upstream remote
git remote add upstream https://github.com/your-org/autoflow.git

# 4. Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# 5. Install development dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 6. Install pre-commit hooks
pre-commit install

# 7. Initialize Autoflow state directories
python3 scripts/autoflow.py init
```

### Understanding the Codebase

Autoflow is organized as a four-layer system:

1. **Control Plane** (Layer 1): State, config, memory, discovery
2. **Skills/Roles** (Layer 2): Spec-writer, task-graph-manager, implementation-runner, reviewer, maintainer
3. **Execution** (Layer 3): Spec, role, agent, prompt, workspace orchestration
4. **Governance** (Layer 4): Review gates, CI/CD, branch policy

Key directories:
- `scripts/`: Core Autoflow control scripts
- `skills/`: Skill definitions for different agent roles
- `config/`: Configuration examples and templates
- `.autoflow/`: Runtime state directory (gitignored)

## Development Workflow

### 1. Find Something to Work On

**Good First Issues**: Look for issues tagged `good first issue` or `help wanted`

**Propose Your Own**: Before starting significant work, open an issue to discuss:
- The problem you're solving
- Your proposed approach
- Potential edge cases

This ensures your work aligns with project goals and avoids duplication.

### 2. Create a Branch

```bash
# Ensure your main branch is up to date
git checkout main
git fetch upstream
git rebase upstream/main

# Create a descriptive branch
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-123-bug-description
```

**Branch naming conventions**:
- `feature/` - New features or enhancements
- `fix/` - Bug fixes
- `docs/` - Documentation improvements
- `refactor/` - Code refactoring (no functional changes)
- `test/` - Test additions or improvements
- `chore/` - Maintenance tasks, dependency updates

### 3. Make Your Changes

**Development guidelines**:
- Keep changes focused and atomic
- One logical change per commit
- Write descriptive commit messages
- Run tests frequently

**Commit message format**:
```
type(scope): brief description

Detailed explanation of the change, why it's needed,
and any relevant context.

Closes #123
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

### 4. Test Your Changes

```bash
# Run the test suite
python3 -m pytest tests/ -v

# Run with coverage
python3 -m pytest tests/ --cov=. --cov-report=html

# Run pre-commit hooks manually
pre-commit run --all-files

# Test Autoflow scripts
python3 scripts/autoflow.py validate-config
```

**Testing requirements**:
- All existing tests must pass
- New features should include tests
- Bug fixes should include regression tests
- Documentation changes should be verified

### 5. Submit Your Changes

```bash
# Push to your fork
git push origin feature/your-feature-name

# Create a pull request on GitHub
# Navigate to: https://github.com/YOUR_USERNAME/autoflow
```

## Coding Standards

### Python Code Style

We follow **PEP 8** with these specific tools:

```bash
# Format code with Black
black .

# Sort imports with isort
isort .

# Lint with flake8
flake8 .

# Type check with mypy (optional for now)
mypy .
```

**Black configuration** (pyproject.toml):
```toml
[tool.black]
line-length = 100
target-version = ['py310']
include = '\.pyi?$'
extend-exclude = '''
/(
  # directories
  \.eggs
  | \.git
  | \.hg
  | \.mypy_cache
  | \.tox
  | \.venv
  | build
  | dist
)/
'''
```

### Code Quality Guidelines

**DO**:
- Write clear, self-documenting code
- Add docstrings to functions, classes, and modules
- Use type hints for function signatures
- Keep functions focused and small (< 50 lines)
- Use descriptive variable names
- Add inline comments for complex logic

**DON'T**:
- Use single-letter variables (except loop counters)
- Write deeply nested code (> 3 levels)
- Use magic numbers or strings (define constants)
- Comment out code (remove it instead)
- Use `print()` for debugging (use logging)

### Documentation Style

**Docstring format** (Google Style):
```python
def create_worktree(spec_slug: str, force: bool = False) -> Path:
    """Create or refresh a git worktree for the specified spec.

    Args:
        spec_slug: The unique identifier for the spec.
        force: If True, rebuild the worktree even if it exists.

    Returns:
        Path to the created worktree.

    Raises:
        WorktreeError: If git worktree creation fails.
    """
    pass
```

**Markdown documentation**:
- Use ATX-style headings (`##` vs `##`)
- Include code fences with language specification
- Add tables for structured data
- Use bullet lists for options/examples
- Include TOC for long documents

### Error Handling

**Guidelines**:
- Use specific exception types
- Include helpful error messages
- Log errors before raising
- Provide context in error messages
- Use custom exceptions for domain-specific errors

```python
# Good
try:
    worktree_path = create_worktree(spec_slug)
except GitError as e:
    logger.error(f"Failed to create worktree for {spec_slug}: {e}")
    raise WorktreeError(f"Cannot initialize worktree: {e}") from e

# Avoid
try:
    worktree_path = create_worktree(spec_slug)
except:
    print("Error")
    raise
```

## Submitting Changes

### Pull Request Guidelines

**PR Title Format**:
```
type: brief description

Example:
feat: add support for custom agent protocols
fix: resolve race condition in worktree creation
docs: improve CONTRIBUTING.md with workflow examples
```

**PR Description Template**:
```markdown
## Summary
Brief description of what this PR does and why.

## Changes
- Change 1
- Change 2
- Change 3

## Testing
- [ ] Tests pass locally
- [ ] Added/updated tests for new functionality
- [ ] Manual testing performed (describe what you tested)

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review performed
- [ ] Documentation updated
- [ ] No merge conflicts
- [ ] Commit messages are clear and descriptive
- [ ] Ready for review

## Related Issues
Closes #123
Related to #456
```

### Review Process

**What to expect**:
1. **Automated checks**: CI runs tests, linting, and type checking
2. **Code review**: Maintainers review your code
3. **Feedback**: Address review comments promptly
4. **Approval**: Once approved and CI passes, your PR will be merged

**Review criteria**:
- Code quality and clarity
- Test coverage
- Documentation completeness
- Alignment with project goals
- Backward compatibility (for changes)

### Merge Policy

**When PRs are merged**:
- All automated checks pass
- At least one maintainer approves
- No unresolved conversations
- Merge conflicts resolved

**Merge methods**:
- **Squash merge**: Default for most PRs (clean history)
- **Merge commit**: For multi-author collaborative features
- **Rebase**: Rarely, only for fixing history issues

## Reporting Issues

### Bug Reports

**Before reporting**:
1. Search existing issues to avoid duplicates
2. Check if the issue is fixed in the latest version
3. Reproduce the issue reliably

**Bug report template**:
```markdown
## Bug Description
Clear and concise description of the bug.

## Steps to Reproduce
1. Step one
2. Step two
3. Step three

**Expected behavior**: What should happen
**Actual behavior**: What actually happens

## Environment
- OS: [e.g., Ubuntu 22.04, macOS 13.2]
- Python version: [e.g., 3.10.6]
- Autoflow version: [e.g., 0.1.0]
- Agent backend: [e.g., Claude Code 1.2.3]

## Logs
Relevant error messages or stack traces

## Additional Context
Screenshots, configs, or other helpful info
```

### Feature Requests

**Feature request template**:
```markdown
## Feature Description
What feature would you like and why would it be useful?

## Proposed Solution
How do you envision this feature working?

## Alternatives Considered
What other approaches did you consider?

## Additional Context
Examples, mockups, or references
```

### Security Issues

**Do NOT report security vulnerabilities publicly**

Instead, send an email to: security@your-org.com

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if known)

## Community Guidelines

### Our Pledge

We pledge to make participation in our community a harassment-free experience for everyone, regardless of:
- Age
- Body size
- Disability
- Ethnicity
- Gender identity and expression
- Level of experience
- Nationality
- Personal appearance
- Race
- Religion
- Sexual identity and orientation

### Our Standards

**Positive behavior**:
- Using welcoming and inclusive language
- Being respectful of differing viewpoints and experiences
- Gracefully accepting constructive criticism
- Focusing on what is best for the community
- Showing empathy towards other community members

**Unacceptable behavior**:
- Use of sexualized language or imagery
- Trolling, insulting/derogatory comments
- Personal or political attacks
- Public or private harassment
- Publishing others' private information without permission
- Other unethical or unprofessional conduct

### Enforcement

Project maintainers have the right and responsibility to:
- Remove, edit, or reject comments, commits, code, wiki edits, issues, and other contributions
- Contact contributors they deem inappropriate or threatening
- Ban temporarily or permanently any contributor who violates community standards

### Getting Help

**Resources**:
- **Documentation**: Start with [README.md](README.md) and existing docs
- **Issues**: Search or create GitHub issues
- **Discussions**: Use GitHub Discussions for questions
- **Discord/Slack**: Join our community chat (link in README)

**Asking good questions**:
1. Describe what you're trying to accomplish
2. Show what you've already tried
3. Include error messages or relevant code
4. Format code and logs properly
5. Follow up when you find a solution

## Recognition

Contributors are recognized in:
- [CONTRIBUTORS.md](CONTRIBUTORS.md) (if it exists)
- Release notes for significant contributions
- Project documentation for major features

All contributions are valued, whether:
- Bug fixes
- Feature implementations
- Documentation improvements
- Bug reports
- Code review
- Community support

---

## Additional Resources

- [Code of Conduct](CODE_OF_CONDUCT.md) (if it exists)
- [Security Policy](SECURITY.md) (if it exists)
- [Project Documentation](docs/)
- [API Reference](docs/api/)

---

<div align="center">

**Thank you for contributing to Autoflow! 🎉**

Every contribution, no matter how small, helps make Autoflow better for everyone.

**[⬆ Back to Top](#contributing-to-autoflow)**

Made with ❤️ by the Autoflow community

</div>
