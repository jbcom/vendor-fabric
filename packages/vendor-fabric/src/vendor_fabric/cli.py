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
import importlib
import inspect
import os
import sys

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from extended_data.containers import ExtendedList
from extended_data.containers.factory import to_builtin
from extended_data.io import wrap_raw_data_for_export
from extended_data.io.files import decode_file
from extended_data.primitives.formats.errors import DataDecodeError
from extended_data.primitives.redaction import redact_sensitive_text

from vendor_fabric.registry import (
    BUILTIN_CONNECTORS,
    get_connector,
    get_connector_class,
    get_connector_info,
    list_connector_info,
    list_connectors_by_capability,
    list_connectors_by_category,
)
from vendor_fabric.surface import connector_data_methods, is_connector_data_method


_CREDENTIAL_SOURCES: dict[str, dict[str, tuple[str, ...]]] = {
    "anthropic": {"required": ("ANTHROPIC_API_KEY",), "optional": (), "notes": ()},
    "aws": {
        "required": (),
        "optional": ("EXECUTION_ROLE_ARN", "ROLE_SESSION_NAME"),
        "notes": ("Uses the standard boto3 credential and config chain.",),
    },
    "cursor": {"required": ("CURSOR_API_KEY",), "optional": (), "notes": ()},
    "github": {
        "required": ("GITHUB_TOKEN", "GITHUB_OWNER"),
        "optional": ("GITHUB_REPO", "GITHUB_BRANCH"),
        "notes": (),
    },
    "google": {"required": ("GOOGLE_SERVICE_ACCOUNT",), "optional": (), "notes": ()},
    "jules": {"required": ("JULES_API_KEY",), "optional": (), "notes": ()},
    "meshy": {"required": ("MESHY_API_KEY",), "optional": (), "notes": ()},
    "slack": {"required": ("SLACK_TOKEN", "SLACK_BOT_TOKEN"), "optional": (), "notes": ()},
    "vault": {
        "required": ("VAULT_ADDR",),
        "optional": (
            "VAULT_TOKEN",
            "VAULT_ROLE_ID",
            "VAULT_SECRET_ID",
            "VAULT_NAMESPACE",
            "VAULT_APPROLE_PATH",
        ),
        "notes": ("Use VAULT_TOKEN or the VAULT_ROLE_ID and VAULT_SECRET_ID AppRole pair.",),
    },
    "zoom": {
        "required": ("ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET", "ZOOM_ACCOUNT_ID"),
        "optional": (),
        "notes": (),
    },
}

_SENSITIVE_ARGUMENT_NAMES = {
    "api_key",
    "bot_token",
    "client_secret",
    "credentials",
    "github_token",
    "password",
    "secret_value",
    "service_account_info",
    "token",
    "vault_token",
    "webhook_secret",
}

_ARGUMENT_SOURCE_SUFFIXES = ("_env", "_file", "_stdin")


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


def _is_sensitive_argument(name: str) -> bool:
    """Return whether a method argument must be sourced outside argv."""
    normalized = name.lower().replace("-", "_")
    return normalized in _SENSITIVE_ARGUMENT_NAMES or normalized.endswith(("_api_key", "_password", "_token"))


def _read_argument_source(source: str, reference: str | None) -> Any:
    """Read and decode one method argument from a non-argv value source."""
    if source == "stdin":
        return _parse_arg_value(sys.stdin.read().rstrip("\r\n"))
    if reference is None:
        msg = f"The --*-{source} argument requires a source name or path"
        raise ValueError(msg)
    if source == "env":
        try:
            value = os.environ[reference]
        except KeyError:
            msg = f"Environment variable {reference!r} is not set"
            raise ValueError(msg) from None
        return _parse_arg_value(value)
    return _parse_arg_value(Path(reference).read_text(encoding="utf-8"))


