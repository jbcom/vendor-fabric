"""Cloud Connectors.

This package provides optional vendor API integrations backed by an adapter
registry. The package root is intentionally lazy so ``import cloud_connectors``
works with only the base dependencies installed.
"""

from __future__ import annotations

import importlib

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any


try:
    __version__ = version("cloud-connectors")
except PackageNotFoundError:  # pragma: no cover - local editable fallback before install
    __version__ = "0.0.0"


if TYPE_CHECKING:
    from cloud_connectors.anthropic import AnthropicConnector
    from cloud_connectors.aws import AWSConnector, AWSOrganizationsMixin, AWSS3Mixin, AWSSSOmixin
    from cloud_connectors.base import ConnectorBase
    from cloud_connectors.connectors import ConnectorFabric
    from cloud_connectors.cursor import CursorConnector
    from cloud_connectors.github import GitHubConnector
    from cloud_connectors.google import (
        GoogleBillingMixin,
        GoogleCloudMixin,
        GoogleConnector,
        GoogleServicesMixin,
        GoogleWorkspaceMixin,
        JulesConnector,
    )
    from cloud_connectors.meshy import MeshyConnector
    from cloud_connectors.registry import (
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
    from cloud_connectors.slack import SlackConnector
    from cloud_connectors.vault import VaultConnector
    from cloud_connectors.zoom import ZoomConnector


_LAZY_EXPORTS = {
    "AWSConnector": ("cloud_connectors.aws", "AWSConnector"),
    "AWSOrganizationsMixin": ("cloud_connectors.aws", "AWSOrganizationsMixin"),
    "AWSS3Mixin": ("cloud_connectors.aws", "AWSS3Mixin"),
    "AWSSSOmixin": ("cloud_connectors.aws", "AWSSSOmixin"),
    "AnthropicConnector": ("cloud_connectors.anthropic", "AnthropicConnector"),
    "BuiltinConnectorAdapter": ("cloud_connectors.registry", "BuiltinConnectorAdapter"),
    "ConnectorAdapter": ("cloud_connectors.registry", "ConnectorAdapter"),
    "ConnectorBase": ("cloud_connectors.base", "ConnectorBase"),
    "ConnectorFabric": ("cloud_connectors.connectors", "ConnectorFabric"),
    "ConnectorInfo": ("cloud_connectors.registry", "ConnectorInfo"),
    "CursorConnector": ("cloud_connectors.cursor", "CursorConnector"),
    "GitHubConnector": ("cloud_connectors.github", "GitHubConnector"),
    "GoogleBillingMixin": ("cloud_connectors.google", "GoogleBillingMixin"),
    "GoogleCloudMixin": ("cloud_connectors.google", "GoogleCloudMixin"),
    "GoogleConnector": ("cloud_connectors.google", "GoogleConnector"),
    "GoogleServicesMixin": ("cloud_connectors.google", "GoogleServicesMixin"),
    "GoogleWorkspaceMixin": ("cloud_connectors.google", "GoogleWorkspaceMixin"),
    "JulesConnector": ("cloud_connectors.google", "JulesConnector"),
    "MeshyConnector": ("cloud_connectors.meshy", "MeshyConnector"),
    "SlackConnector": ("cloud_connectors.slack", "SlackConnector"),
    "VaultConnector": ("cloud_connectors.vault", "VaultConnector"),
    "ZoomConnector": ("cloud_connectors.zoom", "ZoomConnector"),
    "get_connector": ("cloud_connectors.registry", "get_connector"),
    "get_connector_adapter": ("cloud_connectors.registry", "get_connector_adapter"),
    "get_connector_class": ("cloud_connectors.registry", "get_connector_class"),
    "get_connector_info": ("cloud_connectors.registry", "get_connector_info"),
    "list_available_connectors": ("cloud_connectors.registry", "list_available_connectors"),
    "list_connector_capabilities": ("cloud_connectors.registry", "list_connector_capabilities"),
    "list_connector_categories": ("cloud_connectors.registry", "list_connector_categories"),
    "list_connector_info": ("cloud_connectors.registry", "list_connector_info"),
    "list_connectors": ("cloud_connectors.registry", "list_connectors"),
    "list_connectors_by_capability": ("cloud_connectors.registry", "list_connectors_by_capability"),
    "list_connectors_by_category": ("cloud_connectors.registry", "list_connectors_by_category"),
}


def __getattr__(name: str) -> Any:
    """Lazily expose connector classes and registry helpers."""
    if name == "meshy":
        module = importlib.import_module("cloud_connectors.meshy")
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
