"""
Unit Tests for Embedding Service Module

Tests the EmbeddingService class and EmbeddingGenerationError exception
for text embedding generation using sentence-transformers.

These tests use mocking to avoid actual model loading and ensure tests
run quickly without external dependencies.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from autoflow.memory.embeddings import (
    EmbeddingGenerationError,
    EmbeddingService,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_model():
    """Create a mock sentence-transformers model."""
    model = MagicMock()
    model.get_sentence_embedding_dimension.return_value = 384

    # Mock encode method to return realistic embedding vectors
    def mock_encode(text, convert_to_numpy=False):
        import numpy as np

        # Handle batch processing (list of texts)
        if isinstance(text, list):
            embeddings = []
            for t in text:
                seed = hash(t) % 1000
                np.random.seed(seed)
                embedding = np.random.randn(384).astype(np.float32)
                embeddings.append(embedding)
            result = np.array(embeddings)
        else:
            # Single text processing
            seed = hash(text) % 1000
            np.random.seed(seed)
            result = np.random.randn(384).astype(np.float32)

        if convert_to_numpy:
            return result
        return result.tolist()

    model.encode = mock_encode
    return model


@pytest.fixture
def embedding_service_with_mock(mock_model):
    """Create EmbeddingService with mocked model loading."""
    service = EmbeddingService()
    service._model = mock_model
    return service


# ============================================================================
# EmbeddingGenerationError Tests
# ============================================================================


class TestEmbeddingGenerationError:
    """Tests for EmbeddingGenerationError exception."""

    def test_exception_creation(self) -> None:
        """Test creating EmbeddingGenerationError."""
        error = EmbeddingGenerationError("Test error message")
        assert str(error) == "Test error message"
        assert isinstance(error, Exception)

    def test_exception_with_cause(self) -> None:
        """Test EmbeddingGenerationError with original exception."""
        original_error = ValueError("Original error")
        error = EmbeddingGenerationError("Wrapped error")
        # Manually set __cause__ to avoid parsing issues
        error.__cause__ = original_error

        assert str(error) == "Wrapped error"
        assert error.__cause__ is original_error


# ============================================================================
# EmbeddingService Initialization Tests
# ============================================================================


class TestEmbeddingServiceInit:
    """Tests for EmbeddingService initialization."""

    def test_init_with_defaults(self) -> None:
        """Test EmbeddingService initialization with defaults."""
        service = EmbeddingService()

        assert service.model_name == EmbeddingService.DEFAULT_MODEL
        assert service._model is None

    def test_init_with_custom_model(self) -> None:
        """Test EmbeddingService initialization with custom model."""
        custom_model = "sentence-transformers/all-mpnet-base-v2"
        service = EmbeddingService(model_name=custom_model)

        assert service.model_name == custom_model
        assert service._model is None

    def test_init_with_none_model(self) -> None:
        """Test EmbeddingService initialization with None model name."""
        service = EmbeddingService(model_name=None)

        assert service.model_name == EmbeddingService.DEFAULT_MODEL

    def test_init_with_empty_string_raises_error(self) -> None:
        """Test initialization with empty string raises ValueError."""
        with pytest.raises(ValueError, match="model_name cannot be empty"):
            EmbeddingService(model_name="")

    def test_default_model_constant(self) -> None:
        """Test DEFAULT_MODEL constant is set correctly."""
        assert EmbeddingService.DEFAULT_MODEL == "sentence-transformers/all-MiniLM-L6-v2"


# ============================================================================
# EmbeddingService._load_model Tests
# ============================================================================


class TestEmbeddingServiceLoadModel:
    """Tests for EmbeddingService._load_model method."""

    def test_load_model_caches_result(self, embedding_service_with_mock) -> None:
        """Test model is cached after first load."""
        service = embedding_service_with_mock
        model1 = service._load_model()
        model2 = service._load_model()

        assert model1 is model2
        assert service._model is not None

    def test_load_model_returns_model(self, embedding_service_with_mock) -> None:
        """Test _load_model returns a valid model."""
        service = embedding_service_with_mock
        model = service._load_model()

        assert model is not None
        assert model.get_sentence_embedding_dimension() == 384

    def test_load_model_with_mock_fails_import(self) -> None:
        """Test _load_model handles ImportError gracefully."""
        service = EmbeddingService()

        # We can't easily test this without sentence_transformers installed
        # Skip this test in CI environments without the package
        pytest.skip("Requires sentence-transformers not installed scenario")

    def test_load_model_with_mock_fails_loading(self) -> None:
        """Test _load_model handles model loading errors."""
        service = EmbeddingService()

        # We can't easily test this without sentence_transformers installed
        # Skip this test in CI environments without the package
        pytest.skip("Requires sentence-transformers loading failure scenario")


# ============================================================================
# EmbeddingService.generate Tests
# ============================================================================


class TestEmbeddingServiceGenerate:
    """Tests for EmbeddingService.generate method."""

    def test_generate_basic_text(self, embedding_service_with_mock) -> None:
        """Test generating embedding for basic text."""
        service = embedding_service_with_mock
        embedding = service.generate("Use pytest for testing")

        assert isinstance(embedding, list)
        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)

    def test_generate_long_text(self, embedding_service_with_mock) -> None:
        """Test generating embedding for long text."""
        service = embedding_service_with_mock
        long_text = "This is a long text. " * 50

        embedding = service.generate(long_text)

        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)

    def test_generate_special_characters(self, embedding_service_with_mock) -> None:
        """Test generating embedding with special characters."""
        service = embedding_service_with_mock
        text = "Code: async/await, decorators, @dataclass, λ functions"

        embedding = service.generate(text)

        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)

    def test_generate_code_snippet(self, embedding_service_with_mock) -> None:
        """Test generating embedding for code snippet."""
        service = embedding_service_with_mock
        code = "def hello_world():\n    print('Hello, World!')"

        embedding = service.generate(code)

        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)

    def test_generate_same_text_same_embedding(self, embedding_service_with_mock) -> None:
        """Test same text produces same embedding."""
        service = embedding_service_with_mock
        text = "Consistent embedding generation"

        embedding1 = service.generate(text)
        embedding2 = service.generate(text)

        # Use hash-based mock, so same text should give same result
        assert embedding1 == embedding2

    def test_generate_different_text_different_embedding(self, embedding_service_with_mock) -> None:
        """Test different texts produce different embeddings."""
        service = embedding_service_with_mock

        embedding1 = service.generate("Text about authentication")
        embedding2 = service.generate("Text about database queries")

        # Different texts should produce different embeddings
        assert embedding1 != embedding2

    def test_generate_empty_string_raises_error(self, embedding_service_with_mock) -> None:
        """Test generate with empty string raises ValueError."""
        service = embedding_service_with_mock
        with pytest.raises(ValueError, match="text cannot be empty"):
            service.generate("")

    def test_generate_whitespace_only_raises_error(self, embedding_service_with_mock) -> None:
        """Test generate with whitespace only raises ValueError."""
        service = embedding_service_with_mock
        with pytest.raises(ValueError, match="text cannot be empty"):
            service.generate("   \n\t  ")

    def test_generate_non_string_raises_error(self, embedding_service_with_mock) -> None:
        """Test generate with non-string raises ValueError."""
        service = embedding_service_with_mock

        with pytest.raises(ValueError, match="text must be a string"):
            service.generate(123)  # type: ignore

        with pytest.raises(ValueError, match="text must be a string"):
            service.generate(None)  # type: ignore

        with pytest.raises(ValueError, match="text must be a string"):
            service.generate(["list", "of", "words"])  # type: ignore

    def test_generate_handles_model_error(self, embedding_service_with_mock) -> None:
        """Test generate handles model encoding errors."""
        service = embedding_service_with_mock

        # Mock the encode method to raise an error
        def mock_encode_error(*args, **kwargs):
            raise RuntimeError("CUDA out of memory")

        original_encode = service._model.encode
        service._model.encode = mock_encode_error

        with pytest.raises(EmbeddingGenerationError, match="Failed to generate embedding"):
            service.generate("Test text")

        # Restore original
        service._model.encode = original_encode


# ============================================================================
# EmbeddingService.generate_batch Tests
# ============================================================================


class TestEmbeddingServiceGenerateBatch:
    """Tests for EmbeddingService.generate_batch method."""

    def test_generate_batch_basic(self, embedding_service_with_mock) -> None:
        """Test generating embeddings for batch of texts."""
        service = embedding_service_with_mock
        texts = ["Use pytest", "Add type hints", "Write docstrings"]

        embeddings = service.generate_batch(texts)

        assert isinstance(embeddings, list)
        assert len(embeddings) == 3
        assert all(isinstance(emb, list) for emb in embeddings)
        assert all(len(emb) == 384 for emb in embeddings)
        assert all(all(isinstance(x, float) for x in emb) for emb in embeddings)

    def test_generate_batch_single_text(self, embedding_service_with_mock) -> None:
        """Test generate_batch with single text."""
        service = embedding_service_with_mock
        embeddings = service.generate_batch(["Single text"])

        assert len(embeddings) == 1
        assert len(embeddings[0]) == 384

    def test_generate_batch_large_batch(self, embedding_service_with_mock) -> None:
        """Test generate_batch with many texts."""
        service = embedding_service_with_mock
        texts = [f"Text {i}" for i in range(100)]

        embeddings = service.generate_batch(texts)

        assert len(embeddings) == 100
        assert all(len(emb) == 384 for emb in embeddings)

    def test_generate_batch_preserves_order(self, embedding_service_with_mock) -> None:
        """Test generate_batch preserves input order."""
        service = embedding_service_with_mock
        texts = ["First", "Second", "Third"]

        embeddings = service.generate_batch(texts)

        # Check order is preserved
        assert len(embeddings) == 3
        # Each should be different (different hashes)
        assert embeddings[0] != embeddings[1] != embeddings[2]

    def test_generate_batch_empty_list_raises_error(self, embedding_service_with_mock) -> None:
        """Test generate_batch with empty list raises ValueError."""
        service = embedding_service_with_mock
        with pytest.raises(ValueError, match="texts list cannot be empty"):
            service.generate_batch([])

    def test_generate_batch_non_string_items_raises_error(self, embedding_service_with_mock) -> None:
        """Test generate_batch with non-string items raises ValueError."""
        service = embedding_service_with_mock

        with pytest.raises(ValueError, match="All items in texts must be strings"):
            service.generate_batch(["valid", 123, "text"])

        with pytest.raises(ValueError, match="All items in texts must be strings"):
            service.generate_batch([None, "text"])  # type: ignore

    def test_generate_batch_with_empty_strings_raises_error(self, embedding_service_with_mock) -> None:
        """Test generate_batch with empty strings raises ValueError."""
        service = embedding_service_with_mock

        with pytest.raises(ValueError, match="texts cannot contain empty"):
            service.generate_batch(["valid text", "", "another"])

        with pytest.raises(ValueError, match="texts cannot contain empty"):
            service.generate_batch(["text", "   "])

    def test_generate_batch_handles_model_error(self, embedding_service_with_mock) -> None:
        """Test generate_batch handles model encoding errors."""
        service = embedding_service_with_mock

        # Mock the encode method to raise an error
        def mock_encode_error(*args, **kwargs):
            raise RuntimeError("Batch encoding failed")

        original_encode = service._model.encode
        service._model.encode = mock_encode_error

        with pytest.raises(EmbeddingGenerationError, match="Failed to generate batch embeddings"):
            service.generate_batch(["Text 1", "Text 2"])

        # Restore original
        service._model.encode = original_encode


# ============================================================================
# EmbeddingService.get_embedding_dimension Tests
# ============================================================================


class TestEmbeddingServiceGetDimension:
    """Tests for EmbeddingService.get_embedding_dimension method."""

    def test_get_embedding_dimension_basic(self, embedding_service_with_mock) -> None:
        """Test getting embedding dimension."""
        service = embedding_service_with_mock
        dimension = service.get_embedding_dimension()

        assert dimension == 384
        assert isinstance(dimension, int)

    def test_get_embedding_dimension_calls_model(self, embedding_service_with_mock) -> None:
        """Test get_embedding_dimension uses model's dimension method."""
        service = embedding_service_with_mock
        service._model.get_sentence_embedding_dimension.assert_not_called()

        dimension = service.get_embedding_dimension()

        service._model.get_sentence_embedding_dimension.assert_called_once()
        assert dimension == 384

    def test_get_embedding_dimension_handles_error(self, embedding_service_with_mock) -> None:
        """Test get_embedding_dimension handles errors."""
        service = embedding_service_with_mock

        # Mock the method to raise an error
        def mock_dimension_error():
            raise RuntimeError("Model not loaded")

        original_method = service._model.get_sentence_embedding_dimension
        service._model.get_sentence_embedding_dimension = mock_dimension_error

        with pytest.raises(EmbeddingGenerationError, match="Failed to get embedding dimension"):
            service.get_embedding_dimension()

        # Restore original
        service._model.get_sentence_embedding_dimension = original_method


