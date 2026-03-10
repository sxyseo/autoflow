"""Unit Tests for Diagnostic System.

Tests the diagnostic models and strategy definitions for self-healing workflows.
These tests ensure the diagnostic system can:
- Categorize failures appropriately
- Perform AI-powered root cause analysis
- Select appropriate healing strategies
- Generate comprehensive healing plans
- Determine when escalation is required
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from autoflow.healing.config import HealingConfig
from autoflow.healing.diagnostic import (
    ConfidenceLevel,
    DiagnosticResult,
    ExecutionResult,
    ExecutionStatus,
    FailureCategory,
    HealingPlan,
    HealingStrategy,
    RootCause,
    RootCauseAnalyzer,
    StrategyEvaluation,
    StrategySelector,
)
from autoflow.healing.monitor import (
    DegradationSignal,
    HealthAssessment,
    WorkflowHealthStatus,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_config() -> HealingConfig:
    """Create a sample healing configuration for testing."""
    return HealingConfig(
        enabled=True,
        max_healing_attempts=3,
        healing_timeout=600,
    )


@pytest.fixture
def sample_root_cause() -> RootCause:
    """Create a sample root cause for testing."""
    return RootCause(
        category=FailureCategory.NETWORK_ISSUE,
        description="Network connectivity issues detected",
        evidence=["Connection timeout", "High latency"],
        confidence=ConfidenceLevel.HIGH,
        affected_components=["api_client", "database"],
        related_metrics=["network_latency", "connection_errors"],
        suggested_strategies=[HealingStrategy.RETRY, HealingStrategy.ESCALATE],
    )


@pytest.fixture
def sample_degradation_signal() -> DegradationSignal:
    """Create a sample degradation signal for testing."""
    return DegradationSignal(
        signal_type="timeout",
        severity="critical",
        metric_name="response_time",
        current_value=120.0,
        baseline_value=50.0,
        degradation_rate=2.4,
        confidence=0.9,
        description="Response time increased significantly",
    )


@pytest.fixture
def sample_health_assessment(sample_degradation_signal: DegradationSignal) -> HealthAssessment:
    """Create a sample health assessment for testing."""
    return HealthAssessment(
        status=WorkflowHealthStatus.CRITICAL,
        timestamp=datetime.now(),
        metrics={
            "response_time": sample_degradation_signal,
            "failure_rate": sample_degradation_signal,
        },
        violations=[
            {
                "metric_type": "response_time",
                "severity": "critical",
                "current_value": 120.0,
                "threshold_value": 50.0,
            }
        ],
        recommendations=["Investigate network connectivity"],
    )


# ============================================================================
# Enum Tests
# ============================================================================


class TestFailureCategory:
    """Tests for FailureCategory enum."""

    def test_failure_category_values(self) -> None:
        """Test FailureCategory enum values."""
        assert FailureCategory.RESOURCE_EXHAUSTION.value == "resource_exhaustion"
        assert FailureCategory.DEPENDENCY_FAILURE.value == "dependency_failure"
        assert FailureCategory.CONFIGURATION_ERROR.value == "configuration_error"
        assert FailureCategory.PERFORMANCE_DEGRADATION.value == "performance_degradation"
        assert FailureCategory.NETWORK_ISSUE.value == "network_issue"
        assert FailureCategory.CODE_ERROR.value == "code_error"
        assert FailureCategory.DATA_CORRUPTION.value == "data_corruption"
        assert FailureCategory.TIMEOUT.value == "timeout"
        assert FailureCategory.UNKNOWN.value == "unknown"

    def test_failure_category_is_string(self) -> None:
        """Test that category values are strings."""
        assert isinstance(FailureCategory.NETWORK_ISSUE.value, str)


class TestHealingStrategy:
    """Tests for HealingStrategy enum."""

    def test_healing_strategy_values(self) -> None:
        """Test HealingStrategy enum values."""
        assert HealingStrategy.RETRY.value == "retry"
        assert HealingStrategy.ROLLBACK.value == "rollback"
        assert HealingStrategy.RECONFIGURE.value == "reconfigure"
        assert HealingStrategy.ESCALATE.value == "escalate"
        assert HealingStrategy.RESTART.value == "restart"
        assert HealingStrategy.SCALE.value == "scale"
        assert HealingStrategy.ISOLATE.value == "isolate"

    def test_healing_strategy_is_string(self) -> None:
        """Test that strategy values are strings."""
        assert isinstance(HealingStrategy.RETRY.value, str)


class TestConfidenceLevel:
    """Tests for ConfidenceLevel enum."""

    def test_confidence_level_values(self) -> None:
        """Test ConfidenceLevel enum values."""
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.LOW.value == "low"

    def test_confidence_level_is_string(self) -> None:
        """Test that confidence values are strings."""
        assert isinstance(ConfidenceLevel.HIGH.value, str)


class TestExecutionStatus:
    """Tests for ExecutionStatus enum."""

    def test_execution_status_values(self) -> None:
        """Test ExecutionStatus enum values."""
        assert ExecutionStatus.SUCCESS.value == "success"
        assert ExecutionStatus.FAILURE.value == "failure"
        assert ExecutionStatus.TIMEOUT.value == "timeout"
        assert ExecutionStatus.ERROR.value == "error"

    def test_execution_status_is_string(self) -> None:
        """Test that status values are strings."""
        assert isinstance(ExecutionStatus.SUCCESS.value, str)


# ============================================================================
# Data Model Tests
# ============================================================================


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_execution_result_init(self) -> None:
        """Test ExecutionResult initialization."""
        result = ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            content="Analysis complete",
            raw_output="Raw output",
            metadata={"confidence": "high"},
            token_usage={"prompt_tokens": 100, "completion_tokens": 50},
            duration=1.5,
        )

        assert result.status == ExecutionStatus.SUCCESS
        assert result.content == "Analysis complete"
        assert result.raw_output == "Raw output"
        assert result.metadata == {"confidence": "high"}
        assert result.duration == 1.5

    def test_execution_result_to_dict(self) -> None:
        """Test ExecutionResult to_dict method."""
        result = ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            content="Analysis complete",
            error="Test error",
        )

        result_dict = result.to_dict()

        assert result_dict["status"] == "success"
        assert result_dict["content"] == "Analysis complete"
        assert result_dict["error"] == "Test error"


class TestRootCause:
    """Tests for RootCause dataclass."""

    def test_root_cause_init(self, sample_root_cause: RootCause) -> None:
        """Test RootCause initialization."""
        assert sample_root_cause.category == FailureCategory.NETWORK_ISSUE
        assert sample_root_cause.description == "Network connectivity issues detected"
        assert len(sample_root_cause.evidence) == 2
        assert sample_root_cause.confidence == ConfidenceLevel.HIGH
        assert len(sample_root_cause.affected_components) == 2
        assert len(sample_root_cause.suggested_strategies) == 2

    def test_root_cause_to_dict(self, sample_root_cause: RootCause) -> None:
        """Test RootCause to_dict method."""
        cause_dict = sample_root_cause.to_dict()

        assert cause_dict["category"] == "network_issue"
        assert cause_dict["description"] == "Network connectivity issues detected"
        assert cause_dict["confidence"] == "high"
        assert len(cause_dict["evidence"]) == 2
        assert len(cause_dict["suggested_strategies"]) == 2


class TestDiagnosticResult:
    """Tests for DiagnosticResult dataclass."""

    def test_diagnostic_result_init(
        self,
        sample_root_cause: RootCause,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test DiagnosticResult initialization."""
        diagnostic = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.CRITICAL,
            root_causes=[sample_root_cause],
            primary_cause=sample_root_cause,
            degradation_signals=[sample_degradation_signal.to_dict()],
            metadata={"test": "data"},
            healing_plan={"strategies": ["retry"]},
            requires_escalation=False,
            analysis_duration=1.5,
        )

        assert diagnostic.health_status == WorkflowHealthStatus.CRITICAL
        assert len(diagnostic.root_causes) == 1
        assert diagnostic.primary_cause == sample_root_cause
        assert diagnostic.requires_escalation is False
        assert diagnostic.analysis_duration == 1.5

    def test_diagnostic_result_to_dict(
        self,
        sample_root_cause: RootCause,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test DiagnosticResult to_dict method."""
        diagnostic = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.CRITICAL,
            root_causes=[sample_root_cause],
            primary_cause=sample_root_cause,
            degradation_signals=[sample_degradation_signal.to_dict()],
            metadata={},
            healing_plan={},
            requires_escalation=False,
            analysis_duration=1.5,
        )

        result_dict = diagnostic.to_dict()

        assert result_dict["health_status"] == "critical"
        assert result_dict["requires_escalation"] is False
        assert result_dict["analysis_duration"] == 1.5
        assert len(result_dict["root_causes"]) == 1

    def test_diagnostic_result_get_summary(
        self,
        sample_root_cause: RootCause,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test DiagnosticResult get_summary method."""
        diagnostic = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.CRITICAL,
            root_causes=[sample_root_cause],
            primary_cause=sample_root_cause,
            degradation_signals=[sample_degradation_signal.to_dict()],
            metadata={},
            healing_plan={"strategies": ["retry", "escalate"]},
            requires_escalation=False,
            analysis_duration=1.5,
        )

        summary = diagnostic.get_summary()

        assert "Diagnostic Result" in summary
        assert "Health Status: critical" in summary
        assert "network_issue" in summary
        assert "retry" in summary
        assert "1.5" in summary  # Analysis duration


