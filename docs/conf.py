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
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
html_theme = "furo"
html_static_path = ["_static"]
html_css_files = ["vendor-fabric.css"]

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "tasklist",
]
myst_heading_anchors = 3

autodoc2_packages = [
    {
        "path": "../src/vendor_fabric",
        "module": "vendor_fabric",
    }
]
autodoc2_output_dir = "apidocs"
autodoc2_render_plugin = "myst"
autodoc2_hidden_objects = ["dunder", "private"]
