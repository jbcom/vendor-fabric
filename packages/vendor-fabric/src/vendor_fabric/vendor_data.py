"""VendorData facade over Extended Data and provider connectors."""

from __future__ import annotations

import inspect

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Self, cast

from extended_data.containers import ExtendedData, ExtendedDict, ExtendedList, ExtendedString, extend_data, to_builtin
from extended_data.logging import Logging

from vendor_fabric.base import ConnectorBase
from vendor_fabric.capabilities import capability_routes
from vendor_fabric.connectors import ConnectorFabric


SupportSpec = str | Mapping[str, Any]


@dataclass(frozen=True)
class VendorCapability:
    """A public VendorData operation routed to a provider connector method."""

    provider: str
    operation: str
    method: str
    capability: str = "operation"
    description: str = ""
    source: str = "method"

    def as_dict(self) -> ExtendedDict:
        """Return capability metadata as Extended Data."""
        return extend_data(
            {
                "provider": self.provider,
                "operation": self.operation,
                "method": self.method,
                "capability": self.capability,
                "description": self.description,
                "source": self.source,
            }
        )


_OPERATION_PREFIXES = (
    "apply_",
    "copy_",
    "create_",
    "decode_",
    "delete_",
    "download",
    "get_",
    "image_",
    "list_",
    "load_",
    "put_",
    "read_",
    "rig_",
    "send_",
    "text_",
    "update_",
    "write_",
)


def _normalize_provider(provider_id: str) -> str:
    """Normalize provider identifiers used by the public facade."""
    normalized = provider_id.strip().lower().replace("-", "_")
    aliases = {
        "gcp": "google",
        "google_cloud": "google",
        "github_com": "github",
        "secretsmanager": "aws",
        "s3": "aws",
    }
    return aliases.get(normalized, normalized)


def _index_capabilities(capabilities: Iterable[VendorCapability]) -> dict[str, dict[str, VendorCapability]]:
    """Index capabilities as operation -> provider -> route."""
    index: dict[str, dict[str, VendorCapability]] = {}
    for route in capabilities:
        operation = route.operation.strip()
        provider = _normalize_provider(route.provider)
        index.setdefault(operation, {})[provider] = route
    return index


def _coerce_support_spec(provider: str, operation: str, spec: SupportSpec) -> VendorCapability:
    """Convert a provider ``__supports__`` entry into a capability route."""
    if isinstance(spec, str):
        return VendorCapability(provider=provider, operation=operation, method=spec, source="alias")

    method = str(spec.get("method", operation))
    return VendorCapability(
        provider=provider,
        operation=operation,
        method=method,
        capability=str(spec.get("capability", "operation")),
        description=str(spec.get("description", "")),
        source=str(spec.get("source", "alias")),
    )


def _declared_supports(provider: str, connector_cls: type[ConnectorBase]) -> list[VendorCapability]:
    """Read ``__supports__`` metadata from a connector class."""
    raw = getattr(connector_cls, "__supports__", {})
    if not isinstance(raw, Mapping):
        return []
    return [_coerce_support_spec(provider, str(operation), spec) for operation, spec in raw.items()]


def _public_method_supports(provider: str, connector_cls: type[ConnectorBase]) -> list[VendorCapability]:
    """Expose public provider methods as exact-name VendorData operations."""
    routes: list[VendorCapability] = []
    for name, member in inspect.getmembers(connector_cls):
        if name.startswith("_") or not callable(member):
            continue
        if not name.startswith(_OPERATION_PREFIXES):
            continue
        routes.append(VendorCapability(provider=provider, operation=name, method=name, source="method"))
    return routes


def _decorated_supports(provider: str, connector_cls: type[ConnectorBase]) -> list[VendorCapability]:
    """Read ``@capability`` declarations collected on a provider class."""
    return [
        VendorCapability(
            provider=route.provider,
            operation=route.operation,
            method=route.method,
            capability=route.kind,
            description=route.description,
            source=route.source,
        )
        for route in capability_routes(provider, connector_cls).values()
    ]


