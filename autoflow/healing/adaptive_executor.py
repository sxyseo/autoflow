"""Adaptive retry executor with learning integration for intelligent error recovery.

This module provides an adaptive retry executor that extends the base RetryActionExecutor
with learning capabilities from the recovery learning system. It adjusts retry parameters
based on historical patterns and can fall back to learned strategies when default retry
approaches fail.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from autoflow.healing.actions import ActionResult, HealingAction
    from autoflow.healing.diagnostic import RootCause
    from autoflow.healing.recovery_learner import RecoveryLearner

logger = logging.getLogger(__name__)


class AdaptiveRetryExecutor:
    """Executor for adaptive retry actions with learning integration.

    This executor extends the base RetryActionExecutor with intelligent
    parameter adjustment based on learned recovery patterns. It can:
    - Query the learning system for optimal retry parameters
    - Adjust retry strategy based on historical success rates
    - Fall back to alternative learned strategies when default retry fails

    Example:
        executor = AdaptiveRetryExecutor(learner=recovery_learner)
        result = await executor.execute(
            action=retry_action,
            root_cause=diagnostic_result.primary_cause
        )
    """

    def __init__(
        self,
        learner: RecoveryLearner | None = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> None:
        """Initialize the adaptive retry executor.

        Args:
            learner: Optional RecoveryLearner instance for learning integration.
                If None, executor falls back to non-adaptive behavior.
            max_retries: Default maximum number of retry attempts.
            base_delay: Default base delay for exponential backoff in seconds.
        """
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._learner = learner

        # Import RetryActionExecutor to inherit behavior
        # We use composition over inheritance to avoid circular imports
        from autoflow.healing.actions import RetryActionExecutor

        self._base_executor = RetryActionExecutor()
        # Override defaults if provided
        if max_retries != 3:
            self._base_executor._max_retries = max_retries
        if base_delay != 1.0:
            self._base_executor._base_delay = base_delay

    async def execute(
        self,
        action: "HealingAction",
        root_cause: "RootCause | None" = None,
        context: dict[str, Any] | None = None,
    ) -> "ActionResult":
        """Execute an adaptive retry action with learning integration.

        This method enhances the base retry execution by:
        1. Querying the learning system for optimal parameters
        2. Adjusting retry configuration based on learned patterns
        3. Falling back to learned strategies when default retry fails
        4. Recording the attempt for future learning

        Args:
            action: The retry action to execute.
            root_cause: Optional root cause analysis for learning integration.
            context: Additional context about the error.

        Returns:
            ActionResult containing execution details.
        """
        logger.info(f"Executing adaptive retry action: {action.name}")

        # Adjust parameters based on learning if available
        if self._learner and root_cause:
            adjusted_params = self._adjust_parameters_from_learning(
                action, root_cause, context or {}
            )
            if adjusted_params:
                # Update action parameters with learned values
                action.parameters.update(adjusted_params)
                logger.info(
                    f"Adjusted retry parameters based on learning: {adjusted_params}"
                )

        # Execute the base retry logic
        result = await self._base_executor.execute(action)

        # Record attempt for learning if learner is available
        if self._learner and root_cause:
            try:
                from autoflow.healing.recovery_learner import RecoveryOutcome

                # Extract pattern from root cause
                pattern_info = self._learner.extract_pattern(root_cause, context or {})
                pattern_id = pattern_info["pattern_id"]

                # Record the attempt
                self._learner.record_attempt(
                    pattern_id=pattern_id,
                    strategy_used="adaptive_retry",
                    action_type="RETRY",
                    parameters=action.parameters,
                    outcome=RecoveryOutcome.SUCCESS if result.success else RecoveryOutcome.FAILED,
                    success=result.success,
                    execution_time=result.execution_time,
                    error=result.error,
                    changes_made=result.changes_made,
                    verification_passed=result.verification_passed,
                    outcome_details=result.message,
                    metadata={"root_cause": root_cause.to_dict(), "context": context or {}},
                )
            except Exception as e:
                # Don't fail the retry if learning recording fails
                logger.warning(f"Failed to record retry attempt for learning: {e}")

        # Fallback to learned strategies if default retry failed
        if not result.success and self._learner and root_cause:
            logger.info("Default retry failed, attempting fallback to learned strategies")
            fallback_result = await self.try_learned_strategy(
                action=action,
                root_cause=root_cause,
                context=context,
            )

            if fallback_result and fallback_result.success:
                logger.info("Fallback to learned strategy succeeded")
                return fallback_result
            elif fallback_result:
                logger.info("Fallback to learned strategy also failed")
                # Return the fallback result even if it failed, as it has more context
                result = fallback_result
            else:
                logger.info("No suitable learned strategy found for fallback")

        return result

    async def verify(self, action: "HealingAction") -> bool:
        """Verify that the adaptive retry action achieved its intended outcome.

        Args:
            action: The adaptive retry action to verify.

        Returns:
            True if verification passed.
        """
        return await self._base_executor.verify(action)

    async def rollback(self, action: "HealingAction") -> "ActionResult":
        """Rollback an adaptive retry action.

        Args:
            action: The adaptive retry action to rollback.

        Returns:
            ActionResult containing rollback details.
        """
        logger.info(f"Rolling back adaptive retry action: {action.name}")
        return await self._base_executor.rollback(action)

    def _adjust_parameters_from_learning(
        self,
        action: "HealingAction",
        root_cause: "RootCause",
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Adjust retry parameters based on learned patterns.

        Queries the learning system for optimal retry parameters for this
        error pattern and adjusts the action configuration accordingly.

        Args:
            action: The retry action to adjust parameters for.
            root_cause: The root cause analysis for this error.
            context: Additional context about the error.

        Returns:
            Dictionary of adjusted parameters, or None if no learning data available.
        """
        if not self._learner:
            return None

        try:
            # Get recommended strategy from learning system
            from autoflow.healing.recovery_learner import PatternConfidence

            recommendation = self._learner.recommend_strategy(
                root_cause=root_cause,
                context=context,
                min_confidence=PatternConfidence.MEDIUM,  # Require at least medium confidence
            )

            if not recommendation:
                logger.debug(
                    f"No learned strategy available for error pattern: {root_cause.category.value}"
                )
                return None

            strategy = recommendation["strategy"]
            optimal_params = strategy.get("optimal_parameters", {})

            # Extract retry-relevant parameters
            adjusted = {}
            if "max_retries" in optimal_params:
                adjusted["max_retries"] = optimal_params["max_retries"]
            if "base_delay" in optimal_params:
                adjusted["base_delay"] = optimal_params["base_delay"]
            if "backoff_multiplier" in optimal_params:
                adjusted["backoff_multiplier"] = optimal_params["backoff_multiplier"]

            # Log the adjustment rationale
            logger.info(
                f"Applied learned parameters (success rate: {recommendation['success_rate']:.1%}, "
                f"confidence: {recommendation['confidence']}): {adjusted}"
            )

            return adjusted if adjusted else None

        except Exception as e:
            logger.warning(f"Failed to adjust parameters from learning: {e}")
            return None

    async def try_learned_strategy(
        self,
        action: "HealingAction",
        root_cause: "RootCause",
        context: dict[str, Any] | None = None,
    ) -> "ActionResult | None":
        """Try an alternative learned strategy when default retry fails.

        This method is called when the default adaptive retry fails. It queries
        the learning system for alternative strategies that have worked for
        similar error patterns.

        Args:
            action: The original retry action that failed.
            root_cause: The root cause analysis for this error.
            context: Additional context about the error.

        Returns:
            ActionResult from the alternative strategy, or None if no suitable
            alternative found.
        """
        if not self._learner:
            return None

        logger.info("Attempting to find alternative learned strategy...")

        try:
            # Get recommended strategy with lower confidence threshold
            from autoflow.healing.recovery_learner import PatternConfidence

            recommendation = self._learner.recommend_strategy(
                root_cause=root_cause,
                context=context or {},
                min_confidence=PatternConfidence.LOW,  # Accept lower confidence for fallback
            )

            if not recommendation:
                logger.info("No alternative learned strategy found")
                return None

            strategy = recommendation["strategy"]

            # Check if this is a different strategy than what was already tried
            if strategy["strategy_name"] == "adaptive_retry":
                logger.info("No alternative strategy available (same as retry)")
                return None

            logger.info(
                f"Trying alternative strategy: {strategy['strategy_name']} "
                f"(success rate: {recommendation['success_rate']:.1%})"
            )

            # Create a new action for the alternative strategy
            from autoflow.healing.actions import ActionType, HealingAction

            alternative_action = HealingAction(
                action_type=ActionType.RETRY,  # Use retry as base type
                name=f"Alternative: {strategy['strategy_name']}",
                description=f"Alternative retry strategy based on learning: {strategy['description']}",
                severity=action.severity,
                parameters=strategy["optimal_parameters"],
                preconditions=action.preconditions,
                expected_outcome=action.expected_outcome,
                rollback_strategy=action.rollback_strategy,
                timeout=action.timeout,
                requires_approval=action.requires_approval,
            )

            # Execute the alternative strategy
            result = await self._base_executor.execute(alternative_action)

            # Record the attempt
            from autoflow.healing.recovery_learner import RecoveryOutcome

            pattern_info = self._learner.extract_pattern(root_cause, context or {})
            pattern_id = pattern_info["pattern_id"]

            self._learner.record_attempt(
                pattern_id=pattern_id,
                strategy_used=strategy["strategy_name"],
                action_type=strategy["strategy_type"],
                parameters=strategy["optimal_parameters"],
                outcome=RecoveryOutcome.SUCCESS if result.success else RecoveryOutcome.FAILED,
                success=result.success,
                execution_time=result.execution_time,
                error=result.error,
                changes_made=result.changes_made,
                verification_passed=result.verification_passed,
                outcome_details=result.message,
                metadata={
                    "root_cause": root_cause.to_dict(),
                    "context": context or {},
                    "alternative_strategy": True,
                },
            )

            return result

        except Exception as e:
            logger.error(f"Failed to execute alternative learned strategy: {e}")
            return None

    def adjust_parameters(
        self,
        max_retries: int | None = None,
        base_delay: float | None = None,
    ) -> None:
        """Adjust the default retry parameters.

        Args:
            max_retries: New maximum number of retry attempts.
            base_delay: New base delay for exponential backoff.
        """
        if max_retries is not None:
            self._max_retries = max_retries
            self._base_executor._max_retries = max_retries
        if base_delay is not None:
            self._base_delay = base_delay
            self._base_executor._base_delay = base_delay

        logger.info(
            f"Adjusted retry parameters: max_retries={self._max_retries}, "
            f"base_delay={self._base_delay}"
        )
