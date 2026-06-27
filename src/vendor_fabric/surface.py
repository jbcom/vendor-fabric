"""Public connector data-surface helpers."""

from __future__ import annotations

import builtins

from collections.abc import Callable
from typing import Any, cast, get_args, get_origin, get_type_hints

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedSet, ExtendedString, ExtendedTuple


EXTENDED_PAYLOAD_TYPES = (ExtendedDict, ExtendedList, ExtendedSet, ExtendedString, ExtendedTuple)


def connector_data_methods(connector_class: builtins.type[Any]) -> list[tuple[str, Callable[..., Any]]]:
    """Return public connector methods that advertise Extended Data payloads."""
    methods: list[tuple[str, Callable[..., Any]]] = []
    for name in dir(connector_class):
        if name.startswith("_"):
            continue
        attr = getattr(connector_class, name, None)
        if is_connector_data_method(attr):
            methods.append((name, cast(Callable[..., Any], attr)))
    return methods


def is_connector_data_method(method: Any) -> bool:
    """Return True when a callable belongs to the public data payload surface."""
    if not callable(method) or isinstance(method, builtins.type):
        return False

    qualname = getattr(method, "__qualname__", "")
    if qualname.startswith(("ConnectorBase.", "InputProvider.")):
        return False

    return annotation_includes_extended_payload(return_annotation(method))


def return_annotation(method: Callable[..., Any]) -> Any:
    """Resolve a callable return annotation without failing on optional imports."""
    try:
        return get_type_hints(method).get("return")
    except Exception:
        return getattr(method, "__annotations__", {}).get("return")


def annotation_includes_extended_payload(annotation: Any) -> bool:
    """Return True when an annotation includes a Tier 2 container type."""
    if annotation is None:
        return False

    if isinstance(annotation, str):
        return any(payload_type.__name__ in annotation for payload_type in EXTENDED_PAYLOAD_TYPES)

    if annotation in EXTENDED_PAYLOAD_TYPES:
        return True

    origin = get_origin(annotation)
    if origin in EXTENDED_PAYLOAD_TYPES:
        return True

    return any(annotation_includes_extended_payload(arg) for arg in get_args(annotation))
