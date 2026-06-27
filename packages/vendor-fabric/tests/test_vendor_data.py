"""Tests for the VendorData facade."""

from __future__ import annotations

from typing import Any

import pytest

from extended_data.containers import ExtendedData, ExtendedDict, ExtendedList, ExtendedString

from vendor_fabric.base import ConnectorBase
from vendor_fabric.capabilities import capability
from vendor_fabric.vendor_data import VendorCapability, VendorData


class DemoConnector(ConnectorBase):
    """Connector exposing public, declared, and decorated operations."""

    __supports__ = {
        "put_file": {
            "method": "save_file",
            "capability": "files",
            "description": "Save a file.",
        },
        "legacy_read": "fetch",
    }

    @capability(
        "fetch_file",
        kind="files",
        aliases=("get_file", "read_file"),
        description="Fetch a file.",
    )
    def fetch(self, path: str) -> dict[str, str]:
        """Return fake file metadata."""
        return {"path": path, "provider": "demo"}

    def save_file(self, path: str, content: str) -> dict[str, str]:
        """Return fake write metadata."""
        return {"path": path, "content": content}

    def list_widgets(self) -> list[str]:
        """Return public method support inferred by naming convention."""
        return ["alpha", "beta"]

    def helper(self) -> str:
        """Return a helper that should not be exposed as a capability."""
        return "private"


class OtherConnector(ConnectorBase):
    """Second connector used to exercise multi-provider routing."""

    @capability("fetch_file", kind="files", aliases=("get_file",), description="Fetch a file from another provider.")
    def fetch_other(self, path: str) -> dict[str, str]:
        """Return fake file metadata."""
        return {"path": path, "provider": "other"}


class FakeAdapter:
    """Minimal connector adapter used by VendorData tests."""

    def __init__(self, connector_cls: type[ConnectorBase]) -> None:
        self.connector_cls = connector_cls

    def load_class(self) -> type[ConnectorBase]:
        """Return the configured connector class."""
        return self.connector_cls


class FakeFabric:
    """Small in-memory provider fabric for VendorData tests."""

    def __init__(
        self,
        *,
        available: tuple[str, ...] = ("demo",),
        connectors: dict[str, type[ConnectorBase]] | None = None,
    ) -> None:
        self.available = set(available)
        self.connectors = connectors or {"demo": DemoConnector, "other": OtherConnector}
        self.instances: dict[str, ConnectorBase] = {}
        self.logging = None

    def list_connectors(self) -> list[str]:
        """Return known connector ids."""
        return list(self.connectors)

    def get_connector_info(self, name: str, *, include_unavailable: bool = True) -> dict[str, Any]:
        """Return registry-like provider metadata."""
        available = name in self.available and name in self.connectors
        if not include_unavailable and not available:
            return {}
        return {
            "name": name,
            "available": available,
            "install": f"pip install vendor-fabric[{name}]",
        }

    def get_connector_adapter(self, name: str, *, include_unavailable: bool = True) -> FakeAdapter:
        """Return a fake adapter for a known connector."""
        if not include_unavailable and name not in self.available:
            raise KeyError(name)
        return FakeAdapter(self.connectors[name])

    def get_connector(self, name: str, **kwargs: Any) -> ConnectorBase:
        """Return a cached fake connector instance."""
        if name not in self.instances:
            self.instances[name] = self.connectors[name](from_environment=False, **kwargs)
        return self.instances[name]


def test_vendor_data_preserves_wrapped_extended_data_behavior() -> None:
    """VendorData should keep Extended Data container behavior for its wrapped value."""
    data = VendorData({"service": {"name": "api"}}, fabric=FakeFabric())

    assert data.as_builtin() == {"service": {"name": "api"}}
    assert isinstance(data.value, ExtendedDict)
    assert data["service"]["name"].upper_first() == "Api"

    data["count"] = 1

    assert len(data) == 2
    assert "service" in data
    assert set(data) == {"service", "count"}
    assert data.as_builtin()["count"] == 1
    assert data.cast(["alpha"]).as_builtin() == ["alpha"]


def test_vendor_data_bypasses_extended_data_factory_and_stores_internal_value() -> None:
    """VendorData must remain a facade around an internal ExtendedData value."""
    data = VendorData({"service": "api"}, fabric=FakeFabric())

    assert type(data) is VendorData
    assert isinstance(data, ExtendedData)
    assert isinstance(data.value, ExtendedDict)
    assert data.as_builtin() == {"service": "api"}

    data.cast(["agent-runtime-behavior-belongs-downstream"])

    assert type(data) is VendorData
    assert isinstance(data.value, ExtendedList)
    assert data.as_builtin() == ["agent-runtime-behavior-belongs-downstream"]


