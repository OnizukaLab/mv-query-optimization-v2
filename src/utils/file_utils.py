"""File operation utilities."""

import csv
import json
import os
import re
from pathlib import Path
from typing import Any


def natural_sort_key(s: str) -> list:
    """
    Natural sorting key for strings containing numbers.

    Converts numeric parts to integers for proper numerical sorting.

    Args:
        s: String to create sort key for

    Returns:
        List of integers and strings for natural sorting

    Example:
        >>> sorted(['file1.txt', 'file10.txt', 'file2.txt'], key=natural_sort_key)
        ['file1.txt', 'file2.txt', 'file10.txt']
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split("([0-9]+)", s)]


def get_all_files(directory: str, extension: str | None = None) -> list[str]:
    """
    Recursively get all files in directory.

    Args:
        directory: Root directory to search
        extension: Optional file extension filter (e.g., '.json', '.sql')

    Returns:
        List of absolute file paths

    Example:
        >>> files = get_all_files('dataset', extension='.json')
        >>> len(files) > 0
        True
    """
    result = []
    for folder, _, files in os.walk(directory):
        for f in files:
            if extension is None or f.endswith(extension):
                result.append(os.path.join(folder, f))
    return result


def ensure_directory(path: str) -> None:
    """
    Ensure directory exists, create if it doesn't.

    Creates all intermediate directories as needed.

    Args:
        path: Directory path to ensure

    Example:
        >>> ensure_directory('output/experiments/test')
        >>> os.path.exists('output/experiments/test')
        True
    """
    Path(path).mkdir(parents=True, exist_ok=True)


def read_json_file(filepath: str) -> dict[str, Any]:
    """
    Read JSON file and return parsed data.

    Args:
        filepath: Path to JSON file

    Returns:
        Parsed JSON data as dictionary

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file is not valid JSON
    """
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def write_json_file(filepath: str, data: dict[str, Any], indent: int = 2) -> None:
    """
    Write data to JSON file.

    Args:
        filepath: Path to output JSON file
        data: Data to write
        indent: Indentation level for pretty printing
    """
    ensure_directory(os.path.dirname(filepath))
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def read_csv_file(filepath: str, skip_header: bool = True) -> list[list[str]]:
    """
    Read CSV file and return rows.

    Args:
        filepath: Path to CSV file
        skip_header: Whether to skip the first row (header)

    Returns:
        List of rows, where each row is a list of strings
    """
    with open(filepath, encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
        return rows[1:] if skip_header and len(rows) > 0 else rows


def write_csv_file(
    filepath: str, rows: list[list[str]], header: list[str] | None = None
) -> None:
    """
    Write rows to CSV file.

    Args:
        filepath: Path to output CSV file
        rows: List of rows to write
        header: Optional header row
    """
    ensure_directory(os.path.dirname(filepath))
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if header:
            writer.writerow(header)
        writer.writerows(rows)


def read_sql_file(filepath: str) -> str:
    """
    Read SQL file and return contents.

    Args:
        filepath: Path to SQL file

    Returns:
        SQL file contents as string
    """
    with open(filepath, encoding="utf-8") as f:
        return f.read()


def write_sql_file(filepath: str, sql: str) -> None:
    """
    Write SQL to file.

    Args:
        filepath: Path to output SQL file
        sql: SQL content to write
    """
    ensure_directory(os.path.dirname(filepath))
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(sql)


def get_file_size(filepath: str) -> int:
    """
    Get file size in bytes.

    Args:
        filepath: Path to file

    Returns:
        File size in bytes
    """
    return os.path.getsize(filepath)


def file_exists(filepath: str) -> bool:
    """
    Check if file exists.

    Args:
        filepath: Path to file

    Returns:
        True if file exists, False otherwise
    """
    return os.path.isfile(filepath)


def directory_exists(dirpath: str) -> bool:
    """
    Check if directory exists.

    Args:
        dirpath: Path to directory

    Returns:
        True if directory exists, False otherwise
    """
    return os.path.isdir(dirpath)


def list_subdirectories(directory: str) -> list[str]:
    """
    List all subdirectories in a directory.

    Args:
        directory: Root directory

    Returns:
        List of subdirectory paths
    """
    return [
        os.path.join(directory, d)
        for d in os.listdir(directory)
        if os.path.isdir(os.path.join(directory, d))
    ]


def get_filename_without_extension(filepath: str) -> str:
    """
    Get filename without extension.

    Args:
        filepath: Path to file

    Returns:
        Filename without extension

    Example:
        >>> get_filename_without_extension('/path/to/file.json')
        'file'
    """
    return os.path.splitext(os.path.basename(filepath))[0]


def get_file_extension(filepath: str) -> str:
    """
    Get file extension.

    Args:
        filepath: Path to file

    Returns:
        File extension including the dot (e.g., '.json')

    Example:
        >>> get_file_extension('/path/to/file.json')
        '.json'
    """
    return os.path.splitext(filepath)[1]
