"""Tests for connector optional dependency helpers."""

from __future__ import annotations

from importlib import util
from pathlib import Path

import pytest
import tomlkit

from extended_data.containers import ExtendedList, ExtendedString

from vendor_fabric import _optional, registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]


def _pyproject() -> tomlkit.TOMLDocument:
    return tomlkit.parse((PACKAGE_ROOT / "pyproject.toml").read_text())


def test_builtin_connector_metadata_maps_stay_aligned() -> None:
    """Built-in connector registries should fail fast when metadata drifts."""
    names = set(registry.BUILTIN_CONNECTORS)

    assert names == set(_optional.CONNECTOR_REQUIREMENTS)
    assert names == set(_optional.CONNECTOR_EXTRAS)
    assert names == set(registry.BUILTIN_CONNECTOR_ADAPTERS)

    for name, spec in registry.BUILTIN_CONNECTORS.items():
        adapter = registry.BUILTIN_CONNECTOR_ADAPTERS[name]
        extra = _optional.get_extra_for_connector(name)
        assert isinstance(adapter, registry.ConnectorAdapter)
        assert adapter.name == name
        assert adapter.spec == spec
        assert isinstance(extra, ExtendedString)
        assert extra == spec.extra


def test_builtin_adapter_reports_unavailable_metadata_without_raising(monkeypatch) -> None:
    """Missing optional packages should be discoverable as metadata."""
    monkeypatch.setattr(
        registry,
        "get_missing_connector_requirements",
        lambda name: ExtendedList(["boto3"]) if name == "aws" else ExtendedList(),
    )

    adapter = registry.get_connector_adapter(" aws ")
    info = adapter.as_dict()

    assert isinstance(adapter, registry.ConnectorAdapter)
    assert info["name"] == "aws"
    assert info["available"] is False
    assert info["extra"] == "aws"
    assert info["install"] == "pip install vendor-fabric[aws]"
    assert info["missing"] == ["boto3"]


def test_unavailable_adapter_raises_central_install_error_when_constructed(monkeypatch) -> None:
    """Construction failures should come from the adapter registry."""
    monkeypatch.setattr(
        registry,
        "get_missing_connector_requirements",
        lambda name: ExtendedList(["boto3"]) if name == "aws" else ExtendedList(),
    )

    with pytest.raises(ImportError, match=r"vendor-fabric\[aws\]") as exc_info:
        registry.get_connector_adapter("aws", include_unavailable=False)

    assert "Missing packages: boto3" in str(exc_info.value)


def test_connector_optional_metadata_returns_extended_values(monkeypatch) -> None:
    """Connector optional dependency metadata helpers return extended values."""
    monkeypatch.setattr(_optional, "is_available", lambda package: package == "present")
    monkeypatch.setitem(_optional.CONNECTOR_REQUIREMENTS, "custom", ["present", "missing"])
    monkeypatch.setitem(_optional.CONNECTOR_EXTRAS, "custom", "custom-extra")

    package_extra = _optional.get_extra_for_package("boto3")
    connector_extra = _optional.get_extra_for_connector("custom")
    requirements = _optional.get_connector_requirements("custom")
    missing = _optional.get_missing_connector_requirements("custom")
    install = _optional.get_connector_install_command("custom")

    assert isinstance(package_extra, ExtendedString)
    assert package_extra == "aws"
    assert isinstance(connector_extra, ExtendedString)
    assert connector_extra == "custom-extra"
    assert isinstance(requirements, ExtendedList)
    assert requirements == ["present", "missing"]
    assert isinstance(requirements[0], ExtendedString)
    assert isinstance(missing, ExtendedList)
    assert missing == ["missing"]
    assert isinstance(missing[0], ExtendedString)
    assert isinstance(install, ExtendedString)
    assert install == "pip install vendor-fabric[custom-extra]"


def test_builtin_connectors_are_registered_as_entry_points() -> None:
    """Every built-in connector should be published through the connector entry point group."""
    entry_points = _pyproject()["project"]["entry-points"]["vendor_fabric.connectors"]

    assert set(entry_points) == set(registry.BUILTIN_CONNECTORS)

    for name, spec in registry.BUILTIN_CONNECTORS.items():
        assert entry_points[name] == f"{spec.module_path}:{spec.class_name}"


def test_connector_extras_exist_in_pyproject() -> None:
    """Connector extras referenced by registry metadata should exist in pyproject."""
    extras = _pyproject()["project"]["optional-dependencies"]

    for name, extra in _optional.CONNECTOR_EXTRAS.items():
        assert extra in extras, f"{name} uses missing extra {extra}"


def test_secretsync_surface_is_first_class_but_not_a_connector() -> None:
    """SecretSync is a vendor-fabric capability, not a connector entry point."""
    pyproject = _pyproject()
    extras = pyproject["project"]["optional-dependencies"]
    entry_points = pyproject["project"]["entry-points"]["vendor_fabric.connectors"]

    assert "secrets" not in registry.BUILTIN_CONNECTORS
    assert "secrets" not in _optional.CONNECTOR_EXTRAS
    assert "secrets" not in _optional.CONNECTOR_REQUIREMENTS
    assert "secrets" not in extras
    assert "secrets-sync" in extras
    assert "secrets" not in entry_points
    assert util.find_spec("vendor_fabric.secrets") is None
    assert util.find_spec("vendor_fabric.secrets_sync") is not None


