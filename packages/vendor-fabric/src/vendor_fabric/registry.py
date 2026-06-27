"""Connector Registry with Entry Points.

This module provides automatic discovery and registration of vendor fabric
using Python's entry points system. This allows:

1. DRY interface via ConnectorBase ABC
2. Automatic discovery of all connectors (even from other packages)
3. Unified factory function for instantiation
4. Shared registry for CLI and provider dispatch

Usage:
    from vendor_fabric.registry import get_connector, list_available_connectors, list_connectors

    # List catalog connectors or only runtime-ready connectors
    catalog = list_connectors()
    available = list_available_connectors()
    # ExtendedList(["anthropic", "aws", "cursor", ...])

    # Get a specific connector instance
    connector = get_connector('jules', api_key='...')

    # Use it
    sources = connector.list_sources()

Entry Points (in pyproject.toml):
    [project.entry-points."vendor_fabric.connectors"]
    jules = "vendor_fabric.google.jules:JulesConnector"
    cursor = "vendor_fabric.cursor:CursorConnector"
    github = "vendor_fabric.github:GitHubConnector"
"""

from __future__ import annotations

import abc
import builtins
import importlib

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NoReturn

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString, extend_data
from extended_data.primitives.redaction import redact_sensitive_text

from vendor_fabric._optional import (
    get_connector_install_command,
    get_connector_requirements,
    get_extra_for_connector,
    get_missing_connector_requirements,
)


if TYPE_CHECKING:
    from vendor_fabric.base import ConnectorBase


@dataclass(frozen=True)
class BuiltinConnectorSpec:
    """Import metadata for a built-in connector."""

    module_path: str
    class_name: str
    extra: str
    category: str = "external"
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConnectorInfo:
    """Registry metadata for a connector."""

    name: str
    available: bool
    source: str
    extra: str | None
    category: str
    capabilities: tuple[str, ...]
    install: str | None
    requirements: tuple[str, ...]
    missing: tuple[str, ...]
    class_name: str | None
    module: str | None
    base_url: str | None
    description: str | None
    error: str | None

    def as_dict(self) -> ExtendedDict:
        """Return extended JSON-friendly connector metadata."""
        return extend_data(
            {
                "name": self.name,
                "available": self.available,
                "source": self.source,
                "extra": self.extra,
                "category": self.category,
                "capabilities": list(self.capabilities),
                "install": self.install,
                "requirements": list(self.requirements),
                "missing": list(self.missing),
                "class": self.class_name,
                "module": self.module,
                "base_url": self.base_url,
                "description": self.description,
                "error": self.error,
            }
        )


class ConnectorAdapter(abc.ABC):
    """Adapter contract for connector availability, metadata, and construction."""

    name: str

    @abc.abstractmethod
    def load_class(self) -> builtins.type[ConnectorBase]:
        """Return the connector class when the adapter is available."""

    @abc.abstractmethod
    def validate_dependencies(self) -> None:
        """Raise a central install error when adapter requirements are missing."""

    @abc.abstractmethod
    def info(self, error: ImportError | None = None) -> ConnectorInfo:
        """Return registry metadata for this adapter."""

    def create(self, **kwargs: Any) -> ConnectorBase:
        """Instantiate the adapter's connector class."""
        cls = self.load_class()
        return cls(**kwargs)

    def as_dict(self) -> ExtendedDict:
        """Return extended JSON-friendly adapter metadata."""
        return self.info().as_dict()


