"""Meshy logging helpers backed by Extended Data lifecycle logging."""

from __future__ import annotations

from collections.abc import Sequence

from extended_data.logging import Logging
from extended_data.logging.const import VERBOSITY
from extended_data.logging.utils import get_log_level


MESHY_LOGGER_NAME = "vendor_fabric.meshy"
MESHY_STORAGE_MARKER = "meshy"


def create_meshy_logger(
    *,
    level: int | str = "INFO",
    logger_name: str = MESHY_LOGGER_NAME,
    enable_console: bool = False,
    enable_file: bool = False,
    log_file_name: str | None = None,
    default_storage_marker: str | None = MESHY_STORAGE_MARKER,
    allowed_levels: Sequence[str] | None = None,
    denied_levels: Sequence[str] | None = None,
    enable_verbose_output: bool = False,
    verbosity_threshold: int = VERBOSITY,
) -> Logging:
    """Create an Extended Data logger configured for Meshy workflows.

    The helper intentionally avoids import-time side effects and global
    ``logging.basicConfig`` changes. Callers opt into console or file output
    the same way they do with the package-level ``Logging`` surface.
    """
    logger = Logging(
        enable_console=enable_console,
        enable_file=enable_file,
        logger_name=logger_name,
        log_file_name=log_file_name,
        default_storage_marker=default_storage_marker,
        allowed_levels=allowed_levels,
        denied_levels=denied_levels,
        enable_verbose_output=enable_verbose_output,
        verbosity_threshold=verbosity_threshold,
    )
    logger.logger.setLevel(get_log_level(level))
    return logger