def test_vendor_data_open_tracks_active_provider_and_reuses_connector() -> None:
    """Opening a provider should activate it and cache its connector."""
    fabric = FakeFabric()
    data = VendorData(fabric=fabric)

    connector = data.open_provider("demo")

    assert isinstance(connector, DemoConnector)
    assert isinstance(data.active_provider, ExtendedString)
    assert data.active_provider == "demo"
    assert data.provider("demo") is connector
    assert data.open_demo().active_provider == "demo"


def test_vendor_data_reports_unavailable_provider_install_guidance() -> None:
    """Unavailable providers should expose install guidance and support non-strict activation."""
    data = VendorData(fabric=FakeFabric(available=()))

    with pytest.raises(ImportError, match=r"pip install vendor-fabric\[demo\]"):
        data.open("demo")

    data.open("demo", strict=False)

    assert data.active_provider == "demo"
    assert data.is_provider_available("demo") is False


def test_vendor_data_capability_matrix_uses_decorators_aliases_and_declared_supports() -> None:
    """Capability metadata should include decorator aliases, declared supports, and public methods."""
    data = VendorData(fabric=FakeFabric())

    matrix = data.capability_matrix()

    assert matrix["fetch_file"]["demo"]["method"] == "fetch"
    assert matrix["fetch_file"]["demo"]["capability"] == "files"
    assert matrix["fetch_file"]["demo"]["description"] == "Fetch a file."
    assert matrix["fetch_file"]["demo"]["source"] == "decorator"
    assert matrix["get_file"]["demo"]["method"] == "fetch"
    assert matrix["read_file"]["demo"]["method"] == "fetch"
    assert matrix["put_file"]["demo"]["method"] == "save_file"
    assert matrix["put_file"]["demo"]["source"] == "alias"
    assert matrix["legacy_read"]["demo"]["method"] == "fetch"
    assert matrix["list_widgets"]["demo"]["source"] == "method"
    assert "helper" not in matrix
    assert data.supports("demo", "read_file") is True
    assert data.supports("demo", "helper") is False
    assert data.supports("other", "get_file", require_available=True) is False


def test_vendor_data_call_routes_by_explicit_and_active_provider() -> None:
    """Calls should route through provider arguments, explicit calls, and active provider state."""
    data = VendorData(fabric=FakeFabric())

    explicit = data.get_file("demo", "README.md")

    assert isinstance(explicit, ExtendedDict)
    assert explicit == {"path": "README.md", "provider": "demo"}
    assert data.call("put_file", "demo", "README.md", "body") == {"path": "README.md", "content": "body"}

    data.open("demo")
    active = data.read_file("CHANGELOG.md")

    assert active == {"path": "CHANGELOG.md", "provider": "demo"}
    assert data.fetch_file("pyproject.toml") == {"path": "pyproject.toml", "provider": "demo"}
    assert data.list_widgets() == ["alpha", "beta"]


def test_vendor_data_call_rejects_ambiguous_or_unsupported_routes() -> None:
    """Ambiguous and unsupported operations should fail before connector methods run."""
    data = VendorData(fabric=FakeFabric(available=("demo", "other")))

    with pytest.raises(ValueError, match="multiple providers"):
        data.get_file("README.md")

    with pytest.raises(ValueError, match="does not support operation"):
        data.call("put_file", "other", "README.md", "body")

    with pytest.raises(AttributeError, match="Unknown VendorData operation"):
        data.unknown_operation()


def test_vendor_data_constructor_declared_capabilities_remain_supported() -> None:
    """Constructor-provided routes should still dispatch without provider discovery metadata."""

    class DeclaredConnector(ConnectorBase):
        """Connector for constructor-declared routes."""

        def sync(self, value: str) -> dict[str, str]:
            """Return fake sync metadata."""
            return {"synced": value}

    fabric = FakeFabric(available=("declared",), connectors={"declared": DeclaredConnector})
    data = VendorData(
        fabric=fabric,
        capabilities=(VendorCapability(provider="declared", operation="sync", method="sync", capability="sync"),),
    )

    assert data.sync("payload") == {"synced": "payload"}
