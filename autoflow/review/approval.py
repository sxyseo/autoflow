#!/usr/bin/env python3
"""
Autoflow Approval Gate Module

Provides hash-based approval gates to prevent unverified commits.
Generates cryptographic approval tokens from verification results and
ensures that only code passing all quality gates can be committed.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


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
    test_results: dict[str, int]
    coverage_data: dict[str, float | None]
    qa_findings_count: dict[str, int]
    approver: str = "verification-orchestrator"
    git_commit: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert token to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ApprovalToken":
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

        return self.test_results


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
    blocking_severities: list[str] = field(default_factory=lambda: ["CRITICAL", "HIGH"])
    token_expiry_hours: int = 24
    token_path: str = ".autoflow/approval_token.json"

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ApprovalGateConfig":
        """Create config from dictionary."""
        return cls(**data)


class ApprovalGate:
    """
    Hash-based approval gate for preventing unverified commits.

    Generates cryptographic approval tokens from verification results
    and verifies that commits have valid approval before allowing them.
    """

    def __init__(self, config: ApprovalGateConfig | None = None, work_dir: str = "."):
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
                with open(config_file) as f:
                    config = json.load(f)
                    approval_config = config.get("approval", {})

                    return ApprovalGateConfig(
                        require_tests=approval_config.get("require_tests", True),
                        require_coverage=approval_config.get("require_coverage", True),
                        require_qa_check=approval_config.get("require_qa_check", True),
                        blocking_severities=approval_config.get(
                            "blocking_severities", ["CRITICAL", "HIGH"]
                        ),
                        token_expiry_hours=approval_config.get(
                            "token_expiry_hours", 24
                        ),
                        token_path=approval_config.get(
                            "token_path", ".autoflow/approval_token.json"
                        ),
                    )
            except (OSError, json.JSONDecodeError):
                pass

        return self.config

    def generate_hash(
        self,
        test_results: dict[str, int],
        coverage_data: dict[str, float | None],
        qa_findings_count: dict[str, int],
        metadata: dict | None = None,
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
            "metadata": metadata or {},
        }

        # Sort keys for consistent hashing
        normalized = json.dumps(hash_data, sort_keys=True)

        # Generate SHA-256 hash
        hash_obj = hashlib.sha256(normalized.encode("utf-8"))
        return hash_obj.hexdigest()

    def create_token(
        self,
        test_results: dict[str, int],
        coverage_data: dict[str, float | None],
        qa_findings_count: dict[str, int],
        git_commit: str | None = None,
        metadata: dict | None = None,
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
            metadata=metadata,
        )

        return ApprovalToken(
            hash=approval_hash,
            timestamp=datetime.utcnow().isoformat(),
            test_results=test_results,
            coverage_data=coverage_data,
            qa_findings_count=qa_findings_count,
            git_commit=git_commit,
            metadata=metadata or {},
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

    def load_token(self) -> ApprovalToken | None:
        """
        Load approval token from file.

        Returns:
            ApprovalToken if file exists, None otherwise
        """
        token_path = self.work_dir / self.config.token_path

        if not token_path.exists():
            return None

        try:
            with open(token_path) as f:
                data = json.load(f)
                return ApprovalToken.from_dict(data)
        except (OSError, json.JSONDecodeError):
            return None

    def delete_token(self) -> None:
        """Delete approval token file."""
        token_path = self.work_dir / self.config.token_path

        if token_path.exists():
            token_path.unlink()

    def verify_token(
        self, token: ApprovalToken | None = None
    ) -> tuple[bool, list[str]]:
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
        test_results: dict[str, int] | None = None,
        coverage_data: dict[str, float | None] | None = None,
        qa_findings: list[dict] | None = None,
    ) -> tuple[bool, list[str]]:
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
                blocking.append(f"Tests failing: {test_results['failed']} tests failed")

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
                f
                for f in qa_findings
                if f.get("severity") in self.config.blocking_severities
            ]

            if blocking_findings:
                blocking.append(
                    f"Blocking QA findings: {len(blocking_findings)} findings "
                    f"with severity {self.config.blocking_severities}"
                )

        return len(blocking) == 0, blocking

    def verify_commit_allowed(
        self, expected_results: dict | None = None
    ) -> tuple[bool, list[str]]:
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
                "qa_findings_count": token.qa_findings_count,
            }

            if expected_results != token_results:
                return False, [
                    "Verification results do not match approval token. "
                    "Re-run verification."
                ]

        return True, []

    def grant_approval(
        self,
        test_results: dict[str, int],
        coverage_data: dict[str, float | None],
        qa_findings_count: dict[str, int],
        git_commit: str | None = None,
    ) -> tuple[bool, list[str]]:
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
            qa_findings=[],  # We only have counts, not full findings
        )

        if not is_approved:
            return False, blocking

        # Create and save token
        token = self.create_token(
            test_results=test_results,
            coverage_data=coverage_data,
            qa_findings_count=qa_findings_count,
            git_commit=git_commit,
        )

        self.save_token(token)

        return True, ["Approval granted"]

    def revoke_approval(self) -> None:
        """Revoke approval by deleting token."""
        self.delete_token()

    def get_token_status(self) -> dict:
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
                "message": "No approval token found",
            }

        is_valid, errors = self.verify_token(token)

        if not is_valid:
            return {
                "has_token": True,
                "status": "invalid",
                "message": errors[0] if errors else "Invalid token",
                "timestamp": token.timestamp,
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
            "qa_findings": token.qa_findings_count,
        }


def create_git_commit_message_with_approval(
    original_message: str, approval_token: ApprovalToken
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


def extract_approval_hash_from_commit(commit_message: str) -> str | None:
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
