"""Copy authored documentation assets that Sourcey's markdown adapter references."""

from __future__ import annotations

import shutil

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/assets"
DESTINATION = ROOT / "docs/dist/assets"


def main() -> int:
    """Recreate the static asset directory in the Sourcey output."""
    if not ASSETS.is_dir():
        raise SystemExit(f"Documentation asset directory not found: {ASSETS}")
    try:
        if DESTINATION.exists():
            shutil.rmtree(DESTINATION)
        shutil.copytree(ASSETS, DESTINATION)
    except OSError as error:
        raise SystemExit(f"Unable to copy documentation assets: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
