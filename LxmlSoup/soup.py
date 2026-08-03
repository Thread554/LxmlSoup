"""Document parser and node factory for LxmlSoup 2.x."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import re
from typing import Any

from lxml import etree

from .exceptions import FeatureNotFound
from .filters import (
    element_matches,
    matches_string,
    normalize_attributes,
    normalize_name_filter,
)
from .nodes import (
    LxmlComment,
    LxmlDoctype,
    LxmlElement,
    LxmlString,
    SearchMixin,
    TextValue,
)


_DOCTYPE_RE = re.compile(r"^<!DOCTYPE\s+(.*?)\s*>$", re.IGNORECASE | re.DOTALL)
_DOCTYPE_SEARCH_RE = re.compile(
    r"^\ufeff?\s*(?:(?:<\?xml[^>]*\?>|<!--.*?-->)\s*)*<!DOCTYPE\s+(.*?)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_XML_DECLARATION_RE = re.compile(
    r"^\ufeff?\s*<\?xml[^>]*\?>",
    re.IGNORECASE,
)
_SUPPORTED_FEATURES = {"html", "lxml", "lxml-html", "fast-html"}
_SPECIAL_STRING_CONTAINERS = {"script", "style", "template"}


class LxmlSoup(SearchMixin):
    """Parse HTML and expose LxmlSoup's focused query API."""

    name = "[document]"

    def __init__(
        self,
        markup: Any = "",
        features: str | list[str] | tuple[str, ...] | None = None,
        builder: Any = None,
        parse_only: Any = None,
        from_encoding: str | None = None,
        exclude_encodings: Any = None,
        element_classes: Any = None,
        *,
        recover: bool = True,
        remove_comments: bool = False,
        huge_tree: bool = False,
        no_network: bool = True,
        base_url: str | None = None,
        parser: etree.HTMLParser | None = None,
        **kwargs: Any,
    ) -> None:
        if builder is not None:
            raise FeatureNotFound("custom Beautiful Soup builders are not supported")
        if parse_only is not None:
            raise FeatureNotFound("SoupStrainer/parse_only is not supported by the lxml backend")
        if exclude_encodings is not None:
            raise FeatureNotFound(
                "exclude_encodings is not supported; pass from_encoding explicitly"
            )
        if element_classes is not None:
            raise FeatureNotFound("custom element_classes are not supported")
        if kwargs:
            unsupported = ", ".join(sorted(kwargs))
            raise TypeError(f"unsupported LxmlSoup constructor arguments: {unsupported}")
        self._validate_features(features)

        if hasattr(markup, "read"):
            markup = markup.read()
        if markup is None:
            markup = ""
        if not isinstance(markup, (str, bytes, bytearray)):
            raise TypeError("markup must be str, bytes, bytearray, or a readable file-like object")
        if isinstance(markup, bytearray):
            markup = bytes(markup)

        self._soup = self
        self._root: etree._Element | None = None
        self._doctype_markup = ""
        self._doctype_value = ""
        self.original_encoding: str | None = None
        self.declared_html_encoding: str | None = None
        self.errors: tuple[Any, ...] = ()

        if markup == "" or markup == b"":
            return

        html_parser = parser or etree.HTMLParser(
            encoding=from_encoding,
            recover=recover,
            remove_comments=remove_comments,
            huge_tree=huge_tree,
            no_network=no_network,
        )
        parse_markup = (
            _XML_DECLARATION_RE.sub("", markup, count=1)
            if isinstance(markup, str)
            else markup
        )
        self._root = etree.fromstring(parse_markup, parser=html_parser, base_url=base_url)
        self.errors = tuple(html_parser.error_log)
        if self._root is None:
            return

        document_info = self._root.getroottree().docinfo
        self.original_encoding = document_info.encoding if isinstance(markup, bytes) else None
        self.declared_html_encoding = document_info.encoding
        searchable_markup = (
            markup.decode("ascii", errors="ignore")
            if isinstance(markup, bytes)
            else markup
        )
        doctype_match = _DOCTYPE_SEARCH_RE.search(searchable_markup)
        self._set_doctype(f"<!DOCTYPE {doctype_match.group(1)}>" if doctype_match else "")

    @classmethod
    def _from_root(cls, root: etree._Element) -> "LxmlSoup":
        instance = cls.__new__(cls)
        instance._soup = instance
        instance._root = root
        instance._doctype_markup = ""
        instance._doctype_value = ""
        instance.original_encoding = None
        instance.declared_html_encoding = None
        instance.errors = ()
        return instance

    @staticmethod
    def _validate_features(features: str | list[str] | tuple[str, ...] | None) -> None:
        if features is None:
            return
        requested = {features} if isinstance(features, str) else set(features)
        if not requested or not requested.issubset(_SUPPORTED_FEATURES):
            available = ", ".join(sorted(_SUPPORTED_FEATURES))
            raise FeatureNotFound(
                f"LxmlSoup only provides an lxml HTML parser; supported feature names: {available}"
            )

    def _set_doctype(self, markup: str | None) -> None:
        self._doctype_markup = markup or ""
        match = _DOCTYPE_RE.match(self._doctype_markup)
        self._doctype_value = match.group(1) if match else ""

    @property
    def root(self) -> etree._Element | None:
        """The raw lxml document element, kept for 1.x compatibility and escape hatches."""

        return self._root

    @property
    def parent(self) -> None:
        return None

    def _search_root(self) -> etree._Element | None:
        return self._root

    def _search_includes_context(self) -> bool:
        return True

    def _iter_search_strings(self, recursive: bool) -> Iterator[LxmlString]:
        nodes = self.descendants if recursive else self.children
        for node in nodes:
            if isinstance(node, LxmlString) and not isinstance(node, LxmlDoctype):
                yield node

    @property
    def contents(self) -> list[Any]:
        result: list[Any] = []
        if self._doctype_markup:
            result.append(
                LxmlDoctype(
                    self._doctype_value,
                    self,
                    kind="doctype",
                    anchor=None,
                    parent_element=None,
                )
            )
        if self._root is not None:
            result.append(self._wrap_element(self._root))
        return result

    @property
    def children(self) -> Iterator[Any]:
        yield from self.contents

    @property
    def descendants(self) -> Iterator[Any]:
        for child in self.contents:
            yield child
            if isinstance(child, LxmlElement):
                yield from child.descendants

    @property
    def strings(self) -> Iterator[LxmlString]:
        for node in self.descendants:
            if type(node) is LxmlString and self._string_is_visible_from(node, self):
                yield node

    @property
    def stripped_strings(self) -> Iterator[str]:
        for value in self.strings:
            stripped = value.strip()
            if stripped:
                yield stripped

    @property
    def string(self) -> LxmlString | None:
        non_doctype = [item for item in self.contents if not isinstance(item, LxmlDoctype)]
        if len(non_doctype) != 1:
            return None
        child = non_doctype[0]
        return child.string if isinstance(child, LxmlElement) else child

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

    def decode(self, *args: Any, **kwargs: Any) -> str:
        del args, kwargs
        if self._root is None:
            return ""
        body = etree.tostring(self._root, encoding="unicode", method="html", with_tail=False)
        return f"{self._doctype_markup}\n{body}" if self._doctype_markup else body

    def encode(self, encoding: str = "utf-8", *args: Any, **kwargs: Any) -> bytes:
        return self.decode(*args, **kwargs).encode(encoding)

    def decode_contents(self, *args: Any, **kwargs: Any) -> str:
        return self.decode(*args, **kwargs)

    def encode_contents(self, encoding: str = "utf-8", *args: Any, **kwargs: Any) -> bytes:
        return self.encode(encoding, *args, **kwargs)

    renderContents = encode_contents

    def prettify(self, encoding: str | None = None, formatter: Any = "minimal") -> str | bytes:
        del formatter
        if self._root is None:
            return b"" if encoding else ""
        body = etree.tostring(
            self._root,
            encoding=encoding or "unicode",
            method="html",
            pretty_print=True,
            with_tail=False,
        )
        if not self._doctype_markup:
            return body
        if encoding:
            return self._doctype_markup.encode(encoding) + b"\n" + body
        return self._doctype_markup + "\n" + body

    def new_tag(
        self,
        name: str,
        namespace: str | None = None,
        nsprefix: str | None = None,
        attrs: Mapping[str, Any] | None = None,
        sourceline: int | None = None,
        sourcepos: int | None = None,
        string: str | None = None,
        **kwargs: Any,
    ) -> LxmlElement:
        del nsprefix, sourceline, sourcepos
        if not isinstance(name, str) or not name:
            raise ValueError("tag name must be a non-empty string")
        qualified_name = f"{{{namespace}}}{name}" if namespace else name
        element = etree.Element(qualified_name)
        wrapped = LxmlElement(element, self)
        attributes = dict(attrs or {})
        attributes.update(kwargs)
        for key, value in attributes.items():
            wrapped.attrs[key] = value
        if string is not None:
            wrapped.string = string
        return wrapped

    def new_string(self, value: Any, subclass: type[LxmlString] | None = None) -> LxmlString:
        string_class = subclass or LxmlString
        if not issubclass(string_class, LxmlString):
            raise TypeError("subclass must inherit from LxmlString")
        return string_class(
            str(value),
            self,
            kind="detached",
            anchor=None,
            parent_element=None,
        )

    def clear(self, decompose: bool = False) -> None:
        del decompose
        self._root = None
        self._set_doctype("")

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

    def _wrap_element(self, element: etree._Element) -> Any:
        if isinstance(element, etree._Comment):
            return LxmlComment(
                element.text or "",
                self,
                kind="comment",
                anchor=element,
                parent_element=element.getparent(),
            )
        return LxmlElement(element, self)

    def _wrap_xpath_result(self, result: Any) -> Any:
        if isinstance(result, list):
            return [self._wrap_xpath_item(item) for item in result]
        return self._wrap_xpath_item(result)

    def _wrap_xpath_item(self, item: Any) -> Any:
        if isinstance(item, etree._Element):
            return self._wrap_element(item)
        if isinstance(item, etree._ElementUnicodeResult):
            if item.is_attribute:
                return str(item)
            anchor = item.getparent()
            if item.is_text and anchor is not None:
                return LxmlString(
                    str(item),
                    self,
                    kind="text",
                    anchor=anchor,
                    parent_element=anchor,
                )
            if item.is_tail and anchor is not None:
                return LxmlString(
                    str(item),
                    self,
                    kind="tail",
                    anchor=anchor,
                    parent_element=anchor.getparent(),
                )
            return str(item)
        return item

    def _element_contents(self, element: etree._Element) -> Iterator[Any]:
        if element.text:
            yield LxmlString(
                element.text,
                self,
                kind="text",
                anchor=element,
                parent_element=element,
            )
        for child in element:
            yield self._wrap_element(child)
            if child.tail:
                yield LxmlString(
                    child.tail,
                    self,
                    kind="tail",
                    anchor=child,
                    parent_element=element,
                )

    def _element_descendants(self, element: etree._Element) -> Iterator[Any]:
        for child in self._element_contents(element):
            yield child
            if isinstance(child, LxmlElement):
                yield from child.descendants

    @staticmethod
    def _node_key(node: Any) -> tuple[Any, ...]:
        if isinstance(node, LxmlElement):
            return ("element", id(node.element))
        if isinstance(node, LxmlString):
            if node._kind == "doctype":
                return ("doctype",)
            if node._anchor is not None:
                return (node._kind, id(node._anchor))
            return (node._kind, id(node))
        if isinstance(node, LxmlSoup):
            return ("document", id(node))
        return ("other", id(node))

    def _all_nodes(self) -> list[Any]:
        return list(self.descendants)

    def _relative_node(self, node: Any, *, offset: int) -> Any:
        nodes = self._all_nodes()
        key = self._node_key(node)
        for index, candidate in enumerate(nodes):
            if self._node_key(candidate) == key:
                target = index + offset
                return nodes[target] if 0 <= target < len(nodes) else None
        return None

    def _relative_nodes(self, node: Any, *, reverse: bool) -> Iterator[Any]:
        nodes = self._all_nodes()
        key = self._node_key(node)
        for index, candidate in enumerate(nodes):
            if self._node_key(candidate) != key:
                continue
            if reverse:
                yield from reversed(nodes[:index])
            else:
                yield from nodes[index + 1 :]
            return

    def _sibling_collection(self, node: Any) -> tuple[list[Any], int] | None:
        parent = getattr(node, "parent", None)
        if parent is None:
            return None
        siblings = parent.contents
        key = self._node_key(node)
        for index, candidate in enumerate(siblings):
            if self._node_key(candidate) == key:
                return siblings, index
        return None

    def _sibling(self, node: Any, *, offset: int) -> Any:
        collection = self._sibling_collection(node)
        if collection is None:
            return None
        siblings, index = collection
        target = index + offset
        return siblings[target] if 0 <= target < len(siblings) else None

    def _siblings(self, node: Any, *, reverse: bool) -> Iterator[Any]:
        collection = self._sibling_collection(node)
        if collection is None:
            return
        siblings, index = collection
        if reverse:
            yield from reversed(siblings[:index])
        else:
            yield from siblings[index + 1 :]

    def _filter_nodes(
        self,
        nodes: Iterator[Any],
        *,
        name: Any,
        attrs: Any,
        string: Any,
        limit: int | None,
        kwargs: dict[str, Any],
    ) -> list[Any]:
        if "text" in kwargs:
            if string is not None:
                raise TypeError("use either string= or text=, not both")
            string = kwargs.pop("text")
        normalized_limit = SearchMixin._normalize_limit(limit)
        name = normalize_name_filter(name)
        attributes = normalize_attributes(attrs, kwargs)
        string_only = name is None and not attributes and string is not None
        results: list[Any] = []
        for node in nodes:
            if string_only and isinstance(node, LxmlString):
                matched = matches_string(node, string)
            elif isinstance(node, LxmlElement):
                matched = element_matches(
                    node.element,
                    node,
                    name=name,
                    attrs=attributes,
                    string=string,
                )
            else:
                matched = False
            if matched:
                results.append(node)
                if normalized_limit is not None and len(results) >= normalized_limit:
                    break
        return results

    @staticmethod
    def _string_is_visible_from(node: LxmlString, owner: Any) -> bool:
        """Match Beautiful Soup's default exclusion of embedded code text."""

        current = node.parent
        while current is not None and current != owner:
            if (
                isinstance(current, LxmlElement)
                and current.name.lower() in _SPECIAL_STRING_CONTAINERS
            ):
                return False
            current = current.parent
        return True

    def _remove_string(self, node: LxmlString) -> None:
        if node._kind == "text" and node._anchor is not None:
            node._anchor.text = None
        elif node._kind == "tail" and node._anchor is not None:
            node._anchor.tail = None
        elif node._kind == "comment" and node._anchor is not None:
            self._detach_element(node._anchor, preserve_tail=True)
        elif node._kind == "doctype":
            self._set_doctype("")

    def _replace_string(self, node: LxmlString, replacement: Any) -> None:
        value = str(replacement)
        if node._kind == "text" and node._anchor is not None:
            node._anchor.text = value
        elif node._kind == "tail" and node._anchor is not None:
            node._anchor.tail = value
        elif node._kind == "comment" and node._anchor is not None:
            parent = node._anchor.getparent()
            if parent is None:
                return
            previous = node._anchor.getprevious()
            tail = node._anchor.tail or ""
            parent.remove(node._anchor)
            if previous is not None:
                previous.tail = (previous.tail or "") + value + tail
            else:
                parent.text = (parent.text or "") + value + tail
        elif node._kind == "doctype":
            self._doctype_value = value
            self._doctype_markup = f"<!DOCTYPE {value}>"

    @staticmethod
    def _coerce_raw_element(item: Any) -> etree._Element | None:
        if isinstance(item, LxmlElement):
            return item.element
        if isinstance(item, etree._Element):
            return item
        return None

    @staticmethod
    def _is_ancestor(ancestor: etree._Element, element: etree._Element) -> bool:
        return any(candidate is ancestor for candidate in element.iterancestors())

    def _detach_element(self, element: etree._Element, *, preserve_tail: bool) -> None:
        parent = element.getparent()
        if parent is None:
            if element is self._root:
                self._root = None
            return
        tail = element.tail or ""
        previous = element.getprevious()
        parent.remove(element)
        element.tail = None
        if preserve_tail and tail:
            if previous is not None:
                previous.tail = (previous.tail or "") + tail
            else:
                parent.text = (parent.text or "") + tail

    def _unwrap_element(self, element: etree._Element) -> None:
        parent = element.getparent()
        if parent is None:
            raise ValueError("cannot unwrap a detached or document-root element")
        index = parent.index(element)
        previous = element.getprevious()
        if element.text:
            if previous is not None:
                previous.tail = (previous.tail or "") + element.text
            else:
                parent.text = (parent.text or "") + element.text
        moved: list[etree._Element] = []
        for child in list(element):
            element.remove(child)
            parent.insert(index, child)
            index += 1
            moved.append(child)
        tail = element.tail or ""
        element.text = None
        element.tail = None
        parent.remove(element)
        if tail:
            if moved:
                moved[-1].tail = (moved[-1].tail or "") + tail
            elif previous is not None:
                previous.tail = (previous.tail or "") + tail
            else:
                parent.text = (parent.text or "") + tail

    def _replace_element(self, element: etree._Element, replacement: Any) -> None:
        parent = element.getparent()
        if parent is None:
            raise ValueError("cannot replace a detached or document-root element")
        raw_replacement = self._coerce_raw_element(replacement)
        if raw_replacement is None:
            previous = element.getprevious()
            value = str(replacement) + (element.tail or "")
            parent.remove(element)
            if previous is not None:
                previous.tail = (previous.tail or "") + value
            else:
                parent.text = (parent.text or "") + value
            return

        if raw_replacement is element:
            return
        if self._is_ancestor(raw_replacement, element):
            raise ValueError("cannot replace a tag with one of its parents")
        index = parent.index(element)
        replacement_parent = raw_replacement.getparent()
        if replacement_parent is parent and parent.index(raw_replacement) < index:
            index -= 1
        tail = element.tail
        self._detach_element(raw_replacement, preserve_tail=True)
        parent.remove(element)
        raw_replacement.tail = tail
        parent.insert(index, raw_replacement)

    def _wrap_element_with(self, element: etree._Element, wrapper: Any) -> LxmlElement:
        raw_wrapper = self._coerce_raw_element(wrapper)
        if raw_wrapper is None:
            raise TypeError("wrapper must be an LxmlElement or lxml element")
        parent = element.getparent()
        if parent is None:
            raise ValueError("cannot wrap a detached or document-root element")
        if raw_wrapper is element:
            raise ValueError("a tag cannot wrap itself")
        if self._is_ancestor(raw_wrapper, element):
            raise ValueError("cannot wrap a tag with one of its parents")
        index = parent.index(element)
        wrapper_parent = raw_wrapper.getparent()
        if wrapper_parent is parent and parent.index(raw_wrapper) < index:
            index -= 1
        tail = element.tail
        self._detach_element(raw_wrapper, preserve_tail=True)
        parent.remove(element)
        raw_wrapper.tail = tail
        parent.insert(index, raw_wrapper)
        element.tail = None
        raw_wrapper.append(element)
        return LxmlElement(raw_wrapper, self)

    def _attached_string(
        self,
        item: Any,
        value: str,
        *,
        kind: str,
        anchor: etree._Element,
        parent: etree._Element,
    ) -> LxmlString:
        if isinstance(item, LxmlString):
            item._soup = self
            item._kind = kind
            item._anchor = anchor
            item._parent_element = parent
            return item
        return LxmlString(
            value,
            self,
            kind=kind,
            anchor=anchor,
            parent_element=parent,
        )

    def _append_to_element(self, parent: etree._Element, item: Any) -> Any:
        raw_item = self._coerce_raw_element(item)
        if raw_item is None:
            value = str(item)
            if isinstance(item, LxmlString) and item.parent is not None:
                item.extract()
            if len(parent):
                anchor = parent[-1]
                anchor.tail = (anchor.tail or "") + value
                return self._attached_string(
                    item,
                    value,
                    kind="tail",
                    anchor=anchor,
                    parent=parent,
                )
            else:
                parent.text = (parent.text or "") + value
                return self._attached_string(
                    item,
                    value,
                    kind="text",
                    anchor=parent,
                    parent=parent,
                )
        if raw_item is parent or self._is_ancestor(raw_item, parent):
            raise ValueError("cannot append a tag to itself or one of its descendants")
        self._detach_element(raw_item, preserve_tail=True)
        raw_item.tail = None
        parent.append(raw_item)
        return self._wrap_element(raw_item)

    def _insert_into_element(self, parent: etree._Element, position: int, item: Any) -> Any:
        if not isinstance(position, int):
            raise TypeError("position must be an integer")
        contents = list(self._element_contents(parent))
        position = max(0, position + len(contents) if position < 0 else position)
        if position >= len(contents):
            return self._append_to_element(parent, item)

        target = contents[position]
        raw_item = self._coerce_raw_element(item)
        if raw_item is None:
            value = str(item)
            if isinstance(item, LxmlString) and item.parent is not None:
                item.extract()
            if isinstance(target, LxmlString):
                if target._kind == "text" and target._anchor is not None:
                    target._anchor.text = value + (target._anchor.text or "")
                    return self._attached_string(
                        item,
                        value,
                        kind="text",
                        anchor=target._anchor,
                        parent=parent,
                    )
                elif target._kind == "tail" and target._anchor is not None:
                    target._anchor.tail = value + (target._anchor.tail or "")
                    return self._attached_string(
                        item,
                        value,
                        kind="tail",
                        anchor=target._anchor,
                        parent=parent,
                    )
            elif isinstance(target, LxmlElement):
                previous = target.element.getprevious()
                if previous is not None:
                    previous.tail = (previous.tail or "") + value
                    return self._attached_string(
                        item,
                        value,
                        kind="tail",
                        anchor=previous,
                        parent=parent,
                    )
                else:
                    parent.text = (parent.text or "") + value
                    return self._attached_string(
                        item,
                        value,
                        kind="text",
                        anchor=parent,
                        parent=parent,
                    )
            return self.new_string(value)

        if raw_item is parent or self._is_ancestor(raw_item, parent):
            raise ValueError("cannot insert a tag into itself or one of its descendants")
        if isinstance(target, LxmlElement) and raw_item is target.element:
            return self._wrap_element(raw_item)
        self._detach_element(raw_item, preserve_tail=True)
        raw_item.tail = None
        if isinstance(target, LxmlElement):
            parent.insert(parent.index(target.element), raw_item)
        elif isinstance(target, LxmlString) and target._kind == "text":
            old_text = parent.text
            parent.text = None
            parent.insert(0, raw_item)
            raw_item.tail = old_text
        elif (
            isinstance(target, LxmlString)
            and target._kind == "tail"
            and target._anchor is not None
        ):
            old_tail = target._anchor.tail
            target._anchor.tail = None
            parent.insert(parent.index(target._anchor) + 1, raw_item)
            raw_item.tail = old_tail
        else:
            return self._append_to_element(parent, raw_item)
        return self._wrap_element(raw_item)
