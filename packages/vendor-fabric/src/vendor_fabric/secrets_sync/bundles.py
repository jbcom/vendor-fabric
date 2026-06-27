"""Deterministic merge bundle identifiers."""

from __future__ import annotations

import hashlib


def bundle_id(sources: list[str]) -> str:
    """Return the deterministic bundle id for an ordered source sequence."""
    digest = hashlib.sha256("\0".join(sources).encode("utf-8")).digest()
    return digest[:16].hex()


def bundle_path(mount: str, sources: list[str]) -> str:
    """Return a generic merge bundle path."""
    return f"{mount.rstrip('/')}/bundles/{bundle_id(sources)}"


def target_bundle_path(mount: str, target_name: str, sources: list[str]) -> str:
    """Return a target-scoped merge bundle path."""
    return f"{mount.rstrip('/')}/targets/{target_name}/{bundle_id(sources)}"
