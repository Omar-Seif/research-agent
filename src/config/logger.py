import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
from src.config.settings import settings


def setup_logging() -> None:
    """
    Configure the root logger with console and file handlers.

    Console handler: Writes to stdout.
    File handler: Writes to the configured path with rotation at 10MB and 5 backups.

    If the file handler cannot be created, the app degrades gracefully to console-only logging with a warning.

    Usage:
        from src.config.logger import setup_logging
        setup_logging()
    """
    # Get the root logger (no arguments = root logger)
    root_logger = logging.getLogger()

    # Idempotency guard: skip if already configured
    if root_logger.handlers:
        return

    # Convert level string to logging integer constant
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.DEBUG)
    root_logger.setLevel(log_level)

    # Formatter with timestamp, level, logger name, and message
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    try:
        log_path = Path(settings.LOG_FILE_PATH)

        # Create directory if it doesn't exist (including nested directories)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Set up rotating file handler
        file_handler = RotatingFileHandler(
            filename=str(log_path), maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    except OSError as e:
        root_logger.warning(f"Failed to set up file logging: {e}")

    NOISY_LOGGERS = [
        "httpx",
        "httpcore",
        "openai",
        "trafilatura",
        "readability-lxml",
    ]

    for logger_name in NOISY_LOGGERS:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger instance.

    This wrapper exists to give a consistent import pattern and a future
    place to inject custom behavior (e.g., adding a request_id filter).

    Args:
        name: Usually __name__ from the calling module.

    Returns:
        logging.Logger: A configured logger instance.
    """
    return logging.getLogger(name)