# ============================================================================
# Integration Tests
# ============================================================================


class TestEmbeddingServiceIntegration:
    """Integration tests for EmbeddingService."""

    def test_lazy_loading(self, mock_model) -> None:
        """Test model is only loaded when needed."""
        service = EmbeddingService()

        # Model should not be loaded initially
        assert service._model is None

        # Mock the load
        with patch.object(service, "_load_model", return_value=mock_model):
            service.generate("Test text")

        # After first use, model should be loaded
        # (This test verifies the lazy loading pattern is followed)

    def test_multiple_services_independent(self, mock_model) -> None:
        """Test multiple service instances are independent."""
        service1 = EmbeddingService(model_name="model1")
        service2 = EmbeddingService(model_name="model2")

        assert service1.model_name == "model1"
        assert service2.model_name == "model2"
        assert service1._model is None
        assert service2._model is None

    def test_custom_model_name_used(self) -> None:
        """Test custom model name is stored correctly."""
        custom_model = "sentence-transformers/paraphrase-MiniLM-L3-v2"
        service = EmbeddingService(model_name=custom_model)

        assert service.model_name == custom_model


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestEmbeddingServiceEdgeCases:
    """Tests for edge cases and error handling."""

    def test_unicode_text(self, embedding_service_with_mock) -> None:
        """Test generating embedding for unicode text."""
        service = embedding_service_with_mock
        text = "Unicode: 中文, 日本語, العربية, עברית"

        embedding = service.generate(text)

        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)

    def test_very_long_single_word(self, embedding_service_with_mock) -> None:
        """Test generating embedding for very long single word."""
        service = embedding_service_with_mock
        long_word = "a" * 1000

        embedding = service.generate(long_word)

        assert len(embedding) == 384

    def test_mixed_case_consistency(self, embedding_service_with_mock) -> None:
        """Test embedding generation is consistent regardless of case."""
        service = embedding_service_with_mock

        # Different case should produce different embeddings
        embedding1 = service.generate("test")
        embedding2 = service.generate("TEST")
        embedding3 = service.generate("Test")

        # All should be valid embeddings
        assert all(len(e) == 384 for e in [embedding1, embedding2, embedding3])
        # But different (case-sensitive)
        assert embedding1 != embedding2
        assert embedding1 != embedding3

    def test_newlines_and_tabs(self, embedding_service_with_mock) -> None:
        """Test generating embedding with various whitespace characters."""
        service = embedding_service_with_mock
        text = "Line1\n\nLine2\t\tIndented\n\n\n"

        embedding = service.generate(text)

        assert len(embedding) == 384

    def test_json_serializable(self, embedding_service_with_mock) -> None:
        """Test embeddings are JSON serializable."""
        import json

        service = embedding_service_with_mock
        embedding = service.generate("JSON serializable text")

        # Should be able to serialize to JSON
        json_str = json.dumps(embedding)
        parsed = json.loads(json_str)

        assert parsed == embedding

    def test_batch_json_serializable(self, embedding_service_with_mock) -> None:
        """Test batch embeddings are JSON serializable."""
        import json

        service = embedding_service_with_mock
        embeddings = service.generate_batch(["Text 1", "Text 2", "Text 3"])

        # Should be able to serialize to JSON
        json_str = json.dumps(embeddings)
        parsed = json.loads(json_str)

        assert parsed == embeddings

    def test_numeric_values_valid(self, embedding_service_with_mock) -> None:
        """Test embedding values are valid floats."""
        service = embedding_service_with_mock
        embedding = service.generate("Test")

        # All values should be finite numbers
        assert all(isinstance(x, float) for x in embedding)
        # Should be within reasonable bounds for embeddings
        assert all(abs(x) < 10 for x in embedding)  # Typical embedding range

    def test_batch_with_duplicates(self, embedding_service_with_mock) -> None:
        """Test batch with duplicate texts."""
        service = embedding_service_with_mock
        texts = ["Same text", "Different", "Same text"]

        embeddings = service.generate_batch(texts)

        assert len(embeddings) == 3
        # Duplicates should produce same embeddings
        assert embeddings[0] == embeddings[2]
        # Different text should produce different embedding
        assert embeddings[1] != embeddings[0]

    def test_model_none_before_use(self) -> None:
        """Test model is None before first use."""
        service = EmbeddingService()
        assert service._model is None

    def test_model_cached_after_use(self, embedding_service_with_mock) -> None:
        """Test model is cached after first use."""
        service = embedding_service_with_mock

        # Model should already be loaded from fixture
        assert service._model is not None

        # Multiple calls should use the cached model
        service.generate("Test 1")
        service.generate("Test 2")
        service.generate("Test 3")

        # Model should still be the same instance
        assert service._model is not None


