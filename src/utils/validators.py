"""Validation utilities for data and configuration validation."""

import os
from typing import Any


class ValidationError(Exception):
    """Custom exception for validation errors."""

    pass


def validate_file_exists(filepath: str, description: str = "File") -> None:
    """
    Validate that a file exists.

    Args:
        filepath: Path to file
        description: Description of the file for error message

    Raises:
        ValidationError: If file doesn't exist

    Example:
        >>> validate_file_exists('config/default.yaml', 'Config file')
    """
    if not os.path.isfile(filepath):
        raise ValidationError(f"{description} not found: {filepath}")


def validate_directory_exists(dirpath: str, description: str = "Directory") -> None:
    """
    Validate that a directory exists.

    Args:
        dirpath: Path to directory
        description: Description of the directory for error message

    Raises:
        ValidationError: If directory doesn't exist
    """
    if not os.path.isdir(dirpath):
        raise ValidationError(f"{description} not found: {dirpath}")


def validate_not_empty(value: Any, name: str) -> None:
    """
    Validate that a value is not empty.

    Args:
        value: Value to validate
        name: Name of the value for error message

    Raises:
        ValidationError: If value is empty
    """
    if not value:
        raise ValidationError(f"{name} cannot be empty")


def validate_positive_number(value: int | float, name: str) -> None:
    """
    Validate that a number is positive.

    Args:
        value: Number to validate
        name: Name of the value for error message

    Raises:
        ValidationError: If number is not positive
    """
    if value <= 0:
        raise ValidationError(f"{name} must be positive, got {value}")


def validate_non_negative_number(value: int | float, name: str) -> None:
    """
    Validate that a number is non-negative.

    Args:
        value: Number to validate
        name: Name of the value for error message

    Raises:
        ValidationError: If number is negative
    """
    if value < 0:
        raise ValidationError(f"{name} must be non-negative, got {value}")


def validate_in_range(
    value: int | float,
    name: str,
    min_value: int | float | None = None,
    max_value: int | float | None = None,
) -> None:
    """
    Validate that a number is within a specified range.

    Args:
        value: Number to validate
        name: Name of the value for error message
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive)

    Raises:
        ValidationError: If number is out of range
    """
    if min_value is not None and value < min_value:
        raise ValidationError(f"{name} must be >= {min_value}, got {value}")
    if max_value is not None and value > max_value:
        raise ValidationError(f"{name} must be <= {max_value}, got {value}")


def validate_type(value: Any, expected_type: type, name: str) -> None:
    """
    Validate that a value is of the expected type.

    Args:
        value: Value to validate
        expected_type: Expected type
        name: Name of the value for error message

    Raises:
        ValidationError: If value is not of expected type
    """
    if not isinstance(value, expected_type):
        raise ValidationError(
            f"{name} must be of type {expected_type.__name__}, " f"got {type(value).__name__}"
        )


def validate_one_of(value: Any, allowed_values: list[Any], name: str) -> None:
    """
    Validate that a value is one of the allowed values.

    Args:
        value: Value to validate
        allowed_values: List of allowed values
        name: Name of the value for error message

    Raises:
        ValidationError: If value is not in allowed values
    """
    if value not in allowed_values:
        raise ValidationError(f"{name} must be one of {allowed_values}, got {value}")


def validate_file_extension(
    filepath: str, allowed_extensions: list[str], description: str = "File"
) -> None:
    """
    Validate that a file has one of the allowed extensions.

    Args:
        filepath: Path to file
        allowed_extensions: List of allowed extensions (e.g., ['.json', '.yaml'])
        description: Description of the file for error message

    Raises:
        ValidationError: If file extension is not allowed
    """
    ext = os.path.splitext(filepath)[1]
    if ext not in allowed_extensions:
        raise ValidationError(
            f"{description} must have one of these extensions: " f"{allowed_extensions}, got {ext}"
        )


def validate_dict_keys(
    data: dict, required_keys: list[str], description: str = "Dictionary"
) -> None:
    """
    Validate that a dictionary contains all required keys.

    Args:
        data: Dictionary to validate
        required_keys: List of required keys
        description: Description of the dictionary for error message

    Raises:
        ValidationError: If dictionary is missing required keys
    """
    missing_keys = [key for key in required_keys if key not in data]
    if missing_keys:
        raise ValidationError(f"{description} missing required keys: {missing_keys}")


def validate_list_not_empty(value: list[Any], name: str) -> None:
    """
    Validate that a list is not empty.

    Args:
        value: List to validate
        name: Name of the list for error message

    Raises:
        ValidationError: If list is empty
    """
    if not value:
        raise ValidationError(f"{name} cannot be empty")


def validate_path_writable(dirpath: str, description: str = "Directory") -> None:
    """
    Validate that a directory is writable.

    Args:
        dirpath: Path to directory
        description: Description of the directory for error message

    Raises:
        ValidationError: If directory is not writable
    """
    if not os.access(dirpath, os.W_OK):
        raise ValidationError(f"{description} is not writable: {dirpath}")


def validate_storage_limit(storage_limit_bytes: int, min_mb: int = 1, max_mb: int = 10000) -> None:
    """
    Validate storage limit is within reasonable bounds.

    Args:
        storage_limit_bytes: Storage limit in bytes
        min_mb: Minimum storage in MB
        max_mb: Maximum storage in MB

    Raises:
        ValidationError: If storage limit is out of bounds
    """
    min_bytes = min_mb * 1024 * 1024
    max_bytes = max_mb * 1024 * 1024

    if storage_limit_bytes < min_bytes:
        raise ValidationError(
            f"Storage limit must be at least {min_mb} MB, "
            f"got {storage_limit_bytes / (1024 * 1024):.2f} MB"
        )

    if storage_limit_bytes > max_bytes:
        raise ValidationError(
            f"Storage limit must be at most {max_mb} MB, "
            f"got {storage_limit_bytes / (1024 * 1024):.2f} MB"
        )


def validate_database_config(config) -> None:
    """
    Validate database configuration.

    Args:
        config: DatabaseConfig instance

    Raises:
        ValidationError: If configuration is invalid
    """
    validate_not_empty(config.host, "Database host")
    validate_positive_number(config.port, "Database port")
    validate_in_range(config.port, "Database port", 1, 65535)
    validate_not_empty(config.database, "Database name")
    validate_not_empty(config.user, "Database user")
    validate_positive_number(config.timeout, "Database timeout")


def validate_optimization_config(config) -> None:
    """
    Validate optimization configuration.

    Args:
        config: OptimizationConfig instance

    Raises:
        ValidationError: If configuration is invalid
    """
    validate_positive_number(config.storage_limit_mb, "Storage limit (MB)")
    validate_positive_number(config.storage_limit_bytes, "Storage limit (bytes)")
    validate_positive_number(config.insert_queries, "Insert queries count")

    # Validate storage limit consistency
    expected_bytes = config.storage_limit_mb * 1024 * 1024
    if abs(config.storage_limit_bytes - expected_bytes) > 1024:  # 1KB tolerance
        raise ValidationError(
            f"Storage limit mismatch: {config.storage_limit_mb} MB != "
            f"{config.storage_limit_bytes} bytes"
        )
