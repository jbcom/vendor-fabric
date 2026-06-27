"""Unified CLI for Vendor Fabric.

This module provides a command-line interface to all vendor fabric
using the central registry for discovery.

Usage:
    # List connector catalog entries
    vendor-fabric list
    vendor-fabric list --category cloud
    vendor-fabric list --capability repositories

    # Call any connector data method
    vendor-fabric call <connector> <method> [--arg value ...]

"""

from __future__ import annotations

import argparse
import sys

from collections.abc import Mapping, Sequence
from typing import Any

from extended_data.containers import ExtendedList
from extended_data.containers.factory import to_builtin
from extended_data.io import wrap_raw_data_for_export
from extended_data.io.files import decode_file
from extended_data.primitives.formats.errors import DataDecodeError
from extended_data.primitives.redaction import redact_sensitive_text

from vendor_fabric.registry import (
    get_connector,
    get_connector_class,
    get_connector_info,
    list_connector_info,
    list_connectors_by_capability,
    list_connectors_by_category,
)
from vendor_fabric.surface import connector_data_methods, is_connector_data_method


def _json_output(data: Any) -> str:
    """Format data as JSON for output."""
    data = to_builtin(data)
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    elif isinstance(data, Mapping):
        data = dict(data)
    elif hasattr(data, "__iter__") and not isinstance(data, (str, bytes, bytearray)):
        data = [d.model_dump() if hasattr(d, "model_dump") else d for d in data]
    return wrap_raw_data_for_export(data, allow_encoding="json", indent_2=True, default=str)


def _parse_arg_value(value: str) -> Any:
    """Parse a CLI argument value, attempting JSON decode."""
    # Try JSON first
    try:
        return decode_file(value, suffix="json", as_extended=False)
    except DataDecodeError:
        pass

    # Try common conversions
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        pass

    return value


def _format_list(values: list[Any] | tuple[Any, ...] | ExtendedList[Any] | None) -> str:
    """Format a list-like metadata field for CLI output."""
    if not values:
        return "-"
    return ", ".join(str(value) for value in values)


def _write_stdout(message: str) -> None:
    """Write one CLI output line."""
    sys.stdout.write(f"{redact_sensitive_text(message)}\n")


def _write_stderr(message: str) -> None:
    """Write one CLI error line."""
    sys.stderr.write(f"{redact_sensitive_text(message)}\n")


def _filter_connector_info(args: argparse.Namespace) -> ExtendedList[Any]:
    """Return connector catalog entries filtered by CLI flags."""
    include_unavailable = not getattr(args, "available_only", False)
    info = list_connector_info(include_unavailable=include_unavailable)
    names: set[str] | None = None

    if category := getattr(args, "category", None):
        names = {
            str(connector["name"])
            for connector in list_connectors_by_category(category, include_unavailable=include_unavailable)
        }

    if capability := getattr(args, "capability", None):
        capability_names = {
            str(connector["name"])
            for connector in list_connectors_by_capability(capability, include_unavailable=include_unavailable)
        }
        names = capability_names if names is None else names & capability_names

    if names is None:
        return info

    return ExtendedList(connector for connector in info if str(connector["name"]) in names)


# =============================================================================
# Commands
# =============================================================================


def cmd_list(args: argparse.Namespace) -> int:
    """List connector catalog entries."""
    info = _filter_connector_info(args)

    if args.json:
        _write_stdout(_json_output(info))
        return 0

    _write_stdout(f"{'name':<18} {'status':<11} {'category':<16} {'capabilities':<34} {'extra':<10} install")
    for c in info:
        status = "available" if c["available"] else "missing"
        name = str(c["name"])
        category = str(c.get("category") or "-")
        capabilities = _format_list(c.get("capabilities"))
        extra = str(c.get("extra") or "-")
        install = str(c.get("install") or "-")
        _write_stdout(f"{name:<18} {status:<11} {category:<16} {capabilities:<34} {extra:<10} {install}")

    return 0


