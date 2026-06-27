"""AWS diagnostic redaction helpers."""

from __future__ import annotations

import re

from collections.abc import Iterable, Mapping
from typing import Any

from extended_data.primitives.redaction import redact_sensitive_text


AWS_ACCOUNT_ID_RE = re.compile(r"\b\d{12}\b")


def _iter_diagnostic_values(values: Iterable[Any]) -> Iterable[Any]:
    """Yield scalar values from nested diagnostic context."""
    for value in values:
        if value is None:
            continue
        if isinstance(value, Mapping):
            yield from _iter_diagnostic_values(value.values())
        elif isinstance(value, (str, bytes)):
            yield value
        elif isinstance(value, Iterable):
            yield from _iter_diagnostic_values(value)
        else:
            yield value


def safe_aws_text(value: Any, *sensitive_values: Any) -> str:
    """Redact secrets and caller-provided resource identifiers from AWS diagnostics."""
    redacted = redact_sensitive_text(value, values=_iter_diagnostic_values(sensitive_values))
    return AWS_ACCOUNT_ID_RE.sub("[REDACTED]", redacted)


def safe_aws_ref(value: Any) -> str:
    """Redact a single AWS resource reference for diagnostic logs."""
    return safe_aws_text(value, value)


def aws_operation_error(action: str, exc: BaseException, *sensitive_values: Any) -> str:
    """Build a redacted AWS operation error message."""
    return f"{action}: {safe_aws_text(exc, *sensitive_values)}"
