"""Capability declarations for provider facade dispatch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, TypeVar, cast

from extended_data.containers import ExtendedDict, extend_data


F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class CapabilitySpec:
    """A provider-declared operation exposed through a facade."""

    operation: str
    kind: str = "operation"
    aliases: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class CapabilityRoute:
    """Resolved provider operation routed to a concrete method."""

    provider: str
    operation: str
    method: str
    kind: str = "operation"
    description: str = ""
    source: str = "decorator"

    def as_dict(self) -> ExtendedDict:
        """Return capability metadata as Extended Data."""
        return extend_data(
            {
                "provider": self.provider,
                "operation": self.operation,
                "method": self.method,
                "kind": self.kind,
                "description": self.description,
                "source": self.source,
            }
        )


def capability(
    operation: str,
    *,
    kind: str = "operation",
    aliases: tuple[str, ...] = (),
    description: str = "",
) -> Callable[[F], F]:
    """Declare that a provider method supports a facade operation."""

    def decorate(method: F) -> F:
        specs = list(getattr(method, "_vendor_capabilities", ()))
        specs.append(
            CapabilitySpec(
                operation=operation,
                kind=kind,
                aliases=aliases,
                description=description,
            )
        )
        method._vendor_capabilities = tuple(specs)  # type: ignore[attr-defined]
        return method

    return decorate


class CapabilityProviderMixin:
    """Collect provider capability declarations from class methods."""

    vendor_capabilities: ClassVar[dict[str, CapabilitySpec]]
    vendor_capability_methods: ClassVar[dict[str, str]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Collect decorated methods across the full MRO."""
        super().__init_subclass__(**kwargs)
        capabilities: dict[str, CapabilitySpec] = {}
        methods: dict[str, str] = {}

        for owner in reversed(cls.__mro__):
            for method_name, member in getattr(owner, "__dict__", {}).items():
                specs = cast("tuple[CapabilitySpec, ...]", getattr(member, "_vendor_capabilities", ()))
                for spec in specs:
                    for public_name in (spec.operation, *spec.aliases):
                        capabilities[public_name] = spec
                        methods[public_name] = method_name

        cls.vendor_capabilities = capabilities
        cls.vendor_capability_methods = methods


def capability_routes(provider: str, provider_cls: type[Any]) -> dict[str, CapabilityRoute]:
    """Return resolved capability routes for a provider class."""
    capabilities = getattr(provider_cls, "vendor_capabilities", {})
    methods = getattr(provider_cls, "vendor_capability_methods", {})
    routes: dict[str, CapabilityRoute] = {}

    for operation, spec in capabilities.items():
        method = methods[operation]
        routes[operation] = CapabilityRoute(
            provider=provider,
            operation=operation,
            method=method,
            kind=spec.kind,
            description=spec.description,
        )

    return routes
