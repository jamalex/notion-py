import os
import sys
from datetime import date

# for import below
sys.path.insert(0, os.path.abspath("../"))

from notion import __name__, __author__, __version__

project = __name__
author = __author__
release = __version__
copyright = f"{date.today().year}, {__author__}"

html_baseurl = "arturtamborski.pl"
html_theme = "sphinx_rtd_theme"

extensions = [
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.githubpages",
    "sphinx.ext.autodoc",
    "sphinx_rtd_theme",
]

napoleon_include_init_with_doc = True
napoleon_google_docstring = False
napoleon_use_param = True
napoleon_use_rtype = True