BUILTIN_CONNECTORS: dict[str, BuiltinConnectorSpec] = {
    # Google connectors
    "jules": BuiltinConnectorSpec(
        "vendor_fabric.google.jules",
        "JulesConnector",
        "google",
        category="ai",
        capabilities=("sources", "sessions"),
    ),
    "google": BuiltinConnectorSpec(
        "vendor_fabric.google",
        "GoogleConnector",
        "google",
        category="cloud",
        capabilities=("workspace", "cloud", "billing", "services", "iam"),
    ),
    # Other connectors
    "cursor": BuiltinConnectorSpec(
        "vendor_fabric.cursor",
        "CursorConnector",
        "cursor",
        category="ai",
        capabilities=("agents", "repositories", "models"),
    ),
    "github": BuiltinConnectorSpec(
        "vendor_fabric.github",
        "GitHubConnector",
        "github",
        category="development",
        capabilities=("repositories", "teams", "files", "graphql", "workflows"),
    ),
    "meshy": BuiltinConnectorSpec(
        "vendor_fabric.meshy",
        "MeshyConnector",
        "meshy",
        category="media",
        capabilities=("3d-generation", "animation", "rigging", "retexturing", "metadata"),
    ),
    "anthropic": BuiltinConnectorSpec(
        "vendor_fabric.anthropic",
        "AnthropicConnector",
        "anthropic",
        category="ai",
        capabilities=("messages", "models", "tools"),
    ),
    "aws": BuiltinConnectorSpec(
        "vendor_fabric.aws",
        "AWSConnector",
        "aws",
        category="cloud",
        capabilities=("identity", "secrets", "storage", "organizations", "sso"),
    ),
    "slack": BuiltinConnectorSpec(
        "vendor_fabric.slack",
        "SlackConnector",
        "slack",
        category="communications",
        capabilities=("messages", "channels", "users", "usergroups"),
    ),
    "zoom": BuiltinConnectorSpec(
        "vendor_fabric.zoom",
        "ZoomConnector",
        "zoom",
        category="communications",
        capabilities=("users", "meetings"),
    ),
    "vault": BuiltinConnectorSpec(
        "vendor_fabric.vault",
        "VaultConnector",
        "vault",
        category="secrets",
        capabilities=("kv", "aws-iam", "leases"),
    ),
}


@dataclass(frozen=True)
class BuiltinConnectorAdapter(ConnectorAdapter):
    """Adapter for a connector shipped inside this distribution."""

    name: str
    spec: BuiltinConnectorSpec

    @property
    def extra(self) -> str:
        """Return the install extra for this adapter."""
        return self.spec.extra

    @property
    def requirements(self) -> ExtendedList[ExtendedString]:
        """Return import names required by this adapter."""
        return get_connector_requirements(self.name)

    @property
    def missing(self) -> ExtendedList[ExtendedString]:
        """Return missing import names for this adapter."""
        return get_missing_connector_requirements(self.name)

    @property
    def install(self) -> str:
        """Return the pip install command for this adapter."""
        install = get_connector_install_command(self.name)
        return str(install or f"pip install vendor-fabric[{self.spec.extra}]")

    @property
    def available(self) -> bool:
        """Return whether optional runtime requirements are installed."""
        return not self.missing

    def unavailable_error(self, error: ImportError | None = None) -> ImportError:
        """Build the central unavailable-adapter import error."""
        missing = self.missing
        reason = (
            "its optional dependencies are not installed"
            if missing
            else "it could not be loaded from the connector adapter registry"
        )
        msg = f"The '{self.name}' connector is built in but {reason}.\nInstall with: {self.install}"
        if missing:
            msg = f"{msg}\nMissing packages: {', '.join(str(package) for package in missing)}"
        if error and str(error):
            msg = f"{msg}\nOriginal import error: {redact_sensitive_text(error)}"
        return ImportError(msg)

    def validate_dependencies(self) -> None:
        """Ensure this adapter's optional runtime requirements are installed."""
        if self.missing:
            raise self.unavailable_error()

    def load_class(self) -> builtins.type[ConnectorBase]:
        """Load the connector class after dependency validation."""
        self.validate_dependencies()
        try:
            module = importlib.import_module(self.spec.module_path)
            return getattr(module, self.spec.class_name)
        except ImportError as error:
            raise self.unavailable_error(error) from error
        except AttributeError as error:
            msg = (
                f"The built-in '{self.name}' connector adapter points at "
                f"{self.spec.module_path}:{self.spec.class_name}, but that class does not exist."
            )
            raise RuntimeError(msg) from error

    def info(self, error: ImportError | None = None) -> ConnectorInfo:
        """Return metadata without requiring caller-side import juggling."""
        if self.missing or error is not None:
            return _builtin_connector_info(self, available=False, error=error)

        try:
            cls = self.load_class()
        except ImportError as exc:
            return _builtin_connector_info(self, available=False, error=exc)

        return _class_connector_info(self.name, cls, spec=self.spec)


@dataclass(frozen=True)
class RegisteredConnectorAdapter(ConnectorAdapter):
    """Adapter for a connector class discovered through entry points."""

    name: str
    connector_class: builtins.type[ConnectorBase]

    def load_class(self) -> builtins.type[ConnectorBase]:
        """Return the already discovered connector class."""
        return self.connector_class

    def validate_dependencies(self) -> None:
        """Entry-point connectors are considered available after successful load."""

    def info(self, error: ImportError | None = None) -> ConnectorInfo:
        """Return metadata for a loaded entry-point connector."""
        if error is not None:
            return ConnectorInfo(
                name=self.name,
                available=False,
                source="entry_point",
                extra=str(extra) if (extra := get_extra_for_connector(self.name)) is not None else None,
                category="external",
                capabilities=(),
                install=str(install) if (install := get_connector_install_command(self.name)) is not None else None,
                requirements=tuple(str(requirement) for requirement in get_connector_requirements(self.name)),
                missing=tuple(str(requirement) for requirement in get_missing_connector_requirements(self.name)),
                class_name=None,
                module=None,
                base_url=None,
                description=None,
                error=redact_sensitive_text(error),
            )
        return _class_connector_info(self.name, self.connector_class, spec=None)


