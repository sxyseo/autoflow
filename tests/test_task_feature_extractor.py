"""
Tests for TaskFeatureExtractor

Tests the feature extraction logic for task prioritization.
"""

import pytest
from pathlib import Path
from autoflow.prediction.task_feature_extractor import (
    TaskFeatureExtractor,
    TaskFeatures,
    TaskComplexityFeatures,
    TaskDependencyFeatures,
    TaskServiceFeatures,
    TaskHistoricalFeatures,
    TaskStatus,
    TaskType,
)


class TestTaskComplexityFeatures:
    """Test extraction of complexity-related features from task metadata."""

    def test_extract_complexity_features_minimal(self):
        """Test complexity extraction with minimal task data."""
        extractor = TaskFeatureExtractor()
        task_data = {
            "id": "task-1",
            "description": "Fix bug in auth module",
        }

        complexity = extractor._extract_complexity_features(task_data)

        assert complexity.description_length == 22
        assert complexity.description_word_count == 5
        assert complexity.num_files_to_create == 0
        assert complexity.num_files_to_modify == 0
        assert complexity.num_patterns == 0
        assert complexity.has_verification is False
        assert complexity.verification_type == ""

    def test_extract_complexity_features_full(self):
        """Test complexity extraction with full task data."""
        extractor = TaskFeatureExtractor()
        task_data = {
            "id": "task-2",
            "description": "Implement comprehensive user authentication system with JWT tokens, refresh mechanism, and secure session management",
            "files_to_create": ["autoflow/auth/jwt.py", "autoflow/auth/session.py"],
            "files_to_modify": ["autoflow/auth/__init__.py", "autoflow/api/routes/auth.py"],
            "patterns_from": ["autoflow/prediction/feature_extractor.py"],
            "verification": {
                "type": "test",
                "command": "pytest tests/test_auth.py",
            },
        }

        complexity = extractor._extract_complexity_features(task_data)

        assert complexity.description_length == 116
        assert complexity.description_word_count == 14
        assert complexity.num_files_to_create == 2
        assert complexity.num_files_to_modify == 2
        assert complexity.num_patterns == 1
        assert complexity.has_verification is True
        assert complexity.verification_type == "test"

    def test_extract_complexity_features_empty_description(self):
        """Test complexity extraction with empty description."""
        extractor = TaskFeatureExtractor()
        task_data = {
            "id": "task-3",
            "description": "",
        }

        complexity = extractor._extract_complexity_features(task_data)

        assert complexity.description_length == 0
        assert complexity.description_word_count == 0

    def test_extract_complexity_features_missing_fields(self):
        """Test complexity extraction with missing optional fields."""
        extractor = TaskFeatureExtractor()
        task_data = {
            "id": "task-4",
            "description": "Simple task",
        }

        complexity = extractor._extract_complexity_features(task_data)

        # Should handle missing fields gracefully
        assert complexity.description_length == 11
        assert complexity.num_files_to_create == 0
        assert complexity.num_files_to_modify == 0
        assert complexity.num_patterns == 0
        assert complexity.has_verification is False

    def test_extract_complexity_features_verification_types(self):
        """Test different verification types are extracted correctly."""
        extractor = TaskFeatureExtractor()

        verification_types = ["command", "test", "api", "e2e", "manual"]
        for vtype in verification_types:
            task_data = {
                "id": f"task-{vtype}",
                "description": "Task with verification",
                "verification": {"type": vtype},
            }

            complexity = extractor._extract_complexity_features(task_data)
            assert complexity.has_verification is True
            assert complexity.verification_type == vtype

    def test_extract_complexity_features_files_counts(self):
        """Test file counting with various file lists."""
        extractor = TaskFeatureExtractor()

        # Empty lists
        task_data = {
            "id": "task-5",
            "files_to_create": [],
            "files_to_modify": [],
        }
        complexity = extractor._extract_complexity_features(task_data)
        assert complexity.num_files_to_create == 0
        assert complexity.num_files_to_modify == 0

        # Multiple files
        task_data = {
            "id": "task-6",
            "files_to_create": ["file1.py", "file2.py", "file3.py"],
            "files_to_modify": ["file4.py", "file5.py"],
        }
        complexity = extractor._extract_complexity_features(task_data)
        assert complexity.num_files_to_create == 3
        assert complexity.num_files_to_modify == 2

    def test_task_complexity_features_to_dict(self):
        """Test TaskComplexityFeatures serialization to dictionary."""
        features = TaskComplexityFeatures(
            description_length=100,
            description_word_count=15,
            num_files_to_create=3,
            num_files_to_modify=2,
            num_patterns=1,
            has_verification=True,
            verification_type="test",
        )

        result = features.to_dict()

        assert result["task_description_length"] == 100
        assert result["task_description_word_count"] == 15
        assert result["task_files_to_create"] == 3
        assert result["task_files_to_modify"] == 2
        assert result["task_patterns"] == 1
        assert result["task_has_verification"] == 1
        assert result["task_verification_type_test"] == 1


