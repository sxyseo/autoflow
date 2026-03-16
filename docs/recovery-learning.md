# Recovery Learning

## Goal

Enable Autoflow to automatically recover from errors by learning from past recovery attempts. The system tracks which strategies work best for specific error patterns and improves over time through experience.

## Overview

Recovery learning transforms error handling from reactive to proactive:

**Without Learning:**
- Error occurs → Apply generic retry → Often fails → Escalate to human

**With Learning:**
- Error occurs → Identify pattern → Apply learned strategy → Record outcome → Improve knowledge → Next time is smarter

## Key Concepts

### Error Patterns

Error patterns are unique signatures derived from:
- Error message and type
- Failure category (TIMEOUT, NETWORK_ISSUE, DEPENDENCY_ERROR, etc.)
- Contextual features (service name, operation type, environment)
- Historical occurrence data

Example pattern:
```python
{
    "error_category": "TIMEOUT",
    "error_signature": "timeout_after_30s_api_gateway",
    "features": {
        "service": "api-gateway",
        "operation": "POST",
        "timeout": 30,
        "environment": "production"
    }
}
```

### Recovery Attempts

Each recovery attempt captures:
- Strategy used (retry, reconfigure, fallback, etc.)
- Parameters applied (retry count, delays, etc.)
- Outcome (SUCCESS, PARTIAL, FAILED, ESCALATED)
- Execution time and changes made
- Verification results

### Learned Strategies

Successful patterns become learned strategies with:
- Confidence level (HIGH, MEDIUM, LOW)
- Success rate statistics
- Recommended parameters
- Sample size and recency

## Components

### RecoveryLearner

Core learning engine that:
- Extracts patterns from diagnostic results
- Records recovery attempts with outcomes
- Calculates success rates and confidence
- Recommends optimal strategies

Example:
```python
from autoflow.healing.recovery_learner import RecoveryLearner
from autoflow.healing.diagnostic import RootCause

learner = RecoveryLearner()

# Extract pattern from error
root_cause = RootCause(...)  # from diagnostic system
pattern_info = learner.extract_pattern(root_cause, context={})
print(f"Pattern ID: {pattern_info['pattern_id']}")

# Record recovery attempt
learner.record_attempt(
    pattern_id=pattern_info['pattern_id'],
    strategy_used="exponential_backoff",
    action_type="RETRY",
    parameters={"max_retries": 5, "base_delay": 2.0},
    outcome=RecoveryOutcome.SUCCESS,
    success=True,
    execution_time=15.3,
    changes_made=["Updated retry configuration"],
    verification_passed=True
)

# Get recommended strategy
strategy = learner.recommend_strategy(pattern_info['pattern_id'])
if strategy:
    print(f"Recommended: {strategy.strategy_name}")
    print(f"Confidence: {strategy.confidence}")
    print(f"Success rate: {strategy.success_rate:.1%}")
```

### PatternStore

Persistent storage for patterns and strategies:
- Atomic writes for crash safety
- JSON-based storage in `.autoflow/recovery_patterns.json`
- Efficient lookup methods

Example:
```python
from autoflow.healing.pattern_store import PatternStore

store = PatternStore()

# Find patterns by error category
timeout_patterns = store.find_by_error_pattern("TIMEOUT")

# Get strategies for a specific pattern
strategies = store.get_strategies_for_error("timeout_after_30s")

# Get success rate for a strategy
success_rate = store.get_success_rate(
    pattern_id="timeout_after_30s_api_gateway",
    strategy_name="exponential_backoff"
)
print(f"Success rate: {success_rate:.1%}")
```

### AdaptiveRetryExecutor

Intelligent retry executor that:
- Adjusts parameters based on learning
- Falls back to learned strategies
- Records attempts for learning

Example:
```python
from autoflow.healing.adaptive_executor import AdaptiveRetryExecutor
from autoflow.healing.actions import HealingAction

executor = AdaptiveRetryExecutor(learner=recovery_learner)

action = HealingAction(
    name="adaptive_retry",
    action_type="RETRY",
    parameters={"max_retries": 3}  # Will be adjusted by learning
)

result = await executor.execute(
    action=action,
    root_cause=diagnostic_result.primary_cause,
    context={"service": "api-gateway"}
)
```

## Workflow

### 1. Error Occurs

```python
# During workflow execution, an error occurs
try:
    await execute_workflow_step()
except TimeoutError as e:
    # Diagnostic system analyzes the error
    diagnostic_result = await diagnose_error(e)
```

### 2. Pattern Extraction