BUILTIN_CONNECTOR_ADAPTERS: dict[str, BuiltinConnectorAdapter] = {
    name: BuiltinConnectorAdapter(name=name, spec=spec) for name, spec in BUILTIN_CONNECTORS.items()
}


# Cache for discovered connectors
_connector_cache: dict[str, builtins.type[ConnectorBase]] | None = None
_missing_builtin_connectors: dict[str, ImportError] = {}


def _normalize_connector_name(name: str) -> str:
    """Normalize connector registry names."""
    return name.strip().lower()


def _normalize_catalog_token(value: object) -> str:
    """Normalize connector catalog categories and capabilities."""
    return str(value).strip().lower().replace("_", "-")


def _discover_connectors() -> dict[str, builtins.type[ConnectorBase]]:
    """Discover all registered connectors via entry points."""
    global _connector_cache

    if _connector_cache is not None:
        return _connector_cache

    connectors: dict[str, builtins.type[ConnectorBase]] = {}

    # Python 3.10+ uses importlib.metadata
    from importlib.metadata import entry_points

    eps = entry_points(group="vendor_fabric.connectors")

    for ep in eps:
        connector_name = _normalize_connector_name(ep.name)
        try:
            connectors[connector_name] = ep.load()
            _missing_builtin_connectors.pop(connector_name, None)
        except ImportError as e:
            if connector_name in BUILTIN_CONNECTORS:
                _missing_builtin_connectors[connector_name] = e
                continue
            import warnings

            warnings.warn(
                f"Failed to load connector '{redact_sensitive_text(ep.name)}': {redact_sensitive_text(e)}",
                stacklevel=2,
            )
        except Exception as e:
            # Log but don't fail - allow partial loading
            import warnings

            warnings.warn(
                f"Failed to load connector '{redact_sensitive_text(ep.name)}': {redact_sensitive_text(e)}",
                stacklevel=2,
            )

    _connector_cache = connectors
    return connectors


def _raise_missing_builtin_connector(name: str, error: ImportError) -> NoReturn:
    """Raise a clear install hint for a known built-in connector."""
    adapter = BUILTIN_CONNECTOR_ADAPTERS[name]
    raise adapter.unavailable_error(error) from error


def _raise_unregistered_builtin_connector(name: str) -> NoReturn:
    """Raise a packaging error when a declared built-in connector has no entry point."""
    spec = BUILTIN_CONNECTORS[name]
    raise RuntimeError(
        f"The built-in '{name}' connector is declared but is not registered in the "
        "vendor_fabric entry point group. "
        f'Expected: {name} = "{spec.module_path}:{spec.class_name}"'
    )


def _list_connector_classes() -> dict[str, builtins.type[ConnectorBase]]:
    """List available connector classes for internal tool registration."""
    return _discover_connectors().copy()


def list_connectors(*, include_unavailable: bool = True) -> ExtendedList[ExtendedString]:
    """List connector catalog names.

    Returns:
        ExtendedList of known connector registry names.
    """
    return extend_data(
        [str(connector["name"]) for connector in list_connector_info(include_unavailable=include_unavailable)],
    )


def list_available_connectors() -> ExtendedList[ExtendedString]:
    """List connector names whose runtime requirements are installed."""
    return list_connectors(include_unavailable=False)


def get_connector_class(name: str) -> builtins.type[ConnectorBase]:
    """Get a connector class by name.

    Args:
        name: Connector name (e.g., 'jules', 'cursor', 'github')

    Returns:
        The connector class.

    Raises:
        ValueError: If connector not found.
    """
    connectors = _discover_connectors()
    name_lower = _normalize_connector_name(name)

    if name_lower in BUILTIN_CONNECTOR_ADAPTERS:
        try:
            return BUILTIN_CONNECTOR_ADAPTERS[name_lower].load_class()
        except ImportError as error:
            _missing_builtin_connectors[name_lower] = error
            _raise_missing_builtin_connector(name_lower, error)

    if name_lower not in connectors:
        if name_lower in _missing_builtin_connectors:
            _raise_missing_builtin_connector(name_lower, _missing_builtin_connectors[name_lower])
        if name_lower in BUILTIN_CONNECTORS:
            _raise_unregistered_builtin_connector(name_lower)
        available = ", ".join(sorted(connectors.keys()))
        raise ValueError(f"Unknown connector: {redact_sensitive_text(name)}. Available: {available}")

    return connectors[name_lower]