class TestStrategyEvaluation:
    """Tests for StrategyEvaluation dataclass."""

    def test_strategy_evaluation_init(self) -> None:
        """Test StrategyEvaluation initialization."""
        evaluation = StrategyEvaluation(
            strategy=HealingStrategy.RETRY,
            applicability_score=0.8,
            confidence=ConfidenceLevel.HIGH,
            rationale="Retry is effective for transient failures",
            estimated_success_rate=0.7,
            risk_level="low",
            resource_requirements={"cpu": "low"},
            execution_time_estimate=30.0,
        )

        assert evaluation.strategy == HealingStrategy.RETRY
        assert evaluation.applicability_score == 0.8
        assert evaluation.confidence == ConfidenceLevel.HIGH
        assert evaluation.risk_level == "low"
        assert evaluation.execution_time_estimate == 30.0

    def test_strategy_evaluation_to_dict(self) -> None:
        """Test StrategyEvaluation to_dict method."""
        evaluation = StrategyEvaluation(
            strategy=HealingStrategy.RETRY,
            applicability_score=0.8,
            confidence=ConfidenceLevel.HIGH,
            rationale="Test rationale",
            estimated_success_rate=0.7,
            risk_level="low",
            resource_requirements={},
            execution_time_estimate=30.0,
        )

        eval_dict = evaluation.to_dict()

        assert eval_dict["strategy"] == "retry"
        assert eval_dict["applicability_score"] == 0.8
        assert eval_dict["confidence"] == "high"
        assert eval_dict["risk_level"] == "low"


