"""Google connector diagnostic redaction helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from extended_data.primitives.redaction import redact_sensitive_text


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


def safe_google_text(value: Any, *sensitive_values: Any) -> str:
    """Redact secrets and caller-provided resource identifiers from diagnostics."""
    return redact_sensitive_text(value, values=_iter_diagnostic_values(sensitive_values))


def safe_google_ref(value: Any) -> str:
    """Redact a single Google resource reference for diagnostic logs."""
    return safe_google_text(value, value)
