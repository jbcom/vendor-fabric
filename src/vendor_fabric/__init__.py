"""Vendor Fabric.

This package provides optional vendor API integrations backed by an adapter
registry. The package root is intentionally lazy so ``import vendor_fabric``
works with only the base dependencies installed.
"""

from __future__ import annotations

import importlib

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any


try:
    __version__ = version("vendor-fabric")
except PackageNotFoundError:  # pragma: no cover - local editable fallback before install
    __version__ = "0.0.0"


if TYPE_CHECKING:
    from vendor_fabric.anthropic import AnthropicConnector
    from vendor_fabric.aws import AWSConnector, AWSOrganizationsMixin, AWSS3Mixin, AWSSSOmixin
    from vendor_fabric.base import ConnectorBase
    from vendor_fabric.connectors import ConnectorFabric
    from vendor_fabric.cursor import CursorConnector
    from vendor_fabric.github import GitHubConnector
    from vendor_fabric.google import (
        GoogleBillingMixin,
        GoogleCloudMixin,
        GoogleConnector,
        GoogleServicesMixin,
        GoogleWorkspaceMixin,
        JulesConnector,
    )
    from vendor_fabric.meshy import MeshyConnector
    from vendor_fabric.registry import (
        BuiltinConnectorAdapter,
        ConnectorAdapter,
        ConnectorInfo,
        get_connector,
        get_connector_adapter,
        get_connector_class,
        get_connector_info,
        list_available_connectors,
        list_connector_capabilities,
        list_connector_categories,
        list_connector_info,
        list_connectors,
        list_connectors_by_capability,
        list_connectors_by_category,
    )
    from vendor_fabric.slack import SlackConnector
    from vendor_fabric.vault import VaultConnector
    from vendor_fabric.zoom import ZoomConnector


_LAZY_EXPORTS = {
    "AWSConnector": ("vendor_fabric.aws", "AWSConnector"),
    "AWSOrganizationsMixin": ("vendor_fabric.aws", "AWSOrganizationsMixin"),
    "AWSS3Mixin": ("vendor_fabric.aws", "AWSS3Mixin"),
    "AWSSSOmixin": ("vendor_fabric.aws", "AWSSSOmixin"),
    "AnthropicConnector": ("vendor_fabric.anthropic", "AnthropicConnector"),
    "BuiltinConnectorAdapter": ("vendor_fabric.registry", "BuiltinConnectorAdapter"),
    "ConnectorAdapter": ("vendor_fabric.registry", "ConnectorAdapter"),
    "ConnectorBase": ("vendor_fabric.base", "ConnectorBase"),
    "ConnectorFabric": ("vendor_fabric.connectors", "ConnectorFabric"),
    "ConnectorInfo": ("vendor_fabric.registry", "ConnectorInfo"),
    "CursorConnector": ("vendor_fabric.cursor", "CursorConnector"),
    "GitHubConnector": ("vendor_fabric.github", "GitHubConnector"),
    "GoogleBillingMixin": ("vendor_fabric.google", "GoogleBillingMixin"),
    "GoogleCloudMixin": ("vendor_fabric.google", "GoogleCloudMixin"),
    "GoogleConnector": ("vendor_fabric.google", "GoogleConnector"),
    "GoogleServicesMixin": ("vendor_fabric.google", "GoogleServicesMixin"),
    "GoogleWorkspaceMixin": ("vendor_fabric.google", "GoogleWorkspaceMixin"),
    "JulesConnector": ("vendor_fabric.google", "JulesConnector"),
    "MeshyConnector": ("vendor_fabric.meshy", "MeshyConnector"),
    "SlackConnector": ("vendor_fabric.slack", "SlackConnector"),
    "VaultConnector": ("vendor_fabric.vault", "VaultConnector"),
    "ZoomConnector": ("vendor_fabric.zoom", "ZoomConnector"),
    "get_connector": ("vendor_fabric.registry", "get_connector"),
    "get_connector_adapter": ("vendor_fabric.registry", "get_connector_adapter"),
    "get_connector_class": ("vendor_fabric.registry", "get_connector_class"),
    "get_connector_info": ("vendor_fabric.registry", "get_connector_info"),
    "list_available_connectors": ("vendor_fabric.registry", "list_available_connectors"),
    "list_connector_capabilities": ("vendor_fabric.registry", "list_connector_capabilities"),
    "list_connector_categories": ("vendor_fabric.registry", "list_connector_categories"),
    "list_connector_info": ("vendor_fabric.registry", "list_connector_info"),
    "list_connectors": ("vendor_fabric.registry", "list_connectors"),
    "list_connectors_by_capability": ("vendor_fabric.registry", "list_connectors_by_capability"),
    "list_connectors_by_category": ("vendor_fabric.registry", "list_connectors_by_category"),
}


def __getattr__(name: str) -> Any:
    """Lazily expose connector classes and registry helpers."""
    if name == "meshy":
        module = importlib.import_module("vendor_fabric.meshy")
        globals()[name] = module
        return module
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attr_name)
    globals()[name] = value
    return value


__all__ = [
    "AWSConnector",
    "AWSOrganizationsMixin",
    "AWSS3Mixin",
    "AWSSSOmixin",
    "AnthropicConnector",
    "BuiltinConnectorAdapter",
    "ConnectorAdapter",
    "ConnectorBase",
    "ConnectorFabric",
    "ConnectorInfo",
    "CursorConnector",
    "GitHubConnector",
    "GoogleBillingMixin",
    "GoogleCloudMixin",
    "GoogleConnector",
    "GoogleServicesMixin",
    "GoogleWorkspaceMixin",
    "JulesConnector",
    "MeshyConnector",
    "SlackConnector",
    "VaultConnector",
    "ZoomConnector",
    "__version__",
    "get_connector",
    "get_connector_adapter",
    "get_connector_class",
    "get_connector_info",
    "list_available_connectors",
    "list_connector_capabilities",
    "list_connector_categories",
    "list_connector_info",
    "list_connectors",
    "list_connectors_by_capability",
    "list_connectors_by_category",
    "meshy",
]
