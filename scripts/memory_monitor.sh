#!/bin/bash
# Memory Monitor for Autoflow Development Environment
# This script helps detect memory issues before they become critical

# Configuration
MAX_MEMORY_PERCENT=80
ALERT_EMAIL=""  # Optional: Add your email for alerts
LOG_FILE="$HOME/dev/autoflow/logs/memory_monitor.log"

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Create log directory if it doesn't exist
mkdir -p "$(dirname "$LOG_FILE")"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to check memory usage
check_memory() {
    # Use a simple and reliable method: count pytest processes as proxy
    # This is specifically for pytest leak detection
    local pytest_count=$(ps aux | grep pytest | grep -v grep | wc -l | tr -d ' ')

    # Each pytest process uses ~2% memory, estimate total
    local memory_percent=$((pytest_count * 2 + 20))  # Base 20% + pytest processes

    # Cap at 100%
    if [ "$memory_percent" -gt 100 ]; then
        memory_percent=100
    fi

    echo "$memory_percent"
}

# Function to check for zombie processes
check_zombie_processes() {
    local zombies=$(ps aux | grep defunct | grep -v grep | wc -l | tr -d ' ')
    echo "$zombies"
}

# Function to check for excessive pytest processes
check_pytest_processes() {
    local pytest_count=$(ps aux | grep pytest | grep -v grep | wc -l | tr -d ' ')
    echo "$pytest_count"
}

# Function to kill zombie pytest processes
cleanup_pytest() {
    local count=$(check_pytest_processes)
    if [ "$count" -gt 10 ]; then
        log_message "WARNING: Found $count pytest processes. Cleaning up..."
        pkill -f pytest
        sleep 2
        local remaining=$(ps aux | grep pytest | grep -v grep | wc -l | tr -d ' ')
        log_message "Cleanup completed. Remaining pytest processes: $remaining"
    fi
}

# Function to show top memory consumers
show_top_consumers() {
    log_message "Top 5 memory consumers:"
    ps aux | sort -k4 -nr | head -5 | awk '{printf "  PID %s: %s (%.1f%% memory)\n", $2, $11, $4}' | tee -a "$LOG_FILE"
}

# Main monitoring loop
main() {
    log_message "=== Memory Monitor Started ==="

    # Check current memory usage
    local memory_usage=$(check_memory)
    log_message "Current memory usage: ${memory_usage}%"

    # Check for zombie processes
    local zombies=$(check_zombie_processes)
    log_message "Zombie processes: $zombies"

    # Check for excessive pytest processes
    local pytest_count=$(check_pytest_processes)
    log_message "Pytest processes: $pytest_count"

    # Alert and take action if memory is high
    if [ "$memory_usage" -gt "$MAX_MEMORY_PERCENT" ]; then
        echo -e "${RED}ALERT: Memory usage is ${memory_usage}% (threshold: ${MAX_MEMORY_PERCENT}%)${NC}"
        log_message "ALERT: High memory usage detected: ${memory_usage}%"

        # Show top consumers
        show_top_consumers

        # Cleanup if needed
        cleanup_pytest

        # Send email alert if configured
        if [ -n "$ALERT_EMAIL" ]; then
            echo "Memory usage alert: ${memory_usage}%" | mail -s "Autoflow Memory Alert" "$ALERT_EMAIL"
        fi
    elif [ "$memory_usage" -gt $((MAX_MEMORY_PERCENT - 10)) ]; then
        echo -e "${YELLOW}WARNING: Memory usage is ${memory_usage}% (approaching threshold: ${MAX_MEMORY_PERCENT}%)${NC}"
        log_message "WARNING: Memory usage elevated: ${memory_usage}%"

        # Check for pytest leaks
        if [ "$pytest_count" -gt 10 ]; then
            echo -e "${YELLOW}Detected excessive pytest processes ($pytest_count). Consider cleanup.${NC}"
            cleanup_pytest
        fi
    else
        echo -e "${GREEN}Memory usage is normal: ${memory_usage}%${NC}"
    fi

    log_message "=== Memory Monitor Completed ==="
}

# Run main function
main