def cmd_call(args: argparse.Namespace) -> int:
    """Call a connector data method."""
    connector_name = args.connector
    method_name = args.method

    # Parse extra arguments
    kwargs = {}
    json_output = bool(getattr(args, "json", False))
    extra = args.extra or []
    i = 0
    while i < len(extra):
        arg = extra[i]
        if arg == "--json":
            json_output = True
            i += 1
            continue
        if arg.startswith("--"):
            key = arg[2:].replace("-", "_")
            if i + 1 < len(extra) and not extra[i + 1].startswith("--"):
                kwargs[key] = _parse_arg_value(extra[i + 1])
                i += 2
            else:
                kwargs[key] = True
                i += 1
        else:
            i += 1

    try:
        cls = get_connector_class(connector_name)
        class_method = getattr(cls, method_name, None)
        if not is_connector_data_method(class_method):
            _write_stderr(f"Connector {connector_name!r} has no exposed data method {method_name!r}")
            return 1

        connector = get_connector(connector_name)
        method = getattr(connector, method_name, None)

        if method is None or not callable(method):
            _write_stderr(f"Connector {connector_name!r} has no callable method {method_name!r}")
            return 1

        result = method(**kwargs)
        if result is not None:
            if json_output:
                _write_stdout(_json_output(result))
            elif isinstance(result, str):
                _write_stdout(result)
            else:
                _write_stdout(_json_output(result))
        return 0

    except Exception as e:
        _write_stderr(redact_sensitive_text(e, values=kwargs.values()))
        return 1


def cmd_methods(args: argparse.Namespace) -> int:
    """List connector data methods."""
    connector_name = args.connector

    try:
        cls = get_connector_class(connector_name)
    except (ImportError, ValueError) as e:
        _write_stderr(str(e))
        return 1

    methods: list[dict[str, str]] = []
    for name, attr in connector_data_methods(cls):
        doc = attr.__doc__.split("\n")[0].strip()[:50] if attr.__doc__ else "No description"
        methods.append({"name": name, "description": doc})

    if getattr(args, "json", False):
        _write_stdout(_json_output(methods))
        return 0

    for method in methods:
        name = method["name"]
        doc = method["description"]
        _write_stdout(f"  {name:<30} {doc}")

    return 0


def cmd_info(args: argparse.Namespace) -> int:
    """Show info about a specific connector."""
    try:
        info = get_connector_info(args.connector)
        if args.json:
            _write_stdout(_json_output(info))
            return 0

        for key in (
            "name",
            "available",
            "source",
            "category",
            "capabilities",
            "extra",
            "install",
            "requirements",
            "missing",
            "class",
            "module",
            "description",
            "error",
        ):
            value = info.get(key)
            if isinstance(value, list | tuple | ExtendedList):
                value = _format_list(value)
            _write_stdout(f"{key}: {value if value is not None else '-'}")
        return 0
    except (ImportError, ValueError) as e:
        _write_stderr(str(e))
        return 1


# =============================================================================
# Main CLI
# =============================================================================


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="vendor-fabric",
        description="Unified CLI for all vendor fabric",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  vendor-fabric list                    # List connector catalog entries
  vendor-fabric list --category cloud   # List vendor fabric
  vendor-fabric list --capability files # List connectors by capability
  vendor-fabric methods jules           # List Jules data methods
  vendor-fabric call jules list_sources # Call a method
  vendor-fabric call cursor list_agents
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List connector catalog entries")
    list_parser.add_argument("--json", action="store_true", help="JSON output")
    list_parser.add_argument("--available-only", action="store_true", help="Hide connectors with missing extras")
    list_parser.add_argument("--category", help="Filter by catalog category")
    list_parser.add_argument("--capability", help="Filter by catalog capability")
    list_parser.set_defaults(func=cmd_list)

    # Methods command
    methods_parser = subparsers.add_parser("methods", help="List connector data methods")
    methods_parser.add_argument("connector", help="Connector name")
    methods_parser.add_argument("--json", action="store_true", help="JSON output")
    methods_parser.set_defaults(func=cmd_methods)

    # Info command
    info_parser = subparsers.add_parser("info", help="Show connector info")
    info_parser.add_argument("connector", help="Connector name")
    info_parser.add_argument("--json", action="store_true", help="JSON output")
    info_parser.set_defaults(func=cmd_info)

    # Call command
    call_parser = subparsers.add_parser("call", help="Call a connector data method")
    call_parser.add_argument("--json", action="store_true", help="JSON output")
    call_parser.add_argument("connector", help="Connector name")
    call_parser.add_argument("method", help="Method name")
    call_parser.add_argument("extra", nargs=argparse.REMAINDER, help="Method arguments (--arg value)")
    call_parser.set_defaults(func=cmd_call)

    # Parse and execute
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if hasattr(args, "func"):
        try:
            return args.func(args)
        except KeyboardInterrupt:
            return 130
        except Exception as e:
            _write_stderr(str(e))
            return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
