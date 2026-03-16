#!/usr/bin/env python3
"""
Autoflow Code Similarity Analysis Module

Provides token-based code similarity analysis using Python's tokenize module.
This module analyzes code at the token level to detect similarities that may
indicate code duplication, even when the code has been modified through
refactoring or variable renaming.

The token-based approach is more robust than simple text comparison because:
- It ignores whitespace and formatting differences
- It can detect structural similarities despite identifier changes
- It's language-aware, understanding Python's lexical structure

Integration:
- Used by DuplicationDetector for token-based similarity scoring
- Supports configurable token type weighting
- Provides similarity metrics for code blocks

Example:
    from autoflow.analysis.code_similarity import TokenSimilarity

    analyzer = TokenSimilarity()
    code1 = "def foo(x): return x * 2"
    code2 = "def bar(y): return y * 2"

    similarity = analyzer.compare_code_blocks(code1, code2)
    print(f"Similarity: {similarity:.2%}")
"""

from __future__ import annotations

import io
import tokenize
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from pathlib import Path
from typing import Any


class TokenType(str, Enum):
    """Token types used in similarity analysis.

    Attributes:
        KEYWORD: Python keywords (def, class, if, for, etc.)
        IDENTIFIER: Variable names, function names, class names
        OPERATOR: Mathematical and logical operators
        LITERAL: String and numeric literals
        DELIMITER: Punctuation and structural markers
        COMMENT: Comments (ignored by default in analysis)
    """

    KEYWORD = "keyword"
    IDENTIFIER = "identifier"
    OPERATOR = "operator"
    LITERAL = "literal"
    DELIMITER = "delimiter"
    COMMENT = "comment"


@dataclass
class TokenInfo:
    """Extended token information with similarity analysis metadata.

    Attributes:
        type: Token type category
        string: The actual token text
        start_row: Starting line number (1-indexed)
        start_col: Starting column offset (0-indexed)
        end_row: Ending line number (1-indexed)
        end_col: Ending column offset (0-indexed)
        weight: Importance weight for similarity scoring (0.0-1.0)
    """

    type: TokenType
    string: str
    start_row: int
    start_col: int
    end_row: int
    end_col: int
    weight: float = 1.0

    def to_tuple(self) -> tuple:
        """Convert to standard tokenize tuple format."""
        return (
            self.type.value,
            self.string,
            (self.start_row, self.start_col),
            (self.end_row, self.end_col),
            self.string,
        )

    @classmethod
    def from_tokenize(cls, token: tokenize.TokenInfo) -> "TokenInfo":
        """Create TokenInfo from standard tokenize.TokenInfo.

        Args:
            token: Standard tokenize.TokenInfo object

        Returns:
            TokenInfo with categorization applied
        """
        # Categorize token type
        token_type = cls._categorize_token(token)

        # Set weight based on token type
        weight = cls._get_token_weight(token_type)

        return cls(
            type=token_type,
            string=token.string,
            start_row=token.start[0],
            start_col=token.start[1],
            end_row=token.end[0],
            end_col=token.end[1],
            weight=weight,
        )

    @staticmethod
    def _categorize_token(token: tokenize.TokenInfo) -> TokenType:
        """Categorize a token into similarity analysis types.

        Args:
            token: Standard tokenize.TokenInfo object

        Returns:
            TokenType category
        """
        import keyword

        # Check if it's a keyword
        if keyword.iskeyword(token.string):
            return TokenType.KEYWORD

        # Categorize by token type
        if token.type == tokenize.NAME:
            return TokenType.IDENTIFIER
        elif token.type in (tokenize.OP,):
            return TokenType.OPERATOR
        elif token.type in (tokenize.STRING, tokenize.NUMBER):
            return TokenType.LITERAL
        elif token.type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                           tokenize.DEDENT, tokenize.LPAR, tokenize.RPAR,
                           tokenize.LBRACE, tokenize.RBRACE, tokenize.LSQB,
                           tokenize.RSQB, tokenize.COLON, tokenize.COMMA,
                           tokenize.SEMI, tokenize.AT):
            return TokenType.DELIMITER
        elif token.type == tokenize.COMMENT:
            return TokenType.COMMENT
        else:
            # Default to delimiter for uncategorized tokens
            return TokenType.DELIMITER

    @staticmethod
    def _get_token_weight(token_type: TokenType) -> float:
        """Get importance weight for a token type.

        Args:
            token_type: The token type to weight

        Returns:
            Weight value (0.0-1.0)
        """
        weights = {
            TokenType.KEYWORD: 1.0,
            TokenType.OPERATOR: 0.9,
            TokenType.IDENTIFIER: 0.7,
            TokenType.LITERAL: 0.5,
            TokenType.DELIMITER: 0.3,
            TokenType.COMMENT: 0.0,  # Comments ignored in similarity
        }
        return weights.get(token_type, 0.5)


