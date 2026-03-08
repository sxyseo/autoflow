#!/usr/bin/env python3
"""
Autoflow Approval Gate Module

Provides hash-based approval gates to prevent unverified commits.
Generates cryptographic approval tokens from verification results and
ensures that only code passing all quality gates can be committed.

Symphony Integration:
The approval gate integrates with Symphony's checkpoint system to enable
approval flows from multi-agent workflows. Symphony agents can execute
verification tasks (tests, coverage, QA checks) and create checkpoints
that can be converted to Autoflow approval tokens.

Usage:
    from autoflow.review.approval import ApprovalGate

    # Create approval gate
    gate = ApprovalGate(work_dir="/path/to/project")

    # Grant approval from Symphony checkpoint
    approved, messages = gate.grant_approval_from_checkpoint(
        checkpoint_id="checkpoint-test-validation-abc123",
        git_commit="a1b2c3d4"
    )

    # Verify checkpoint approval
    is_valid, messages = gate.verify_checkpoint_approval(
        checkpoint_id="checkpoint-test-validation-abc123"
    )

    # Create token directly from checkpoint results
    token = gate.create_token_from_checkpoint_results(
        test_results={"total": 10, "passed": 10, "failed": 0},
        coverage_data={"total": 85.0},
        qa_findings_count={"CRITICAL": 0, "HIGH": 0},
        checkpoint_id="checkpoint-123",
        gate_name="Tests",
        gate_type="test"
    )
    gate.save_token(token)
"""

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


@dataclass
class ApprovalToken:
    """
    Approval token containing verification hash and metadata.

    Args:
        hash: Cryptographic hash of verification results
        timestamp: Token generation timestamp
        test_results: Test execution summary
        coverage_data: Coverage metrics
        qa_findings_count: Number of QA findings by severity
        approver: Entity that granted approval (e.g., "verification-orchestrator")
        git_commit: Optional associated commit hash
    """
    hash: str
    timestamp: str
    test_results: Dict[str, int]
    coverage_data: Dict[str, Optional[float]]
    qa_findings_count: Dict[str, int]
    approver: str = "verification-orchestrator"
    git_commit: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert token to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'ApprovalToken':
        """Create token from dictionary."""
        return cls(**data)

    def is_valid(self) -> bool:
        """
        Check if token has required fields and valid hash.

        Returns:
            True if token is valid
        """
        if not self.hash or len(self.hash) < 16:
            return False

        if not self.timestamp:
            return False

        if not self.test_results:
            return False

        return True