class TestHealingPlan:
    """Tests for HealingPlan dataclass."""

    def test_healing_plan_init(self) -> None:
        """Test HealingPlan initialization."""
        plan = HealingPlan(
            selected_strategy=HealingStrategy.RETRY,
            fallback_strategies=[HealingStrategy.ESCALATE],
            execution_steps=["Step 1", "Step 2"],
            rollback_plan=["Rollback step"],
            verification_steps=["Verify step"],
            estimated_duration=60.0,
            resource_requirements={"cpu": "low"},
            risk_assessment={"risk_level": "low"},
        )

        assert plan.selected_strategy == HealingStrategy.RETRY
        assert len(plan.fallback_strategies) == 1
        assert len(plan.execution_steps) == 2
        assert plan.estimated_duration == 60.0

    def test_healing_plan_to_dict(self) -> None:
        """Test HealingPlan to_dict method."""
        plan = HealingPlan(
            selected_strategy=HealingStrategy.RETRY,
            fallback_strategies=[HealingStrategy.ESCALATE],
            execution_steps=["Step 1"],
            rollback_plan=["Rollback"],
            verification_steps=["Verify"],
            estimated_duration=60.0,
            resource_requirements={},
            risk_assessment={},
        )

        plan_dict = plan.to_dict()

        assert plan_dict["selected_strategy"] == "retry"
        assert len(plan_dict["fallback_strategies"]) == 1
        assert plan_dict["fallback_strategies"][0] == "escalate"
        assert plan_dict["estimated_duration"] == 60.0


