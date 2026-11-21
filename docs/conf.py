"""Sphinx configuration for the PyPowerlines documentation."""

from pypowerlines import __version__

project = "PyPowerlines"
author = "Tom Scott"
release = __version__
version = ".".join(__version__.split(".")[:2])

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]
napoleon_numpy_docstring = True
napoleon_google_docstring = False
autodoc_typehints = "description"

exclude_patterns = ["_build"]
html_theme = "alabaster"
