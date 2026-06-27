"""Secret payload merge helpers backed by Extended Data primitives."""

from __future__ import annotations

import json

from collections.abc import Mapping
from typing import Any

from extended_data.containers import to_builtin
from extended_data.primitives.mappings import deep_merge as extended_deep_merge


def deep_merge(dst: Mapping[str, Any] | None, src: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge ``src`` into ``dst`` using the shared Extended Data semantics."""
    return extended_deep_merge(to_builtin(dst or {}), to_builtin(src or {}))


def normalize_for_compare(value: Any) -> Any:
    """Normalize JSON-compatible values before equality checks."""
    if isinstance(value, Mapping):
        return {str(key): normalize_for_compare(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_for_compare(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_for_compare(item) for item in value]
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return value


def deep_equal(left: Any, right: Any) -> bool:
    """Return whether two secret payloads are equal after JSON normalization."""
    return normalize_for_compare(left) == normalize_for_compare(right)


def compare_secret_json(existing: str | bytes, new: str | bytes) -> bool:
    """Compare two secret strings as JSON when possible, else as raw strings."""
    existing_text = existing.decode("utf-8") if isinstance(existing, bytes) else existing
    new_text = new.decode("utf-8") if isinstance(new, bytes) else new

    try:
        existing_value = json.loads(existing_text)
        new_value = json.loads(new_text)
    except json.JSONDecodeError:
        return existing_text == new_text
    return deep_equal(existing_value, new_value)
