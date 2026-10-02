"""Logging utilities for consistent logging across the application."""

import logging
import sys
from pathlib import Path

from config.settings import get_settings


def setup_logging(
    name: str | None = None,
    level: str | None = None,
    log_file: str | None = None,
    console: bool = True,
) -> logging.Logger:
    """
    Set up logging with consistent formatting.

    Args:
        name: Logger name (default: root logger)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
               If None, uses setting from config
        log_file: Path to log file. If None, uses setting from config
        console: Whether to also log to console

    Returns:
        Configured logger instance

    Example:
        >>> logger = setup_logging(__name__)
        >>> logger.info("Application started")
    """
    # Get settings for defaults
    settings = get_settings()

    if level is None:
        level = settings.logging.level
    if log_file is None:
        log_file = settings.logging.file

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(settings.logging.format)

    # Add file handler if log_file specified
    if log_file:
        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Add console handler if requested
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level.upper()))
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the application's standard configuration.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.debug("Debug message")
    """
    return logging.getLogger(name)


class LoggerMixin:
    """
    Mixin class to add logging capabilities to any class.

    Example:
        >>> class MyClass(LoggerMixin):
        ...     def __init__(self):
        ...         self.logger.info("MyClass initialized")
    """

    @property
    def logger(self) -> logging.Logger:
        """Get logger for this class."""
        name = f"{self.__class__.__module__}.{self.__class__.__name__}"
        return get_logger(name)


def log_function_call(func):
    """
    Decorator to log function calls with arguments and return values.

    Args:
        func: Function to decorate

    Returns:
        Decorated function

    Example:
        >>> @log_function_call
        ... def my_function(x, y):
        ...     return x + y
    """
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)

        # Log function call
        args_str = ", ".join([repr(a) for a in args])
        kwargs_str = ", ".join([f"{k}={repr(v)}" for k, v in kwargs.items()])
        all_args = ", ".join(filter(None, [args_str, kwargs_str]))

        logger.debug(f"Calling {func.__name__}({all_args})")

        try:
            result = func(*args, **kwargs)
            logger.debug(f"{func.__name__} returned {repr(result)}")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} raised {type(e).__name__}: {e}")
            raise

    return wrapper


def log_execution_time(func):
    """
    Decorator to log function execution time.

    Args:
        func: Function to decorate

    Returns:
        Decorated function

    Example:
        >>> @log_execution_time
        ... def slow_function():
        ...     import time
        ...     time.sleep(1)
    """
    import functools
    import time

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)

        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()

        elapsed = end_time - start_time
        logger.info(f"{func.__name__} executed in {elapsed:.4f} seconds")

        return result

    return wrapper


class ProgressLogger:
    """
    Helper class for logging progress of long-running operations.

    Example:
        >>> progress = ProgressLogger("Processing queries", total=100)
        >>> for i in range(100):
        ...     # Do work
        ...     progress.update(i + 1)
        >>> progress.complete()
    """

    def __init__(self, description: str, total: int, logger: logging.Logger | None = None):
        """
        Initialize progress logger.

        Args:
            description: Description of the operation
            total: Total number of items to process
            logger: Optional logger instance (uses root logger if None)
        """
        self.description = description
        self.total = total
        self.logger = logger or get_logger(__name__)
        self.current = 0
        self.logger.info(f"{description}: Starting (0/{total})")

    def update(self, current: int, message: str | None = None) -> None:
        """
        Update progress.

        Args:
            current: Current progress count
            message: Optional additional message
        """
        self.current = current
        percentage = (current / self.total) * 100 if self.total > 0 else 0

        msg = f"{self.description}: {current}/{self.total} ({percentage:.1f}%)"
        if message:
            msg += f" - {message}"

        self.logger.info(msg)

    def complete(self, message: str | None = None) -> None:
        """
        Mark operation as complete.

        Args:
            message: Optional completion message
        """
        msg = f"{self.description}: Completed ({self.total}/{self.total})"
        if message:
            msg += f" - {message}"

        self.logger.info(msg)
