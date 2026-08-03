"""Public exceptions raised by LxmlSoup."""


class LxmlSoupError(Exception):
    """Base exception for LxmlSoup-specific failures."""


class FeatureNotFound(LxmlSoupError, ValueError):
    """Raised when a caller requests a parser backend LxmlSoup cannot provide."""


class SelectorError(LxmlSoupError, ValueError):
    """Raised when a CSS selector cannot be translated or evaluated."""


class XPathError(LxmlSoupError, ValueError):
    """Raised when an XPath expression cannot be evaluated."""
