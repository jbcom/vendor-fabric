"""Sphinx configuration for vendor-fabric."""

from __future__ import annotations


project = "Vendor Fabric"
author = "Jon Bogaty"
copyright = "2026, Jon Bogaty"  # noqa: A001

extensions = [
    "myst_parser",
    "autodoc2",
    "sphinx_copybutton",
]

source_suffix = {
    ".rst": "restructuredtext",
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
html_theme = "furo"
html_static_path = ["_static"]
html_css_files = ["vendor-fabric.css"]

autodoc2_packages = [
    {
        "path": "../packages/vendor-fabric/src/vendor_fabric",
        "module": "vendor_fabric",
    }
]
autodoc2_output_dir = "apidocs"
autodoc2_render_plugin = "rst"
autodoc2_docstring_parser_regexes = [(r".*", "myst")]
autodoc2_hidden_objects = ["dunder", "private"]

# Suppress ambiguous cross-reference warnings for common field names like
# ``type`` that appear on multiple pydantic/dataclass models across
# connectors. sphinx-autodoc2 generates a ``:type:`` cross-reference for
# each annotated field, and when multiple classes declare a field named
# ``type`` the reference is ambiguous. These are field-name collisions,
# not real documentation gaps.
suppress_warnings = ["ref.python"]
