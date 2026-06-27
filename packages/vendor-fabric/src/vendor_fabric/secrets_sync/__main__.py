"""Command line entry point for the vendor-fabric SecretSync binding facade."""

from vendor_fabric.secrets_sync.cli import main


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