@dataclass
class TokenSequence:
    """A sequence of tokens representing a code block.

    Attributes:
        tokens: List of TokenInfo objects in the sequence
        source_file: Optional source file path
        start_line: Starting line number in source (1-indexed)
        end_line: Ending line number in source (1-indexed)
    """

    tokens: list[TokenInfo] = field(default_factory=list)
    source_file: str | None = None
    start_line: int = 0
    end_line: int = 0

    def __len__(self) -> int:
        """Return the number of tokens in the sequence."""
        return len(self.tokens)

    def __getitem__(self, index: int) -> TokenInfo:
        """Get token at index."""
        return self.tokens[index]

    def __iter__(self):
        """Iterate over tokens."""
        return iter(self.tokens)

    def get_token_types(self) -> list[TokenType]:
        """Get list of token types in the sequence."""
        return [t.type for t in self.tokens]

    def get_token_strings(self) -> list[str]:
        """Get list of token strings in the sequence."""
        return [t.string for t in self.tokens]

    def get_weighted_tokens(self) -> list[tuple[TokenInfo, float]]:
        """Get tokens with their weights applied."""
        return [(t, t.weight) for t in self.tokens]

    def filter_by_type(self, token_type: TokenType) -> "TokenSequence":
        """Create a new sequence with only tokens of specified type.

        Args:
            token_type: Type of tokens to keep

        Returns:
            New TokenSequence with filtered tokens
        """
        filtered = [t for t in self.tokens if t.type == token_type]
        return TokenSequence(
            tokens=filtered,
            source_file=self.source_file,
            start_line=self.start_line,
            end_line=self.end_line,
        )


@dataclass
class SimilarityResult:
    """Result of a similarity comparison between two code blocks.

    Attributes:
        similarity_score: Overall similarity score (0.0-1.0)
        token_similarity: Token-level similarity score
        structural_similarity: Structural pattern similarity score
        matches_count: Number of matching tokens
        total_tokens: Total number of tokens compared
        details: Detailed breakdown by token type
    """

    similarity_score: float
    token_similarity: float
    structural_similarity: float
    matches_count: int
    total_tokens: int
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        """Return string representation of similarity result."""
        return (
            f"Similarity: {self.similarity_score:.2%} "
            f"(tokens: {self.token_similarity:.2%}, "
            f"structure: {self.structural_similarity:.2%})"
        )


