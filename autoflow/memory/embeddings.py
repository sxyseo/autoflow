"""
Autoflow Memory Embeddings

Embedding service for generating semantic vector representations of text.
Uses sentence-transformers with the all-MiniLM-L6-v2 model for fast,
high-quality embeddings optimized for semantic search.

Usage:
    from autoflow.memory.embeddings import EmbeddingService

    service = EmbeddingService()
    embedding = service.generate("Use pytest for testing with fixtures")
    # Returns: list[float] - 384-dimensional vector
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class EmbeddingGenerationError(Exception):
    """Exception raised when embedding generation fails."""

    pass


class EmbeddingService:
    """
    Service for generating text embeddings using sentence-transformers.

    This service provides a simple interface for converting text into
    dense vector representations that capture semantic meaning. These
    embeddings enable semantic search and similarity matching.

    The service uses lazy initialization - the model is only loaded
    when first needed, not during service instantiation.

    Default model: all-MiniLM-L6-v2
    - Fast inference (suitable for on-the-fly generation)
    - Good quality semantic representations
    - 384-dimensional output vectors
    - Optimized for English text

    Attributes:
        model_name: Name of the sentence-transformers model to use
        _model: Cached model instance (lazy loaded)

    Example:
        >>> service = EmbeddingService()
        >>> embedding = service.generate("Authentication failed with JWT error")
        >>> len(embedding)
        384
    """

    # Default model for embedding generation
    # all-MiniLM-L6-v2: Fast, good quality, 384 dimensions
    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, model_name: Optional[str] = None) -> None:
        """
        Initialize the embedding service.

        The model is not loaded until the first call to generate()
        to avoid unnecessary startup overhead.

        Args:
            model_name: Optional model name. If None, uses DEFAULT_MODEL.
                       Must be a valid sentence-transformers model name.

        Raises:
            ValueError: If model_name is empty string
        """
        if model_name == "":
            raise ValueError("model_name cannot be empty string")

        self.model_name = model_name or self.DEFAULT_MODEL
        self._model: Optional[SentenceTransformer] = None

    def _load_model(self) -> "SentenceTransformer":
        """
        Load the sentence-transformers model (lazy loading).

        The model is cached after first load for reuse across multiple
        embedding generation calls.

        Returns:
            Loaded SentenceTransformer model

        Raises:
            EmbeddingGenerationError: If model loading fails
        """
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
            except ImportError as e:
                raise EmbeddingGenerationError(
                    f"Failed to import sentence-transformers: {e}. "
                    "Install with: pip install sentence-transformers"
                ) from e
            except Exception as e:
                raise EmbeddingGenerationError(
                    f"Failed to load model '{self.model_name}': {e}"
                ) from e

        return self._model

    def generate(self, text: str) -> list[float]:
        """
        Generate an embedding vector for the given text.

        Converts the input text into a dense vector representation that
        captures semantic meaning. The resulting vector can be used for
        semantic similarity comparisons and search.

        Args:
            text: Input text to generate embedding for. Can be any length.

        Returns:
            List of floats representing the embedding vector.
            Dimension depends on model (384 for all-MiniLM-L6-v2).

        Raises:
            EmbeddingGenerationError: If embedding generation fails
            ValueError: If text is empty or not a string

        Example:
            >>> service = EmbeddingService()
            >>> embedding = service.generate("Use async/await for I/O operations")
            >>> isinstance(embedding, list)
            True
            >>> all(isinstance(x, float) for x in embedding)
            True
        """
        if not isinstance(text, str):
            raise ValueError(f"text must be a string, got {type(text).__name__}")

        if not text or not text.strip():
            raise ValueError("text cannot be empty or whitespace only")

        try:
            model = self._load_model()
            embedding = model.encode(text, convert_to_numpy=True)

            # Convert numpy array to list of floats for JSON serialization
            return embedding.tolist()

        except Exception as e:
            if isinstance(e, EmbeddingGenerationError):
                raise

            raise EmbeddingGenerationError(
                f"Failed to generate embedding for text: {e}"
            ) from e

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts in a single batch.

        More efficient than calling generate() multiple times for
        large batches of texts.

        Args:
            texts: List of input texts to generate embeddings for

        Returns:
            List of embedding vectors (one per input text)

        Raises:
            EmbeddingGenerationError: If batch embedding generation fails
            ValueError: If texts is empty or contains empty strings

        Example:
            >>> service = EmbeddingService()
            >>> texts = ["Use pytest", "Add type hints", "Write docstrings"]
            >>> embeddings = service.generate_batch(texts)
            >>> len(embeddings)
            3
        """
        if not texts:
            raise ValueError("texts list cannot be empty")

        if not all(isinstance(t, str) for t in texts):
            raise ValueError("All items in texts must be strings")

        if not all(t.strip() for t in texts):
            raise ValueError("texts cannot contain empty or whitespace-only strings")

        try:
            model = self._load_model()
            embeddings = model.encode(texts, convert_to_numpy=True)

            # Convert numpy array to list of lists for JSON serialization
            return embeddings.tolist()

        except Exception as e:
            if isinstance(e, EmbeddingGenerationError):
                raise

            raise EmbeddingGenerationError(
                f"Failed to generate batch embeddings: {e}"
            ) from e

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of the embedding vectors produced by this model.

        Returns the size of the embedding vectors that will be returned
        by generate() and generate_batch(). Useful for validation and
        storage allocation.

        Returns:
            Dimension of the embedding vectors (e.g., 384 for all-MiniLM-L6-v2)

        Raises:
            EmbeddingGenerationError: If model loading fails

        Example:
            >>> service = EmbeddingService()
            >>> service.get_embedding_dimension()
            384
        """
        try:
            model = self._load_model()
            return model.get_sentence_embedding_dimension()
        except Exception as e:
            raise EmbeddingGenerationError(
                f"Failed to get embedding dimension: {e}"
            ) from e