def get_connector(name: str, **kwargs: Any) -> ConnectorBase:
    """Factory to instantiate a connector by name.

    Args:
        name: Connector name (e.g., 'jules', 'cursor', 'github')
        **kwargs: Arguments passed to connector constructor

    Returns:
        Instantiated connector.

    Raises:
        ValueError: If connector not found.

    Example:
        >>> connector = get_connector('jules', api_key='...')
        >>> connector.list_sources()
    """
    return get_connector_adapter(name, include_unavailable=False).create(**kwargs)


def clear_cache() -> None:
    """Clear the connector cache (useful for testing)."""
    global _connector_cache
    _connector_cache = None
    _missing_builtin_connectors.clear()


def _get_description(cls: builtins.type[ConnectorBase]) -> str | None:
    """Get the first useful line from a connector docstring."""
    if not cls.__doc__:
        return None
    for line in cls.__doc__.splitlines():
        description = line.strip()
        if description:
            return description
    return None


def _get_category(cls: builtins.type[ConnectorBase], spec: BuiltinConnectorSpec | None) -> str:
    """Get normalized category metadata for a connector."""
    raw_category = spec.category if spec else getattr(cls, "CONNECTOR_CATEGORY", "external")
    return _normalize_catalog_token(raw_category) or "external"


def _get_capabilities(cls: builtins.type[ConnectorBase], spec: BuiltinConnectorSpec | None) -> tuple[str, ...]:
    """Get normalized capability metadata for a connector."""
    raw_capabilities = spec.capabilities if spec else getattr(cls, "CONNECTOR_CAPABILITIES", ())
    capability_values = (raw_capabilities,) if isinstance(raw_capabilities, str) else raw_capabilities
    capabilities = [_normalize_catalog_token(capability) for capability in capability_values]
    capabilities = [capability for capability in capabilities if capability]
    return tuple(dict.fromkeys(capabilities))


def _class_connector_info(
    name: str,
    cls: builtins.type[ConnectorBase],
    *,
    spec: BuiltinConnectorSpec | None,
) -> ConnectorInfo:
    """Build metadata for a loadable connector class."""
    source = "builtin" if spec else "entry_point"
    extra_value = spec.extra if spec else get_extra_for_connector(name)
    extra = str(extra_value) if extra_value is not None else None
    requirements = tuple(str(requirement) for requirement in get_connector_requirements(name))
    missing = tuple(str(requirement) for requirement in get_missing_connector_requirements(name))
    install_value = get_connector_install_command(name)

    return ConnectorInfo(
        name=name,
        available=not missing,
        source=source,
        extra=extra,
        category=_get_category(cls, spec),
        capabilities=_get_capabilities(cls, spec),
        install=str(install_value) if install_value is not None else None,
        requirements=requirements,
        missing=missing,
        class_name=cls.__name__,
        module=cls.__module__,
        base_url=getattr(cls, "BASE_URL", None),
        description=_get_description(cls),
        error=None,
    )


def _available_connector_info(name: str, cls: builtins.type[ConnectorBase]) -> ConnectorInfo:
    """Build metadata for a loadable connector."""
    return _class_connector_info(name, cls, spec=BUILTIN_CONNECTORS.get(name))


def _builtin_connector_info(
    adapter: BuiltinConnectorAdapter,
    *,
    available: bool,
    error: ImportError | None,
) -> ConnectorInfo:
    """Build metadata for a known built-in connector that cannot be loaded."""
    error_message = redact_sensitive_text(error) if error else "Connector optional dependencies are not installed."

    return ConnectorInfo(
        name=adapter.name,
        available=available,
        source="builtin",
        extra=adapter.extra,
        category=adapter.spec.category,
        capabilities=adapter.spec.capabilities,
        install=adapter.install,
        requirements=tuple(str(requirement) for requirement in adapter.requirements),
        missing=tuple(str(requirement) for requirement in adapter.missing),
        class_name=adapter.spec.class_name,
        module=adapter.spec.module_path,
        base_url=None,
        description=None,
        error=error_message,
    )


