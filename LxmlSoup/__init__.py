"""Fast, focused HTML querying powered by lxml."""

from .exceptions import FeatureNotFound, LxmlSoupError, SelectorError, XPathError
from .nodes import LxmlComment, LxmlDoctype, LxmlElement, LxmlString, TextValue
from .soup import LxmlSoup

__version__ = "2.0.0"

__all__ = [
    "LxmlSoup",
    "LxmlElement",
    "LxmlString",
    "LxmlComment",
    "LxmlDoctype",
    "TextValue",
    "LxmlSoupError",
    "FeatureNotFound",
    "SelectorError",
    "XPathError",
    "__version__",
]