class TokenSimilarity:
    """Token-based code similarity analyzer.

    Analyzes Python code at the token level to detect similarities
    that may indicate code duplication. Uses Python's tokenize module
    for accurate lexical analysis.

    The similarity analysis considers:
    - Token type matching (keywords, operators, identifiers, etc.)
    - Token sequence patterns
    - Weighted importance of different token types
    - Structural similarities beyond exact text matching

    Example:
        analyzer = TokenSimilarity()
        result = analyzer.compare_code_blocks(code1, code2)
        print(f"Similarity: {result.similarity_score:.2%}")
    """

    # Default token type weights
    DEFAULT_WEIGHTS = {
        TokenType.KEYWORD: 1.0,
        TokenType.OPERATOR: 0.9,
        TokenType.IDENTIFIER: 0.7,
        TokenType.LITERAL: 0.5,
        TokenType.DELIMITER: 0.3,
        TokenType.COMMENT: 0.0,
    }

    def __init__(
        self,
        token_weights: dict[TokenType, float] | None = None,
        ignore_comments: bool = True,
        min_sequence_length: int = 3,
    ) -> None:
        """Initialize the token similarity analyzer.

        Args:
            token_weights: Custom weights for token types. If None, uses defaults.
            ignore_comments: Whether to ignore comments in similarity analysis
            min_sequence_length: Minimum token sequence length for comparison
        """
        self.token_weights = token_weights or self.DEFAULT_WEIGHTS.copy()
        self.ignore_comments = ignore_comments
        self.min_sequence_length = min_sequence_length

    def tokenize_code(self, code: str) -> TokenSequence:
        """Tokenize Python code into a TokenSequence.

        Args:
            code: Python source code as string

        Returns:
            TokenSequence containing all tokens from the code

        Raises:
            SyntaxError: If code has invalid Python syntax
            tokenize.TokenError: If code has tokenization errors
        """
        # Convert code to bytes for tokenize
        code_bytes = code.encode("utf-8")

        # Create StringIO for tokenize
        code_stream = io.BytesIO(code_bytes)

        # Tokenize the code
        tokens = []
        try:
            for tok in tokenize.tokenize(code_stream.readline):
                # Skip ENCODING and ENDMARKER tokens
                if tok.type in (tokenize.ENCODING, tokenize.ENDMARKER):
                    continue

                # Convert to our TokenInfo format
                token_info = TokenInfo.from_tokenize(tok)

                # Skip comments if configured
                if self.ignore_comments and token_info.type == TokenType.COMMENT:
                    continue

                tokens.append(token_info)

        except (SyntaxError, tokenize.TokenError) as e:
            raise SyntaxError(f"Failed to tokenize code: {e}") from e

        return TokenSequence(tokens=tokens)

    def tokenize_file(self, file_path: str | Path) -> TokenSequence:
        """Tokenize a Python file.

        Args:
            file_path: Path to Python source file

        Returns:
            TokenSequence containing all tokens from the file

        Raises:
            FileNotFoundError: If file does not exist
            SyntaxError: If file has invalid Python syntax
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Read file content
        with open(file_path, encoding="utf-8") as f:
            code = f.read()

        # Tokenize
        sequence = self.tokenize_code(code)
        sequence.source_file = str(file_path)

        return sequence

    def compare_sequences(
        self,
        seq1: TokenSequence,
        seq2: TokenSequence,
    ) -> SimilarityResult:
        """Compare two token sequences for similarity.

        Args:
            seq1: First token sequence
            seq2: Second token sequence

        Returns:
            SimilarityResult with similarity metrics
        """
        if not seq1.tokens or not seq2.tokens:
            return SimilarityResult(
                similarity_score=0.0,
                token_similarity=0.0,
                structural_similarity=0.0,
                matches_count=0,
                total_tokens=0,
            )

        # Calculate token-level similarity
        token_similarity = self._calculate_token_similarity(seq1, seq2)

        # Calculate structural similarity
        structural_similarity = self._calculate_structural_similarity(seq1, seq2)

        # Calculate overall similarity (weighted average)
        overall_similarity = (
            token_similarity * 0.6 +
            structural_similarity * 0.4
        )

        # Count matches
        matches_count = self._count_matching_tokens(seq1, seq2)
        total_tokens = max(len(seq1), len(seq2))

        # Build details dictionary
        details = self._build_similarity_details(seq1, seq2)

        return SimilarityResult(
            similarity_score=overall_similarity,
            token_similarity=token_similarity,
            structural_similarity=structural_similarity,
            matches_count=matches_count,
            total_tokens=total_tokens,
            details=details,
        )

    def compare_code_blocks(self, code1: str, code2: str) -> SimilarityResult:
        """Compare two Python code blocks for similarity.

        Args:
            code1: First Python code block
            code2: Second Python code block

        Returns:
            SimilarityResult with similarity metrics

        Raises:
            SyntaxError: If either code block has invalid syntax
        """
        # Tokenize both code blocks
        seq1 = self.tokenize_code(code1)
        seq2 = self.tokenize_code(code2)

        # Compare sequences
        return self.compare_sequences(seq1, seq2)

    def compare_files(
        self,
        file1: str | Path,
        file2: str | Path,
    ) -> SimilarityResult:
        """Compare two Python files for similarity.

        Args:
            file1: Path to first Python file
            file2: Path to second Python file

        Returns:
            SimilarityResult with similarity metrics

        Raises:
            FileNotFoundError: If either file does not exist
            SyntaxError: If either file has invalid syntax
        """
        # Tokenize both files
        seq1 = self.tokenize_file(file1)
        seq2 = self.tokenize_file(file2)

        # Compare sequences
        return self.compare_sequences(seq1, seq2)

    def find_similar_blocks(
        self,
        code: str,
        target_sequence: TokenSequence,
        min_similarity: float = 0.7,
    ) -> list[tuple[int, int, float]]:
        """Find code blocks similar to a target token sequence.

        Args:
            code: Python code to search within
            target_sequence: Token sequence to search for
            min_similarity: Minimum similarity threshold (0.0-1.0)

        Returns:
            List of tuples (start_line, end_line, similarity) for matches
        """
        # Tokenize the code
        code_sequence = self.tokenize_code(code)

        if len(target_sequence) < self.min_sequence_length:
            return []

        matches = []

        # Sliding window comparison
        window_size = len(target_sequence)
        if window_size > len(code_sequence):
            window_size = len(code_sequence)

        for i in range(len(code_sequence) - window_size + 1):
            # Extract window
            window = TokenSequence(tokens=code_sequence.tokens[i:i + window_size])

            # Compare with target
            result = self.compare_sequences(target_sequence, window)

            if result.similarity_score >= min_similarity:
                # Get line numbers
                start_token = code_sequence.tokens[i]
                end_token = code_sequence.tokens[min(i + window_size - 1,
                                                     len(code_sequence) - 1)]

                matches.append((
                    start_token.start_row,
                    end_token.end_row,
                    result.similarity_score,
                ))

        return matches

    def _calculate_token_similarity(
        self,
        seq1: TokenSequence,
        seq2: TokenSequence,
    ) -> float:
        """Calculate token-level similarity between sequences.

        Args:
            seq1: First token sequence
            seq2: Second token sequence

        Returns:
            Similarity score (0.0-1.0)
        """
        if not seq1.tokens or not seq2.tokens:
            return 0.0

        # Get token strings for comparison
        tokens1 = seq1.get_token_strings()
        tokens2 = seq2.get_token_strings()

        # Use SequenceMatcher for similarity
        matcher = SequenceMatcher(None, tokens1, tokens2)
        return matcher.ratio()

    def _calculate_structural_similarity(
        self,
        seq1: TokenSequence,
        seq2: TokenSequence,
    ) -> float:
        """Calculate structural similarity between sequences.

        Compares token type patterns rather than exact tokens,
        allowing for identifier renaming and literal changes.

        Args:
            seq1: First token sequence
            seq2: Second token sequence

        Returns:
            Similarity score (0.0-1.0)
        """
        if not seq1.tokens or not seq2.tokens:
            return 0.0

        # Get token types
        types1 = [t.type.value for t in seq1.tokens]
        types2 = [t.type.value for t in seq2.tokens]

        # Use SequenceMatcher on type sequences
        matcher = SequenceMatcher(None, types1, types2)
        return matcher.ratio()

    def _count_matching_tokens(
        self,
        seq1: TokenSequence,
        seq2: TokenSequence,
    ) -> int:
        """Count matching tokens between sequences.

        Args:
            seq1: First token sequence
            seq2: Second token sequence

        Returns:
            Number of matching tokens
        """
        if not seq1.tokens or not seq2.tokens:
            return 0

        # Get token strings
        tokens1 = seq1.get_token_strings()
        tokens2 = seq2.get_token_strings()

        # Count matches using SequenceMatcher
        matcher = SequenceMatcher(None, tokens1, tokens2)
        matches = matcher.get_matching_blocks()

        # Sum up match lengths
        match_count = sum(m.size for m in matches)

        return match_count

    def _build_similarity_details(
        self,
        seq1: TokenSequence,
        seq2: TokenSequence,
    ) -> dict[str, Any]:
        """Build detailed similarity breakdown by token type.

        Args:
            seq1: First token sequence
            seq2: Second token sequence

        Returns:
            Dictionary with similarity details by token type
        """
        details = {}

        # Count tokens by type in each sequence
        type_counts1: dict[TokenType, int] = {}
        type_counts2: dict[TokenType, int] = {}

        for token in seq1.tokens:
            type_counts1[token.type] = type_counts1.get(token.type, 0) + 1

        for token in seq2.tokens:
            type_counts2[token.type] = type_counts2.get(token.type, 0) + 1

        # Calculate similarity for each token type
        for token_type in TokenType:
            if token_type == TokenType.COMMENT and self.ignore_comments:
                continue

            count1 = type_counts1.get(token_type, 0)
            count2 = type_counts2.get(token_type, 0)

            # Calculate type similarity
            max_count = max(count1, count2)
            if max_count == 0:
                type_similarity = 1.0
            else:
                type_similarity = 1.0 - abs(count1 - count2) / max_count

            details[token_type.value] = {
                "count_seq1": count1,
                "count_seq2": count2,
                "similarity": type_similarity,
                "weight": self.token_weights.get(token_type, 0.5),
            }

        return details
