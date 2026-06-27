"""Tests for deterministic SecretSync bundle paths."""

from __future__ import annotations

from vendor_fabric.secrets_sync.bundles import bundle_id, bundle_path, target_bundle_path


def test_bundle_paths_trim_mount_slashes_and_reuse_stable_ids() -> None:
    """Bundle paths should be deterministic for the same ordered sources."""
    sources = ["base", "env"]
    identifier = bundle_id(sources)

    assert len(identifier) == 32
    assert bundle_path("secret/", sources) == f"secret/bundles/{identifier}"
    assert target_bundle_path("secret/", "prod", sources) == f"secret/targets/prod/{identifier}"
    assert bundle_id(["env", "base"]) != identifier