def _parse_call_arguments(extra: Sequence[str], *, json_output: bool) -> tuple[dict[str, Any], bool]:
    """Parse dynamic method arguments and their safe value sources."""
    kwargs: dict[str, Any] = {}
    i = 0
    while i < len(extra):
        arg = extra[i]
        if arg == "--json":
            json_output = True
            i += 1
            continue
        if not arg.startswith("--"):
            msg = f"Unexpected positional argument {arg!r}; method arguments use --name value"
            raise ValueError(msg)

        option_name = arg[2:].replace("-", "_")
        source = next((suffix[1:] for suffix in _ARGUMENT_SOURCE_SUFFIXES if option_name.endswith(suffix)), None)
        key = option_name[: -(len(source) + 1)] if source is not None else option_name
        if not key:
            msg = f"Invalid method argument {arg!r}"
            raise ValueError(msg)
        if key in kwargs:
            msg = f"Method argument --{key.replace('_', '-')} was provided more than once"
            raise ValueError(msg)

        if source == "stdin":
            kwargs[key] = _read_argument_source(source, None)
            i += 1
            continue

        has_value = i + 1 < len(extra) and not extra[i + 1].startswith("--")
        if source is not None:
            if not has_value:
                msg = f"{arg} requires a source name or path"
                raise ValueError(msg)
            kwargs[key] = _read_argument_source(source, extra[i + 1])
            i += 2
            continue

        if _is_sensitive_argument(key):
            safe_name = key.replace("_", "-")
            msg = (
                f"Sensitive argument --{safe_name} cannot be passed literally; use "
                f"--{safe_name}-env, --{safe_name}-file, or --{safe_name}-stdin"
            )
            raise ValueError(msg)

        kwargs[key] = _parse_arg_value(extra[i + 1]) if has_value else True
        i += 2 if has_value else 1

    return kwargs, json_output


def _surface_connector_class(connector_name: str) -> type[Any]:
    """Load a connector class for discovery without requiring its SDK extra."""
    try:
        return get_connector_class(connector_name)
    except ImportError:
        normalized = connector_name.strip().lower()
        spec = BUILTIN_CONNECTORS.get(normalized)
        if spec is None:
            raise
        module = importlib.import_module(spec.module_path)
        return getattr(module, spec.class_name)


def _method_signature(method: Any) -> inspect.Signature:
    """Return a user-facing method signature without self or cls."""
    signature = inspect.signature(method)
    parameters = list(signature.parameters.values())
    if parameters and parameters[0].name in {"self", "cls"}:
        parameters = parameters[1:]
    return signature.replace(parameters=parameters)


def _validate_method_arguments(method: Any, kwargs: Mapping[str, Any]) -> None:
    """Validate dynamic CLI arguments against the selected connector method."""
    signature = inspect.signature(method)
    parameters = list(signature.parameters.values())
    positional = [None] if parameters and parameters[0].name in {"self", "cls"} else []
    signature.bind(*positional, **kwargs)


def _connector_kwargs_from_environment(connector_name: str) -> dict[str, Any]:
    """Build non-secret constructor context using existing environment names."""
    normalized = connector_name.strip().lower()
    if normalized == "github":
        owner = os.environ.get("GITHUB_OWNER")
        if not owner:
            msg = "GITHUB_OWNER is required for GitHub CLI commands"
            raise ValueError(msg)
        kwargs = {"github_owner": owner}
        if repository := os.environ.get("GITHUB_REPO"):
            kwargs["github_repo"] = repository
        if branch := os.environ.get("GITHUB_BRANCH"):
            kwargs["github_branch"] = branch
        return kwargs
    if normalized == "aws" and (execution_role_arn := os.environ.get("EXECUTION_ROLE_ARN")):
        return {"execution_role_arn": execution_role_arn}
    return {}


def _apply_environment_method_defaults(method: Any, kwargs: dict[str, Any]) -> None:
    """Apply optional method context from established environment variables."""
    parameters = inspect.signature(method).parameters
    if (
        "role_session_name" in parameters
        and "role_session_name" not in kwargs
        and (role_session_name := os.environ.get("ROLE_SESSION_NAME"))
    ):
        kwargs["role_session_name"] = role_session_name


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

    kwargs: dict[str, Any] = {}
    json_output = bool(getattr(args, "json", False))

    try:
        cls = _surface_connector_class(connector_name)
        class_method = getattr(cls, method_name, None)
        if not is_connector_data_method(class_method):
            _write_stderr(f"Connector {connector_name!r} has no exposed data method {method_name!r}")
            return 1

        kwargs, json_output = _parse_call_arguments(args.extra or [], json_output=json_output)
        _apply_environment_method_defaults(class_method, kwargs)
        _validate_method_arguments(class_method, kwargs)
        connector_kwargs = _connector_kwargs_from_environment(connector_name)
        connector = get_connector(connector_name, **connector_kwargs)
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
        cls = _surface_connector_class(connector_name)
    except (ImportError, ValueError) as e:
        _write_stderr(str(e))
        return 1

    methods: list[dict[str, str]] = []
    for name, attr in connector_data_methods(cls):
        doc = attr.__doc__.split("\n")[0].strip()[:50] if attr.__doc__ else "No description"
        methods.append({"name": name, "signature": str(_method_signature(attr)), "description": doc})

    if getattr(args, "json", False):
        _write_stdout(_json_output(methods))
        return 0

    for method in methods:
        name = method["name"]
        signature = method["signature"]
        doc = method["description"]
        _write_stdout(f"  {name}{signature}  {doc}")

    return 0


