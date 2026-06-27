"""CLI for native vendor-fabric SecretSync capabilities."""

from __future__ import annotations

import argparse
import sys

from extended_data.io import wrap_raw_data_for_export
from extended_data.primitives.redaction import redact_sensitive_text

from vendor_fabric.secrets_sync.models import OutputFormat, SyncOperation, SyncOptions
from vendor_fabric.secrets_sync.pipeline import get_config_info, run_pipeline, validate_config


def _write_stdout(payload: object, *, encoding: str = "json") -> None:
    sys.stdout.write(wrap_raw_data_for_export(payload, allow_encoding=encoding))
    sys.stdout.write("\n")


def _write_stderr(message: object) -> None:
    sys.stderr.write(redact_sensitive_text(message))
    sys.stderr.write("\n")


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a config file."""
    result = validate_config(args.config)
    _write_stdout(result)
    return 0 if result["valid"] else 2


def cmd_info(args: argparse.Namespace) -> int:
    """Inspect a config file."""
    _write_stdout(get_config_info(args.config))
    return 0


def cmd_pipeline(args: argparse.Namespace) -> int:
    """Run a pipeline operation."""
    options = SyncOptions(
        operation=SyncOperation(args.operation),
        dry_run=args.dry_run,
        targets=args.targets or [],
        continue_on_error=args.continue_on_error,
        parallelism=args.parallelism,
        compute_diff=args.diff or args.dry_run,
        output_format=OutputFormat(args.output),
    )
    result = run_pipeline(args.config, options)
    _write_stdout(result)
    return 0 if result["success"] else 2


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(prog="vendor-fabric-secrets-sync")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a pipeline config")
    validate.add_argument("--config", required=True)
    validate.set_defaults(func=cmd_validate)

    info = subparsers.add_parser("info", help="Inspect a pipeline config")
    info.add_argument("--config", required=True)
    info.set_defaults(func=cmd_info)

    pipeline = subparsers.add_parser("pipeline", help="Run a merge/sync pipeline")
    pipeline.add_argument("--config", required=True)
    pipeline.add_argument("--operation", choices=[item.value for item in SyncOperation], default=SyncOperation.PIPELINE.value)
    pipeline.add_argument("--target", dest="targets", action="append", default=[])
    pipeline.add_argument("--dry-run", action="store_true")
    pipeline.add_argument("--diff", action="store_true")
    pipeline.add_argument("--output", choices=[item.value for item in OutputFormat], default=OutputFormat.JSON.value)
    pipeline.add_argument("--parallelism", type=int, default=4)
    pipeline.add_argument("--continue-on-error", action=argparse.BooleanOptionalAction, default=True)
    pipeline.set_defaults(func=cmd_pipeline)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        _write_stderr(exc)
        return 2
