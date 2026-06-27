"""Tests for Meshy logging helpers."""

from __future__ import annotations

import logging

from extended_data.logging import Logging

from cloud_connectors.meshy import MESHY_LOGGER_NAME, MESHY_STORAGE_MARKER, create_meshy_logger


def test_create_meshy_logger_returns_extended_data_logger() -> None:
    """Meshy logging should use the package lifecycle logging surface."""
    logger = create_meshy_logger(level="WARNING")

    assert isinstance(logger, Logging)
    assert logger.logger.name == MESHY_LOGGER_NAME
    assert logger.logger.level == logging.WARNING
    assert logger.enable_console is False
    assert logger.enable_file is False
    assert logger.default_storage_marker == MESHY_STORAGE_MARKER


def test_create_meshy_logger_uses_tier2_storage_and_redaction() -> None:
    """Meshy logging should keep stored connector messages promoted and redacted."""
    logger = create_meshy_logger(
        level="INFO",
        default_storage_marker="asset-generation",
        allowed_levels=["info"],
    )

    result = logger.logged_statement(
        "Meshy request failed with Authorization: Bearer raw_token",
        json_data={"api_key": "key_123", "task_id": "task_456"},
        log_level="info",
    )

    assert result is not None
    assert "raw_token" not in result
    assert "key_123" not in result
    stored = logger.get_stored_messages("asset-generation")
    assert len(stored) == 1
    stored_message = next(iter(stored))
    assert "raw_token" not in stored_message
    assert "key_123" not in stored_message
    assert "task_456" in stored_message