```python
from autoflow.healing.recovery_learner import RecoveryLearner

learner = RecoveryLearner()

# Extract pattern from diagnostic result
pattern_info = learner.extract_pattern(
    root_cause=diagnostic_result.primary_cause,
    context={
        "service": "api-gateway",
        "operation": "POST",
        "timeout": 30
    }
)

# pattern_info contains:
# - pattern_id: Unique hash for this error pattern
# - error_category: TIMEOUT, NETWORK_ISSUE, etc.
# - features: Dict of contextual features
```

### 3. Strategy Recommendation

```python
# Query learning system for best strategy
strategy = learner.recommend_strategy(pattern_info['pattern_id'])

if strategy and strategy.confidence == PatternConfidence.HIGH:
    # Use learned strategy with high confidence
    print(f"Using learned strategy: {strategy.strategy_name}")
    print(f"Recommended parameters: {strategy.parameters}")
    print(f"Expected success rate: {strategy.success_rate:.1%}")
else:
    # Fall back to default strategy
    print("No high-confidence strategy found, using default")
    strategy = None
```

### 4. Recovery Execution

```python
from autoflow.healing.actions import HealingAction

if strategy:
    # Use learned strategy
    action = HealingAction(
        name=strategy.strategy_name,
        action_type="RETRY",
        parameters=strategy.parameters
    )
else:
    # Use default strategy
    action = HealingAction(
        name="default_retry",
        action_type="RETRY",
        parameters={"max_retries": 3, "base_delay": 1.0}
    )

# Execute recovery
result = await executor.execute(
    action=action,
    root_cause=diagnostic_result.primary_cause
)
```

### 5. Record and Learn

```python
from autoflow.healing.recovery_learner import RecoveryOutcome

# Record the attempt for learning
learner.record_attempt(
    pattern_id=pattern_info['pattern_id'],
    strategy_used=action.name,
    action_type=action.action_type,
    parameters=action.parameters,
    outcome=RecoveryOutcome.SUCCESS if result.success else RecoveryOutcome.FAILED,
    success=result.success,
    execution_time=result.execution_time,
    error=result.error,
    changes_made=result.changes_made,
    verification_passed=result.verification_passed,
    outcome_details=result.message,
    metadata={"root_cause": diagnostic_result.primary_cause.to_dict()}
)

# Trigger learning update
learner.learn_from_history()
```

## Integration with Healing System

The recovery learning system integrates with the existing healing orchestrator:

```python
from autoflow.healing.orchestrator import HealingOrchestrator
from autoflow.healing.config import HealingConfig

# Enable learning in config
config = HealingConfig(
    learning_enabled=True,
    pattern_store_path=".autoflow/recovery_patterns.json"
)

# Orchestrator automatically uses learning
orchestrator = HealingOrchestrator(config=config)

# When errors occur, orchestrator:
# 1. Diagnoses the error
# 2. Queries learning system for strategies
# 3. Attempts recovery with learned parameters
# 4. Records outcome for learning
```

## Confidence Levels

### HIGH Confidence
- >80% success rate
- At least 10 samples
- Used within last 7 days

**Action:** Use learned strategy automatically

### MEDIUM Confidence
- 50-80% success rate
- At least 5 samples
- Used within last 14 days

**Action:** Use learned strategy with logging

### LOW Confidence
- <50% success rate
- Less than 5 samples
- Not used recently

**Action:** Prefer default strategy

## Best Practices

### 1. Start with Default Strategies

```python
# Don't rely on learning from day one
strategy = learner.recommend_strategy(pattern_id)

if strategy and strategy.confidence >= PatternConfidence.MEDIUM:
    use_learned_strategy(strategy)
else:
    use_default_strategy()
```

### 2. Record All Attempts

```python
# Even failed attempts provide valuable data
try:
    result = await execute_recovery()
finally:
    learner.record_attempt(
        pattern_id=pattern_id,
        strategy_used=strategy_name,
        outcome=RecoveryOutcome.FAILED,  # Record failures too!
        success=False,
        error=str(e)
    )
```

### 3. Verify Before Learning

```python
# Only record as success if verification passes
if result.success and result.verification_passed:
    outcome = RecoveryOutcome.SUCCESS
elif result.success:
    outcome = RecoveryOutcome.PARTIAL
else:
    outcome = RecoveryOutcome.FAILED
```

### 4. Monitor Confidence

```python
# Track learning progress
for pattern_id in store.list_patterns():
    pattern = store.get_pattern(pattern_id)
    strategy = store.get_best_strategy(pattern_id)

    if strategy:
        print(f"{pattern_id}: {strategy.confidence} "
              f"({strategy.success_rate:.1%} success, "
              f"{strategy.sample_size} samples)")
```

