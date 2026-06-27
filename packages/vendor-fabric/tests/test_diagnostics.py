"""Tests for provider diagnostic redaction helpers."""

from __future__ import annotations

from vendor_fabric.aws import _diagnostics as aws_diagnostics
from vendor_fabric.github import _diagnostics as github_diagnostics
from vendor_fabric.google import _diagnostics as google_diagnostics


def test_github_diagnostic_values_flatten_nested_context() -> None:
    """GitHub diagnostics should collect scalar values from nested context."""
    values = list(
        github_diagnostics._iter_diagnostic_values(
            [
                None,
                {"owner": "private-org", "repo": ["private-repo", b"raw-bytes"]},
                42,
            ]
        )
    )

    assert values == ["private-org", "private-repo", b"raw-bytes", 42]


def test_github_diagnostics_redact_nested_context_values() -> None:
    """GitHub diagnostic text should redact caller-provided resource names."""
    text = github_diagnostics.safe_github_text(
        "failed private-org/private-repo with token=raw-token",
        {"owner": "private-org", "repo": "private-repo"},
    )

    assert "private-org" not in text
    assert "private-repo" not in text
    assert "raw-token" not in text
    assert "[REDACTED]" in text


def test_google_diagnostic_values_flatten_nested_context() -> None:
    """Google diagnostics should collect scalar values from nested context."""
    values = list(
        google_diagnostics._iter_diagnostic_values(
            [
                None,
                {"project": "private-project", "location": ["us-central1", b"raw-bytes"]},
                7,
            ]
        )
    )

    assert values == ["private-project", "us-central1", b"raw-bytes", 7]


def test_google_diagnostics_redact_single_refs() -> None:
    """Google diagnostic references should redact the whole supplied value."""
    text = google_diagnostics.safe_google_ref("projects/private-project/locations/us-central1")

    assert "private-project" not in text
    assert "us-central1" not in text
    assert "[REDACTED]" in text


def test_aws_diagnostic_values_flatten_nested_context() -> None:
    """AWS diagnostics should collect scalar values from nested context."""
    values = list(
        aws_diagnostics._iter_diagnostic_values(
            [
                None,
                {"account": "123456789012", "role": ["AdminRole", b"raw-bytes"]},
                9,
            ]
        )
    )

    assert values == ["123456789012", "AdminRole", b"raw-bytes", 9]


def test_aws_diagnostics_redact_account_ids_and_operation_context() -> None:
    """AWS diagnostic text should redact account IDs and supplied context."""
    text = aws_diagnostics.aws_operation_error(
        "CreateRole",
        RuntimeError("failed account 123456789012 role AdminRole token=raw-token"),
        {"account": "123456789012", "role": "AdminRole"},
    )

    assert "123456789012" not in text
    assert "AdminRole" not in text
    assert "raw-token" not in text
    assert text.startswith("CreateRole: ")
    assert "[REDACTED]" in text
