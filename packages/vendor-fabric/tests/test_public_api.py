"""Tests for package-level public API exports."""

from __future__ import annotations

import pytest

import vendor_fabric


def test_lazy_meshy_module_export(monkeypatch: pytest.MonkeyPatch) -> None:
    """The top-level package should lazily expose the Meshy module."""
    monkeypatch.delitem(vendor_fabric.__dict__, "meshy", raising=False)

    module = vendor_fabric.meshy

    assert module.__name__ == "vendor_fabric.meshy"
    assert vendor_fabric.__dict__["meshy"] is module


def test_unknown_top_level_export_raises_attribute_error() -> None:
    """Unknown package attributes should fail as normal Python attributes."""
    with pytest.raises(AttributeError, match="missing_export"):
        vendor_fabric.__getattr__("missing_export")
