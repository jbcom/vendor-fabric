"""Optional dependency utilities.

This module provides utilities for checking optional dependencies and
providing helpful error messages when they're missing.

Usage:
    from vendor_fabric._optional import require_extra, is_available

    # Check if available (returns bool)
    if is_available("boto3"):
        import boto3

    # Require with helpful error (raises ImportError)
    require_extra("boto3", "aws")  # -> "Install with: pip install vendor-fabric[aws]"
"""

from __future__ import annotations

import importlib

from typing import Any, cast

from extended_data.containers import ExtendedList, ExtendedString, extend_data


# Mapping of package names to their extras
PACKAGE_TO_EXTRA: dict[str, str] = {
    # Connector extras
    "boto3": "aws",
    "google.cloud": "google",
    "google.api_core": "google",
    "googleapiclient": "google",
    "github": "github",
    "python_graphql_client": "github",
    "slack_sdk": "slack",
    "hvac": "vault",
    "anthropic": "anthropic",
    "rich": "meshy",
    "numpy": "meshy",
    "validators": "meshy",
    "secrets_sync": "secrets-sync",
    # Features
    "fastapi": "webhooks",
    "uvicorn": "webhooks",
    "sqlite_vec": "vector",
}

# Cache for import checks
_import_cache: dict[str, bool] = {}

PACKAGE_INSTALL_HINTS: dict[str, str] = {
    "secrets_sync": (
        "Install secrets-sync-python-binding, or build and install it from jbcom/secrets-sync. "
        "vendor-fabric consumes the binding as the secrets_sync import."
    ),
    "sentence_transformers": (
        "Install sentence-transformers separately after reviewing its dependency tree; vendor-fabric does not "
        "include it in the vector extra while current releases pull vulnerable torch versions."
    ),
}

def is_available(package: str) -> bool:
    """Check if a package is available for import.

    Args:
        package: Package name to check (e.g., "boto3", "googleapiclient")

    Returns:
        True if package can be imported, False otherwise
    """
    if package in _import_cache:
        return _import_cache[package]

    try:
        importlib.import_module(package)
        _import_cache[package] = True
        return True
    except ImportError:
        _import_cache[package] = False
        return False


def get_extra_for_package(package: str) -> ExtendedString | None:
    """Get the extra name for a package.

    Args:
        package: Package name

    Returns:
        Extra name or None if not mapped
    """
    extra = PACKAGE_TO_EXTRA.get(package)
    if extra is None:
        return None
    return ExtendedString(extra)


def require_extra(package: str, extra: str | None = None) -> Any:
    """Import a package, raising helpful error if missing.

    Args:
        package: Package name to import
        extra: Optional extra name override (auto-detected if not provided)

    Returns:
        The imported module

    Raises:
        ImportError: With helpful install instructions if package is missing
    """
    try:
        return importlib.import_module(package)
    except ImportError as e:
        if package in PACKAGE_INSTALL_HINTS:
            raise ImportError(
                f"Package '{package}' is required but not installed.\n{PACKAGE_INSTALL_HINTS[package]}"
            ) from e
        extra_name = str(extra or get_extra_for_package(package) or package)
        raise ImportError(
            f"Package '{package}' is required but not installed.\n"
            f"Install with: pip install vendor-fabric[{extra_name}]"
        ) from e


def require_any(*packages: str, extra: str) -> Any:
    """Import the first available package from a list.

    Args:
        *packages: Package names to try (in order)
        extra: Extra name for error message

    Returns:
        The first successfully imported module

    Raises:
        ImportError: If none of the packages are available
    """
    errors = []
    for package in packages:
        try:
            return importlib.import_module(package)
        except ImportError as e:
            errors.append(str(e))

    raise ImportError(
        f"None of the required packages are installed: {', '.join(packages)}\n"
        f"Install with: pip install vendor-fabric[{extra}]"
    )


# === Connector Availability ===

CONNECTOR_REQUIREMENTS: dict[str, list[str]] = {
    # Core-only connectors (always available)
    "cursor": [],  # httpx is in core
    "meshy": [],  # httpx, pydantic, tenacity are in core
    "zoom": [],  # requests is in core
    # Connectors requiring extras
    "anthropic": ["anthropic"],
    "aws": ["boto3"],
    "google": ["googleapiclient"],
    "github": ["github"],
    "jules": ["googleapiclient"],
    "slack": ["slack_sdk"],
    "vault": ["hvac"],
}

CONNECTOR_EXTRAS: dict[str, str] = {
    "anthropic": "anthropic",
    "aws": "aws",
    "cursor": "cursor",
    "google": "google",
    "github": "github",
    "jules": "google",
    "meshy": "meshy",
    "slack": "slack",
    "vault": "vault",
    "zoom": "zoom",
}


def _normalize_connector_name(connector: str) -> str:
    """Normalize connector names for optional dependency lookup."""
    return connector.strip().lower()


def get_extra_for_connector(connector: str) -> ExtendedString | None:
    """Get the optional dependency extra for a connector."""
    extra = CONNECTOR_EXTRAS.get(_normalize_connector_name(connector))
    if extra is None:
        return None
    return ExtendedString(extra)


def get_connector_requirements(connector: str) -> ExtendedList[ExtendedString]:
    """Get package imports required by a connector."""
    return cast(
        ExtendedList[ExtendedString],
        extend_data(list(CONNECTOR_REQUIREMENTS.get(_normalize_connector_name(connector), []))),
    )


def get_missing_connector_requirements(connector: str) -> ExtendedList[ExtendedString]:
    """Get missing package imports for a connector."""
    return cast(
        ExtendedList[ExtendedString],
        extend_data([str(pkg) for pkg in get_connector_requirements(connector) if not is_available(str(pkg))]),
    )


def get_connector_install_command(connector: str) -> ExtendedString | None:
    """Get the pip install command for a connector extra."""
    extra = get_extra_for_connector(connector)
    if extra is None:
        return None
    return ExtendedString(f"pip install vendor-fabric[{extra}]")


def is_connector_available(connector: str) -> bool:
    """Check if a connector's dependencies are available.

    Args:
        connector: Connector name (e.g., "aws", "meshy")

    Returns:
        True if all required packages are available
    """
    return not get_missing_connector_requirements(connector)


def get_available_connectors() -> ExtendedList[ExtendedString]:
    """Get list of connectors with available dependencies.

    Returns:
        Extended list of connector names that can be used.
    """
    return extend_data([name for name in CONNECTOR_REQUIREMENTS if is_connector_available(name)])


def require_connector(connector: str) -> None:
    """Ensure a connector's dependencies are available.

    Args:
        connector: Connector name

    Raises:
        ImportError: With helpful message if dependencies missing
    """
    missing = get_missing_connector_requirements(connector)

    if missing:
        extra = get_extra_for_connector(connector) or connector
        raise ImportError(
            f"The '{connector}' connector requires additional dependencies.\n"
            f"Missing packages: {', '.join(str(package) for package in missing)}\n"
            f"Install with: pip install vendor-fabric[{extra}]"
        )
