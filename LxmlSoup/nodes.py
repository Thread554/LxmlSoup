"""Public node objects and the Beautiful Soup-compatible query surface."""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from functools import lru_cache
from typing import Any, TYPE_CHECKING

from cssselect import HTMLTranslator, SelectorError as CSSSelectorError
from lxml import etree

from .exceptions import SelectorError, XPathError
from .filters import (
    attribute_value,
    build_xpath_plan,
    element_matches,
    matches_string,
    normalize_attributes,
    normalize_name_filter,
)

if TYPE_CHECKING:
    from .soup import LxmlSoup


class TextValue(str):
    """A text value that remains callable for legacy API compatibility."""

    def __call__(self) -> str:
        return str(self)


@lru_cache(maxsize=512)
def _css_to_xpath(selector: str, prefix: str) -> str:
    return HTMLTranslator().css_to_xpath(selector, prefix=prefix)


class SearchMixin:
    """Shared descendant-search implementation for documents and tags."""

    _soup: "LxmlSoup"

    def _search_root(self) -> etree._Element | None:
        raise NotImplementedError

    def _search_includes_context(self) -> bool:
        return False

    def _iter_search_strings(self, recursive: bool) -> Iterator["LxmlString"]:
        raise NotImplementedError

    def _iter_search_elements(self, recursive: bool, name: Any = None) -> Iterator[etree._Element]:
        root = self._search_root()
        if root is None:
            return
        tag = name.decode("utf-8", errors="replace") if isinstance(name, bytes) else name
        tag_filter = tag if isinstance(tag, str) else None
        if self._search_includes_context():
            candidates = root.iter(tag_filter) if recursive else iter((root,))
        elif recursive:
            candidates = root.iterdescendants(tag_filter)
        else:
            candidates = root.iterchildren(tag_filter)
        for candidate in candidates:
            if isinstance(candidate.tag, str):
                yield candidate

    @staticmethod
    def _normalize_limit(limit: int | None) -> int | None:
        if limit is None or limit == 0:
            return None
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer or None")
        if limit < 0:
            raise ValueError("limit must not be negative")
        return limit

    def find_all(
        self,
        name: Any = None,
        attrs: Any = None,
        recursive: bool = True,
        string: Any = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        """Find descendants using Beautiful Soup's common filtering contract."""

        if "text" in kwargs:
            if string is not None:
                raise TypeError("use either string= or text=, not both")
            string = kwargs.pop("text")
        normalized_limit = self._normalize_limit(limit)
        name = normalize_name_filter(name)
        attributes = normalize_attributes(attrs, kwargs)

        if name is None and not attributes and string is not None:
            results: list[LxmlString] = []
            for candidate in self._iter_search_strings(recursive):
                if matches_string(candidate, string):
                    results.append(candidate)
                    if normalized_limit is not None and len(results) >= normalized_limit:
                        break
            return results

        if normalized_limit == 1:
            for candidate in self._iter_search_elements(bool(recursive), name):
                wrapped = self._soup._wrap_element(candidate)
                if isinstance(wrapped, LxmlElement) and element_matches(
                    candidate,
                    wrapped,
                    name=name,
                    attrs=attributes,
                    string=string,
                ):
                    return [wrapped]
            return []

        root = self._search_root()
        if root is None:
            return []

        plan = build_xpath_plan(
            name=name,
            attrs=attributes,
            recursive=bool(recursive),
            include_context=self._search_includes_context(),
            string=string,
            limit=normalized_limit,
        )
        candidates = root.xpath(plan.expression, **plan.variables)
        results: list[LxmlElement] = []
        for candidate in candidates:
            if not isinstance(candidate, etree._Element) or not isinstance(candidate.tag, str):
                continue
            wrapped = self._soup._wrap_element(candidate)
            if not isinstance(wrapped, LxmlElement):
                continue
            if plan.exact or element_matches(
                candidate,
                wrapped,
                name=name,
                attrs=attributes,
                string=string,
            ):
                results.append(wrapped)
                if normalized_limit is not None and len(results) >= normalized_limit:
                    break
        return results

    def find(
        self,
        name: Any = None,
        attrs: Any = None,
        recursive: bool = True,
        string: Any = None,
        **kwargs: Any,
    ) -> Any:
        if "text" in kwargs:
            if string is not None:
                raise TypeError("use either string= or text=, not both")
            string = kwargs.pop("text")
        name = normalize_name_filter(name)
        attributes = normalize_attributes(attrs, kwargs)
        if name is None and not attributes and string is not None:
            for candidate in self._iter_search_strings(bool(recursive)):
                if matches_string(candidate, string):
                    return candidate
            return None
        for candidate in self._iter_search_elements(bool(recursive), name):
            wrapped = self._soup._wrap_element(candidate)
            if isinstance(wrapped, LxmlElement) and element_matches(
                candidate,
                wrapped,
                name=name,
                attrs=attributes,
                string=string,
            ):
                return wrapped
        return None

    def findel(self, tag: Any = None, attrs: Any = None, **kwargs: Any) -> list[Any]:
        """Backward-compatible alias for :meth:`find_all`."""

        return self.find_all(tag, attrs, **kwargs)

    findAll = find_all
    findChild = find
    findChildren = find_all
    find_child = find
    find_children = find_all

    def select(
        self,
        selector: str,
        namespaces: dict[str, str] | None = None,
        limit: int = 0,
        **kwargs: Any,
    ) -> list["LxmlElement"]:
        if kwargs:
            unsupported = ", ".join(sorted(kwargs))
            raise TypeError(f"unsupported select() arguments: {unsupported}")
        normalized_limit = self._normalize_limit(limit)
        root = self._search_root()
        if root is None:
            return []
        prefix = "descendant-or-self::" if self._search_includes_context() else "descendant::"
        try:
            expression = _css_to_xpath(selector, prefix)
            if normalized_limit == 1:
                remainder = (
                    expression[len(prefix) :]
                    if expression.startswith(prefix)
                    else expression
                )
                if "/" not in remainder and " | " not in remainder:
                    candidates = root.xpath(expression + "[1]", namespaces=namespaces)
                else:
                    candidates = root.xpath(f"({expression})[1]", namespaces=namespaces)
            else:
                candidates = root.xpath(expression, namespaces=namespaces)
        except (CSSSelectorError, etree.XPathError) as exc:
            raise SelectorError(f"invalid or unsupported CSS selector {selector!r}: {exc}") from exc
        results = [
            wrapped
            for candidate in candidates
            if isinstance(candidate, etree._Element) and isinstance(candidate.tag, str)
            if isinstance((wrapped := self._soup._wrap_element(candidate)), LxmlElement)
        ]
        return results[:normalized_limit] if normalized_limit is not None else results

    def select_one(
        self,
        selector: str,
        namespaces: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> "LxmlElement | None":
        results = self.select(selector, namespaces=namespaces, limit=1, **kwargs)
        return results[0] if results else None

    def xpath(
        self,
        expression: str,
        namespaces: dict[str, str] | None = None,
        extensions: Any = None,
        smart_strings: bool = True,
        **variables: Any,
    ) -> Any:
        """Evaluate XPath and wrap returned HTML nodes in LxmlSoup objects."""

        root = self._search_root()
        if root is None:
            return []
        try:
            result = root.xpath(
                expression,
                namespaces=namespaces,
                extensions=extensions,
                smart_strings=smart_strings,
                **variables,
            )
        except etree.XPathError as exc:
            raise XPathError(f"invalid or unsupported XPath {expression!r}: {exc}") from exc
        return self._soup._wrap_xpath_result(result)


class PageElement:
    """Navigation shared by tags and string-like nodes."""

    _soup: "LxmlSoup"

    @property
    def parent(self) -> Any:
        raise NotImplementedError

    @property
    def parents(self) -> Iterator[Any]:
        current = self.parent
        while current is not None:
            yield current
            current = getattr(current, "parent", None)

    @property
    def next_sibling(self) -> Any:
        return self._soup._sibling(self, offset=1)

    @property
    def previous_sibling(self) -> Any:
        return self._soup._sibling(self, offset=-1)

    @property
    def next_siblings(self) -> Iterator[Any]:
        yield from self._soup._siblings(self, reverse=False)

    @property
    def previous_siblings(self) -> Iterator[Any]:
        yield from self._soup._siblings(self, reverse=True)

    @property
    def next_element(self) -> Any:
        return self._soup._relative_node(self, offset=1)

    @property
    def previous_element(self) -> Any:
        return self._soup._relative_node(self, offset=-1)

    @property
    def next_elements(self) -> Iterator[Any]:
        yield from self._soup._relative_nodes(self, reverse=False)

    @property
    def previous_elements(self) -> Iterator[Any]:
        yield from self._soup._relative_nodes(self, reverse=True)

    def find_parent(self, name: Any = None, attrs: Any = None, **kwargs: Any) -> Any:
        results = self.find_parents(name=name, attrs=attrs, limit=1, **kwargs)
        return results[0] if results else None

    def find_parents(
        self,
        name: Any = None,
        attrs: Any = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        return self._soup._filter_nodes(
            self.parents,
            name=name,
            attrs=attrs,
            string=None,
            limit=limit,
            kwargs=kwargs,
        )

    findParent = find_parent
    findParents = find_parents

    def find_next_sibling(
        self,
        name: Any = None,
        attrs: Any = None,
        string: Any = None,
        **kwargs: Any,
    ) -> Any:
        results = self.find_next_siblings(name, attrs, string=string, limit=1, **kwargs)
        return results[0] if results else None

    def find_next_siblings(
        self,
        name: Any = None,
        attrs: Any = None,
        string: Any = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        return self._soup._filter_nodes(
            self.next_siblings,
            name=name,
            attrs=attrs,
            string=string,
            limit=limit,
            kwargs=kwargs,
        )

    def find_previous_sibling(
        self,
        name: Any = None,
        attrs: Any = None,
        string: Any = None,
        **kwargs: Any,
    ) -> Any:
        results = self.find_previous_siblings(name, attrs, string=string, limit=1, **kwargs)
        return results[0] if results else None

    def find_previous_siblings(
        self,
        name: Any = None,
        attrs: Any = None,
        string: Any = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        return self._soup._filter_nodes(
            self.previous_siblings,
            name=name,
            attrs=attrs,
            string=string,
            limit=limit,
            kwargs=kwargs,
        )

    findNextSibling = find_next_sibling
    findNextSiblings = find_next_siblings
    findPreviousSibling = find_previous_sibling
    findPreviousSiblings = find_previous_siblings

    def find_next(
        self,
        name: Any = None,
        attrs: Any = None,
        string: Any = None,
        **kwargs: Any,
    ) -> Any:
        results = self.find_all_next(name, attrs, string=string, limit=1, **kwargs)
        return results[0] if results else None

    def find_all_next(
        self,
        name: Any = None,
        attrs: Any = None,
        string: Any = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        return self._soup._filter_nodes(
            self.next_elements,
            name=name,
            attrs=attrs,
            string=string,
            limit=limit,
            kwargs=kwargs,
        )

    def find_previous(
        self,
        name: Any = None,
        attrs: Any = None,
        string: Any = None,
        **kwargs: Any,
    ) -> Any:
        results = self.find_all_previous(name, attrs, string=string, limit=1, **kwargs)
        return results[0] if results else None

    def find_all_previous(
        self,
        name: Any = None,
        attrs: Any = None,
        string: Any = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        return self._soup._filter_nodes(
            self.previous_elements,
            name=name,
            attrs=attrs,
            string=string,
            limit=limit,
            kwargs=kwargs,
        )

    findNext = find_next
    findAllNext = find_all_next
    findPrevious = find_previous
    findAllPrevious = find_all_previous

    # Historical Beautiful Soup navigation aliases.
    next = property(lambda self: self.next_element)
    previous = property(lambda self: self.previous_element)
    nextSibling = property(lambda self: self.next_sibling)
    previousSibling = property(lambda self: self.previous_sibling)
    nextGenerator = property(lambda self: self.next_elements)
    previousGenerator = property(lambda self: self.previous_elements)


class AttributeMap(MutableMapping[str, Any]):
    """Live mapping over an lxml element's HTML attributes."""

    def __init__(self, element: etree._Element):
        self._element = element

    def __getitem__(self, key: str) -> Any:
        raw_value = self._element.attrib[key]
        return attribute_value(key, raw_value)

    def __setitem__(self, key: str, value: Any) -> None:
        if isinstance(value, (list, tuple, set, frozenset)):
            serialized = " ".join(str(item) for item in value)
        elif value is None:
            serialized = ""
        else:
            serialized = str(value)
        self._element.set(key, serialized)

    def __delitem__(self, key: str) -> None:
        del self._element.attrib[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._element.attrib)

    def __len__(self) -> int:
        return len(self._element.attrib)

    def __repr__(self) -> str:
        return repr(dict(self.items()))

    def copy(self) -> dict[str, Any]:
        return dict(self.items())


class LxmlString(str, PageElement):
    """A text node with Beautiful Soup-style navigation metadata."""

    def __new__(
        cls,
        value: str,
        soup: "LxmlSoup",
        *,
        kind: str,
        anchor: etree._Element | None,
        parent_element: etree._Element | None,
    ) -> "LxmlString":
        instance = str.__new__(cls, value)
        instance._soup = soup
        instance._kind = kind
        instance._anchor = anchor
        instance._parent_element = parent_element
        return instance

    @property
    def parent(self) -> Any:
        if self._kind == "doctype":
            return self._soup
        if self._parent_element is None:
            return None
        return self._soup._wrap_element(self._parent_element)

    @property
    def string(self) -> "LxmlString":
        return self

    @property
    def text(self) -> TextValue:
        return TextValue(str(self))

    def get_text(self, separator: str = "", strip: bool = False, types: Any = None) -> str:
        del separator, types
        return str(self).strip() if strip else str(self)

    getText = get_text

    def extract(self) -> "LxmlString":
        self._soup._remove_string(self)
        return self

    def replace_with(self, replacement: Any) -> "LxmlString":
        self._soup._replace_string(self, replacement)
        return self


class LxmlComment(LxmlString):
    """An HTML comment node."""


class LxmlDoctype(LxmlString):
    """A document type declaration."""


class LxmlElement(PageElement, SearchMixin):
    """A lightweight, live wrapper around an lxml HTML element."""

    __slots__ = ("_element", "_soup")

    def __init__(self, element: etree._Element, soup: "LxmlSoup | None" = None):
        if soup is None:
            from .soup import LxmlSoup

            soup = LxmlSoup._from_root(element)
        self._element = element
        self._soup = soup

    @property
    def element(self) -> etree._Element:
        """The underlying lxml element, available as an explicit escape hatch."""

        return self._element

    def _search_root(self) -> etree._Element:
        return self._element

    def _iter_search_strings(self, recursive: bool) -> Iterator[LxmlString]:
        nodes = self.descendants if recursive else self.children
        for node in nodes:
            if isinstance(node, LxmlString):
                yield node

    @property
    def name(self) -> str:
        return str(self._element.tag)

    @name.setter
    def name(self, value: str) -> None:
        self._element.tag = value

    @property
    def attrs(self) -> AttributeMap:
        return AttributeMap(self._element)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self.attrs[key]
        except KeyError:
            return default

    def attribute(self, name: str) -> Any:
        """Backward-compatible alias for :meth:`get`."""

        return self.get(name)

    def get_attribute_list(self, key: str, default: Any = None) -> list[Any]:
        if not self.has_attr(key):
            return [] if default is None else [default]
        value = self.get(key, default)
        if isinstance(value, list):
            return value
        return [value]

    def has_attr(self, key: str) -> bool:
        return key in self._element.attrib

    def has_class(self, class_name: str) -> bool:
        return class_name in (self._element.get("class") or "").split()

    def __getitem__(self, key: str) -> Any:
        return self.attrs[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.attrs[key] = value

    def __delitem__(self, key: str) -> None:
        del self.attrs[key]

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.has_attr(key)

    @property
    def contents(self) -> list[Any]:
        return list(self._soup._element_contents(self._element))

    @property
    def children(self) -> Iterator[Any]:
        yield from self._soup._element_contents(self._element)

    @property
    def descendants(self) -> Iterator[Any]:
        yield from self._soup._element_descendants(self._element)

    @property
    def strings(self) -> Iterator[LxmlString]:
        for node in self.descendants:
            if type(node) is LxmlString and self._soup._string_is_visible_from(node, self):
                yield node

    @property
    def stripped_strings(self) -> Iterator[str]:
        for value in self.strings:
            stripped = value.strip()
            if stripped:
                yield stripped

    @property
    def string(self) -> LxmlString | None:
        contents = self.contents
        if len(contents) != 1:
            return None
        child = contents[0]
        if isinstance(child, LxmlElement):
            return child.string
        if isinstance(child, LxmlString):
            return child
        return None

    @string.setter
    def string(self, value: Any) -> None:
        self.clear()
        self._element.text = str(value)

    def get_text(self, separator: str = "", strip: bool = False, types: Any = None) -> str:
        values: Iterator[LxmlString] = self.strings
        if types is not None:
            allowed = types if isinstance(types, tuple) else (types,)
            values = (value for value in values if isinstance(value, allowed))
        if strip:
            return separator.join(value for item in values if (value := item.strip()))
        return separator.join(str(item) for item in values)

    getText = get_text

    @property
    def text(self) -> TextValue:
        return TextValue(self.get_text())

    @property
    def parent(self) -> Any:
        parent = self._element.getparent()
        if parent is None:
            return self._soup if self._element is self._soup.root else None
        return self._soup._wrap_element(parent)

    @property
    def sourceline(self) -> int | None:
        return self._element.sourceline

    def decode(self, *args: Any, **kwargs: Any) -> str:
        del args, kwargs
        return etree.tostring(
            self._element,
            encoding="unicode",
            method="html",
            with_tail=False,
        )

    def encode(self, encoding: str = "utf-8", *args: Any, **kwargs: Any) -> bytes:
        del args, kwargs
        return etree.tostring(
            self._element,
            encoding=encoding,
            method="html",
            with_tail=False,
        )

    def decode_contents(self, *args: Any, **kwargs: Any) -> str:
        del args, kwargs
        markup = self.decode()
        opening_end = markup.find(">")
        closing = f"</{self.name}>"
        if opening_end < 0 or not markup.endswith(closing):
            return ""
        return markup[opening_end + 1 : -len(closing)]

    def encode_contents(self, encoding: str = "utf-8", *args: Any, **kwargs: Any) -> bytes:
        return self.decode_contents(*args, **kwargs).encode(encoding)

    renderContents = encode_contents

    def prettify(self, encoding: str | None = None, formatter: Any = "minimal") -> str | bytes:
        del formatter
        return etree.tostring(
            self._element,
            encoding=encoding or "unicode",
            method="html",
            pretty_print=True,
            with_tail=False,
        )

    def to_html(self) -> str:
        return self.decode()

    def clear(self, decompose: bool = False) -> None:
        del decompose
        self._element.text = None
        for child in list(self._element):
            self._element.remove(child)

    def extract(self) -> "LxmlElement":
        self._soup._detach_element(self._element, preserve_tail=True)
        return self

    def decompose(self) -> None:
        self._soup._detach_element(self._element, preserve_tail=True)
        self._element.clear()

    def unwrap(self) -> "LxmlElement":
        self._soup._unwrap_element(self._element)
        return self

    replace_with_children = unwrap
    replaceWithChildren = unwrap

    def replace_with(self, replacement: Any) -> "LxmlElement":
        self._soup._replace_element(self._element, replacement)
        return self

    replaceWith = replace_with

    def append(self, item: Any) -> Any:
        return self._soup._append_to_element(self._element, item)

    def extend(self, items: Any) -> list[Any]:
        appended = []
        for item in items:
            appended.append(self.append(item))
        return appended

    def insert(self, position: int, item: Any) -> list[Any]:
        return [self._soup._insert_into_element(self._element, position, item)]

    def index(self, element: Any) -> int:
        key = self._soup._node_key(element)
        for position, child in enumerate(self.contents):
            if self._soup._node_key(child) == key:
                return position
        raise ValueError(f"{element!r} is not in this tag")

    def insert_before(self, *args: Any) -> list[Any]:
        parent = self.parent
        if not isinstance(parent, LxmlElement):
            raise ValueError("cannot insert before a detached or document-root element")
        position = parent.index(self)
        inserted = []
        for offset, item in enumerate(args):
            inserted.extend(parent.insert(position + offset, item))
        return inserted

    def insert_after(self, *args: Any) -> list[Any]:
        parent = self.parent
        if not isinstance(parent, LxmlElement):
            raise ValueError("cannot insert after a detached or document-root element")
        position = parent.index(self) + 1
        inserted = []
        for offset, item in enumerate(args):
            inserted.extend(parent.insert(position + offset, item))
        return inserted

    insertBefore = insert_before
    insertAfter = insert_after

    def wrap(self, wrapper: Any) -> "LxmlElement":
        return self._soup._wrap_element_with(self._element, wrapper)

    def __call__(self, *args: Any, **kwargs: Any) -> list[Any]:
        return self.find_all(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return self.find(name)

    def __str__(self) -> str:
        return self.decode()

    def __repr__(self) -> str:
        return self.decode()

    def __eq__(self, other: object) -> bool:
        return isinstance(other, LxmlElement) and self._element is other._element

    def __hash__(self) -> int:
        return hash(self._element)
