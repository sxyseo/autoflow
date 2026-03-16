#!/usr/bin/env python3
"""
Autoflow Duplication Detection Module

Provides code duplication detection using token-based similarity analysis
and AST-based structural comparison. Detects code duplication in AI-generated
changes before they reach the codebase, addressing the critical problem where
AI tools increase code duplication by 8x.

Integration:
- Works with QA findings system to report duplication issues
- Configurable thresholds per project
- Supports CLI and programmatic access
"""

import ast
import json
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


@dataclass
class DuplicationThreshold:
    """
    Duplication threshold configuration.

    Args:
        minimum_similarity: Minimum similarity percentage to flag as duplication (0.0-1.0)
        minimum_lines: Minimum number of lines to consider for duplication detection
        token_similarity_weight: Weight for token-based similarity (0.0-1.0)
        structure_similarity_weight: Weight for structure-based similarity (0.0-1.0)
        file_overrides: Per-file threshold overrides (optional)
            Maps file patterns to threshold overrides.
            Patterns can be exact file paths or glob patterns.
            Example: {"autoflow/core/*": {"minimum_similarity": 0.9}}
    """

    minimum_similarity: float = 0.7
    minimum_lines: int = 5
    token_similarity_weight: float = 0.5
    structure_similarity_weight: float = 0.5
    file_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get_threshold_for_file(self, file_path: str) -> "DuplicationThreshold":
        """
        Get threshold configuration for a specific file.

        Checks file overrides for matching patterns and returns
        a threshold with overrides applied. Patterns are matched
        in order, with first match taking precedence.

        Args:
            file_path: Path to file (e.g., "autoflow/core/module.py")

        Returns:
            DuplicationThreshold with file-specific overrides applied
        """
        # Normalize path for matching
        normalized_path = file_path.replace("\\", "/")

        # Check for exact match first
        if normalized_path in self.file_overrides:
            override = self.file_overrides[normalized_path]
            return DuplicationThreshold(
                minimum_similarity=override.get("minimum_similarity", self.minimum_similarity),
                minimum_lines=override.get("minimum_lines", self.minimum_lines),
                token_similarity_weight=override.get("token_similarity_weight", self.token_similarity_weight),
                structure_similarity_weight=override.get("structure_similarity_weight", self.structure_similarity_weight),
                file_overrides=self.file_overrides,
            )

        # Check for pattern matches (e.g., "autoflow/core/*")
        # Sort patterns by specificity (longer first)
        patterns = sorted(
            self.file_overrides.keys(), key=lambda p: len(p), reverse=True
        )

        import fnmatch

        for pattern in patterns:
            if fnmatch.fnmatch(normalized_path, pattern):
                override = self.file_overrides[pattern]
                return DuplicationThreshold(
                    minimum_similarity=override.get("minimum_similarity", self.minimum_similarity),
                    minimum_lines=override.get("minimum_lines", self.minimum_lines),
                    token_similarity_weight=override.get("token_similarity_weight", self.token_similarity_weight),
                    structure_similarity_weight=override.get("structure_similarity_weight", self.structure_similarity_weight),
                    file_overrides=self.file_overrides,
                )

        # No override found, return self
        return self

    def check_passes(
        self,
        similarity: float,
        lines: int | None = None,
        file_path: str | None = None,
    ) -> bool:
        """
        Check if duplication meets threshold for flagging.

        Args:
            similarity: Similarity percentage (0.0-1.0)
            lines: Number of lines in the duplicated code
            file_path: Optional file path for per-file thresholds

        Returns:
            True if duplication should be flagged (exceeds threshold)
        """
        # Get file-specific threshold if file_path provided
        threshold = self.get_threshold_for_file(file_path) if file_path else self

        # Check similarity threshold
        if similarity < threshold.minimum_similarity:
            return False

        # Check minimum lines if provided
        if lines is not None and lines < threshold.minimum_lines:
            return False

        return True

    def get_warning_threshold(self) -> float:
        """
        Get warning threshold (slightly below minimum).

        Returns:
            Warning threshold as percentage (0.0-1.0)
        """
        return max(0.0, self.minimum_similarity - 0.1)