def _missing_builtin_connector_info(name: str, error: ImportError | None) -> ConnectorInfo:
    """Build metadata for a known built-in connector that cannot be loaded."""
    return BUILTIN_CONNECTOR_ADAPTERS[name].info(error)


# =============================================================================
# Connector Info Helpers
# =============================================================================


def get_connector_info(name: str, *, include_unavailable: bool = True) -> ExtendedDict:
    """Get registry metadata about a connector."""
    connector_name = _normalize_connector_name(name)
    connectors = _discover_connectors()

    if connector_name in BUILTIN_CONNECTOR_ADAPTERS:
        adapter = BUILTIN_CONNECTOR_ADAPTERS[connector_name]
        info = adapter.info(_missing_builtin_connectors.get(connector_name))
        if info.available or include_unavailable:
            return info.as_dict()
        _raise_missing_builtin_connector(
            connector_name,
            _missing_builtin_connectors.get(connector_name) or adapter.unavailable_error(),
        )

    if connector_name in connectors:
        return _available_connector_info(connector_name, connectors[connector_name]).as_dict()

    if connector_name in _missing_builtin_connectors:
        if include_unavailable:
            return _missing_builtin_connector_info(
                connector_name, _missing_builtin_connectors[connector_name]
            ).as_dict()
        _raise_missing_builtin_connector(connector_name, _missing_builtin_connectors[connector_name])

    if include_unavailable and connector_name in BUILTIN_CONNECTORS:
        return _missing_builtin_connector_info(connector_name, None).as_dict()

    available = ", ".join(sorted(connectors.keys()))
    raise ValueError(f"Unknown connector: {redact_sensitive_text(name)}. Available: {available}")


def get_connector_adapter(name: str, *, include_unavailable: bool = True) -> ConnectorAdapter:
    """Get the adapter registry entry for a connector."""
    connector_name = _normalize_connector_name(name)
    connectors = _discover_connectors()

    if connector_name in BUILTIN_CONNECTOR_ADAPTERS:
        adapter = BUILTIN_CONNECTOR_ADAPTERS[connector_name]
        if adapter.info(_missing_builtin_connectors.get(connector_name)).available or include_unavailable:
            return adapter
        _raise_missing_builtin_connector(
            connector_name,
            _missing_builtin_connectors.get(connector_name) or adapter.unavailable_error(),
        )

    if connector_name in connectors:
        return RegisteredConnectorAdapter(connector_name, connectors[connector_name])

    available = ", ".join(sorted(set(connectors) | set(BUILTIN_CONNECTORS)))
    raise ValueError(f"Unknown connector: {redact_sensitive_text(name)}. Available: {available}")


def list_connector_info(*, include_unavailable: bool = True) -> ExtendedList[ExtendedDict]:
    """Get registry metadata for known connectors."""
    connectors = _discover_connectors()
    names = set(connectors) | set(BUILTIN_CONNECTOR_ADAPTERS)
    if include_unavailable:
        names.update(_missing_builtin_connectors)
    info = [get_connector_info(name, include_unavailable=True) for name in sorted(names)]
    if not include_unavailable:
        return extend_data([connector for connector in info if connector["available"]])
    return extend_data(info)


def list_connector_categories(*, include_unavailable: bool = True) -> ExtendedList[ExtendedString]:
    """List connector catalog categories."""
    categories = {
        str(connector["category"])
        for connector in list_connector_info(include_unavailable=include_unavailable)
        if connector["category"]
    }
    return extend_data(sorted(categories))


def list_connector_capabilities(*, include_unavailable: bool = True) -> ExtendedList[ExtendedString]:
    """List connector catalog capabilities."""
    capabilities: set[str] = set()
    for connector in list_connector_info(include_unavailable=include_unavailable):
        capabilities.update(str(capability) for capability in connector["capabilities"])
    return extend_data(sorted(capabilities))


def list_connectors_by_category(
    category: str,
    *,
    include_unavailable: bool = True,
) -> ExtendedList[ExtendedDict]:
    """List connector catalog entries for a category."""
    normalized = _normalize_catalog_token(category)
    return extend_data(
        [
            connector
            for connector in list_connector_info(include_unavailable=include_unavailable)
            if str(connector["category"]) == normalized
        ],
    )


def list_connectors_by_capability(
    capability: str,
    *,
    include_unavailable: bool = True,
) -> ExtendedList[ExtendedDict]:
    """List connector catalog entries for a capability."""
    normalized = _normalize_catalog_token(capability)
    return extend_data(
        [
            connector
            for connector in list_connector_info(include_unavailable=include_unavailable)
            if normalized in {str(value) for value in connector["capabilities"]}
        ],
    )
