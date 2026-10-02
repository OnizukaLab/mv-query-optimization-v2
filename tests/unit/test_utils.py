"""Test utility modules."""

import os
import tempfile

import pytest

from src.utils.file_utils import (
    ensure_directory,
    get_file_extension,
    get_filename_without_extension,
    natural_sort_key,
    read_csv_file,
    read_json_file,
    write_csv_file,
    write_json_file,
)
from src.utils.validators import (
    ValidationError,
    validate_directory_exists,
    validate_file_exists,
    validate_in_range,
    validate_non_negative_number,
    validate_not_empty,
    validate_one_of,
    validate_positive_number,
    validate_type,
)


class TestFileUtils:
    """Test file utility functions."""

    def test_natural_sort_key(self):
        """Test natural sorting."""
        files = ["file10.txt", "file2.txt", "file1.txt", "file20.txt"]
        sorted_files = sorted(files, key=natural_sort_key)
        assert sorted_files == ["file1.txt", "file2.txt", "file10.txt", "file20.txt"]

    def test_ensure_directory(self):
        """Test directory creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = os.path.join(tmpdir, "test", "nested", "dir")
            ensure_directory(test_dir)
            assert os.path.isdir(test_dir)

    def test_read_write_json(self):
        """Test JSON file operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.json")
            data = {"key": "value", "number": 42}

            write_json_file(filepath, data)
            loaded_data = read_json_file(filepath)

            assert loaded_data == data

    def test_read_write_csv(self):
        """Test CSV file operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.csv")
            header = ["col1", "col2", "col3"]
            rows = [["a", "b", "c"], ["1", "2", "3"]]

            write_csv_file(filepath, rows, header=header)
            loaded_rows = read_csv_file(filepath, skip_header=True)

            assert loaded_rows == rows

    def test_get_filename_without_extension(self):
        """Test filename extraction."""
        assert get_filename_without_extension("/path/to/file.json") == "file"
        assert get_filename_without_extension("file.tar.gz") == "file.tar"

    def test_get_file_extension(self):
        """Test file extension extraction."""
        assert get_file_extension("/path/to/file.json") == ".json"
        assert get_file_extension("file.tar.gz") == ".gz"


class TestValidators:
    """Test validation functions."""

    def test_validate_file_exists(self):
        """Test file existence validation."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            filepath = f.name

        try:
            # Should not raise
            validate_file_exists(filepath)

            # Should raise
            os.unlink(filepath)
            with pytest.raises(ValidationError):
                validate_file_exists(filepath)
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_validate_directory_exists(self):
        """Test directory existence validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Should not raise
            validate_directory_exists(tmpdir)

        # Should raise (directory deleted)
        with pytest.raises(ValidationError):
            validate_directory_exists(tmpdir)

    def test_validate_not_empty(self):
        """Test non-empty validation."""
        # Should not raise
        validate_not_empty("value", "test")
        validate_not_empty([1, 2, 3], "test")

        # Should raise
        with pytest.raises(ValidationError):
            validate_not_empty("", "test")
        with pytest.raises(ValidationError):
            validate_not_empty([], "test")
        with pytest.raises(ValidationError):
            validate_not_empty(None, "test")

    def test_validate_positive_number(self):
        """Test positive number validation."""
        # Should not raise
        validate_positive_number(1, "test")
        validate_positive_number(100.5, "test")

        # Should raise
        with pytest.raises(ValidationError):
            validate_positive_number(0, "test")
        with pytest.raises(ValidationError):
            validate_positive_number(-1, "test")

    def test_validate_non_negative_number(self):
        """Test non-negative number validation."""
        # Should not raise
        validate_non_negative_number(0, "test")
        validate_non_negative_number(100, "test")

        # Should raise
        with pytest.raises(ValidationError):
            validate_non_negative_number(-1, "test")

    def test_validate_in_range(self):
        """Test range validation."""
        # Should not raise
        validate_in_range(50, "test", min_value=0, max_value=100)
        validate_in_range(0, "test", min_value=0)
        validate_in_range(100, "test", max_value=100)

        # Should raise
        with pytest.raises(ValidationError):
            validate_in_range(-1, "test", min_value=0)
        with pytest.raises(ValidationError):
            validate_in_range(101, "test", max_value=100)

    def test_validate_type(self):
        """Test type validation."""
        # Should not raise
        validate_type("string", str, "test")
        validate_type(42, int, "test")
        validate_type([1, 2, 3], list, "test")

        # Should raise
        with pytest.raises(ValidationError):
            validate_type("string", int, "test")
        with pytest.raises(ValidationError):
            validate_type(42, str, "test")

    def test_validate_one_of(self):
        """Test one-of validation."""
        # Should not raise
        validate_one_of("a", ["a", "b", "c"], "test")
        validate_one_of(2, [1, 2, 3], "test")

        # Should raise
        with pytest.raises(ValidationError):
            validate_one_of("d", ["a", "b", "c"], "test")
        with pytest.raises(ValidationError):
            validate_one_of(4, [1, 2, 3], "test")


class TestLoggingUtils:
    """Test logging utilities."""

    def test_setup_logging(self):
        """Test logging setup."""
        from src.utils.logging_utils import get_logger, setup_logging

        # Setup logger
        logger = setup_logging("test_logger", level="DEBUG", console=False)
        assert logger is not None
        assert logger.name == "test_logger"

        # Get logger
        logger2 = get_logger("test_logger")
        assert logger2.name == "test_logger"

    def test_logger_mixin(self):
        """Test LoggerMixin."""
        from src.utils.logging_utils import LoggerMixin

        class TestClass(LoggerMixin):
            pass

        obj = TestClass()
        assert obj.logger is not None
        assert "TestClass" in obj.logger.name

    def test_progress_logger(self):
        """Test ProgressLogger."""
        from src.utils.logging_utils import ProgressLogger, setup_logging

        logger = setup_logging("test", level="INFO", console=False)
        progress = ProgressLogger("Test operation", total=10, logger=logger)

        progress.update(5)
        assert progress.current == 5

        progress.complete()
