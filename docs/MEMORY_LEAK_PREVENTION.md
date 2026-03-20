# Memory Leak Prevention Guide

## Overview

This guide helps prevent memory issues and process leaks in the Autoflow development environment.

## Quick Reference

### Emergency Commands

```bash
# If system becomes unresponsive due to memory issues:
bash scripts/emergency_cleanup.sh

# Monitor memory usage periodically:
bash scripts/memory_monitor.sh
```

### Prevention Configuration

1. **Apply pytest prevention settings:**
   ```bash
   source config/pytest_prevention.conf
   ```

2. **Add to your `.zshrc` or `.bashrc`:**
   ```bash
   echo 'source /Users/abel/dev/autoflow/config/pytest_prevention.conf' >> ~/.zshrc
   ```

## Scripts Description

### 1. memory_monitor.sh

**Purpose:** Regular monitoring of memory usage and process counts

**Usage:**
```bash
bash scripts/memory_monitor.sh
```

**What it does:**
- Checks current memory usage
- Counts zombie processes
- Detects excessive pytest processes
- Shows top memory consumers
- Automatically cleans up if threshold exceeded

**Configuration:**
- `MAX_MEMORY_PERCENT`: Alert threshold (default: 80%)
- `LOG_FILE`: Where to store logs

### 2. emergency_cleanup.sh

**Purpose:** Interactive cleanup when system becomes unresponsive

**Usage:**
```bash
bash scripts/emergency_cleanup.sh
```

**What it does:**
- Shows current memory usage
- Counts and displays process statistics
- Offers to kill excessive processes
- Cleans Python cache
- Removes old temporary files
- Shows final memory status

### 3. pytest_prevention.conf

**Purpose:** Environment variables to prevent pytest process leaks

**Usage:**
```bash
source config/pytest_prevention.conf
```

**What it sets:**
- Limits pytest workers to 2
- Sets timeout for tests (300s)
- Enables Python optimization
- Reduces memory allocation arenas

## pytest Configuration Updates

The `pyproject.toml` has been updated with:

1. **Test failure limit:** `--maxfail=5`
2. **Timeout enabled:** Default 300 seconds
3. **Warning filtering:** `-p no:warnings`
4. **Strict markers:** `--strict-markers`

## Common Issues and Solutions

### Issue: System becomes unresponsive

**Symptoms:**
- Applications freeze
- High memory usage (>80%)
- Many zombie processes

**Solution:**
```bash
bash scripts/emergency_cleanup.sh
```

### Issue: Too many pytest processes

**Symptoms:**
- 50+ pytest processes running
- Memory usage climbing
- Tests hanging

**Solution:**
```bash
# Kill pytest processes
pkill -f pytest

# Or run emergency cleanup
bash scripts/emergency_cleanup.sh
```

### Issue: Tests hanging indefinitely

**Symptoms:**
- Test never completes
- High CPU usage
- pytest process won't exit

**Solution:**
```bash
# Kill with timeout
timeout 300 pytest tests/

# Or use pytest with timeout built-in
pytest --timeout=300 tests/
```

## Monitoring Best Practices

### 1. Regular Checks

Add to crontab for periodic monitoring:
```bash
# Check every 15 minutes
*/15 * * * * /Users/abel/dev/autoflow/scripts/memory_monitor.sh >> /Users/abel/dev/autoflow/logs/memory_monitor.log 2>&1
```

### 2. Setup Alerts

Edit `scripts/memory_monitor.sh` to set your email:
```bash
ALERT_EMAIL="your-email@example.com"
```

### 3. Dashboard Monitoring

Consider using tools like:
- `htop` for interactive monitoring
- `activity monitor` (built-in macOS)
- `stats` in terminal

## Development Guidelines

### When Running Tests

1. **Use specific test files instead of entire suite:**
   ```bash
   # Good: Specific test
   pytest tests/test_specific.py

   # Avoid: All tests
   pytest tests/
   ```

2. **Limit parallel execution:**
   ```bash
   # If using xdist, limit workers
   pytest -n 2 tests/

   # Don't use unlimited workers
   pytest -n auto tests/  # AVOID
   ```

3. **Use timeouts:**
   ```bash
   pytest --timeout=300 tests/
   ```

### When Debugging

1. **Clean up before debugging:**
   ```bash
   bash scripts/emergency_cleanup.sh
   ```

2. **Monitor while debugging:**
   ```bash
   # In another terminal
   watch -n 5 'ps aux | grep pytest | wc -l'
   ```

3. **Check memory leaks:**
   ```bash
   python3 -m memory_profiler your_script.py
   ```

## Maintenance Schedule

### Daily
- Run `memory_monitor.sh` at start and end of day
- Check log file: `logs/memory_monitor.log`

### Weekly
- Run `emergency_cleanup.sh` as preventive measure
- Review `pyproject.toml` settings

### Monthly
- Review and update prevention settings
- Check for new pytest versions with better memory management
- Archive old log files

## Getting Help

If issues persist after following this guide:

1. Check system logs: `Console.app` on macOS
2. Review pytest logs: `logs/pytest_*.log`
3. Run diagnostics: `python3 scripts/maintenance.py --health-check`

## Additional Resources

- pytest documentation: https://docs.pytest.org/
- pytest-xdist: https://pytest-xdist.readthedocs.io/
- pytest-timeout: https://github.com/pytest-dev/pytest-timeout/
- macOS memory management: https://support.apple.com/en-us/HT201538