class VendorData(ExtendedData):
    """Extended Data facade with lazy vendor activation and capability dispatch.

    ``VendorData`` keeps ordinary Extended Data behavior for the wrapped value
    while adding a provider fabric. Providers are dormant until opened or used.
    Public operations such as ``get_file`` and ``list_users`` accept the provider
    id as their first argument, then dispatch to the provider-specific connector
    method declared in the capability matrix.
    """

    def __new__(
        cls,
        value: Any = None,
        *,
        fabric: ConnectorFabric | None = None,
        logger: Logging | None = None,
        capabilities: Iterable[VendorCapability] = (),
        **fabric_kwargs: Any,
    ) -> Self:
        """Allocate a facade instance instead of using the ExtendedData factory."""
        return object.__new__(cls)

    def __init__(
        self,
        value: Any = None,
        *,
        fabric: ConnectorFabric | None = None,
        logger: Logging | None = None,
        capabilities: Iterable[VendorCapability] = (),
        **fabric_kwargs: Any,
    ) -> None:
        self._data = ExtendedData(value)
        self.fabric = fabric or ConnectorFabric(logger=logger, **fabric_kwargs)
        self.logging = logger or getattr(self.fabric, "logging", None)
        self._declared_capabilities = tuple(capabilities)
        self._capability_index = _index_capabilities(self._declared_capabilities)
        self._provider_capability_cache: dict[str, dict[str, VendorCapability]] = {}
        self._providers: dict[str, Any] = {}
        self._unavailable: dict[str, ExtendedDict] = {}
        self._active_provider: str | None = None

    @property
    def value(self) -> Any:
        """Return the wrapped Extended Data value."""
        return self._data

    @property
    def data_type(self) -> str:
        """Return the wrapped value type name."""
        return type(self._data).__name__

    @property
    def shape(self) -> str:
        """Return the wrapped value shape."""
        return getattr(self._data, "shape", type(self._data).__name__)

    @property
    def active_provider(self) -> ExtendedString | None:
        """Return the active provider id, when one has been opened."""
        return ExtendedString(self._active_provider) if self._active_provider else None

    def as_builtin(self) -> Any:
        """Return the wrapped data lowered to built-in containers."""
        return to_builtin(self._data)

    def as_extended(self) -> Any:
        """Return the wrapped data as an Extended Data value."""
        return extend_data(self.as_builtin())

    def cast(self, value: Any) -> Self:
        """Mutate the wrapped value to a new Extended Data subtype."""
        self._data = ExtendedData(value)
        return self

    def open(self, provider_id: str, *, strict: bool = True, **kwargs: Any) -> Self:
        """Activate a provider connector and make it the active provider."""
        provider = _normalize_provider(provider_id)
        if provider in self._providers:
            self._active_provider = provider
            return self

        info = self.provider_info(provider)
        if not info.get("available", False):
            self._unavailable[provider] = info
            if strict:
                install = info.get("install") or f"pip install vendor-fabric[{provider}]"
                msg = f"Provider '{provider}' is not available. Install with: {install}"
                raise ImportError(msg)
            self._active_provider = provider
            return self

        self._providers[provider] = self.fabric.get_connector(provider, **kwargs)
        self._active_provider = provider
        return self

    def open_provider(self, provider_id: str, **kwargs: Any) -> Any:
        """Activate and return a provider connector."""
        provider = _normalize_provider(provider_id)
        self.open(provider, **kwargs)
        return self._providers[provider]

    def provider(self, provider_id: str, **kwargs: Any) -> Any:
        """Return an active provider connector, opening it when needed."""
        provider = _normalize_provider(provider_id)
        if provider not in self._providers:
            self.open(provider, **kwargs)
        return self._providers[provider]

    def provider_info(self, provider_id: str, *, include_unavailable: bool = True) -> ExtendedDict:
        """Return provider registry metadata."""
        return extend_data(
            self.fabric.get_connector_info(_normalize_provider(provider_id), include_unavailable=include_unavailable)
        )

    def is_provider_available(self, provider_id: str) -> bool:
        """Return whether a provider can be opened in this environment."""
        return bool(self.provider_info(provider_id).get("available", False))

    def capabilities(self, provider_id: str | None = None, *, include_unavailable: bool = True) -> ExtendedList[Any]:
        """Return VendorData capability routes."""
        routes = list(self._declared_capabilities)
        provider = _normalize_provider(provider_id) if provider_id else None
        providers = [provider] if provider else [str(item) for item in self.fabric.list_connectors()]
        for provider_name in providers:
            routes.extend(self._provider_supports(provider_name).values())
        if provider:
            routes = [route for route in routes if _normalize_provider(route.provider) == provider]
        if not include_unavailable:
            routes = [route for route in routes if self.is_provider_available(route.provider)]
        return ExtendedList(route.as_dict() for route in routes)

    def capability_matrix(self, *, include_unavailable: bool = True) -> ExtendedDict:
        """Return operation -> provider -> route metadata."""
        matrix: dict[str, dict[str, Any]] = {}
        for route in self.capabilities(include_unavailable=include_unavailable):
            matrix.setdefault(str(route["operation"]), {})[str(route["provider"])] = route
        return extend_data(matrix)

    def supports(self, provider_id: str, operation: str, *, require_available: bool = False) -> bool:
        """Return whether a provider supports a VendorData operation."""
        provider = _normalize_provider(provider_id)
        route = self._provider_supports(provider).get(operation) or self._capability_index.get(operation, {}).get(provider)
        if route is None:
            return False
        return not require_available or self.is_provider_available(provider)

    def call(self, operation: str, provider_id: str | None = None, *args: Any, **kwargs: Any) -> Any:
        """Dispatch an operation through its provider connector."""
        provider, route, remaining_args = self._resolve_route(operation, provider_id, args)
        connector = self.provider(provider)
        method = getattr(connector, route.method, None)
        if not callable(method):
            msg = f"Provider '{provider}' declares operation '{operation}' but has no method '{route.method}'"
            raise TypeError(msg)
        return extend_data(method(*remaining_args, **kwargs))

    def __getattr__(self, name: str) -> Any:
        """Expose ``open_<provider>`` and capability dispatchers dynamically."""
        if name.startswith("open_"):
            provider = name.removeprefix("open_")
            return lambda **kwargs: self.open(provider, **kwargs)

        if not name.startswith("_"):
            return lambda *args, **kwargs: self.call(name, None, *args, **kwargs)

        return getattr(self._data, name)

    @classmethod
    def declare_supports(cls, connector_cls: type[ConnectorBase], supports: Mapping[str, SupportSpec]) -> None:
        """Attach ``__supports__`` metadata to a provider class."""
        existing = dict(getattr(connector_cls, "__supports__", {}))
        existing.update(supports)
        cast("Any", connector_cls).__supports__ = existing

    def __len__(self) -> int:
        """Return length of wrapped data when available."""
        return len(self._data)

    def __iter__(self) -> Any:
        """Iterate over wrapped data when available."""
        return iter(self._data)

    def __getitem__(self, key: Any) -> Any:
        """Read from wrapped data when it supports indexing."""
        return self._data[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        """Write to wrapped data when it supports item assignment."""
        self._data[key] = extend_data(value)

    def __contains__(self, item: object) -> bool:
        """Return membership against wrapped data."""
        return item in self._data

    def _resolve_route(
        self,
        operation: str,
        provider_id: str | None,
        args: tuple[Any, ...],
    ) -> tuple[str, VendorCapability, tuple[Any, ...]]:
        provider_routes = self._operation_routes(operation)
        if not provider_routes:
            msg = f"Unknown VendorData operation '{operation}'"
            raise AttributeError(msg)

        remaining_args = args
        provider = _normalize_provider(provider_id) if provider_id else None
        if provider is None and args and isinstance(args[0], str):
            candidate = _normalize_provider(args[0])
            if candidate in provider_routes:
                provider = candidate
                remaining_args = args[1:]

        if provider is None and self._active_provider in provider_routes:
            provider = self._active_provider

        if provider is None and len(provider_routes) == 1:
            provider = next(iter(provider_routes))

        if provider is None:
            options = ", ".join(sorted(provider_routes))
            msg = f"Operation '{operation}' is supported by multiple providers. Pass provider id first: {options}"
            raise ValueError(msg)

        route = provider_routes.get(provider)
        route = route or self._provider_supports(provider).get(operation)
        if route is None:
            options = ", ".join(sorted({*provider_routes, *self._provider_supports(provider)}))
            msg = f"Provider '{provider}' does not support operation '{operation}'. Supported providers: {options}"
            raise ValueError(msg)

        return provider, route, remaining_args

    def _operation_routes(self, operation: str) -> dict[str, VendorCapability]:
        """Return all currently known provider routes for one operation."""
        routes = dict(self._capability_index.get(operation, {}))
        for provider_name in self.fabric.list_connectors():
            provider = _normalize_provider(str(provider_name))
            route = self._provider_supports(provider).get(operation)
            if route is not None:
                routes[provider] = route
        return routes

    def _provider_supports(self, provider_id: str) -> dict[str, VendorCapability]:
        """Return operation routes declared or inferred for one provider."""
        provider = _normalize_provider(provider_id)
        if provider in self._provider_capability_cache:
            return self._provider_capability_cache[provider]

        info = self.provider_info(provider)
        if not info.get("available", False):
            self._provider_capability_cache[provider] = {}
            return {}

        adapter = self.fabric.get_connector_adapter(provider)
        connector_cls = adapter.load_class()
        routes = _public_method_supports(provider, connector_cls)
        routes.extend(_declared_supports(provider, connector_cls))
        routes.extend(_decorated_supports(provider, connector_cls))
        route_index = {route.operation: route for route in routes}
        self._provider_capability_cache[provider] = route_index
        return route_index
