#!/bin/bash
# Emergency Cleanup Script for Autoflow Development Environment
# Use this when the system becomes unresponsive due to memory issues

echo "🚨 Autoflow Emergency Cleanup Script"
echo "====================================="
echo ""

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to count processes
count_processes() {
    local pattern=$1
    local count=$(ps aux | grep -E "$pattern" | grep -v grep | wc -l | tr -d ' ')
    echo "$count"
}

# Function to kill processes safely
kill_processes_safely() {
    local pattern=$1
    local name=$2
    local max_allowed=$3

    local count=$(count_processes "$pattern")

    if [ "$count" -gt "$max_allowed" ]; then
        print_message "$YELLOW" "⚠️  Found $count $name processes (max allowed: $max_allowed)"
        read -p "Kill excess processes? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_message "$BLUE" "🔧 Cleaning up $name processes..."
            pkill -f "$pattern"
            sleep 2
            local remaining=$(count_processes "$pattern")
            print_message "$GREEN" "✅ Cleanup completed. Remaining: $remaining"
        else
            print_message "$YELLOW" "⏭️  Skipped cleanup"
        fi
    else
        print_message "$GREEN" "✅ $name processes OK: $count"
    fi
}

# Show current memory usage
print_message "$BLUE" "📊 Current Memory Usage:"
top -l 1 | grep "PhysMem"
echo ""

# Count various processes
print_message "$BLUE" "🔍 Process Analysis:"
pytest_count=$(count_processes "pytest")
print_message "$BLUE" "  - Pytest processes: $pytest_count"

python_count=$(count_processes "python.*maintenance")
print_message "$BLUE" "  - Maintenance scripts: $python_count"

node_count=$(count_processes "node.*autoflow|openclaw")
print_message "$BLUE" "  - Node/Autoflow processes: $node_count"

zombie_count=$(ps aux | grep defunct | grep -v grep | wc -l | tr -d ' ')
print_message "$BLUE" "  - Zombie processes: $zombie_count"
echo ""

# Check for excessive pytest processes
if [ "$pytest_count" -gt 50 ]; then
    print_message "$RED" "🚨 CRITICAL: Excessive pytest processes detected!"
    kill_processes_safely "pytest" "pytest" 10
fi

# Check for excessive maintenance scripts
if [ "$python_count" -gt 5 ]; then
    print_message "$YELLOW" "⚠️  Multiple maintenance script instances detected"
    kill_processes_safely "maintenance.py" "maintenance" 2
fi

# Clear Python cache
print_message "$BLUE" "🧹 Cleaning Python cache..."
find /Users/abel/dev/autoflow -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find /Users/abel/dev/autoflow -type f -name "*.pyc" -delete 2>/dev/null || true
print_message "$GREEN" "✅ Python cache cleaned"

# Clear temporary files
print_message "$BLUE" "🧹 Cleaning temporary files..."
if [ -d "/Users/abel/dev/autoflow/.tmp" ]; then
    find /Users/abel/dev/autoflow/.tmp -type f -mtime +1 -delete 2>/dev/null || true
    print_message "$GREEN" "✅ Temp files cleaned"
fi

# Show final memory status
print_message "$BLUE" ""
print_message "$BLUE" "📊 Final Memory Status:"
top -l 1 | grep "PhysMem"

print_message "$GREEN" ""
print_message "$GREEN" "✨ Emergency cleanup completed!"
print_message "$BLUE" "💡 Run 'bash /Users/abel/dev/autoflow/scripts/memory_monitor.sh' periodically to monitor memory usage"