def cmd_credentials(args: argparse.Namespace) -> int:
    """List connector credential and configuration source names."""
    names = [args.connector] if args.connector else sorted(_CREDENTIAL_SOURCES)
    entries: list[dict[str, Any]] = [
        {
            "connector": name,
            "required": list(_CREDENTIAL_SOURCES[name]["required"]),
            "optional": list(_CREDENTIAL_SOURCES[name]["optional"]),
            "notes": list(_CREDENTIAL_SOURCES[name]["notes"]),
        }
        for name in names
    ]
    if args.json:
        _write_stdout(_json_output(entries))
        return 0

    for entry in entries:
        _write_stdout(str(entry["connector"]))
        _write_stdout(f"  required: {_format_list(entry['required'])}")
        _write_stdout(f"  optional: {_format_list(entry['optional'])}")
        for note in entry["notes"]:
            _write_stdout(f"  note: {note}")
    return 0


def cmd_secrets_sync(args: argparse.Namespace) -> int:
    """Route a command through the binding-backed SecretSync CLI."""
    from vendor_fabric.secrets_sync import cli as secrets_sync_cli

    extra = list(args.extra)
    if getattr(args, "secrets_sync_help", False):
        extra.insert(0, "--help")
    return secrets_sync_cli.main(extra)


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
  vendor-fabric cursor list_agents      # Direct provider spelling
  vendor-fabric credentials github      # Show credential variable names
  vendor-fabric secrets-sync validate --config pipeline.yaml
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

    # Credential source discovery
    credentials_parser = subparsers.add_parser("credentials", help="Show connector credential source names")
    credentials_parser.add_argument("connector", nargs="?", choices=sorted(_CREDENTIAL_SOURCES))
    credentials_parser.add_argument("--json", action="store_true", help="JSON output")
    credentials_parser.set_defaults(func=cmd_credentials)

    # Call command
    call_parser = subparsers.add_parser("call", help="Call a connector data method")
    call_parser.add_argument("--json", action="store_true", help="JSON output")
    call_parser.add_argument("connector", help="Connector name")
    call_parser.add_argument("method", help="Method name")
    call_parser.add_argument("extra", nargs=argparse.REMAINDER, help="Method arguments (--arg value)")
    call_parser.set_defaults(func=cmd_call)

    # Direct aliases retain the call command's dynamic argument style.
    for connector_name in sorted(BUILTIN_CONNECTORS):
        provider_parser = subparsers.add_parser(
            connector_name,
            help=f"Call an exposed {connector_name} connector method",
        )
        provider_parser.add_argument("--json", action="store_true", help="JSON output")
        provider_parser.add_argument("method", help="Connector method name")
        provider_parser.add_argument("extra", nargs=argparse.REMAINDER, help="Method arguments (--arg value)")
        provider_parser.set_defaults(func=cmd_call, connector=connector_name)

    # Preserve the standalone SecretSync parser and exit-code behavior.
    secrets_sync_parser = subparsers.add_parser(
        "secrets-sync",
        help="Run the binding-backed SecretSync CLI",
        add_help=False,
    )
    secrets_sync_parser.add_argument("-h", "--help", dest="secrets_sync_help", action="store_true")
    secrets_sync_parser.add_argument("extra", nargs=argparse.REMAINDER)
    secrets_sync_parser.set_defaults(func=cmd_secrets_sync)

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