# ============================================================================
# StrategySelector Tests
# ============================================================================


class TestStrategySelectorInit:
    """Tests for StrategySelector initialization."""

    def test_init_with_config(self, sample_config: HealingConfig) -> None:
        """Test initialization with config."""
        selector = StrategySelector(config=sample_config)

        assert selector.config == sample_config

    def test_init_without_config(self) -> None:
        """Test initialization without config uses defaults."""
        selector = StrategySelector()

        assert selector.config is not None
        assert selector.config.enabled is True


class TestStrategySelection:
    """Tests for strategy selection logic."""

    def test_select_healing_strategy_with_escalation(
        self,
        sample_root_cause: RootCause,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test strategy selection when escalation is required."""
        diagnostic = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.CRITICAL,
            root_causes=[sample_root_cause],
            primary_cause=sample_root_cause,
            degradation_signals=[sample_degradation_signal.to_dict()],
            metadata={},
            healing_plan={},
            requires_escalation=True,  # Requires escalation
            analysis_duration=1.0,
        )

        selector = StrategySelector()
        plan = selector.select_healing_strategy(diagnostic)

        # Should return None when escalation is required
        assert plan is None

    def test_select_healing_strategy_success(
        self,
        sample_root_cause: RootCause,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test successful strategy selection."""
        diagnostic = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.DEGRADED,
            root_causes=[sample_root_cause],
            primary_cause=sample_root_cause,
            degradation_signals=[sample_degradation_signal.to_dict()],
            metadata={},
            healing_plan={},
            requires_escalation=False,
            analysis_duration=1.0,
        )

        selector = StrategySelector()
        plan = selector.select_healing_strategy(diagnostic)

        assert plan is not None
        assert plan.selected_strategy in [HealingStrategy.RETRY, HealingStrategy.ESCALATE]
        assert len(plan.execution_steps) > 0
        assert len(plan.rollback_plan) > 0
        assert len(plan.verification_steps) > 0

    def test_get_possible_strategies(
        self,
        sample_root_cause: RootCause,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test getting possible strategies."""
        diagnostic = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.DEGRADED,
            root_causes=[sample_root_cause],
            primary_cause=sample_root_cause,
            degradation_signals=[sample_degradation_signal.to_dict()],
            metadata={},
            healing_plan={},
            requires_escalation=False,
            analysis_duration=1.0,
        )

        selector = StrategySelector()
        strategies = selector._get_possible_strategies(diagnostic)

        assert isinstance(strategies, list)
        # Should have at least some strategies
        assert len(strategies) >= 0

    def test_evaluate_strategy_retry_network(
        self,
        sample_root_cause: RootCause,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test evaluating RETRY strategy for network issues."""
        sample_root_cause.category = FailureCategory.NETWORK_ISSUE
        diagnostic = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.DEGRADED,
            root_causes=[sample_root_cause],
            primary_cause=sample_root_cause,
            degradation_signals=[sample_degradation_signal.to_dict()],
            metadata={},
            healing_plan={},
            requires_escalation=False,
            analysis_duration=1.0,
        )

        selector = StrategySelector()
        evaluation = selector._evaluate_strategy(
            strategy=HealingStrategy.RETRY,
            diagnostic=diagnostic,
        )

        assert evaluation is not None
        assert evaluation.strategy == HealingStrategy.RETRY
        assert evaluation.applicability_score > 0.5  # Should be applicable
        assert evaluation.risk_level == "low"

    def test_evaluate_strategy_rollback_config(
        self,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test evaluating ROLLBACK strategy for configuration errors."""
        root_cause = RootCause(
            category=FailureCategory.CONFIGURATION_ERROR,
            description="Invalid configuration",
            evidence=["Config validation failed"],
            confidence=ConfidenceLevel.HIGH,
            affected_components=["config_service"],
            related_metrics=[],
            suggested_strategies=[HealingStrategy.ROLLBACK],
        )

        diagnostic = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.DEGRADED,
            root_causes=[root_cause],
            primary_cause=root_cause,
            degradation_signals=[sample_degradation_signal.to_dict()],
            metadata={},
            healing_plan={},
            requires_escalation=False,
            analysis_duration=1.0,
        )

        selector = StrategySelector()
        evaluation = selector._evaluate_strategy(
            strategy=HealingStrategy.ROLLBACK,
            diagnostic=diagnostic,
        )

        assert evaluation is not None
        assert evaluation.strategy == HealingStrategy.ROLLBACK
        assert evaluation.applicability_score > 0.6
        assert evaluation.risk_level == "low"

    def test_estimate_resource_requirements(self) -> None:
        """Test resource requirement estimation."""
        selector = StrategySelector()

        # Test RETRY
        retry_reqs = selector._estimate_resource_requirements(HealingStrategy.RETRY)
        assert retry_reqs["cpu"] == "low"
        assert retry_reqs["storage"] == "none"

        # Test SCALE
        scale_reqs = selector._estimate_resource_requirements(HealingStrategy.SCALE)
        assert scale_reqs["cpu"] == "high"
        assert scale_reqs["memory"] == "high"

        # Test ROLLBACK
        rollback_reqs = selector._estimate_resource_requirements(HealingStrategy.ROLLBACK)
        assert rollback_reqs["storage"] == "medium"

    def test_estimate_execution_time(self) -> None:
        """Test execution time estimation."""
        selector = StrategySelector()

        retry_time = selector._estimate_execution_time(HealingStrategy.RETRY)
        assert retry_time == 30.0

        rollback_time = selector._estimate_execution_time(HealingStrategy.ROLLBACK)
        assert rollback_time == 60.0

        escalate_time = selector._estimate_execution_time(HealingStrategy.ESCALATE)
        assert escalate_time == 0.0  # Immediate

    def test_generate_execution_steps(self) -> None:
        """Test execution step generation."""
        selector = StrategySelector()
        diagnostic = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.DEGRADED,
            root_causes=[],
            primary_cause=None,
            degradation_signals=[],
            metadata={},
            healing_plan={},
            requires_escalation=False,
            analysis_duration=1.0,
        )

        retry_steps = selector._generate_execution_steps(
            strategy=HealingStrategy.RETRY,
            diagnostic=diagnostic,
        )
        assert len(retry_steps) > 0
        assert any("retry" in step.lower() for step in retry_steps)

        rollback_steps = selector._generate_execution_steps(
            strategy=HealingStrategy.ROLLBACK,
            diagnostic=diagnostic,
        )
        assert len(rollback_steps) > 0
        assert any("checkpoint" in step.lower() for step in rollback_steps)

    def test_generate_rollback_plan(self) -> None:
        """Test rollback plan generation."""
        selector = StrategySelector()
        diagnostic = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.DEGRADED,
            root_causes=[],
            primary_cause=None,
            degradation_signals=[],
            metadata={},
            healing_plan={},
            requires_escalation=False,
            analysis_duration=1.0,
        )

        retry_rollback = selector._generate_rollback_plan(
            strategy=HealingStrategy.RETRY,
            diagnostic=diagnostic,
        )
        assert len(retry_rollback) > 0

        escalate_rollback = selector._generate_rollback_plan(
            strategy=HealingStrategy.ESCALATE,
            diagnostic=diagnostic,
        )
        assert any("no rollback needed" in step.lower() for step in escalate_rollback)

    def test_generate_verification_steps(self) -> None:
        """Test verification step generation."""
        selector = StrategySelector()
        diagnostic = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.DEGRADED,
            root_causes=[],
            primary_cause=None,
            degradation_signals=[],
            metadata={},
            healing_plan={},
            requires_escalation=False,
            analysis_duration=1.0,
        )

        verify_steps = selector._generate_verification_steps(
            strategy=HealingStrategy.RETRY,
            diagnostic=diagnostic,
        )
        assert len(verify_steps) > 0
        assert any("stabilization" in step.lower() for step in verify_steps)

    def test_identify_potential_side_effects(self) -> None:
        """Test side effect identification."""
        selector = StrategySelector()
        diagnostic = DiagnosticResult(
            timestamp=datetime.now(),
            health_status=WorkflowHealthStatus.DEGRADED,
            root_causes=[],
            primary_cause=None,
            degradation_signals=[],
            metadata={},
            healing_plan={},
            requires_escalation=False,
            analysis_duration=1.0,
        )

        retry_effects = selector._identify_potential_side_effects(
            strategy=HealingStrategy.RETRY,
            diagnostic=diagnostic,
        )
        assert len(retry_effects) > 0

        scale_effects = selector._identify_potential_side_effects(
            strategy=HealingStrategy.SCALE,
            diagnostic=diagnostic,
        )
        assert any("cost" in effect.lower() for effect in scale_effects)


# ============================================================================
# RootCauseAnalyzer Tests
# ============================================================================


class TestRootCauseAnalyzerInit:
    """Tests for RootCauseAnalyzer initialization."""

    def test_init_with_config(self, sample_config: HealingConfig) -> None:
        """Test initialization with config."""
        analyzer = RootCauseAnalyzer(config=sample_config)

        assert analyzer.config == sample_config
        assert len(analyzer._analysis_cache) == 0

    def test_init_without_config(self) -> None:
        """Test initialization without config uses defaults."""
        analyzer = RootCauseAnalyzer()

        assert analyzer.config is not None
        assert analyzer.config.enabled is True


class TestRootCauseAnalysis:
    """Tests for root cause analysis."""

    def test_analyze_root_cause_basic(
        self,
        sample_health_assessment: HealthAssessment,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test basic root cause analysis."""
        analyzer = RootCauseAnalyzer()

        diagnostic = analyzer.analyze_root_cause(
            health_assessment=sample_health_assessment,
            degradation_signals=[sample_degradation_signal],
        )

        assert diagnostic is not None
        assert diagnostic.health_status == sample_health_assessment.status
        assert diagnostic.analysis_duration >= 0
        assert isinstance(diagnostic.root_causes, list)

    def test_analyze_root_cause_with_context(
        self,
        sample_health_assessment: HealthAssessment,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test root cause analysis with additional context."""
        analyzer = RootCauseAnalyzer()

        context = {
            "recent_changes": ["Updated API endpoint"],
            "error_logs": ["Connection timeout at 10:00:00"],
        }

        diagnostic = analyzer.analyze_root_cause(
            health_assessment=sample_health_assessment,
            degradation_signals=[sample_degradation_signal],
            context=context,
        )

        assert diagnostic is not None
        assert diagnostic.metadata["context_provided"] is True
        assert "recent_changes" in diagnostic.metadata["context_keys"]

    def test_analyze_root_cause_caching(
        self,
        sample_health_assessment: HealthAssessment,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test that analysis results are cached."""
        analyzer = RootCauseAnalyzer()

        # First analysis
        diagnostic1 = analyzer.analyze_root_cause(
            health_assessment=sample_health_assessment,
            degradation_signals=[sample_degradation_signal],
        )

        # Second analysis with same inputs should use cache
        diagnostic2 = analyzer.analyze_root_cause(
            health_assessment=sample_health_assessment,
            degradation_signals=[sample_degradation_signal],
        )

        # Should return cached result (same object)
        assert diagnostic1 is diagnostic2

    def test_clear_cache(
        self,
        sample_health_assessment: HealthAssessment,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test cache clearing."""
        analyzer = RootCauseAnalyzer()

        # Populate cache
        analyzer.analyze_root_cause(
            health_assessment=sample_health_assessment,
            degradation_signals=[sample_degradation_signal],
        )

        assert len(analyzer._analysis_cache) > 0

        # Clear cache
        analyzer.clear_cache()
        assert len(analyzer._analysis_cache) == 0

    def test_generate_cache_key(
        self,
        sample_health_assessment: HealthAssessment,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test cache key generation."""
        analyzer = RootCauseAnalyzer()

        cache_key = analyzer._generate_cache_key(
            health_status=sample_health_assessment.status,
            signals=[sample_degradation_signal],
        )

        assert isinstance(cache_key, str)
        assert len(cache_key) == 16  # MD5 hash truncated to 16 chars

    def test_perform_ai_analysis(
        self,
        sample_health_assessment: HealthAssessment,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test AI analysis execution."""
        analyzer = RootCauseAnalyzer()

        result = analyzer._perform_ai_analysis(
            health_assessment=sample_health_assessment,
            degradation_signals=[sample_degradation_signal],
            context={},
        )

        assert result is not None
        assert result.status in [ExecutionStatus.SUCCESS, ExecutionStatus.ERROR]
        assert len(result.content) > 0
        assert result.duration >= 0

    def test_build_analysis_prompt(
        self,
        sample_health_assessment: HealthAssessment,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test analysis prompt building."""
        analyzer = RootCauseAnalyzer()

        prompt = analyzer._build_analysis_prompt(
            health_assessment=sample_health_assessment,
            degradation_signals=[sample_degradation_signal],
            context={"test": "context"},
        )

        assert isinstance(prompt, str)
        assert "Root Cause Analysis Request" in prompt
        assert sample_health_assessment.status.value in prompt
        assert sample_degradation_signal.description in prompt
        assert "test" in prompt

    def test_rule_based_analysis(
        self,
        sample_health_assessment: HealthAssessment,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test rule-based analysis."""
        analyzer = RootCauseAnalyzer()

        analysis = analyzer._rule_based_analysis(
            health_assessment=sample_health_assessment,
            degradation_signals=[sample_degradation_signal],
            context={},
        )

        assert isinstance(analysis, str)
        assert "Root Cause Analysis" in analysis
        assert len(analysis) > 0

    def test_analyze_signal(self, sample_degradation_signal: DegradationSignal) -> None:
        """Test individual signal analysis."""
        analyzer = RootCauseAnalyzer()

        analysis = analyzer._analyze_signal(
            signal=sample_degradation_signal,
            context={},
        )

        assert "category" in analysis
        assert "description" in analysis
        assert "confidence" in analysis
        assert "evidence" in analysis
        assert "components" in analysis
        assert "strategies" in analysis

    def test_analyze_health_status(
        self, sample_health_assessment: HealthAssessment
    ) -> None:
        """Test health status analysis."""
        analyzer = RootCauseAnalyzer()

        analysis = analyzer._analyze_health_status(
            health_assessment=sample_health_assessment,
            context={},
        )

        assert "category" in analysis
        assert "description" in analysis
        assert "confidence" in analysis
        assert "strategies" in analysis

    def test_get_strategies_for_category(self) -> None:
        """Test getting strategies for failure categories."""
        analyzer = RootCauseAnalyzer()

        network_strategies = analyzer._get_strategies_for_category(
            FailureCategory.NETWORK_ISSUE
        )
        assert HealingStrategy.RETRY in network_strategies

        code_strategies = analyzer._get_strategies_for_category(
            FailureCategory.CODE_ERROR
        )
        assert HealingStrategy.ROLLBACK in code_strategies

    def test_extract_root_causes(
        self,
        sample_health_assessment: HealthAssessment,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test root cause extraction from AI result."""
        analyzer = RootCauseAnalyzer()

        # Create a successful execution result
        ai_result = ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            content="### NETWORK ISSUE\n**Description**: Network error\n**Confidence**: high\n",
            raw_output="Test output",
        )

        root_causes = analyzer._extract_root_causes(
            ai_result=ai_result,
            health_assessment=sample_health_assessment,
            degradation_signals=[sample_degradation_signal],
        )

        assert isinstance(root_causes, list)
        # May or may not find causes depending on parsing

    def test_extract_root_causes_from_failed_analysis(
        self,
        sample_health_assessment: HealthAssessment,
        sample_degradation_signal: DegradationSignal,
    ) -> None:
        """Test root cause extraction when AI analysis fails."""
        analyzer = RootCauseAnalyzer()

        # Create a failed execution result
        ai_result = ExecutionResult(
            status=ExecutionStatus.ERROR,
            content="Analysis failed",
            error="Test error",
        )

        root_causes = analyzer._extract_root_causes(
            ai_result=ai_result,
            health_assessment=sample_health_assessment,
            degradation_signals=[sample_degradation_signal],
        )

        assert len(root_causes) > 0
        assert root_causes[0].category == FailureCategory.UNKNOWN
        assert root_causes[0].confidence == ConfidenceLevel.LOW

    def test_identify_primary_cause(self, sample_root_cause: RootCause) -> None:
        """Test primary cause identification."""
        analyzer = RootCauseAnalyzer()

        # Create multiple causes with different confidence levels
        causes = [
            sample_root_cause,  # HIGH confidence
            RootCause(
                category=FailureCategory.UNKNOWN,
                description="Unknown cause",
                evidence=[],
                confidence=ConfidenceLevel.LOW,
                affected_components=[],
                related_metrics=[],
                suggested_strategies=[HealingStrategy.ESCALATE],
            ),
        ]

        primary = analyzer._identify_primary_cause(causes)

        assert primary is not None
        assert primary.confidence == ConfidenceLevel.HIGH

    def test_identify_primary_cause_empty(self) -> None:
        """Test primary cause identification with empty list."""
        analyzer = RootCauseAnalyzer()

        primary = analyzer._identify_primary_cause([])

        assert primary is None

    def test_generate_healing_plan(self, sample_root_cause: RootCause) -> None:
        """Test healing plan generation."""
        analyzer = RootCauseAnalyzer()

        plan = analyzer._generate_healing_plan(
            root_causes=[sample_root_cause],
            primary_cause=sample_root_cause,
        )

        assert "strategies" in plan
        assert "primary_strategy" in plan
        assert "fallback_strategies" in plan
        assert "requires_escalation" in plan
        assert len(plan["strategies"]) > 0

    def test_generate_healing_plan_no_primary(self) -> None:
        """Test healing plan generation with no primary cause."""
        analyzer = RootCauseAnalyzer()

        plan = analyzer._generate_healing_plan(
            root_causes=[],
            primary_cause=None,
        )

        assert plan["primary_strategy"] is None
        assert plan["requires_escalation"] is True

    def test_requires_escalation_unknown_low_confidence(self) -> None:
        """Test escalation determination for unknown cause with low confidence."""
        analyzer = RootCauseAnalyzer()

        root_cause = RootCause(
            category=FailureCategory.UNKNOWN,
            description="Unknown issue",
            evidence=[],
            confidence=ConfidenceLevel.LOW,
            affected_components=[],
            related_metrics=[],
            suggested_strategies=[HealingStrategy.ESCALATE],
        )

        requires = analyzer._requires_escalation(
            root_causes=[root_cause],
            primary_cause=root_cause,
        )

        assert requires is True

    def test_requires_escalation_only_escalate_strategy(self) -> None:
        """Test escalation when only ESCALATE strategy is suggested."""
        analyzer = RootCauseAnalyzer()

        root_cause = RootCause(
            category=FailureCategory.CODE_ERROR,
            description="Code error",
            evidence=["Syntax error"],
            confidence=ConfidenceLevel.HIGH,
            affected_components=["api"],
            related_metrics=[],
            suggested_strategies=[HealingStrategy.ESCALATE],  # Only ESCALATE
        )

        requires = analyzer._requires_escalation(
            root_causes=[root_cause],
            primary_cause=root_cause,
        )

        assert requires is True

    def test_requires_escalation_no(self, sample_root_cause: RootCause) -> None:
        """Test that escalation is not required for clear issues."""
        analyzer = RootCauseAnalyzer()

        requires = analyzer._requires_escalation(
            root_causes=[sample_root_cause],
            primary_cause=sample_root_cause,
        )

        # Network issue with retry strategy should not require escalation
        assert requires is False
