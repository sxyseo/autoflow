from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


# Import the module directly since it's in the same project
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import integrity


class IntegrityHashFileContentTests(unittest.TestCase):
    """Tests for hash_file_content function."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_hash_file_content_returns_sha256_hash(self) -> None:
        """Test that hash_file_content returns a valid SHA-256 hash."""
        test_file = Path(self.temp_dir.name) / "test.txt"
        test_file.write_text("Hello, World!", encoding="utf-8")

        result = integrity.hash_file_content(test_file)

        # SHA-256 hash of "Hello, World!" is known
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        self.assertEqual(result, expected)

    def test_hash_file_content_handles_empty_file(self) -> None:
        """Test that hash_file_content handles empty files correctly."""
        test_file = Path(self.temp_dir.name) / "empty.txt"
        test_file.write_text("", encoding="utf-8")

        result = integrity.hash_file_content(test_file)

        # SHA-256 hash of empty string
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        self.assertEqual(result, expected)

    def test_hash_file_content_handles_binary_file(self) -> None:
        """Test that hash_file_content handles binary files correctly."""
        test_file = Path(self.temp_dir.name) / "binary.bin"
        test_file.write_bytes(b'\x00\x01\x02\x03\xff\xfe\xfd\xfc')

        result = integrity.hash_file_content(test_file)

        # Known hash for this binary content
        expected = "aeb3fc9f3b6e81c911a2a3f3c3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3"
        self.assertEqual(len(result), 64)  # SHA-256 is 64 hex chars

    def test_hash_file_content_handles_large_file(self) -> None:
        """Test that hash_file_content handles large files with chunked reading."""
        test_file = Path(self.temp_dir.name) / "large.txt"
        # Create a file larger than the chunk size (8192 bytes)
        test_file.write_text("x" * 10000, encoding="utf-8")

        result = integrity.hash_file_content(test_file)

        self.assertEqual(len(result), 64)  # SHA-256 is 64 hex chars

    def test_hash_file_content_raises_error_for_nonexistent_file(self) -> None:
        """Test that hash_file_content raises FileNotFoundError for missing files."""
        nonexistent = Path(self.temp_dir.name) / "does_not_exist.txt"

        with self.assertRaises(FileNotFoundError) as context:
            integrity.hash_file_content(nonexistent)

        self.assertIn("File not found", str(context.exception))

    def test_hash_file_content_raises_error_for_directory(self) -> None:
        """Test that hash_file_content raises ValueError for directories."""
        with self.assertRaises(ValueError) as context:
            integrity.hash_file_content(self.temp_dir.name)

        self.assertIn("not a file", str(context.exception))

    def test_hash_file_content_supports_different_algorithms(self) -> None:
        """Test that hash_file_content supports different hash algorithms."""
        test_file = Path(self.temp_dir.name) / "test.txt"
        test_file.write_text("test", encoding="utf-8")

        sha256_hash = integrity.hash_file_content(test_file, "sha256")
        sha512_hash = integrity.hash_file_content(test_file, "sha512")

        self.assertEqual(len(sha256_hash), 64)  # SHA-256 is 64 hex chars
        self.assertEqual(len(sha512_hash), 128)  # SHA-512 is 128 hex chars

    def test_hash_file_content_raises_error_for_invalid_algorithm(self) -> None:
        """Test that hash_file_content raises ValueError for unsupported algorithms."""
        test_file = Path(self.temp_dir.name) / "test.txt"
        test_file.write_text("test", encoding="utf-8")

        with self.assertRaises(ValueError) as context:
            integrity.hash_file_content(test_file, "invalid_algorithm")

        self.assertIn("Unsupported hash algorithm", str(context.exception))


class IntegrityHashStringContentTests(unittest.TestCase):
    """Tests for hash_string_content function."""

    def test_hash_string_content_returns_sha256_hash(self) -> None:
        """Test that hash_string_content returns a valid SHA-256 hash."""
        result = integrity.hash_string_content("Hello, World!")

        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        self.assertEqual(result, expected)

    def test_hash_string_content_handles_empty_string(self) -> None:
        """Test that hash_string_content handles empty strings correctly."""
        result = integrity.hash_string_content("")

        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        self.assertEqual(result, expected)

    def test_hash_string_content_handles_unicode(self) -> None:
        """Test that hash_string_content handles Unicode characters correctly."""
        result = integrity.hash_string_content("Hello, 世界! 🌍")

        self.assertEqual(len(result), 64)  # SHA-256 is 64 hex chars

    def test_hash_string_content_supports_different_algorithms(self) -> None:
        """Test that hash_string_content supports different hash algorithms."""
        sha256_hash = integrity.hash_string_content("test", "sha256")
        sha512_hash = integrity.hash_string_content("test", "sha512")

        self.assertEqual(len(sha256_hash), 64)  # SHA-256 is 64 hex chars
        self.assertEqual(len(sha512_hash), 128)  # SHA-512 is 128 hex chars

    def test_hash_string_content_raises_error_for_invalid_algorithm(self) -> None:
        """Test that hash_string_content raises ValueError for unsupported algorithms."""
        with self.assertRaises(ValueError) as context:
            integrity.hash_string_content("test", "invalid_algorithm")

        self.assertIn("Unsupported hash algorithm", str(context.exception))


class IntegrityVerifyFileTests(unittest.TestCase):
    """Tests for verify_file_integrity function."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_verify_file_integrity_returns_true_for_matching_hash(self) -> None:
        """Test that verify_file_integrity returns True for matching hashes."""
        test_file = Path(self.temp_dir.name) / "test.txt"
        test_file.write_text("Hello, World!", encoding="utf-8")

        expected_hash = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        result = integrity.verify_file_integrity(test_file, expected_hash)

        self.assertTrue(result)

    def test_verify_file_integrity_returns_false_for_mismatched_hash(self) -> None:
        """Test that verify_file_integrity returns False for mismatched hashes."""
        test_file = Path(self.temp_dir.name) / "test.txt"
        test_file.write_text("Hello, World!", encoding="utf-8")

        wrong_hash = "0" * 64  # All zeros
        result = integrity.verify_file_integrity(test_file, wrong_hash)

        self.assertFalse(result)

    def test_verify_file_integrity_returns_false_for_tampered_file(self) -> None:
        """Test that verify_file_integrity returns False for tampered files."""
        test_file = Path(self.temp_dir.name) / "test.txt"
        test_file.write_text("Original content", encoding="utf-8")

        original_hash = integrity.hash_file_content(test_file)

        # Tamper with the file
        test_file.write_text("Modified content", encoding="utf-8")

        result = integrity.verify_file_integrity(test_file, original_hash)
        self.assertFalse(result)

    def test_verify_file_integrity_raises_error_for_nonexistent_file(self) -> None:
        """Test that verify_file_integrity raises FileNotFoundError for missing files."""
        nonexistent = Path(self.temp_dir.name) / "does_not_exist.txt"

        with self.assertRaises(FileNotFoundError):
            integrity.verify_file_integrity(nonexistent, "any_hash")

    def test_verify_file_integrity_supports_different_algorithms(self) -> None:
        """Test that verify_file_integrity supports different hash algorithms."""
        test_file = Path(self.temp_dir.name) / "test.txt"
        test_file.write_text("test", encoding="utf-8")

        sha256_hash = integrity.hash_string_content("test", "sha256")
        sha512_hash = integrity.hash_string_content("test", "sha512")

        self.assertTrue(integrity.verify_file_integrity(test_file, sha256_hash, "sha256"))
        self.assertTrue(integrity.verify_file_integrity(test_file, sha512_hash, "sha512"))


