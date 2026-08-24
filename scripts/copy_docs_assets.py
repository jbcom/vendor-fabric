#!/usr/bin/env python3
"""Copy authored documentation assets that Sourcey's markdown adapter references."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/assets"
DESTINATION = ROOT / "docs/dist/assets"


def main() -> int:
    """Recreate the static asset directory in the Sourcey output."""
    if DESTINATION.exists():
        shutil.rmtree(DESTINATION)
    shutil.copytree(ASSETS, DESTINATION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