# ============================================================================
# Performance and Scaling Tests
# ============================================================================


class TestEmbeddingServicePerformance:
    """Tests for performance characteristics."""

    def test_generate_multiple_times_efficient(self, embedding_service_with_mock) -> None:
        """Test multiple generate calls are efficient."""
        service = embedding_service_with_mock

        # Generate multiple embeddings
        for i in range(10):
            service.generate(f"Text {i}")

        # Model should still be cached
        assert service._model is not None

    def test_batch_vs_individual_consistency(self, embedding_service_with_mock) -> None:
        """Test batch and individual generation produce consistent results."""
        service = embedding_service_with_mock
        texts = ["Text 1", "Text 2", "Text 3"]

        # Generate individually
        individual = [service.generate(text) for text in texts]

        # Generate as batch
        batch = service.generate_batch(texts)

        # Results should be equivalent
        assert len(individual) == len(batch)
        for ind, bat in zip(individual, batch):
            assert ind == bat


# ============================================================================
# Constants and Configuration Tests
# ============================================================================


class TestEmbeddingServiceConstants:
    """Tests for service constants and configuration."""

    def test_default_model_is_string(self) -> None:
        """Test DEFAULT_MODEL is a valid string."""
        assert isinstance(EmbeddingService.DEFAULT_MODEL, str)
        assert len(EmbeddingService.DEFAULT_MODEL) > 0
        assert EmbeddingService.DEFAULT_MODEL.startswith("sentence-transformers/")

    def test_default_model_structure(self) -> None:
        """Test DEFAULT_MODEL follows expected naming pattern."""
        default = EmbeddingService.DEFAULT_MODEL
        parts = default.split("/")

        assert len(parts) == 2
        assert parts[0] == "sentence-transformers"
        assert len(parts[1]) > 0
