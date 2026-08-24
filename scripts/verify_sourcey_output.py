"""Validate the committed Sourcey site contract without browser-only assumptions."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "docs/dist"
REQUIRED = (
    "index.html",
    "reference/api/index.html",
    "llms.txt",
    "llms-full.txt",
    "sitemap.xml",
    "search-index.json",
    "assets/vendor-fabric-hero.png",
)


def main() -> int:
    """Fail for absent context exports, API reference, or repository-owned assets."""
    missing = [path for path in REQUIRED if not (DIST / path).is_file()]
    if missing:
        raise SystemExit(f"Sourcey output is incomplete: {', '.join(missing)}")
    homepage = (DIST / "index.html").read_text(encoding="utf-8")
    if 'src="assets/vendor-fabric-hero.png"' not in homepage:
        raise SystemExit("Sourcey homepage does not reference the Vendor Fabric hero asset")
    if 'href="/vendor-fabric/"' not in homepage:
        raise SystemExit("Sourcey homepage is not configured for its production subdirectory")
    context = (DIST / "llms-full.txt").read_text(encoding="utf-8")
    if "Vendor Fabric" not in context or "/vendor-fabric/" not in context or ".rst" in context:
        raise SystemExit("Sourcey context export contains an unexpected documentation graph")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
