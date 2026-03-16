"""
Unit Tests for Code Duplication Detection

Tests the DuplicationDetector, DuplicationThreshold, DuplicationFinding,
and DuplicationReport classes for detecting code duplication in AI-generated
changes.

These tests use file system fixtures and mock file operations to avoid
requiring actual project files in the test environment.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import ast
import pytest

from autoflow.analysis.duplication_detector import (
    DuplicationDetector,
    DuplicationFinding,
    DuplicationReport,
    DuplicationReportManager,
    DuplicationThreshold,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_workdir(tmp_path: Path) -> Path:
    """Create a temporary working directory."""
    workdir = tmp_path / "project"
    workdir.mkdir()
    return workdir


@pytest.fixture
def sample_python_file(temp_workdir: Path) -> Path:
    """Create a sample Python file for testing."""
    file_path = temp_workdir / "sample.py"
    file_path.write_text("""def hello_world():
    print("Hello, world!")

def greet(name: str) -> str:
    return f"Hello, {name}!"

class MyClass:
    def method_one(self):
        pass

    def method_two(self):
        pass
""")
    return file_path


@pytest.fixture
def duplicate_python_file(temp_workdir: Path) -> Path:
    """Create a duplicate Python file for testing."""
    file_path = temp_workdir / "duplicate.py"
    file_path.write_text("""def hello_world():
    print("Hello, world!")

def greet(name: str) -> str:
    return f"Hello, {name}!"

class MyClass:
    def method_one(self):
        pass

    def method_two(self):
        pass