class TestTaskDependencyFeatures:
    """Test extraction of dependency-related features."""

    def test_extract_dependency_features_no_dependencies(self):
        """Test dependency extraction for task with no dependencies."""
        extractor = TaskFeatureExtractor()
        task_data = {"id": "task-1", "depends_on": []}
        all_tasks = [task_data]

        dependencies = extractor._extract_dependency_features(task_data, all_tasks)

        assert dependencies.num_dependencies == 0
        assert dependencies.num_dependents == 0
        assert dependencies.is_blocking is False
        assert dependencies.dependency_depth == 0
        assert dependencies.has_circular_dependency is False

    def test_extract_dependency_features_with_dependencies(self):
        """Test dependency extraction for task with dependencies."""
        extractor = TaskFeatureExtractor()
        tasks = [
            {"id": "task-1", "depends_on": []},
            {"id": "task-2", "depends_on": ["task-1"]},
            {"id": "task-3", "depends_on": ["task-1"]},
        ]

        # Check task-1 (blocking task)
        deps = extractor._extract_dependency_features(tasks[0], tasks)
        assert deps.num_dependencies == 0
        assert deps.num_dependents == 2
        assert deps.is_blocking is True
        assert deps.dependency_depth == 0

        # Check task-2 (dependent task)
        deps = extractor._extract_dependency_features(tasks[1], tasks)
        assert deps.num_dependencies == 1
        assert deps.num_dependents == 0
        assert deps.is_blocking is False
        assert deps.dependency_depth == 1

    def test_extract_dependency_features_chain(self):
        """Test dependency extraction for chained dependencies."""
        extractor = TaskFeatureExtractor()
        tasks = [
            {"id": "task-1", "depends_on": []},
            {"id": "task-2", "depends_on": ["task-1"]},
            {"id": "task-3", "depends_on": ["task-2"]},
            {"id": "task-4", "depends_on": ["task-3"]},
        ]

        # task-4 should have depth 3
        deps = extractor._extract_dependency_features(tasks[3], tasks)
        assert deps.dependency_depth == 3

        # task-3 should have depth 2
        deps = extractor._extract_dependency_features(tasks[2], tasks)
        assert deps.dependency_depth == 2


class TestTaskServiceFeatures:
    """Test extraction of service-related features."""

    def test_extract_service_features(self):
        """Test service feature extraction."""
        extractor = TaskFeatureExtractor()
        task_data = {
            "id": "task-1",
            "service": "backend",
            "role": "implementation",
            "type": "implementation",
        }

        service = extractor._extract_service_features(task_data)

        assert service.service == "backend"
        assert service.role == "implementation"
        assert service.phase_type == "implementation"

    def test_extract_service_features_missing_fields(self):
        """Test service extraction with missing fields."""
        extractor = TaskFeatureExtractor()
        task_data = {"id": "task-1"}

        service = extractor._extract_service_features(task_data)

        assert service.service == ""
        assert service.role == ""
        assert service.phase_type == ""