@dataclass
class DuplicationFinding:
    """
    A single code duplication finding.

    Args:
        file: File path where duplication was found
        line_start: Start line of duplicated code
        line_end: End line of duplicated code
        similarity: Similarity percentage (0.0-1.0)
        duplicated_in: File path where the duplicate code exists
        duplicated_line_start: Start line in the duplicated file
        duplicated_line_end: End line in the duplicated file
        snippet: Snippet of the duplicated code
        category: Type of duplication (e.g., "exact", "structural", "token")
    """

    file: str
    line_start: int
    line_end: int
    similarity: float
    duplicated_in: str
    duplicated_line_start: int
    duplicated_line_end: int
    snippet: str
    category: str = "structural"

    def to_dict(self) -> dict:
        """Convert finding to dictionary for JSON serialization."""
        return {
            "file": self.file,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "similarity": self.similarity,
            "duplicated_in": self.duplicated_in,
            "duplicated_line_start": self.duplicated_line_start,
            "duplicated_line_end": self.duplicated_line_end,
            "snippet": self.snippet,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DuplicationFinding":
        """
        Create finding from dictionary.

        Args:
            data: Dictionary with finding data

        Returns:
            DuplicationFinding instance
        """
        return cls(
            file=data["file"],
            line_start=data["line_start"],
            line_end=data["line_end"],
            similarity=data["similarity"],
            duplicated_in=data["duplicated_in"],
            duplicated_line_start=data["duplicated_line_start"],
            duplicated_line_end=data["duplicated_line_end"],
            snippet=data["snippet"],
            category=data.get("category", "structural"),
        )

    def __str__(self) -> str:
        """Return string representation of finding."""
        location = f"{self.file}:{self.line_start}-{self.line_end}"
        dup_location = f"{self.duplicated_in}:{self.duplicated_line_start}-{self.duplicated_line_end}"
        return f"[{self.category}] {location} ~ {dup_location} ({self.similarity:.1%} similar)"


@dataclass
class DuplicationReport:
    """
    Collection of code duplication findings.

    Args:
        findings: List of duplication findings
        total_duplication: Overall duplication score (0.0-1.0)
        files_analyzed: Number of files analyzed
        timestamp: Report generation timestamp
    """

    findings: list[DuplicationFinding] = field(default_factory=list)
    total_duplication: float = 0.0
    files_analyzed: int = 0
    timestamp: str = ""

    def to_dict(self) -> dict:
        """Convert report to dictionary for JSON serialization."""
        return {
            "findings": [f.to_dict() for f in self.findings],
            "total_duplication": self.total_duplication,
            "files_analyzed": self.files_analyzed,
            "timestamp": self.timestamp,
            "summary": self.get_summary(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DuplicationReport":
        """
        Create report from dictionary.

        Args:
            data: Dictionary with report data

        Returns:
            DuplicationReport instance
        """
        return cls(
            findings=[DuplicationFinding.from_dict(f) for f in data.get("findings", [])],
            total_duplication=data.get("total_duplication", 0.0),
            files_analyzed=data.get("files_analyzed", 0),
            timestamp=data.get("timestamp", ""),
        )

    def add_finding(self, finding: DuplicationFinding) -> None:
        """
        Add a finding to the report.

        Args:
            finding: DuplicationFinding to add
        """
        self.findings.append(finding)

    def get_findings_by_file(self, file_path: str) -> list[DuplicationFinding]:
        """
        Get all findings for a specific file.

        Args:
            file_path: File path to filter by

        Returns:
            List of findings for the specified file
        """
        return [f for f in self.findings if f.file == file_path]

    def get_findings_by_category(self, category: str) -> list[DuplicationFinding]:
        """
        Get all findings of a specific category.

        Args:
            category: Category to filter by

        Returns:
            List of findings with the specified category
        """
        return [f for f in self.findings if f.category == category]

    def get_summary(self) -> dict[str, Any]:
        """
        Get summary statistics of findings.

        Returns:
            Dictionary with summary statistics
        """
        # Count by category
        by_category: dict[str, int] = {}
        for finding in self.findings:
            by_category[finding.category] = by_category.get(finding.category, 0) + 1

        # Get unique files
        unique_files = set()
        for finding in self.findings:
            unique_files.add(finding.file)
            unique_files.add(finding.duplicated_in)

        # Calculate average similarity
        avg_similarity = 0.0
        if self.findings:
            avg_similarity = sum(f.similarity for f in self.findings) / len(self.findings)

        return {
            "total_findings": len(self.findings),
            "by_category": by_category,
            "unique_files_affected": len(unique_files),
            "average_similarity": avg_similarity,
            "total_duplication_score": self.total_duplication,
        }

    def has_high_duplication(self, threshold: float = 0.3) -> bool:
        """
        Check if report has high duplication.

        Args:
            threshold: Duplication threshold to check against

        Returns:
            True if total duplication exceeds threshold
        """
        return self.total_duplication > threshold

    def get_unique_files(self) -> list[str]:
        """
        Get list of unique files with findings.

        Returns:
            Sorted list of unique file paths
        """
        files = set()
        for finding in self.findings:
            files.add(finding.file)
            files.add(finding.duplicated_in)
        return sorted(files)


class DuplicationDetector:
    """
    Code duplication detector using token and AST analysis.

    Detects code duplication by analyzing token similarity and
    structural patterns. Supports configurable thresholds and
    integrates with the QA findings system.
    """

    def __init__(
        self,
        threshold: DuplicationThreshold | None = None,
        config_path: str | None = None,
        work_dir: str = ".",
    ):
        """
        Initialize duplication detector.

        Args:
            threshold: Duplication threshold configuration
            config_path: Path to configuration file
            work_dir: Working directory for file operations
        """
        self.work_dir = Path(work_dir)
        self.threshold = threshold or self._load_threshold(config_path)

    def _load_threshold(self, config_path: str | None = None) -> DuplicationThreshold:
        """
        Load duplication threshold from configuration.

        Args:
            config_path: Path to configuration file

        Returns:
            DuplicationThreshold with configured values
        """
        if config_path:
            config_file = self.work_dir / config_path
        else:
            config_file = self.work_dir / ".autoflow" / "duplication.json"

        if config_file.exists():
            try:
                with open(config_file) as f:
                    config = json.load(f)
                    return DuplicationThreshold(
                        minimum_similarity=config.get("minimum_similarity", 0.7),
                        minimum_lines=config.get("minimum_lines", 5),
                        token_similarity_weight=config.get("token_similarity_weight", 0.5),
                        structure_similarity_weight=config.get("structure_similarity_weight", 0.5),
                        file_overrides=config.get("file_overrides", {}),
                    )
            except (OSError, json.JSONDecodeError):
                pass

        return DuplicationThreshold()

    def detect(
        self,
        file_path: str,
        compare_files: list[str] | None = None,
    ) -> DuplicationReport:
        """
        Detect code duplication in a file.

        Args:
            file_path: Path to file to analyze
            compare_files: List of files to compare against (optional)

        Returns:
            DuplicationReport with findings

        Raises:
            FileNotFoundError: If file_path does not exist
        """
        target_file = self.work_dir / file_path

        if not target_file.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Read target file content
        with open(target_file) as f:
            target_content = f.read()

        # Parse target file into lines and AST
        target_lines = target_content.splitlines()
        try:
            target_ast = ast.parse(target_content)
        except SyntaxError:
            # If file has syntax errors, skip AST analysis
            target_ast = None

        report = DuplicationReport(files_analyzed=1)
        findings = []

        # If compare_files not provided, search for Python files in the project
        if compare_files is None:
            compare_files = self._find_python_files()

        # Compare against each file
        for compare_file in compare_files:
            if compare_file == file_path:
                continue  # Skip comparing file with itself

            compare_path = self.work_dir / compare_file
            if not compare_path.exists():
                continue

            try:
                with open(compare_path) as f:
                    compare_content = f.read()

                compare_lines = compare_content.splitlines()
                try:
                    compare_ast = ast.parse(compare_content)
                except SyntaxError:
                    compare_ast = None

                # Detect duplications
                file_findings = self._detect_duplication(
                    file_path,
                    target_lines,
                    target_ast,
                    compare_file,
                    compare_lines,
                    compare_ast,
                )
                findings.extend(file_findings)

            except (OSError, UnicodeDecodeError):
                # Skip files that can't be read
                continue

        report.findings = findings
        report.timestamp = self._get_timestamp()

        # Calculate total duplication score
        if findings:
            report.total_duplication = sum(f.similarity for f in findings) / len(findings)

        return report

    def _find_python_files(self) -> list[str]:
        """
        Find all Python files in the working directory.

        Returns:
            List of Python file paths relative to work_dir
        """
        python_files = []

        for path in self.work_dir.rglob("*.py"):
            # Skip hidden directories and common non-source directories
            if any(part.startswith('.') for part in path.parts):
                continue
            if any(part in ('venv', 'env', '.venv', '__pycache__', 'node_modules') for part in path.parts):
                continue

            # Get relative path
            rel_path = path.relative_to(self.work_dir)
            python_files.append(str(rel_path))

        return python_files

    def _detect_duplication(
        self,
        file1: str,
        lines1: list[str],
        ast1: ast.AST | None,
        file2: str,
        lines2: list[str],
        ast2: ast.AST | None,
    ) -> list[DuplicationFinding]:
        """
        Detect duplication between two files.

        Args:
            file1: First file path
            lines1: First file lines
            ast1: First file AST (optional)
            file2: Second file path
            lines2: Second file lines
            ast2: Second file AST (optional)

        Returns:
            List of DuplicationFinding objects
        """
        findings = []

        # Token-based similarity analysis
        token_findings = self._detect_token_duplication(file1, lines1, file2, lines2)
        findings.extend(token_findings)

        # AST-based structural comparison (if both files have valid ASTs)
        if ast1 is not None and ast2 is not None:
            structure_findings = self._detect_structure_duplication(
                file1, lines1, ast1, file2, lines2, ast2
            )
            findings.extend(structure_findings)

        # Filter findings by threshold
        threshold = self.threshold.get_threshold_for_file(file1)
        filtered = [
            f for f in findings
            if threshold.check_passes(f.similarity, f.line_end - f.line_start + 1, file1)
        ]

        return filtered

    def _detect_token_duplication(
        self,
        file1: str,
        lines1: list[str],
        file2: str,
        lines2: list[str],
    ) -> list[DuplicationFinding]:
        """
        Detect duplication using token-based similarity.

        Args:
            file1: First file path
            lines1: First file lines
            file2: Second file path
            lines2: Second file lines

        Returns:
            List of DuplicationFinding objects
        """
        findings = []

        # Compare blocks of lines
        min_lines = self.threshold.minimum_lines

        for i in range(len(lines1) - min_lines + 1):
            for j in range(len(lines2) - min_lines + 1):
                # Extract blocks
                block1 = lines1[i:i + min_lines]
                block2 = lines2[j:j + min_lines]

                # Calculate similarity
                similarity = self._calculate_similarity(block1, block2)

                if similarity >= self.threshold.minimum_similarity:
                    # Expand to find full duplicated block
                    end1, end2, expanded_similarity = self._expand_block(
                        lines1, lines2, i, j, min_lines
                    )

                    snippet = '\n'.join(lines1[i:end1 + 1])

                    findings.append(DuplicationFinding(
                        file=file1,
                        line_start=i + 1,  # 1-indexed
                        line_end=end1 + 1,
                        similarity=expanded_similarity,
                        duplicated_in=file2,
                        duplicated_line_start=j + 1,
                        duplicated_line_end=end2 + 1,
                        snippet=snippet,
                        category="token",
                    ))

                    # Skip ahead to avoid overlapping findings
                    i = end1
                    break

        return findings

    def _detect_structure_duplication(
        self,
        file1: str,
        lines1: list[str],
        ast1: ast.AST,
        file2: str,
        lines2: list[str],
        ast2: ast.AST,
    ) -> list[DuplicationFinding]:
        """
        Detect duplication using AST structural comparison.

        Args:
            file1: First file path
            lines1: First file lines
            ast1: First file AST
            file2: Second file path
            lines2: Second file lines
            ast2: Second file AST

        Returns:
            List of DuplicationFinding objects
        """
        findings = []

        # Compare function definitions
        funcs1 = self._extract_functions(ast1)
        funcs2 = self._extract_functions(ast2)

        for func1 in funcs1:
            for func2 in funcs2:
                similarity = self._compare_ast_nodes(func1, func2)

                if similarity >= self.threshold.minimum_similarity:
                    # Get line numbers
                    line_start = func1.lineno
                    line_end = func1.end_lineno if func1.end_lineno else line_start

                    dup_line_start = func2.lineno
                    dup_line_end = func2.end_lineno if func2.end_lineno else dup_line_start

                    # Extract snippet
                    snippet = '\n'.join(lines1[line_start - 1:line_end])

                    findings.append(DuplicationFinding(
                        file=file1,
                        line_start=line_start,
                        line_end=line_end,
                        similarity=similarity,
                        duplicated_in=file2,
                        duplicated_line_start=dup_line_start,
                        duplicated_line_end=dup_line_end,
                        snippet=snippet,
                        category="structural",
                    ))

        # Compare class definitions
        classes1 = self._extract_classes(ast1)
        classes2 = self._extract_classes(ast2)

        for cls1 in classes1:
            for cls2 in classes2:
                similarity = self._compare_ast_nodes(cls1, cls2)

                if similarity >= self.threshold.minimum_similarity:
                    line_start = cls1.lineno
                    line_end = cls1.end_lineno if cls1.end_lineno else line_start

                    dup_line_start = cls2.lineno
                    dup_line_end = cls2.end_lineno if cls2.end_lineno else dup_line_start

                    snippet = '\n'.join(lines1[line_start - 1:line_end])

                    findings.append(DuplicationFinding(
                        file=file1,
                        line_start=line_start,
                        line_end=line_end,
                        similarity=similarity,
                        duplicated_in=file2,
                        duplicated_line_start=dup_line_start,
                        duplicated_line_end=dup_line_end,
                        snippet=snippet,
                        category="structural",
                    ))

        return findings

    def _calculate_similarity(self, lines1: list[str], lines2: list[str]) -> float:
        """
        Calculate similarity between two line lists.

        Args:
            lines1: First list of lines
            lines2: Second list of lines

        Returns:
            Similarity score (0.0-1.0)
        """
        if not lines1 or not lines2:
            return 0.0

        # Join lines and compare
        text1 = '\n'.join(lines1)
        text2 = '\n'.join(lines2)

        # Use SequenceMatcher for similarity
        return SequenceMatcher(None, text1, text2).ratio()

    def _expand_block(
        self,
        lines1: list[str],
        lines2: list[str],
        start1: int,
        start2: int,
        min_length: int,
    ) -> tuple[int, int, float]:
        """
        Expand a duplicated block to find full extent.

        Args:
            lines1: First file lines
            lines2: Second file lines
            start1: Start index in first file
            start2: Start index in second file
            min_length: Minimum block length

        Returns:
            Tuple of (end1, end2, similarity)
        """
        end1 = start1 + min_length - 1
        end2 = start2 + min_length - 1

        # Expand while similarity remains high
        while (
            end1 + 1 < len(lines1) and
            end2 + 1 < len(lines2)
        ):
            similarity = self._calculate_similarity(
                lines1[start1:end1 + 2],
                lines2[start2:end2 + 2],
            )

            if similarity < self.threshold.minimum_similarity:
                break

            end1 += 1
            end2 += 1

        # Calculate final similarity
        final_similarity = self._calculate_similarity(
            lines1[start1:end1 + 1],
            lines2[start2:end2 + 1],
        )

        return end1, end2, final_similarity

    def _extract_functions(self, tree: ast.AST) -> list[ast.FunctionDef]:
        """
        Extract all function definitions from AST.

        Args:
            tree: AST to extract from

        Returns:
            List of FunctionDef nodes
        """
        functions = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append(node)

        return functions

    def _extract_classes(self, tree: ast.AST) -> list[ast.ClassDef]:
        """
        Extract all class definitions from AST.

        Args:
            tree: AST to extract from

        Returns:
            List of ClassDef nodes
        """
        classes = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node)

        return classes

    def _compare_ast_nodes(self, node1: ast.AST, node2: ast.AST) -> float:
        """
        Compare two AST nodes for structural similarity.

        Args:
            node1: First AST node
            node2: Second AST node

        Returns:
            Similarity score (0.0-1.0)
        """
        # Check if nodes are same type
        if type(node1) != type(node2):
            return 0.0

        # Compare based on node type
        if isinstance(node1, ast.FunctionDef):
            return self._compare_functions(node1, node2)
        elif isinstance(node1, ast.ClassDef):
            return self._compare_classes(node1, node2)
        else:
            return self._compare_generic_nodes(node1, node2)

    def _compare_functions(self, func1: ast.FunctionDef, func2: ast.FunctionDef) -> float:
        """
        Compare two function definitions for similarity.

        Args:
            func1: First function
            func2: Second function

        Returns:
            Similarity score (0.0-1.0)
        """
        # Compare name similarity
        name_similarity = SequenceMatcher(None, func1.name, func2.name).ratio()

        # Compare argument count
        args_match = len(func1.args.args) == len(func2.args.args)

        # Compare body structure
        body_similarity = self._compare_generic_nodes(func1, func2)

        # Weighted average
        weights = self.threshold
        return (
            name_similarity * 0.2 +
            (1.0 if args_match else 0.0) * 0.2 +
            body_similarity * 0.6
        )

    def _compare_classes(self, cls1: ast.ClassDef, cls2: ast.ClassDef) -> float:
        """
        Compare two class definitions for similarity.

        Args:
            cls1: First class
            cls2: Second class

        Returns:
            Similarity score (0.0-1.0)
        """
        # Compare name similarity
        name_similarity = SequenceMatcher(None, cls1.name, cls2.name).ratio()

        # Compare method count
        methods1 = self._extract_functions(cls1)
        methods2 = self._extract_functions(cls2)
        method_count_similarity = 1.0 - abs(len(methods1) - len(methods2)) / max(len(methods1), len(methods2), 1)

        # Compare body structure
        body_similarity = self._compare_generic_nodes(cls1, cls2)

        # Weighted average
        return (
            name_similarity * 0.2 +
            method_count_similarity * 0.2 +
            body_similarity * 0.6
        )

    def _compare_generic_nodes(self, node1: ast.AST, node2: ast.AST) -> float:
        """
        Compare two AST nodes for structural similarity.

        Args:
            node1: First AST node
            node2: Second AST node

        Returns:
            Similarity score (0.0-1.0)
        """
        # Compare fields
        fields1 = {field: getattr(node1, field) for field in node1._fields if hasattr(node1, field)}
        fields2 = {field: getattr(node2, field) for field in node2._fields if hasattr(node2, field)}

        # Check field names match
        field_names1 = set(fields1.keys())
        field_names2 = set(fields2.keys())

        if field_names1 != field_names2:
            return 0.0

        # Compare each field
        similarities = []
        for field in field_names1:
            val1 = fields1[field]
            val2 = fields2[field]

            if isinstance(val1, list) and isinstance(val2, list):
                # Compare lists
                if len(val1) != len(val2):
                    similarities.append(0.5)
                else:
                    for v1, v2 in zip(val1, val2):
                        if isinstance(v1, ast.AST) and isinstance(v2, ast.AST):
                            similarities.append(self._compare_ast_nodes(v1, v2))
                        elif isinstance(v1, str) and isinstance(v2, str):
                            similarities.append(SequenceMatcher(None, v1, v2).ratio())
                        else:
                            similarities.append(1.0 if v1 == v2 else 0.0)
            elif isinstance(val1, ast.AST) and isinstance(val2, ast.AST):
                similarities.append(self._compare_ast_nodes(val1, val2))
            elif isinstance(val1, str) and isinstance(val2, str):
                similarities.append(SequenceMatcher(None, val1, val2).ratio())
            else:
                similarities.append(1.0 if val1 == val2 else 0.0)

        if not similarities:
            return 1.0

        return sum(similarities) / len(similarities)

    def _get_timestamp(self) -> str:
        """
        Get current timestamp in ISO format.

        Returns:
            ISO format timestamp string
        """
        from datetime import datetime
        return datetime.now().isoformat()

    def save_report(self, report: DuplicationReport, output_path: str) -> None:
        """
        Save duplication report to file.

        Args:
            report: DuplicationReport to save
            output_path: Path to output file
        """
        output_file = self.work_dir / output_path
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(report.to_dict(), f, indent=2)

    def load_report(self, input_path: str) -> DuplicationReport:
        """
        Load duplication report from file.

        Args:
            input_path: Path to input file

        Returns:
            DuplicationReport with loaded data
        """
        input_file = self.work_dir / input_path

        with open(input_file) as f:
            data = json.load(f)

        return DuplicationReport.from_dict(data)