""")
    return file_path


@pytest.fixture
def default_threshold() -> DuplicationThreshold:
    """Create a default DuplicationThreshold instance."""
    return DuplicationThreshold()


@pytest.fixture
def custom_threshold() -> DuplicationThreshold:
    """Create a custom DuplicationThreshold instance."""
    return DuplicationThreshold(
        minimum_similarity=0.8,
        minimum_lines=10,
        token_similarity_weight=0.6,
        structure_similarity_weight=0.4,
    )


@pytest.fixture
def threshold_with_overrides() -> DuplicationThreshold:
    """Create a threshold with file overrides."""
    return DuplicationThreshold(
        minimum_similarity=0.7,
        minimum_lines=5,
        file_overrides={
            "autoflow/core/*": {"minimum_similarity": 0.9, "minimum_lines": 10},
            "tests/test_*.py": {"minimum_similarity": 0.6},
        },
    )


@pytest.fixture
def sample_finding() -> DuplicationFinding:
    """Create a sample DuplicationFinding instance."""
    return DuplicationFinding(
        file="src/module.py",
        line_start=10,
        line_end=20,
        similarity=0.85,
        duplicated_in="src/other.py",
        duplicated_line_start=30,
        duplicated_line_end=40,
        snippet="def example():\n    pass",
        category="structural",
    )


@pytest.fixture
def sample_report() -> DuplicationReport:
    """Create a sample DuplicationReport instance."""
    report = DuplicationReport(
        findings=[
            DuplicationFinding(
                file="src/module.py",
                line_start=10,
                line_end=20,
                similarity=0.85,
                duplicated_in="src/other.py",
                duplicated_line_start=30,
                duplicated_line_end=40,
                snippet="def example():\n    pass",
                category="structural",
            ),
            DuplicationFinding(
                file="src/another.py",
                line_start=5,
                line_end=15,
                similarity=0.75,
                duplicated_in="src/module.py",
                duplicated_line_start=25,
                duplicated_line_end=35,
                snippet="class Example:\n    pass",
                category="token",
            ),
        ],
        total_duplication=0.8,
        files_analyzed=2,
        timestamp="2024-03-16T12:00:00",
    )
    return report


@pytest.fixture
def detector(temp_workdir: Path) -> DuplicationDetector:
    """Create a basic DuplicationDetector instance for testing."""
    return DuplicationDetector(work_dir=str(temp_workdir))


# ============================================================================
# DuplicationThreshold Tests
# ============================================================================


class TestDuplicationThreshold:
    """Tests for DuplicationThreshold dataclass."""

    def test_threshold_init_defaults(self) -> None:
        """Test threshold initialization with defaults."""
        threshold = DuplicationThreshold()

        assert threshold.minimum_similarity == 0.7
        assert threshold.minimum_lines == 5
        assert threshold.token_similarity_weight == 0.5
        assert threshold.structure_similarity_weight == 0.5
        assert threshold.file_overrides == {}

    def test_threshold_init_custom(self) -> None:
        """Test threshold initialization with custom values."""
        threshold = DuplicationThreshold(
            minimum_similarity=0.8,
            minimum_lines=10,
            token_similarity_weight=0.6,
            structure_similarity_weight=0.4,
        )

        assert threshold.minimum_similarity == 0.8
        assert threshold.minimum_lines == 10
        assert threshold.token_similarity_weight == 0.6
        assert threshold.structure_similarity_weight == 0.4

    def test_get_threshold_for_file_no_override(self, default_threshold: DuplicationThreshold) -> None:
        """Test get_threshold_for_file without overrides."""
        result = default_threshold.get_threshold_for_file("src/module.py")

        assert result is default_threshold

    def test_get_threshold_for_file_exact_match(self, threshold_with_overrides: DuplicationThreshold) -> None:
        """Test get_threshold_for_file with exact match."""
        # Add an exact match override
        threshold_with_overrides.file_overrides["src/module.py"] = {
            "minimum_similarity": 0.95,
            "minimum_lines": 15,
        }

        result = threshold_with_overrides.get_threshold_for_file("src/module.py")

        assert result.minimum_similarity == 0.95
        assert result.minimum_lines == 15

    def test_get_threshold_for_file_pattern_match(self, threshold_with_overrides: DuplicationThreshold) -> None:
        """Test get_threshold_for_file with pattern match."""
        result = threshold_with_overrides.get_threshold_for_file("autoflow/core/module.py")

        assert result.minimum_similarity == 0.9
        assert result.minimum_lines == 10

    def test_get_threshold_for_file_multiple_patterns(self, threshold_with_overrides: DuplicationThreshold) -> None:
        """Test get_threshold_for_file with multiple pattern matches."""
        # More specific pattern should take precedence
        threshold_with_overrides.file_overrides["autoflow/core/specific/*"] = {
            "minimum_similarity": 0.95,
        }

        result = threshold_with_overrides.get_threshold_for_file("autoflow/core/specific/module.py")

        assert result.minimum_similarity == 0.95

    def test_check_passes_similarity_only(self, default_threshold: DuplicationThreshold) -> None:
        """Test check_passes with similarity only."""
        assert default_threshold.check_passes(0.8) is True
        assert default_threshold.check_passes(0.6) is False

    def test_check_passes_with_lines(self, default_threshold: DuplicationThreshold) -> None:
        """Test check_passes with line count."""
        assert default_threshold.check_passes(0.8, lines=10) is True
        assert default_threshold.check_passes(0.8, lines=3) is False

    def test_check_passes_with_file_path(self, threshold_with_overrides: DuplicationThreshold) -> None:
        """Test check_passes with file path for override."""
        # Override threshold requires 0.9 similarity and 10 lines
        result = threshold_with_overrides.check_passes(
            0.95, lines=12, file_path="autoflow/core/module.py"
        )

        assert result is True  # Should use override threshold (0.9 similarity, 10 lines)

    def test_get_warning_threshold(self, default_threshold: DuplicationThreshold) -> None:
        """Test get_warning_threshold method."""
        warning = default_threshold.get_warning_threshold()

        assert warning == 0.6  # 0.7 - 0.1

    def test_get_warning_threshold_edge_case(self) -> None:
        """Test get_warning_threshold with low similarity."""
        threshold = DuplicationThreshold(minimum_similarity=0.05)
        warning = threshold.get_warning_threshold()

        assert warning == 0.0  # Should not go below 0.0


# ============================================================================
# DuplicationFinding Tests
# ============================================================================


class TestDuplicationFinding:
    """Tests for DuplicationFinding dataclass."""

    def test_finding_init(self, sample_finding: DuplicationFinding) -> None:
        """Test finding initialization."""
        assert sample_finding.file == "src/module.py"
        assert sample_finding.line_start == 10
        assert sample_finding.line_end == 20
        assert sample_finding.similarity == 0.85
        assert sample_finding.category == "structural"

    def test_finding_to_dict(self, sample_finding: DuplicationFinding) -> None:
        """Test to_dict method."""
        data = sample_finding.to_dict()

        assert data["file"] == "src/module.py"
        assert data["line_start"] == 10
        assert data["line_end"] == 20
        assert data["similarity"] == 0.85
        assert data["category"] == "structural"

    def test_finding_from_dict(self) -> None:
        """Test from_dict class method."""
        data = {
            "file": "src/module.py",
            "line_start": 10,
            "line_end": 20,
            "similarity": 0.85,
            "duplicated_in": "src/other.py",
            "duplicated_line_start": 30,
            "duplicated_line_end": 40,
            "snippet": "def example():\n    pass",
            "category": "structural",
        }

        finding = DuplicationFinding.from_dict(data)

        assert finding.file == "src/module.py"
        assert finding.similarity == 0.85
        assert finding.category == "structural"

    def test_finding_from_dict_default_category(self) -> None:
        """Test from_dict with default category."""
        data = {
            "file": "src/module.py",
            "line_start": 10,
            "line_end": 20,
            "similarity": 0.85,
            "duplicated_in": "src/other.py",
            "duplicated_line_start": 30,
            "duplicated_line_end": 40,
            "snippet": "def example():\n    pass",
        }

        finding = DuplicationFinding.from_dict(data)

        assert finding.category == "structural"  # Default

    def test_finding_str(self, sample_finding: DuplicationFinding) -> None:
        """Test __str__ method."""
        str_repr = str(sample_finding)

        assert "[structural]" in str_repr
        assert "src/module.py:10-20" in str_repr
        assert "85.0%" in str_repr

    def test_finding_to_qa_finding_critical(self) -> None:
        """Test to_qa_finding with critical severity."""
        finding = DuplicationFinding(
            file="src/module.py",
            line_start=10,
            line_end=20,
            similarity=0.95,
            duplicated_in="src/other.py",
            duplicated_line_start=30,
            duplicated_line_end=40,
            snippet="def example():\n    pass",
            category="structural",
        )

        qa_finding = finding.to_qa_finding()

        # If QAFinding is available, check the conversion
        if qa_finding is not None:
            # Check against the severity value (enum or string)
            severity_value = qa_finding.severity.value if hasattr(qa_finding.severity, 'value') else qa_finding.severity
            assert severity_value == "critical"
            assert "95.0%" in qa_finding.message

    def test_finding_to_qa_finding_high(self) -> None:
        """Test to_qa_finding with high severity."""
        finding = DuplicationFinding(
            file="src/module.py",
            line_start=10,
            line_end=20,
            similarity=0.85,
            duplicated_in="src/other.py",
            duplicated_line_start=30,
            duplicated_line_end=40,
            snippet="def example():\n    pass",
        )

        qa_finding = finding.to_qa_finding()

        if qa_finding is not None:
            severity_value = qa_finding.severity.value if hasattr(qa_finding.severity, 'value') else qa_finding.severity
            assert severity_value == "high"

    def test_finding_to_qa_finding_medium(self) -> None:
        """Test to_qa_finding with medium severity."""
        finding = DuplicationFinding(
            file="src/module.py",
            line_start=10,
            line_end=20,
            similarity=0.75,
            duplicated_in="src/other.py",
            duplicated_line_start=30,
            duplicated_line_end=40,
            snippet="def example():\n    pass",
        )

        qa_finding = finding.to_qa_finding()

        if qa_finding is not None:
            severity_value = qa_finding.severity.value if hasattr(qa_finding.severity, 'value') else qa_finding.severity
            assert severity_value == "medium"


# ============================================================================
# DuplicationReport Tests
# ============================================================================


class TestDuplicationReport:
    """Tests for DuplicationReport dataclass."""

    def test_report_init_defaults(self) -> None:
        """Test report initialization with defaults."""
        report = DuplicationReport()

        assert report.findings == []
        assert report.total_duplication == 0.0
        assert report.files_analyzed == 0
        assert report.timestamp == ""

    def test_report_init_custom(self, sample_report: DuplicationReport) -> None:
        """Test report initialization with custom values."""
        assert len(sample_report.findings) == 2
        assert sample_report.total_duplication == 0.8
        assert sample_report.files_analyzed == 2
        assert sample_report.timestamp == "2024-03-16T12:00:00"

    def test_report_to_dict(self, sample_report: DuplicationReport) -> None:
        """Test to_dict method."""
        data = sample_report.to_dict()

        assert data["total_duplication"] == 0.8
        assert data["files_analyzed"] == 2
        assert len(data["findings"]) == 2
        assert "summary" in data

    def test_report_from_dict(self) -> None:
        """Test from_dict class method."""
        data = {
            "findings": [
                {
                    "file": "src/module.py",
                    "line_start": 10,
                    "line_end": 20,
                    "similarity": 0.85,
                    "duplicated_in": "src/other.py",
                    "duplicated_line_start": 30,
                    "duplicated_line_end": 40,
                    "snippet": "def example():\n    pass",
                    "category": "structural",
                }
            ],
            "total_duplication": 0.85,
            "files_analyzed": 1,
            "timestamp": "2024-03-16T12:00:00",
        }

        report = DuplicationReport.from_dict(data)

        assert len(report.findings) == 1
        assert report.total_duplication == 0.85
        assert report.files_analyzed == 1

    def test_add_finding(self, sample_report: DuplicationReport) -> None:
        """Test add_finding method."""
        initial_count = len(sample_report.findings)

        new_finding = DuplicationFinding(
            file="src/new.py",
            line_start=1,
            line_end=5,
            similarity=0.9,
            duplicated_in="src/old.py",
            duplicated_line_start=10,
            duplicated_line_end=14,
            snippet="code",
            category="token",
        )

        sample_report.add_finding(new_finding)

        assert len(sample_report.findings) == initial_count + 1

    def test_get_findings_by_file(self, sample_report: DuplicationReport) -> None:
        """Test get_findings_by_file method."""
        findings = sample_report.get_findings_by_file("src/module.py")

        assert len(findings) == 1
        assert findings[0].file == "src/module.py"

    def test_get_findings_by_file_not_found(self, sample_report: DuplicationReport) -> None:
        """Test get_findings_by_file with non-existent file."""
        findings = sample_report.get_findings_by_file("nonexistent.py")

        assert len(findings) == 0

    def test_get_findings_by_category(self, sample_report: DuplicationReport) -> None:
        """Test get_findings_by_category method."""
        findings = sample_report.get_findings_by_category("structural")

        assert len(findings) == 1
        assert findings[0].category == "structural"

    def test_get_summary(self, sample_report: DuplicationReport) -> None:
        """Test get_summary method."""
        summary = sample_report.get_summary()

        assert summary["total_findings"] == 2
        assert summary["by_category"]["structural"] == 1
        assert summary["by_category"]["token"] == 1
        assert summary["unique_files_affected"] == 3
        assert "average_similarity" in summary

    def test_has_high_duplication(self, sample_report: DuplicationReport) -> None:
        """Test has_high_duplication method."""
        assert sample_report.has_high_duplication(threshold=0.3) is True
        assert sample_report.has_high_duplication(threshold=0.9) is False

    def test_get_unique_files(self, sample_report: DuplicationReport) -> None:
        """Test get_unique_files method."""
        files = sample_report.get_unique_files()

        assert len(files) == 3
        assert "src/module.py" in files
        assert "src/other.py" in files
        assert "src/another.py" in files

    def test_to_qa_report(self, sample_report: DuplicationReport) -> None:
        """Test to_qa_report method."""
        qa_report = sample_report.to_qa_report()

        if qa_report is not None:
            assert qa_report.source == "duplication-detection"
            assert len(qa_report.findings) == 2


# ============================================================================
# DuplicationDetector Initialization Tests
# ============================================================================


class TestDuplicationDetectorInit:
    """Tests for DuplicationDetector initialization."""

    def test_init_default(self, detector: DuplicationDetector) -> None:
        """Test detector initialization with defaults."""
        assert detector.threshold.minimum_similarity == 0.7
        assert detector.work_dir == Path(detector.work_dir)

    def test_init_with_float_threshold(self, temp_workdir: Path) -> None:
        """Test detector initialization with float threshold."""
        detector = DuplicationDetector(threshold=0.8, work_dir=str(temp_workdir))

        assert detector.threshold.minimum_similarity == 0.8

    def test_init_with_invalid_float_threshold(self, temp_workdir: Path) -> None:
        """Test detector initialization with invalid float threshold."""
        with pytest.raises(ValueError) as exc_info:
            DuplicationDetector(threshold=1.5, work_dir=str(temp_workdir))

        assert "between 0.0 and 1.0" in str(exc_info.value)

    def test_init_with_threshold_object(self, temp_workdir: Path) -> None:
        """Test detector initialization with threshold object."""
        custom_threshold = DuplicationThreshold(minimum_similarity=0.9)
        detector = DuplicationDetector(
            threshold=custom_threshold, work_dir=str(temp_workdir)
        )

        assert detector.threshold.minimum_similarity == 0.9

    def test_init_with_invalid_threshold_type(self, temp_workdir: Path) -> None:
        """Test detector initialization with invalid threshold type."""
        with pytest.raises(TypeError) as exc_info:
            DuplicationDetector(threshold="invalid", work_dir=str(temp_workdir))

        assert "must be DuplicationThreshold, float, or None" in str(exc_info.value)

    def test_validate_threshold_valid(self, detector: DuplicationDetector) -> None:
        """Test _validate_threshold with valid threshold."""
        # Should not raise
        detector._validate_threshold(
            DuplicationThreshold(
                minimum_similarity=0.7,
                minimum_lines=5,
                token_similarity_weight=0.5,
                structure_similarity_weight=0.5,
            )
        )

    def test_validate_threshold_invalid_similarity(self, detector: DuplicationDetector) -> None:
        """Test _validate_threshold with invalid similarity."""
        with pytest.raises(ValueError) as exc_info:
            detector._validate_threshold(
                DuplicationThreshold(minimum_similarity=1.5)
            )

        assert "minimum_similarity must be between 0.0 and 1.0" in str(exc_info.value)

    def test_validate_threshold_negative_lines(self, detector: DuplicationDetector) -> None:
        """Test _validate_threshold with negative lines."""
        with pytest.raises(ValueError) as exc_info:
            detector._validate_threshold(
                DuplicationThreshold(minimum_lines=-1)
            )

        assert "minimum_lines must be non-negative" in str(exc_info.value)

    def test_validate_threshold_invalid_weights(self, detector: DuplicationDetector) -> None:
        """Test _validate_threshold with invalid weights."""
        with pytest.raises(ValueError) as exc_info:
            detector._validate_threshold(
                DuplicationThreshold(
                    token_similarity_weight=0.8,
                    structure_similarity_weight=0.5,  # Sum = 1.3
                )
            )

        assert "approximately 1.0" in str(exc_info.value)


# ============================================================================
# DuplicationDetector Detection Tests
# ============================================================================


class TestDuplicationDetectorDetection:
    """Tests for DuplicationDetector detection methods."""

    def test_detect_file_not_found(self, detector: DuplicationDetector) -> None:
        """Test detect with non-existent file."""
        with pytest.raises(FileNotFoundError) as exc_info:
            detector.detect("nonexistent.py")

        assert "File not found" in str(exc_info.value)

    def test_detect_with_compare_files(
        self,
        detector: DuplicationDetector,
        sample_python_file: Path,
        duplicate_python_file: Path,
    ) -> None:
        """Test detect with explicit compare files."""
        report = detector.detect(
            str(sample_python_file.name),
            compare_files=[str(duplicate_python_file.name)],
        )

        assert isinstance(report, DuplicationReport)
        assert report.files_analyzed == 1

    def test_find_python_files(
        self,
        detector: DuplicationDetector,
        sample_python_file: Path,
    ) -> None:
        """Test _find_python_files method."""
        files = detector._find_python_files()

        assert len(files) > 0
        assert sample_python_file.name in [Path(f).name for f in files]

    def test_calculate_similarity(self, detector: DuplicationDetector) -> None:
        """Test _calculate_similarity method."""
        lines1 = ["def hello():", "    pass"]
        lines2 = ["def hello():", "    pass"]

        similarity = detector._calculate_similarity(lines1, lines2)

        assert similarity == 1.0

    def test_calculate_similarity_different(self, detector: DuplicationDetector) -> None:
        """Test _calculate_similarity with different lines."""
        lines1 = ["def hello():", "    pass"]
        lines2 = ["def world():", "    return 42"]

        similarity = detector._calculate_similarity(lines1, lines2)

        assert 0.0 <= similarity <= 1.0

    def test_calculate_similarity_empty(self, detector: DuplicationDetector) -> None:
        """Test _calculate_similarity with empty lines."""
        similarity = detector._calculate_similarity([], [])

        assert similarity == 0.0

    def test_expand_block(
        self,
        detector: DuplicationDetector,
        sample_python_file: Path,
    ) -> None:
        """Test _expand_block method."""
        lines = sample_python_file.read_text().splitlines()

        end1, end2, similarity = detector._expand_block(
            lines, lines, 0, 0, 2
        )

        assert end1 >= 1
        assert end2 >= 1
        assert 0.0 <= similarity <= 1.0

    def test_extract_functions(self, detector: DuplicationDetector) -> None:
        """Test _extract_functions method."""
        code = """