class TestTaskFeatureExtraction:
    """Test end-to-end task feature extraction."""

    def test_extract_task_features_complete(self):
        """Test complete task feature extraction."""
        extractor = TaskFeatureExtractor()
        task_data = {
            "id": "task-1",
            "status": "todo",
            "description": "Implement feature",
            "service": "backend",
            "role": "implementation",
            "type": "implementation",
            "files_to_create": ["file.py"],
            "depends_on": [],
        }

        features = extractor.extract_task_features(
            task_data=task_data,
            spec_id="spec-1",
            phase_id="implementation",
            all_tasks=[task_data],
        )

        assert isinstance(features, TaskFeatures)
        assert features.task_id == "task-1"
        assert features.spec_id == "spec-1"
        assert features.phase_id == "implementation"
        assert features.status == TaskStatus.TODO
        assert features.task_type == TaskType.IMPLEMENTATION
        assert isinstance(features.complexity, TaskComplexityFeatures)
        assert isinstance(features.dependencies, TaskDependencyFeatures)
        assert isinstance(features.service, TaskServiceFeatures)
        assert isinstance(features.historical, TaskHistoricalFeatures)

    def test_extract_batch_features(self):
        """Test batch feature extraction."""
        extractor = TaskFeatureExtractor()
        tasks = [
            {
                "id": "task-1",
                "status": "todo",
                "description": "First task",
                "depends_on": [],
            },
            {
                "id": "task-2",
                "status": "todo",
                "description": "Second task",
                "depends_on": ["task-1"],
            },
        ]

        features_list = extractor.extract_batch_features(
            tasks=tasks, spec_id="spec-1", phase_id="implementation"
        )

        assert len(features_list) == 2
        assert all(isinstance(f, TaskFeatures) for f in features_list)
        assert features_list[0].task_id == "task-1"
        assert features_list[1].task_id == "task-2"

    def test_task_features_to_dict(self):
        """Test TaskFeatures serialization to dictionary."""
        extractor = TaskFeatureExtractor()
        task_data = {
            "id": "task-1",
            "status": "todo",
            "description": "Test task",
            "service": "backend",
            "role": "implementation",
            "type": "implementation",
            "depends_on": [],
        }

        features = extractor.extract_task_features(
            task_data=task_data,
            spec_id="spec-1",
            phase_id="implementation",
            all_tasks=[task_data],
        )

        result = features.to_dict()

        # Check basic fields
        assert result["task_id"] == "task-1"
        assert result["spec_id"] == "spec-1"
        assert result["phase_id"] == "implementation"
        assert result["task_status_todo"] == 1
        assert result["task_type_implementation"] == 1

        # Check complexity fields are present
        assert "task_description_length" in result
        assert "task_description_word_count" in result

        # Check dependency fields are present
        assert "task_num_dependencies" in result
        assert "task_dependency_depth" in result

        # Check service fields are present
        assert "task_service_backend" in result
        assert "task_role_implementation" in result

        # Check historical fields are present
        assert "task_avg_completion_time" in result
        assert "task_success_rate" in result


