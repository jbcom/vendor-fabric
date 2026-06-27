"""Tests for provider capability declarations."""

from __future__ import annotations

from extended_data.containers import ExtendedDict

from vendor_fabric.capabilities import CapabilityRoute


def test_capability_route_serializes_to_extended_data() -> None:
    """Route metadata should cross package boundaries as Extended Data."""
    route = CapabilityRoute(
        provider="github",
        operation="get_file",
        method="get_file",
        kind="files",
        description="Read a file.",
        source="test",
    )

    payload = route.as_dict()

    assert isinstance(payload, ExtendedDict)
    assert payload["provider"] == "github"
    assert payload["operation"] == "get_file"
    assert payload["source"] == "test"