def test_ownership_map_documents_current_package_boundaries() -> None:
    """Moved surfaces should have explicit destination ownership in public docs."""
    ownership_map = (REPO_ROOT / "docs" / "ownership-map.rst").read_text(encoding="utf-8")

    for expected_text in (
        "jbcom/extended-data",
        "extended-data",
        "jbcom/secrets-sync",
        "vendor_fabric.secrets_sync",
        "agentic-fabric",
    ):
        assert expected_text in ownership_map


def test_connector_requirement_packages_map_to_connector_extras() -> None:
    """Connector import checks should point users to the same extra as the connector itself."""
    for name, requirements in _optional.CONNECTOR_REQUIREMENTS.items():
        extra = _optional.CONNECTOR_EXTRAS[name]

        for requirement in requirements:
            assert _optional.PACKAGE_TO_EXTRA[requirement] == extra


def test_sentence_transformers_explains_user_managed_install(monkeypatch) -> None:
    """Missing sentence-transformers reports the deliberate no-extra install policy."""

    def fake_import_module(name: str) -> object:
        if name == "sentence_transformers":
            raise ImportError("No module named 'sentence_transformers'")
        pytest.fail(f"unexpected import: {name}")

    monkeypatch.setattr(_optional.importlib, "import_module", fake_import_module)

    with pytest.raises(ImportError) as exc_info:
        _optional.require_extra("sentence_transformers")

    message = str(exc_info.value)
    assert "sentence-transformers separately" in message
    assert "torch" in message
    assert "vendor-fabric[vector]" not in message
    assert _optional.get_extra_for_package("sentence_transformers") is None


def test_secrets_sync_binding_reports_contract_install_guidance(monkeypatch) -> None:
    """Missing SecretSync bindings point to the canonical binding package and import."""

    def fake_import_module(name: str) -> object:
        if name == "secrets_sync":
            raise ImportError("No module named 'secrets_sync'")
        pytest.fail(f"unexpected import: {name}")

    monkeypatch.setattr(_optional.importlib, "import_module", fake_import_module)

    with pytest.raises(ImportError) as exc_info:
        _optional.require_extra("secrets_sync")

    message = str(exc_info.value)
    assert "secrets-sync-python-binding" in message
    assert "secrets_sync import" in message
    assert _optional.get_extra_for_package("secrets_sync") == "secrets-sync"


def test_missing_unmapped_dependency_reports_package_named_extra(monkeypatch) -> None:
    """Unmapped optional imports should still give a usable package-specific install command."""

    def fake_import_module(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(_optional.importlib, "import_module", fake_import_module)

    with pytest.raises(ImportError) as exc_info:
        _optional.require_extra("unmapped_package")

    message = str(exc_info.value)
    assert "unmapped_package" in message
    assert "vendor-fabric[unmapped_package]" in message


def test_require_any_returns_first_available_package(monkeypatch) -> None:
    """Fallback imports should return the first import that succeeds."""
    module = object()

    def fake_import_module(name: str) -> object:
        if name == "missing":
            raise ImportError("missing")
        if name == "present":
            return module
        pytest.fail(f"unexpected import: {name}")

    monkeypatch.setattr(_optional.importlib, "import_module", fake_import_module)

    assert _optional.require_any("missing", "present", extra="custom") is module


def test_require_any_reports_all_missing_packages(monkeypatch) -> None:
    """Fallback import failures should name every accepted package."""

    def fake_import_module(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(_optional.importlib, "import_module", fake_import_module)

    with pytest.raises(ImportError) as exc_info:
        _optional.require_any("first", "second", extra="custom")

    message = str(exc_info.value)
    assert "first, second" in message
    assert "vendor-fabric[custom]" in message


def test_unknown_connector_optional_helpers_return_empty_values() -> None:
    """Unknown connector names should not manufacture install metadata."""
    assert _optional.get_extra_for_connector(" unknown ") is None
    assert _optional.get_connector_requirements("unknown") == []
    assert _optional.get_connector_install_command("unknown") is None
    assert _optional.is_connector_available("unknown") is True


def test_require_connector_raises_with_missing_dependency(monkeypatch) -> None:
    """Connector requirement failures should include the missing packages and extra."""
    monkeypatch.setattr(_optional, "get_missing_connector_requirements", lambda name: ExtendedList(["boto3"]))

    with pytest.raises(ImportError) as exc_info:
        _optional.require_connector("aws")

    message = str(exc_info.value)
    assert "Missing packages: boto3" in message
    assert "vendor-fabric[aws]" in message


def test_require_connector_returns_none_when_available(monkeypatch) -> None:
    """Available connector requirements should not raise."""
    monkeypatch.setattr(_optional, "get_missing_connector_requirements", lambda name: ExtendedList())

    assert _optional.require_connector("aws") is None


def test_available_connectors_returns_extended_names(monkeypatch) -> None:
    """Connector availability helper returns first-class extended names."""
    monkeypatch.setattr(_optional, "is_connector_available", lambda connector: connector in {"cursor", "meshy"})

    connectors = _optional.get_available_connectors()

    assert isinstance(connectors, ExtendedList)
    assert "cursor" in connectors
    assert "meshy" in connectors
    assert isinstance(connectors[0], ExtendedString)
