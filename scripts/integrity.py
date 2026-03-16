#!/usr/bin/env python3
"""
Autoflow File Integrity Module

Provides cryptographic integrity verification for run artifacts.
Generates and verifies SHA-256 hashes for files to detect tampering
and ensure only authorized code is executed.
"""

import hashlib
from pathlib import Path
from typing import Optional, Union


def hash_file_content(
    file_path: Union[str, Path],
    algorithm: str = "sha256"
) -> str:
    """
    Generate cryptographic hash of file content.

    Args:
        file_path: Path to the file to hash
        algorithm: Hash algorithm to use (default: sha256)

    Returns:
        Hexadecimal hash string

    Raises:
        FileNotFoundError: If file does not exist
        IOError: If file cannot be read
        ValueError: If algorithm is not supported
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    # Validate algorithm
    try:
        hasher = hashlib.new(algorithm)
    except ValueError:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")

    # Read file in binary mode and compute hash
    try:
        with open(file_path, 'rb') as f:
            # Read in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
    except IOError as e:
        raise IOError(f"Failed to read file: {file_path}: {e}")

    return hasher.hexdigest()


def hash_string_content(
    content: str,
    algorithm: str = "sha256"
) -> str:
    """
    Generate cryptographic hash of string content.

    Args:
        content: String content to hash
        algorithm: Hash algorithm to use (default: sha256)

    Returns:
        Hexadecimal hash string

    Raises:
        ValueError: If algorithm is not supported
    """
    try:
        hasher = hashlib.new(algorithm)
    except ValueError:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")

    hasher.update(content.encode('utf-8'))
    return hasher.hexdigest()


def verify_file_integrity(
    file_path: Union[str, Path],
    expected_hash: str,
    algorithm: str = "sha256"
) -> bool:
    """
    Verify file integrity by comparing computed hash with expected hash.

    Args:
        file_path: Path to the file to verify
        expected_hash: Expected hash value (hexadecimal string)
        algorithm: Hash algorithm to use (default: sha256)

    Returns:
        True if file hash matches expected hash, False otherwise

    Raises:
        FileNotFoundError: If file does not exist
        IOError: If file cannot be read
        ValueError: If algorithm is not supported
    """
    computed_hash = hash_file_content(file_path, algorithm)

    # Compare hashes in constant time to prevent timing attacks
    return _compare_hashes(computed_hash, expected_hash)


def _compare_hashes(hash1: str, hash2: str) -> bool:
    """
    Compare two hashes in constant time to prevent timing attacks.

    Args:
        hash1: First hash string
        hash2: Second hash string

    Returns:
        True if hashes are equal, False otherwise
    """
    if len(hash1) != len(hash2):
        return False

    result = 0
    for c1, c2 in zip(hash1, hash2):
        result |= ord(c1) ^ ord(c2)

    return result == 0