def func1():
    pass

def func2():
    pass

class MyClass:
    def method(self):
        pass
"""
        tree = ast.parse(code)

        functions = detector._extract_functions(tree)

        assert len(functions) == 3  # func1, func2, and method

    def test_extract_classes(self, detector: DuplicationDetector) -> None:
        """Test _extract_classes method."""
        code = """
class Class1:
    pass

class Class2:
    pass
"""
        tree = ast.parse(code)

        classes = detector._extract_classes(tree)

        assert len(classes) == 2

    def test_compare_ast_nodes_same_function(self, detector: DuplicationDetector) -> None:
        """Test _compare_ast_nodes with identical functions."""
        code = "def hello():\n    pass"
        tree = ast.parse(code)
        func = list(ast.walk(tree))[1]  # Get the FunctionDef node

        similarity = detector._compare_ast_nodes(func, func)

        assert similarity == 1.0

    def test_compare_ast_nodes_different_types(self, detector: DuplicationDetector) -> None:
        """Test _compare_ast_nodes with different node types."""
        code = "def hello():\n    pass"
        tree = ast.parse(code)
        func = list(ast.walk(tree))[1]
        module = tree

        similarity = detector._compare_ast_nodes(func, module)

        assert similarity == 0.0


# ============================================================================
# DuplicationDetector I/O Tests
# ============================================================================


class TestDuplicationDetectorIO:
    """Tests for DuplicationDetector I/O methods."""

    def test_save_report(
        self,
        detector: DuplicationDetector,
        sample_report: DuplicationReport,
        temp_workdir: Path,
    ) -> None:
        """Test save_report method."""
        output_path = "reports/duplication.json"

        detector.save_report(sample_report, output_path)

        output_file = temp_workdir / output_path
        assert output_file.exists()

    def test_load_report(
        self,
        detector: DuplicationDetector,
        sample_report: DuplicationReport,
        temp_workdir: Path,
    ) -> None:
        """Test load_report method."""
        output_path = "reports/duplication.json"

        # Save first
        detector.save_report(sample_report, output_path)

        # Then load
        loaded_report = detector.load_report(output_path)

        assert loaded_report.total_duplication == sample_report.total_duplication
        assert len(loaded_report.findings) == len(sample_report.findings)


# ============================================================================
# DuplicationReportManager Tests
# ============================================================================


class TestDuplicationReportManager:
    """Tests for DuplicationReportManager class."""

    @pytest.fixture
    def manager(self, temp_workdir: Path) -> DuplicationReportManager:
        """Create a DuplicationReportManager instance."""
        return DuplicationReportManager(work_dir=str(temp_workdir))

    def test_manager_init(self, manager: DuplicationReportManager) -> None:
        """Test manager initialization."""
        assert manager.work_dir == Path(manager.work_dir)

    def test_create_report(self, manager: DuplicationReportManager) -> None:
        """Test create_report method."""
        report = manager.create_report()

        assert isinstance(report, DuplicationReport)
        assert report.findings == []

    def test_save_and_load_report(
        self,
        manager: DuplicationReportManager,
        sample_report: DuplicationReport,
        temp_workdir: Path,
    ) -> None:
        """Test save_report and load_report methods."""
        output_path = "reports/duplication.json"

        # Save report
        manager.save_report(sample_report, output_path)

        output_file = temp_workdir / output_path
        assert output_file.exists()

        # Load report
        loaded_report = manager.load_report(output_path)

        assert loaded_report.total_duplication == sample_report.total_duplication
        assert len(loaded_report.findings) == len(sample_report.findings)

    def test_load_nonexistent_report(self, manager: DuplicationReportManager) -> None:
        """Test load_report with non-existent file."""
        with pytest.raises(FileNotFoundError):
            manager.load_report("nonexistent.json")


# ============================================================================
# Integration Tests
# ============================================================================


class TestDuplicationDetectorIntegration:
    """Integration tests for DuplicationDetector."""

    def test_full_detection_workflow(
        self,
        temp_workdir: Path,
        sample_python_file: Path,
        duplicate_python_file: Path,
    ) -> None:
        """Test complete detection workflow."""
        # Create detector
        detector = DuplicationDetector(
            threshold=0.7,
            work_dir=str(temp_workdir)
        )

        # Run detection
        report = detector.detect(
            str(sample_python_file.name),
            compare_files=[str(duplicate_python_file.name)],
        )

        # Verify report
        assert isinstance(report, DuplicationReport)
        assert report.files_analyzed == 1
        assert report.timestamp != ""

        # Save and load report
        output_path = "reports/test_duplication.json"
        detector.save_report(report, output_path)

        loaded_report = detector.load_report(output_path)
        assert loaded_report.total_duplication == report.total_duplication

    def test_threshold_override_workflow(
        self,
        temp_workdir: Path,
        sample_python_file: Path,
    ) -> None:
        """Test threshold override in detection workflow."""
        # Create detector with file overrides
        threshold = DuplicationThreshold(
            minimum_similarity=0.7,
            file_overrides={
                "*.py": {"minimum_similarity": 0.9, "minimum_lines": 3},
            },
        )
        detector = DuplicationDetector(
            threshold=threshold,
            work_dir=str(temp_workdir)
        )

        # Verify override is applied
        file_threshold = detector.threshold.get_threshold_for_file(sample_python_file.name)

        assert file_threshold.minimum_similarity == 0.9
        assert file_threshold.minimum_lines == 3
