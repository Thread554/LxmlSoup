# Changelog

## 2.0.0

- Rebuilt the package around separate document, node, and filter layers.
- Added safe XPath variable binding and identifier validation.
- Added early termination for `find()`, `find_all(limit=1)`, and simple
  `select_one()` selectors.
- Added Beautiful Soup-style filters, text nodes, comments, attributes,
  navigation, CSS selection, serialization, and common mutations.
- Added explicit parser options, empty-document handling, parser diagnostics,
  typed public exports, and compatibility aliases.
- Added guarded tree mutations that reject cyclic parent/child operations
  before changing the document.
- Added `xpath()` to documents and tags with namespaces, variables, scalar
  results, and automatic wrapping of elements, comments, and text nodes.
- Replaced legacy packaging metadata with `pyproject.toml`.
- Added differential tests and a reproducible benchmark suite.

### Breaking changes

- The redundant `from LxmlSoup.LxmlSoup import LxmlSoup` path was removed; use
  `from LxmlSoup import LxmlSoup`.
- `parent`, `children`, sibling members, and `text` now follow Beautiful Soup's
  property-based API.
- Calling a tag now invokes `find_all()` like Beautiful Soup instead of
  returning its text.
- `contents` and `descendants` include string and comment nodes.
- `get_text()` now defaults to `separator=""` and `strip=False`.
- Unsupported Beautiful Soup constructor features raise `FeatureNotFound`.