## Monitoring and Debugging

### View Learned Patterns

```python
from autoflow.healing.pattern_store import PatternStore

store = PatternStore()

# List all patterns
for pattern_id, pattern in store.patterns.items():
    print(f"\n{pattern_id}")
    print(f"  Category: {pattern.error_category}")
    print(f"  Occurrences: {pattern.occurrence_count}")
    print(f"  Success rate: {pattern.success_count}/{pattern.occurrence_count}")
    print(f"  Confidence: {pattern.confidence}")
```

### Analyze Recovery Attempts

```python
# Get recent attempts for a pattern
attempts = store.get_attempts_for_pattern(pattern_id)

for attempt in attempts[-10:]:  # Last 10 attempts
    print(f"\n{attempt.timestamp}")
    print(f"  Strategy: {attempt.strategy_used}")
    print(f"  Outcome: {attempt.outcome}")
    print(f"  Execution time: {attempt.execution_time}s")
    print(f"  Details: {attempt.outcome_details}")
```

### Export Learning Data

```python
import json

# Export for analysis
data = {
    "patterns": {pid: p.to_dict() for pid, p in store.patterns.items()},
    "strategies": {sid: s.to_dict() for sid, s in store.strategies.items()},
    "attempts": {aid: a.to_dict() for aid, a in store.attempts.items()}
}

with open("recovery_analysis.json", "w") as f:
    json.dump(data, f, indent=2)
```

## Configuration

Enable and configure recovery learning in `HealingConfig`:

```python
from autoflow.healing.config import HealingConfig

config = HealingConfig(
    # Enable learning
    learning_enabled=True,

    # Storage location
    pattern_store_path=".autoflow/recovery_patterns.json",

    # Confidence thresholds
    high_confidence_threshold=0.8,
    medium_confidence_threshold=0.5,

    # Sample size requirements
    high_confidence_min_samples=10,
    medium_confidence_min_samples=5,

    # Recency requirements
    high_confidence_max_age_days=7,
    medium_confidence_max_age_days=14
)
```

## Advanced Usage

### Custom Pattern Features

```python
# Extract custom features for better pattern matching
def custom_feature_extractor(root_cause: RootCause, context: dict) -> dict:
    features = {
        "error_type": root_cause.error_type,
        "service": context.get("service", "unknown"),
        "operation": context.get("operation", "unknown"),
        # Add custom features
        "is_idempotent": context.get("idempotent", False),
        "has_fallback": context.get("fallback_service") is not None,
        "criticality": context.get("criticality", "medium")
    }
    return features

pattern_info = learner.extract_pattern(
    root_cause=root_cause,
    context=context,
    features=custom_feature_extractor(root_cause, context)
)
```

### Strategy Composition

```python
# Combine multiple strategies
def compose_strategies(strategies: list[LearnedStrategy]) -> dict:
    """Combine multiple learned strategies."""
    combined = {
        "max_retries": max(s.parameters.get("max_retries", 3) for s in strategies),
        "base_delay": statistics.mean(s.parameters.get("base_delay", 1.0) for s in strategies),
        "strategies_used": [s.strategy_name for s in strategies]
    }
    return combined
```

## Troubleshooting

### Learning Not Working

1. **Check if learning is enabled:**
   ```python
   config = HealingConfig()
   print(f"Learning enabled: {config.learning_enabled}")
   ```

2. **Verify pattern store:**
   ```python
   store = PatternStore()
   print(f"Patterns stored: {len(store.patterns)}")
   ```

3. **Check attempts are being recorded:**
   ```python
   print(f"Attempts recorded: {len(store.attempts)}")
   ```

### Poor Strategy Recommendations

1. **Increase sample size:**
   ```python
   config = HealingConfig(
       high_confidence_min_samples=20  # Require more samples
   )
   ```

2. **Adjust confidence thresholds:**
   ```python
   config = HealingConfig(
       high_confidence_threshold=0.9  # Require higher success rate
   )
   ```

3. **Filter by recency:**
   ```python
   config = HealingConfig(
       high_confidence_max_age_days=3  # Only use recent data
   )
   ```

## Future Enhancements

- **Cross-pattern learning:** Identify similarities between different error patterns
- **Strategy transfer:** Apply successful strategies from similar patterns
- **Predictive recovery:** Anticipate failures before they occur
- **Multi-armed bandit:** Balance exploration and exploitation
- **Explainable recommendations:** Provide reasoning for strategy choices