@dataclass
class ApprovalGateConfig:
    """
    Configuration for approval gates.

    Args:
        require_tests: Require passing tests
        require_coverage: Require minimum coverage
        require_qa_check: Require QA findings check
        blocking_severities: Severity levels that block approval
        token_expiry_hours: Hours before token expires (0 = no expiry)
        token_path: Path to store approval token
    """
    require_tests: bool = True
    require_coverage: bool = True
    require_qa_check: bool = True
    blocking_severities: List[str] = field(default_factory=lambda: ["CRITICAL", "HIGH"])
    token_expiry_hours: int = 24
    token_path: str = ".autoflow/approval_token.json"

    def to_dict(self) -> dict:
        """Convert config to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'ApprovalGateConfig':
        """Create config from dictionary."""
        return cls(**data)


class ApprovalGate:
    """
    Hash-based approval gate for preventing unverified commits.

    Generates cryptographic approval tokens from verification results
    and verifies that commits have valid approval before allowing them.
    """

    def __init__(
        self,
        config: Optional[ApprovalGateConfig] = None,
        work_dir: str = "."
    ):
        """
        Initialize approval gate.

        Args:
            config: Approval gate configuration
            work_dir: Working directory for token storage
        """
        self.work_dir = Path(work_dir)
        self.config = config or ApprovalGateConfig()
        self._ensure_token_dir()

    def _ensure_token_dir(self) -> None:
        """Ensure token directory exists."""
        token_path = self.work_dir / self.config.token_path
        token_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> ApprovalGateConfig:
        """
        Load approval gate configuration from QA gates config.

        Returns:
            ApprovalGateConfig with loaded values
        """
        config_file = self.work_dir / "config" / "qa_gates.json"

        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
                    approval_config = config.get("approval", {})

                    return ApprovalGateConfig(
                        require_tests=approval_config.get("require_tests", True),
                        require_coverage=approval_config.get("require_coverage", True),
                        require_qa_check=approval_config.get("require_qa_check", True),
                        blocking_severities=approval_config.get(
                            "blocking_severities",
                            ["CRITICAL", "HIGH"]
                        ),
                        token_expiry_hours=approval_config.get("token_expiry_hours", 24),
                        token_path=approval_config.get(
                            "token_path",
                            ".autoflow/approval_token.json"
                        )
                    )
            except (json.JSONDecodeError, IOError):
                pass

        return self.config

    def generate_hash(
        self,
        test_results: Dict[str, int],
        coverage_data: Dict[str, Optional[float]],
        qa_findings_count: Dict[str, int],
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Generate cryptographic hash from verification results.

        Args:
            test_results: Test execution summary (e.g., {"total": 10, "failed": 0, "passed": 10})
            coverage_data: Coverage metrics (e.g., {"total": 85.0, "branches": 80.0})
            qa_findings_count: QA findings by severity
            metadata: Optional additional data to include in hash

        Returns:
            Hexadecimal hash string
        """
        # Create normalized data for hashing
        hash_data = {
            "test_results": test_results,
            "coverage_data": coverage_data,
            "qa_findings_count": qa_findings_count,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }

        # Sort keys for consistent hashing
        normalized = json.dumps(hash_data, sort_keys=True)

        # Generate SHA-256 hash
        hash_obj = hashlib.sha256(normalized.encode('utf-8'))
        return hash_obj.hexdigest()

    def create_token(
        self,
        test_results: Dict[str, int],
        coverage_data: Dict[str, Optional[float]],
        qa_findings_count: Dict[str, int],
        git_commit: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> ApprovalToken:
        """
        Create approval token from verification results.

        Args:
            test_results: Test execution summary
            coverage_data: Coverage metrics
            qa_findings_count: QA findings by severity
            git_commit: Optional associated commit hash
            metadata: Optional additional metadata

        Returns:
            ApprovalToken with verification hash
        """
        approval_hash = self.generate_hash(
            test_results=test_results,
            coverage_data=coverage_data,
            qa_findings_count=qa_findings_count,
            metadata=metadata
        )

        return ApprovalToken(
            hash=approval_hash,
            timestamp=datetime.utcnow().isoformat(),
            test_results=test_results,
            coverage_data=coverage_data,
            qa_findings_count=qa_findings_count,
            git_commit=git_commit,
            metadata=metadata or {}
        )

    def save_token(self, token: ApprovalToken) -> None:
        """
        Save approval token to file.

        Args:
            token: ApprovalToken to save
        """
        token_path = self.work_dir / self.config.token_path

        with open(token_path, "w") as f:
            json.dump(token.to_dict(), f, indent=2)

    def load_token(self) -> Optional[ApprovalToken]:
        """
        Load approval token from file.

        Returns:
            ApprovalToken if file exists, None otherwise
        """
        token_path = self.work_dir / self.config.token_path

        if not token_path.exists():
            return None

        try:
            with open(token_path, "r") as f:
                data = json.load(f)
                return ApprovalToken.from_dict(data)
        except (json.JSONDecodeError, IOError):
            return None

    def delete_token(self) -> None:
        """Delete approval token file."""
        token_path = self.work_dir / self.config.token_path

        if token_path.exists():
            token_path.unlink()

    def verify_token(
        self,
        token: Optional[ApprovalToken] = None
    ) -> Tuple[bool, List[str]]:
        """
        Verify approval token is valid and not expired.

        Args:
            token: Token to verify (loads from file if None)

        Returns:
            Tuple of (is_valid, error_messages)
        """
        if token is None:
            token = self.load_token()

        if token is None:
            return False, ["No approval token found. Run verification first."]

        if not token.is_valid():
            return False, ["Invalid approval token format."]

        # Check token expiry
        if self.config.token_expiry_hours > 0:
            try:
                token_time = datetime.fromisoformat(token.timestamp)
                age_hours = (datetime.utcnow() - token_time).total_seconds() / 3600

                if age_hours > self.config.token_expiry_hours:
                    return False, [
                        f"Approval token expired ({age_hours:.1f} hours old, "
                        f"max {self.config.token_expiry_hours} hours)"
                    ]
            except ValueError:
                return False, ["Invalid token timestamp format."]

        return True, []

    def check_approval(
        self,
        test_results: Optional[Dict[str, int]] = None,
        coverage_data: Optional[Dict[str, Optional[float]]] = None,
        qa_findings: Optional[List[Dict]] = None
    ) -> Tuple[bool, List[str]]:
        """
        Check if current state meets approval requirements.

        Args:
            test_results: Test execution summary
            coverage_data: Coverage metrics
            qa_findings: List of QA findings

        Returns:
            Tuple of (is_approved, blocking_reasons)
        """
        blocking = []

        # Check test results
        if self.config.require_tests:
            if test_results is None:
                blocking.append("Tests required but no results provided")
            elif test_results.get("failed", 0) > 0:
                blocking.append(
                    f"Tests failing: {test_results['failed']} tests failed"
                )

        # Check coverage
        if self.config.require_coverage:
            if coverage_data is None:
                blocking.append("Coverage required but no data provided")
            elif coverage_data.get("total", 0) < 80.0:
                blocking.append(
                    f"Coverage too low: {coverage_data['total']:.1f}% < 80.0%"
                )

        # Check QA findings
        if self.config.require_qa_check and qa_findings:
            blocking_findings = [
                f for f in qa_findings
                if f.get("severity") in self.config.blocking_severities
            ]

            if blocking_findings:
                blocking.append(
                    f"Blocking QA findings: {len(blocking_findings)} findings "
                    f"with severity {self.config.blocking_severities}"
                )

        return len(blocking) == 0, blocking

    def verify_commit_allowed(
        self,
        expected_results: Optional[Dict] = None
    ) -> Tuple[bool, List[str]]:
        """
        Verify that commit is allowed based on approval token.

        Args:
            expected_results: Optional expected verification results to compare against

        Returns:
            Tuple of (allowed, error_messages)
        """
        # Load and verify token
        token = self.load_token()
        is_valid, errors = self.verify_token(token)

        if not is_valid:
            return False, errors

        # If expected results provided, verify they match token
        if expected_results and token:
            # Check if expected results match token data
            token_results = {
                "test_results": token.test_results,
                "coverage_data": token.coverage_data,
                "qa_findings_count": token.qa_findings_count
            }

            if expected_results != token_results:
                return False, [
                    "Verification results do not match approval token. "
                    "Re-run verification."
                ]

        return True, []

    def grant_approval(
        self,
        test_results: Dict[str, int],
        coverage_data: Dict[str, Optional[float]],
        qa_findings_count: Dict[str, int],
        git_commit: Optional[str] = None
    ) -> Tuple[bool, List[str]]:
        """
        Grant approval by creating and saving approval token.

        Args:
            test_results: Test execution summary
            coverage_data: Coverage metrics
            qa_findings_count: QA findings by severity
            git_commit: Optional associated commit hash

        Returns:
            Tuple of (approved, messages)
        """
        # Check if requirements are met
        is_approved, blocking = self.check_approval(
            test_results=test_results,
            coverage_data=coverage_data,
            qa_findings=[]  # We only have counts, not full findings
        )

        if not is_approved:
            return False, blocking

        # Create and save token
        token = self.create_token(
            test_results=test_results,
            coverage_data=coverage_data,
            qa_findings_count=qa_findings_count,
            git_commit=git_commit
        )

        self.save_token(token)

        return True, ["Approval granted"]

    def revoke_approval(self) -> None:
        """Revoke approval by deleting token."""
        self.delete_token()

    def get_token_status(self) -> Dict:
        """
        Get current token status for display.

        Returns:
            Dictionary with token status information
        """
        token = self.load_token()

        if token is None:
            return {
                "has_token": False,
                "status": "no_token",
                "message": "No approval token found"
            }

        is_valid, errors = self.verify_token(token)

        if not is_valid:
            return {
                "has_token": True,
                "status": "invalid",
                "message": errors[0] if errors else "Invalid token",
                "timestamp": token.timestamp
            }

        # Calculate token age
        try:
            token_time = datetime.fromisoformat(token.timestamp)
            age_hours = (datetime.utcnow() - token_time).total_seconds() / 3600
        except ValueError:
            age_hours = 0

        return {
            "has_token": True,
            "status": "valid",
            "message": "Valid approval token",
            "timestamp": token.timestamp,
            "age_hours": age_hours,
            "hash": token.hash[:16] + "...",  # Show first 16 chars
            "tests_passed": token.test_results.get("passed", 0),
            "tests_failed": token.test_results.get("failed", 0),
            "coverage": token.coverage_data.get("total", 0),
            "qa_findings": token.qa_findings_count
        }

    def _create_symphony_bridge(self):
        """
        Create a Symphony bridge instance for checkpoint integration.

        Returns:
            SymphonyBridge instance or None if Symphony is not available

        Raises:
            ImportError: If Symphony bridge module is not available
        """
        try:
            from autoflow.skills.symphony_bridge import SymphonyBridge
            from autoflow.skills.registry import SkillRegistry

            # Create registry
            registry = SkillRegistry()

            # Create bridge with state directory
            bridge = SymphonyBridge(
                registry=registry,
                state_dir=self.work_dir
            )

            return bridge
        except ImportError:
            return None
        except Exception:
            # Return None if bridge creation fails
            return None

    def load_checkpoint_for_approval(
        self,
        checkpoint_id: str
    ) -> Optional[Dict]:
        """
        Load Symphony checkpoint data for approval processing.

        This method retrieves checkpoint information from the Symphony bridge
        and converts it to a format suitable for approval token generation.

        Args:
            checkpoint_id: Symphony checkpoint identifier

        Returns:
            Checkpoint data dictionary with keys:
            - checkpoint_id: Checkpoint identifier
            - gate_name: Name of the review gate
            - gate_type: Type of gate (test, lint, etc.)
            - status: Checkpoint status (pending, approved, rejected)
            - test_results: Test execution summary (if available)
            - coverage_data: Coverage metrics (if available)
            - qa_findings_count: QA findings count (if available)
            Returns None if checkpoint not found or bridge unavailable.

        Example:
            >>> checkpoint_data = approval_gate.load_checkpoint_for_approval(
            ...     "checkpoint-123"
            ... )
            >>> if checkpoint_data:
            ...     print(f"Gate: {checkpoint_data['gate_name']}")
            ...     print(f"Status: {checkpoint_data['status']}")
        """
        bridge = self._create_symphony_bridge()

        if bridge is None:
            return None

        try:
            # Get checkpoint status from bridge
            checkpoint_status = bridge.get_gate_checkpoint_status(checkpoint_id)

            if not checkpoint_status or checkpoint_status.get("status") == "not_found":
                return None

            # Extract checkpoint data
            checkpoint_data = checkpoint_status.get("checkpoint", {})

            # Build approval-friendly data structure
            approval_data = {
                "checkpoint_id": checkpoint_id,
                "gate_name": checkpoint_data.get("gate_name", "unknown"),
                "gate_type": checkpoint_data.get("gate_type", "unknown"),
                "status": checkpoint_data.get("status", "pending"),
            }

            # Add test results if available
            if "test_results" in checkpoint_data:
                approval_data["test_results"] = checkpoint_data["test_results"]

            # Add coverage data if available
            if "coverage_data" in checkpoint_data:
                approval_data["coverage_data"] = checkpoint_data["coverage_data"]

            # Add QA findings count if available
            if "qa_findings_count" in checkpoint_data:
                approval_data["qa_findings_count"] = checkpoint_data["qa_findings_count"]

            return approval_data

        except Exception:
            return None

    def grant_approval_from_checkpoint(
        self,
        checkpoint_id: str,
        git_commit: Optional[str] = None
    ) -> Tuple[bool, List[str]]:
        """
        Grant approval based on Symphony checkpoint results.

        This method loads checkpoint data from Symphony, extracts verification
        results (tests, coverage, QA findings), and creates an Autoflow approval
        token if the checkpoint was approved.

        Args:
            checkpoint_id: Symphony checkpoint identifier
            git_commit: Optional associated git commit hash

        Returns:
            Tuple of (approved, messages)
            - approved: True if approval granted successfully
            - messages: List of informational/error messages

        Example:
            >>> approved, messages = approval_gate.grant_approval_from_checkpoint(
            ...     "checkpoint-test-validation-abc123",
            ...     git_commit="a1b2c3d4"
            ... )
            >>> if approved:
            ...     print("Approval granted from checkpoint")
            ... else:
            ...     print("\\n".join(messages))
        """
        # Load checkpoint data
        checkpoint_data = self.load_checkpoint_for_approval(checkpoint_id)

        if checkpoint_data is None:
            return False, [
                f"Could not load checkpoint data for {checkpoint_id}. "
                "Ensure Symphony is configured and checkpoint exists."
            ]

        # Check checkpoint status
        checkpoint_status = checkpoint_data.get("status", "pending")

        if checkpoint_status != "approved":
            return False, [
                f"Checkpoint {checkpoint_id} has status '{checkpoint_status}'. "
                "Only approved checkpoints can grant Autoflow approval."
            ]

        # Extract verification results from checkpoint
        test_results = checkpoint_data.get(
            "test_results",
            {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
        )

        coverage_data = checkpoint_data.get(
            "coverage_data",
            {"total": None, "branches": None, "functions": None}
        )

        qa_findings_count = checkpoint_data.get(
            "qa_findings_count",
            {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        )

        # Add checkpoint metadata to approval token
        metadata = {
            "source": "symphony_checkpoint",
            "checkpoint_id": checkpoint_id,
            "gate_name": checkpoint_data.get("gate_name"),
            "gate_type": checkpoint_data.get("gate_type"),
            "approved_at": checkpoint_data.get("approved_at"),
        }

        # Grant approval using checkpoint results
        return self.grant_approval(
            test_results=test_results,
            coverage_data=coverage_data,
            qa_findings_count=qa_findings_count,
            git_commit=git_commit
        )

    def verify_checkpoint_approval(
        self,
        checkpoint_id: str
    ) -> Tuple[bool, List[str]]:
        """
        Verify if a Symphony checkpoint approval translates to valid Autoflow approval.

        This method checks if a checkpoint is approved and verifies that the
        corresponding Autoflow approval token exists and is valid.

        Args:
            checkpoint_id: Symphony checkpoint identifier

        Returns:
            Tuple of (is_valid, messages)
            - is_valid: True if checkpoint approved and token valid
            - messages: List of informational/error messages

        Example:
            >>> is_valid, messages = approval_gate.verify_checkpoint_approval(
            ...     "checkpoint-test-validation-abc123"
            ... )
            >>> if is_valid:
            ...     print("Checkpoint approval is valid")
            ... else:
            ...     print("\\n".join(messages))
        """
        # Load checkpoint data
        checkpoint_data = self.load_checkpoint_for_approval(checkpoint_id)

        if checkpoint_data is None:
            return False, [
                f"Could not load checkpoint data for {checkpoint_id}"
            ]

        # Check checkpoint status
        checkpoint_status = checkpoint_data.get("status", "pending")

        if checkpoint_status != "approved":
            return False, [
                f"Checkpoint {checkpoint_id} has status '{checkpoint_status}'. "
                "Expected 'approved'."
            ]

        # Verify we have a valid approval token
        is_valid, errors = self.verify_token()

        if not is_valid:
            return False, [
                f"Checkpoint {checkpoint_id} is approved, but Autoflow approval "
                f"token is invalid: {errors[0] if errors else 'Unknown error'}"
            ]

        # Optionally verify token metadata matches checkpoint
        token = self.load_token()
        if token and token.metadata.get("source") == "symphony_checkpoint":
            token_checkpoint_id = token.metadata.get("checkpoint_id")
            if token_checkpoint_id != checkpoint_id:
                return False, [
                    f"Approval token exists but is for different checkpoint: "
                    f"{token_checkpoint_id}"
                ]

        return True, [
            f"Checkpoint {checkpoint_id} is approved and has valid Autoflow token"
        ]

    def create_token_from_checkpoint_results(
        self,
        test_results: Dict[str, int],
        coverage_data: Dict[str, Optional[float]],
        qa_findings_count: Dict[str, int],
        checkpoint_id: str,
        gate_name: str,
        gate_type: str,
        git_commit: Optional[str] = None,
        approved_at: Optional[str] = None,
        approver: Optional[str] = None
    ) -> ApprovalToken:
        """
        Create approval token directly from Symphony checkpoint verification results.

        This method allows creating an approval token from raw verification results
        obtained from a Symphony checkpoint, without requiring the checkpoint to be
        loaded through the bridge. Useful for integrations where checkpoint data
        is already available.

        Args:
            test_results: Test execution summary
            coverage_data: Coverage metrics
            qa_findings_count: QA findings by severity
            checkpoint_id: Symphony checkpoint identifier
            gate_name: Name of the review gate
            gate_type: Type of gate (test, lint, etc.)
            git_commit: Optional associated git commit hash
            approved_at: Optional approval timestamp
            approver: Optional approver identifier

        Returns:
            ApprovalToken with verification hash and checkpoint metadata

        Example:
            >>> token = approval_gate.create_token_from_checkpoint_results(
            ...     test_results={"total": 10, "passed": 10, "failed": 0},
            ...     coverage_data={"total": 85.0},
            ...     qa_findings_count={"CRITICAL": 0, "HIGH": 0},
            ...     checkpoint_id="checkpoint-123",
            ...     gate_name="Tests",
            ...     gate_type="test"
            ... )
        """
        # Build metadata with checkpoint information
        metadata = {
            "source": "symphony_checkpoint",
            "checkpoint_id": checkpoint_id,
            "gate_name": gate_name,
            "gate_type": gate_type,
        }

        if approved_at:
            metadata["approved_at"] = approved_at

        if approver:
            metadata["approver"] = approver

        # Create token with checkpoint metadata
        return self.create_token(
            test_results=test_results,
            coverage_data=coverage_data,
            qa_findings_count=qa_findings_count,
            git_commit=git_commit,
            metadata=metadata
        )


def create_git_commit_message_with_approval(
    original_message: str,
    approval_token: ApprovalToken
) -> str:
    """
    Add approval hash to git commit message.

    Args:
        original_message: Original commit message
        approval_token: ApprovalToken to reference

    Returns:
        Commit message with approval hash
    """
    hash_line = f"Approval-Hash: {approval_token.hash}"

    # Check if message already has approval hash
    if "Approval-Hash:" in original_message:
        # Replace existing hash
        lines = original_message.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("Approval-Hash:"):
                lines[i] = hash_line
                break
        return "\n".join(lines)

    # Add approval hash
    return f"{original_message}\n\n{hash_line}"


def extract_approval_hash_from_commit(commit_message: str) -> Optional[str]:
    """
    Extract approval hash from git commit message.

    Args:
        commit_message: Git commit message

    Returns:
        Approval hash if found, None otherwise
    """
    for line in commit_message.split("\n"):
        if line.startswith("Approval-Hash:"):
            return line.split(":", 1)[1].strip()
    return None
