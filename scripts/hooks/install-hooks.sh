#!/bin/bash

#############################################
# Git Hooks Installation Script
#
# Automatically installs Autoflow git hooks
# (pre-commit and pre-push) to the .git/hooks
# directory.
#
# Part of Enhanced Review Gates system.
#############################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Hooks directory
HOOKS_SOURCE_DIR="$SCRIPT_DIR"

# Determine the actual git directory (handles worktrees)
if [ -f "$PROJECT_ROOT/.git" ]; then
    # This is a git worktree - read the gitdir from .git file
    GITDIR_FILE="$PROJECT_ROOT/.git"
    GIT_DIR=$(grep "^gitdir:" "$GITDIR_FILE" | cut -d ' ' -f 2)
    HOOKS_TARGET_DIR="$GIT_DIR/hooks"
else
    # Normal git repository
    GIT_DIR="$PROJECT_ROOT/.git"
    HOOKS_TARGET_DIR="$GIT_DIR/hooks"
fi

#############################################
# HELPER FUNCTIONS
#############################################

print_header() {
    echo ""
    echo "========================================"
    echo "$1"
    echo "========================================"
}

print_section() {
    echo ""
    echo -e "${BLUE}▶ $1${NC}"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

#############################################
# VALIDATE ENVIRONMENT
#############################################

print_header "INSTALLING GIT HOOKS"

# Check if we're in a git repository
if [ -f "$PROJECT_ROOT/.git" ]; then
    # Git worktree
    success "Found git worktree at: $PROJECT_ROOT"
elif [ -d "$PROJECT_ROOT/.git" ]; then
    # Normal git repository
    success "Found git repository at: $PROJECT_ROOT"
else
    error "Not a git repository: $PROJECT_ROOT"
    error "Git hooks can only be installed in git repositories"
    exit 1
fi

# Check if hooks source directory exists
if [ ! -d "$HOOKS_SOURCE_DIR" ]; then
    error "Hooks source directory not found: $HOOKS_SOURCE_DIR"
    exit 1
fi

success "Found hooks source directory: $HOOKS_SOURCE_DIR"

# Create target directory if it doesn't exist
if [ ! -d "$HOOKS_TARGET_DIR" ]; then
    mkdir -p "$HOOKS_TARGET_DIR"
    success "Created git hooks directory: $HOOKS_TARGET_DIR"
else
    success "Using git hooks directory: $HOOKS_TARGET_DIR"
fi

#############################################
# INSTALL HOOKS
#############################################

print_section "Installing hooks"

# Array of hooks to install
HOOKS=("pre-commit" "pre-push")

INSTALLED_COUNT=0
SKIPPED_COUNT=0
FAILED_COUNT=0

for hook in "${HOOKS[@]}"; do
    HOOK_SOURCE="$HOOKS_SOURCE_DIR/$hook"
    HOOK_TARGET="$HOOKS_TARGET_DIR/$hook"

    # Check if source hook exists
    if [ ! -f "$HOOK_SOURCE" ]; then
        warning "Hook not found in source: $hook"
        SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
        continue
    fi

    # Check if target hook already exists
    if [ -f "$HOOK_TARGET" ]; then
        # Check if it's the same file
        if cmp -s "$HOOK_SOURCE" "$HOOK_TARGET"; then
            success "$hook already installed (up to date)"
            INSTALLED_COUNT=$((INSTALLED_COUNT + 1))
            continue
        else
            warning "Backing up existing $hook"
            mv "$HOOK_TARGET" "$HOOK_TARGET.backup"
        fi
    fi

    # Copy hook to target directory
    if cp "$HOOK_SOURCE" "$HOOK_TARGET"; then
        # Make hook executable
        chmod +x "$HOOK_TARGET"
        success "Installed $hook"
        INSTALLED_COUNT=$((INSTALLED_COUNT + 1))
    else
        error "Failed to install $hook"
        FAILED_COUNT=$((FAILED_COUNT + 1))
    fi
done

#############################################
# SUMMARY
#############################################

print_header "INSTALLATION SUMMARY"

echo ""
echo "Installed: $INSTALLED_COUNT hook(s)"
if [ $SKIPPED_COUNT -gt 0 ]; then
    echo "Skipped:   $SKIPPED_COUNT hook(s)"
fi
if [ $FAILED_COUNT -gt 0 ]; then
    echo "Failed:    $FAILED_COUNT hook(s)"
fi
echo ""

if [ $INSTALLED_COUNT -gt 0 ]; then
    success "Git hooks installed successfully"
    echo ""
    echo "The following hooks are now active:"
    for hook in "${HOOKS[@]}"; do
        if [ -f "$HOOKS_TARGET_DIR/$hook" ]; then
            echo "  • $hook"
        fi
    done
    echo ""
    echo "These hooks will run automatically before commits and pushes."
    echo "To temporarily skip hooks, use environment variables:"
    echo "  SKIP_TESTS=1 git commit"
    echo "  SKIP_COVERAGE=1 git commit"
    echo "  SKIP_QA_CHECK=1 git push"
    echo ""
else
    warning "No hooks were installed"
    exit 1
fi

exit 0