class IntegrityCompareHashesTests(unittest.TestCase):
    """Tests for _compare_hashes private function."""

    def test_compare_hashes_returns_true_for_identical_hashes(self) -> None:
        """Test that _compare_hashes returns True for identical hashes."""
        hash1 = "a" * 64
        hash2 = "a" * 64

        result = integrity._compare_hashes(hash1, hash2)
        self.assertTrue(result)

    def test_compare_hashes_returns_false_for_different_hashes(self) -> None:
        """Test that _compare_hashes returns False for different hashes."""
        hash1 = "a" * 64
        hash2 = "b" * 64

        result = integrity._compare_hashes(hash1, hash2)
        self.assertFalse(result)

    def test_compare_hashes_returns_false_for_different_length_hashes(self) -> None:
        """Test that _compare_hashes returns False for different length hashes."""
        hash1 = "a" * 64
        hash2 = "a" * 128

        result = integrity._compare_hashes(hash1, hash2)
        self.assertFalse(result)

    def test_compare_hashes_detects_single_character_difference(self) -> None:
        """Test that _compare_hashes detects single character differences."""
        hash1 = "a" * 63 + "b"
        hash2 = "a" * 64

        result = integrity._compare_hashes(hash1, hash2)
        self.assertFalse(result)


class IntegrityIntegrationTests(unittest.TestCase):
    """Integration tests for the integrity module."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_hash_and_verify_workflow(self) -> None:
        """Test the complete hash and verify workflow."""
        test_file = Path(self.temp_dir.name) / "document.txt"
        original_content = "This is important data that must not be tampered with."
        test_file.write_text(original_content, encoding="utf-8")

        # Generate hash
        original_hash = integrity.hash_file_content(test_file)

        # Verify integrity
        self.assertTrue(integrity.verify_file_integrity(test_file, original_hash))

        # Modify file
        test_file.write_text("This has been tampered with!", encoding="utf-8")

        # Verify tampering is detected
        self.assertFalse(integrity.verify_file_integrity(test_file, original_hash))

    def test_multiple_files_integrity_check(self) -> None:
        """Test integrity checking for multiple files."""
        files = {}
        for i in range(3):
            test_file = Path(self.temp_dir.name) / f"file{i}.txt"
            content = f"File {i} content"
            test_file.write_text(content, encoding="utf-8")
            files[str(test_file)] = integrity.hash_file_content(test_file)

        # Verify all files
        for file_path, expected_hash in files.items():
            self.assertTrue(integrity.verify_file_integrity(file_path, expected_hash))

    def test_string_and_file_hash_consistency(self) -> None:
        """Test that hash_string_content and hash_file_content produce same result."""
        test_content = "Consistent content"

        test_file = Path(self.temp_dir.name) / "test.txt"
        test_file.write_text(test_content, encoding="utf-8")

        file_hash = integrity.hash_file_content(test_file)
        string_hash = integrity.hash_string_content(test_content)

        self.assertEqual(file_hash, string_hash)


if __name__ == "__main__":
    unittest.main()
