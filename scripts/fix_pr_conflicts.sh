#!/bin/bash
set -e

# Script to resolve conflicts in all PR branches
# This resolves the same conflicts we fixed in PR4

PR_BRANCHES=(
    "auto-claude/008-automatic-rollback-and-recovery-system"
    "auto-claude/020-ai-code-quality-prediction"
    "auto-claude/021-self-healing-workflows"
)

MAIN_BRANCH="origin/main"

# Updated .gitignore content
GITIGNORE_CONTENT='# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
.venv/
venv/
ENV/
env/

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# Auto Claude
.auto-claude/
.auto-claude-security.json
.auto-claude-status
.claude_settings.json

# Autoflow local state (keep structure, ignore generated content)
.autoflow/logs/
.autoflow/memory/
.autoflow/runs/
.autoflow/worktrees/
.autoflow/discovered_agents.json
.autoflow/.DS_Store

# OS
.DS_Store
Thumbs.db

# Security
.security-key
logs/security/

# Temporary files
*.tmp
*.temp
*.log'

# Updated autoflow/review/__init__.py content
REVIEW_INIT_CONTENT='"""
Autoflow Review Module

This module provides comprehensive review functionality including:
- Review Gates: Verification and quality gates for automatic test execution
- Cross Review: Multi-agent code review capabilities
- Coverage analysis and QA findings management

Review Gates Components:
    - CoverageTracker, CoverageThreshold, CoverageReport
    - ApprovalToken, ApprovalGate, create_git_commit_message_with_approval
    - VerificationOrchestrator, VerificationResult, create_verification_report

Cross Review Components:
    - CrossReviewer: Orchestrates multi-agent review process
    - Review artifacts: Structured output for review results
    - Multiple approval strategies: consensus, majority, weighted voting

Usage:
    # Review Gates
    from autoflow.review import ApprovalGate, VerificationOrchestrator

    # Cross Review
    from autoflow.review import CrossReviewer, ReviewStrategy

    reviewer = CrossReviewer()
    result = await reviewer.review_code(
        changes=[{"file_path": "app.py", "diff": "..."}],
        author_agent="implementer"
    )
"""

from autoflow.review.coverage import (
    CoverageTracker,
    CoverageThreshold,
    CoverageReport
)
from autoflow.review.approval import (
    ApprovalToken,
    ApprovalGateConfig,
    ApprovalGate,
    create_git_commit_message_with_approval,
    extract_approval_hash_from_commit
)
from autoflow.review.verification import (
    VerificationOrchestrator,
    VerificationResult,
    VerificationConfig,
    create_verification_report
)

from autoflow.review.cross_review import (
    CodeChange,
    CrossReviewer,
    CrossReviewerError,
    CrossReviewerStats,
    CrossReviewResult,
    ReviewerConfig,
    ReviewerResult,
    ReviewFinding,
    ReviewSeverity,
    ReviewStatus,
    ReviewStrategy,
    create_cross_reviewer,
)

__all__ = [
    # Review Gates
    "CoverageTracker",
    "CoverageThreshold",
    "CoverageReport",
    "ApprovalToken",
    "ApprovalGateConfig",
    "ApprovalGate",
    "create_git_commit_message_with_approval",
    "extract_approval_hash_from_commit",
    "VerificationOrchestrator",
    "VerificationResult",
    "VerificationConfig",
    "create_verification_report",
    # Cross Review
    "CrossReviewer",
    "CrossReviewerError",
    "CrossReviewerStats",
    "create_cross_reviewer",
    "CrossReviewResult",
    "ReviewerResult",
    "ReviewFinding",
    "CodeChange",
    "ReviewerConfig",
    "ReviewStatus",
    "ReviewSeverity",
    "ReviewStrategy",
]'

echo "Starting to resolve conflicts in all PR branches..."

for branch in "${PR_BRANCHES[@]}"; do
    echo ""
    echo "=========================================="
    echo "Processing branch: $branch"
    echo "=========================================="

    # Check if worktree exists
    worktree_path="/Users/abel/dev/autoflow/.auto-claude/worktrees/tasks/${branch#auto-claude/}"

    if [ -d "$worktree_path" ]; then
        echo "Worktree exists at: $worktree_path"

        cd "$worktree_path"

        # Fetch latest changes
        echo "Fetching latest changes..."
        git fetch origin

        # Merge main into the branch
        echo "Merging main into $branch..."
        if git merge origin/main 2>&1 | grep -q "CONFLICT"; then
            echo "Conflicts detected, resolving..."

            # Resolve .gitignore
            if [ -f ".gitignore" ]; then
                echo "$GITIGNORE_CONTENT" > .gitignore
                git add .gitignore
                echo "✅ Resolved .gitignore"
            fi

            # Resolve autoflow/review/__init__.py
            if [ -f "autoflow/review/__init__.py" ]; then
                echo "$REVIEW_INIT_CONTENT" > autoflow/review/__init__.py
                git add autoflow/review/__init__.py
                echo "✅ Resolved autoflow/review/__init__.py"
            fi

            # Complete the merge
            echo "Completing merge..."
            git commit -m "Merge main into $branch

Resolved conflicts in:
- .gitignore: Use comprehensive version from main branch
- autoflow/review/__init__.py: Merge review gates and cross-review functionality

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

            # Push to remote
            echo "Pushing changes to remote..."
            git push origin "$branch"

            echo "✅ Successfully resolved conflicts in $branch"
        else
            echo "No conflicts found in $branch"
        fi

        # Return to main directory
        cd /Users/abel/dev/autoflow
    else
        echo "⚠️  Worktree not found for $branch"
    fi
done

echo ""
echo "=========================================="
echo "✅ All PR conflicts resolved!"
echo "=========================================="