class TestDependencyAnalysis:
    """Test dependency graph analysis for task ordering."""

    def test_dependency_analysis_simple(self):
        """Test dependency analysis with simple linear chain."""
        extractor = TaskFeatureExtractor()
        tasks = [
            {"id": "task-1", "depends_on": []},
            {"id": "task-2", "depends_on": ["task-1"]},
            {"id": "task-3", "depends_on": ["task-2"]},
        ]

        analysis = extractor.dependency_analysis(tasks)

        assert analysis["execution_order"] == ["task-1", "task-2", "task-3"]
        assert len(analysis["critical_path"]) == 3
        assert "task-1" in analysis["blocking_tasks"]
        assert "task-2" in analysis["blocking_tasks"]
        assert len(analysis["cycles"]) == 0

    def test_dependency_analysis_parallel(self):
        """Test dependency analysis with parallel tasks."""
        extractor = TaskFeatureExtractor()
        tasks = [
            {"id": "task-1", "depends_on": []},
            {"id": "task-2", "depends_on": ["task-1"]},
            {"id": "task-3", "depends_on": ["task-1"]},
            {"id": "task-4", "depends_on": ["task-2", "task-3"]},
        ]

        analysis = extractor.dependency_analysis(tasks)

        # task-2 and task-3 should be parallel-safe (same level)
        parallel_groups = analysis["parallel_safe"]
        assert any(set(["task-2", "task-3"]) == set(g) for g in parallel_groups)

    def test_dependency_analysis_cycle_detection(self):
        """Test dependency analysis detects circular dependencies."""
        extractor = TaskFeatureExtractor()
        tasks = [
            {"id": "task-1", "depends_on": ["task-2"]},
            {"id": "task-2", "depends_on": ["task-3"]},
            {"id": "task-3", "depends_on": ["task-1"]},
        ]

        analysis = extractor.dependency_analysis(tasks)

        # Should detect cycles
        assert len(analysis["cycles"]) > 0

    def test_dependency_analysis_levels(self):
        """Test dependency level calculation."""
        extractor = TaskFeatureExtractor()
        tasks = [
            {"id": "task-1", "depends_on": []},
            {"id": "task-2", "depends_on": ["task-1"]},
            {"id": "task-3", "depends_on": ["task-1"]},
            {"id": "task-4", "depends_on": ["task-2"]},
        ]

        analysis = extractor.dependency_analysis(tasks)

        levels = analysis["levels"]
        assert levels["task-1"] == 0
        assert levels["task-2"] == 1
        assert levels["task-3"] == 1
        assert levels["task-4"] == 2


class TestPriorityScore:
    """Test priority score calculation."""

    def test_calculate_priority_score_blocking(self):
        """Test that blocking tasks get higher priority."""
        extractor = TaskFeatureExtractor()

        blocking_deps = TaskDependencyFeatures(
            num_dependencies=0, num_dependents=3, is_blocking=True, dependency_depth=0
        )
        non_blocking_deps = TaskDependencyFeatures(
            num_dependencies=0, num_dependents=0, is_blocking=False, dependency_depth=0
        )

        complexity = TaskComplexityFeatures()
        service = TaskServiceFeatures()
        historical = TaskHistoricalFeatures()

        blocking_score = extractor._calculate_priority_score(
            complexity, blocking_deps, service, historical
        )
        non_blocking_score = extractor._calculate_priority_score(
            complexity, non_blocking_deps, service, historical
        )

        assert blocking_score > non_blocking_score

    def test_calculate_priority_score_complexity(self):
        """Test that simpler tasks get slightly higher priority."""
        extractor = TaskFeatureExtractor()

        simple_complexity = TaskComplexityFeatures(
            description_length=10, num_files_to_create=0, num_files_to_modify=1
        )
        complex_complexity = TaskComplexityFeatures(
            description_length=100, num_files_to_create=5, num_files_to_modify=10
        )

        deps = TaskDependencyFeatures()
        service = TaskServiceFeatures()
        historical = TaskHistoricalFeatures()

        simple_score = extractor._calculate_priority_score(
            simple_complexity, deps, service, historical
        )
        complex_score = extractor._calculate_priority_score(
            complex_complexity, deps, service, historical
        )

        assert simple_score > complex_score

    def test_priority_score_bounds(self):
        """Test that priority scores are normalized to 0-100 range."""
        extractor = TaskFeatureExtractor()

        features = extractor.extract_task_features(
            task_data={
                "id": "test",
                "status": "todo",
                "description": "Test",
                "depends_on": [],
            },
            spec_id="spec-1",
            phase_id="impl",
        )

        assert 0 <= features.priority_score <= 100
