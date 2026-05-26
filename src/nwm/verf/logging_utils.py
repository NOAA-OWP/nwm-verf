"""Logging configuration."""

import logging
import sys
from pathlib import Path
from typing import Iterable, Optional, Union


class CustomLoggingFormatter(logging.Formatter):
    """Change ERROR→SEVERE and CRITICAL→FATAL to match ngen style."""

    def format(self, record):
        if record.levelno == logging.ERROR:
            record.levelname = "SEVERE"
        elif record.levelno == logging.CRITICAL:
            record.levelname = "FATAL"
        return super().format(record)


class NoisyDistributedFilter(logging.Filter):
    """Filter noisy Dask/Tornado connection + heartbeat errors."""

    IGNORED_KEYWORDS = (
        "Failed to communicate with scheduler during heartbeat",
        "CommClosedError",
        "StreamClosedError",
        "distributed.comm.core.CommClosedError",
        "tornado.iostream.StreamClosedError",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()

        if any(k in msg for k in self.IGNORED_KEYWORDS):
            return False

        if record.exc_info:
            exc_text = logging.Formatter().formatException(record.exc_info)
            if any(k in exc_text for k in self.IGNORED_KEYWORDS):
                return False

        return True


class StderrFilter:
    """Filter stderr tracebacks that bypass logging (SLURM/container cases)."""

    IGNORED_KEYWORDS = NoisyDistributedFilter.IGNORED_KEYWORDS

    def write(self, msg):
        if any(k in msg for k in self.IGNORED_KEYWORDS):
            return
        sys.__stderr__.write(msg)

    def flush(self):
        sys.__stderr__.flush()


def setup_logging(
    level: Union[int, str] = logging.INFO,
    target_packages: Iterable[str] = ("utils",),
    log_file: Optional[Union[str, Path]] = None,
    file_level: Optional[Union[int, str]] = None,
    filter_stderr: bool = True,  # ← enable stderr filtering
):
    """Configure logging with noise suppression for Dask/distributed."""
    user_log_levels = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "warn": logging.WARNING,
        "error": logging.ERROR,
        "severe": logging.ERROR,
        "fatal": logging.CRITICAL,
        "critical": logging.CRITICAL,
    }

    if isinstance(level, str):
        level = user_log_levels.get(level.lower(), logging.INFO)

    if isinstance(file_level, str):
        file_level = user_log_levels.get(file_level.lower(), level)

    file_level = file_level or level

    # Root logger baseline
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)

    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    formatter = CustomLoggingFormatter(
        "%(asctime)s - %(name)s - [%(levelname)s] - %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    file_handler = None
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, mode="w")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(file_level)

    # Install noise filter
    noise_filter = NoisyDistributedFilter()
    console_handler.addFilter(noise_filter)
    if file_handler:
        file_handler.addFilter(noise_filter)

    # Target package loggers
    for pkg in target_packages:
        logger = logging.getLogger(pkg)
        logger.setLevel(min(level, file_level))

        for h in logger.handlers[:]:
            logger.removeHandler(h)

        logger.addHandler(console_handler)
        if file_handler:
            logger.addHandler(file_handler)

        logger.propagate = False

    # Suppress overly verbose loggers
    logging.getLogger("google.auth.compute_engine._metadata").setLevel(logging.ERROR)
    logging.getLogger("fsspec.reference").setLevel(logging.WARNING)
    logging.getLogger("distributed").setLevel(logging.WARNING)
    logging.getLogger("distributed.worker").setLevel(logging.WARNING)
    logging.getLogger("distributed.comm").setLevel(logging.ERROR)
    logging.getLogger("dask").setLevel(logging.WARNING)
    logging.getLogger("tornado").setLevel(logging.ERROR)

    # Also attach filter directly to distributed loggers
    logging.getLogger("distributed").addFilter(noise_filter)
    logging.getLogger("distributed.worker").addFilter(noise_filter)

    # Optional stderr filtering for cases where logging may be bypassed (e.g., SLURM/container environments)
    if filter_stderr:
        sys.stderr = StderrFilter()
