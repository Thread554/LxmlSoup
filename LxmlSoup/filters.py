"""Beautiful Soup-style filters and safe XPath candidate generation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from typing import Any

from lxml import etree


_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_MULTI_VALUE_ATTRIBUTES = {
    "class",
    "rel",
    "rev",
    "accept-charset",
    "headers",
    "accesskey",
}


@dataclass(frozen=True)
class XPathPlan:
    expression: str
    variables: dict[str, Any]
    exact: bool


def normalize_attributes(attrs: Any, kwargs: Mapping[str, Any]) -> dict[str, Any]:
    """Merge Beautiful Soup's ``attrs`` argument with attribute keywords."""

    if attrs is None:
        result: dict[str, Any] = {}
    elif isinstance(attrs, Mapping):
        result = {str(key): value for key, value in attrs.items()}
    else:
        # Beautiful Soup treats the second positional string/list as a class filter.
        result = {"class": attrs}

    for key, value in kwargs.items():
        result["class" if key == "class_" else key] = value
    for key, value in result.items():
        if _is_filter_iterable(value):
            result[key] = tuple(value)
    return result


def normalize_name_filter(name: Any) -> Any:
    """Materialize one-shot iterables so candidate matching is repeatable."""

    return tuple(name) if _is_filter_iterable(name) else name


def attribute_value(name: str, raw_value: str | None) -> Any:
    """Expose HTML multi-value attributes in Beautiful Soup's list-like form."""

    if raw_value is None:
        return None
    if name.lower() in _MULTI_VALUE_ATTRIBUTES:
        return raw_value.split()
    return raw_value


def _is_regex(value: Any) -> bool:
    return callable(getattr(value, "search", None))


def _is_filter_iterable(value: Any) -> bool:
    return isinstance(value, Iterable) and not isinstance(
        value, (str, bytes, bytearray, Mapping)
    )


def _as_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def matches_name(tag_name: str, criterion: Any, wrapper: Any) -> bool:
    if criterion is None or criterion is True:
        return True
    if criterion is False:
        return False
    if isinstance(criterion, (str, bytes)):
        return tag_name == _as_text(criterion)
    if _is_regex(criterion):
        return criterion.search(tag_name) is not None
    if callable(criterion):
        return bool(criterion(wrapper))
    if _is_filter_iterable(criterion):
        return any(matches_name(tag_name, item, wrapper) for item in criterion)
    return False


def matches_string(value: Any, criterion: Any) -> bool:
    if criterion is None:
        return True
    if criterion is True:
        return value is not None
    if criterion is False:
        return value is None
    if value is None:
        return False
    text = str(value)
    if isinstance(criterion, (str, bytes)):
        return text == _as_text(criterion)
    if _is_regex(criterion):
        return criterion.search(text) is not None
    if callable(criterion):
        return bool(criterion(value))
    if _is_filter_iterable(criterion):
        return any(matches_string(value, item) for item in criterion)
    return False


def matches_attribute(raw_value: str | None, criterion: Any, *, name: str) -> bool:
    if criterion is True:
        return raw_value is not None
    if criterion is False or criterion is None:
        return raw_value is None
    if _is_filter_iterable(criterion):
        return any(matches_attribute(raw_value, item, name=name) for item in criterion)
    if raw_value is None:
        return False

    is_multi = name.lower() in _MULTI_VALUE_ATTRIBUTES
    tokens = raw_value.split() if is_multi else [raw_value]

    if isinstance(criterion, (str, bytes)):
        expected = _as_text(criterion)
        if is_multi:
            if any(character.isspace() for character in expected):
                return " ".join(tokens) == " ".join(expected.split())
            return expected in tokens
        return raw_value == expected
    if _is_regex(criterion):
        return any(criterion.search(candidate) is not None for candidate in (*tokens, raw_value))
    if callable(criterion):
        candidates: tuple[Any, ...] = (*tokens, raw_value) if is_multi else (raw_value,)
        return any(bool(criterion(candidate)) for candidate in candidates)
    return False


def element_matches(
    element: etree._Element,
    wrapper: Any,
    *,
    name: Any,
    attrs: Mapping[str, Any],
    string: Any,
) -> bool:
    if not isinstance(element.tag, str):
        return False
    if not matches_name(element.tag, name, wrapper):
        return False
    for attr_name, criterion in attrs.items():
        if not matches_attribute(element.get(attr_name), criterion, name=attr_name):
            return False
    if string is not None and not matches_string(wrapper.string, string):
        return False
    return True


def _simple_xpath_filter(
    attr_name: str,
    criterion: Any,
    index: str,
) -> tuple[str | None, dict[str, Any], bool]:
    if not _NAME_RE.fullmatch(attr_name):
        return None, {}, False

    attribute = f"@{attr_name}"
    if criterion is True:
        return attribute, {}, True
    if criterion is False or criterion is None:
        return f"not({attribute})", {}, True

    if _is_filter_iterable(criterion):
        parts: list[str] = []
        variables: dict[str, Any] = {}
        exact = True
        for child_index, child in enumerate(criterion):
            part, child_vars, child_exact = _simple_xpath_filter(
                attr_name, child, f"{index}_{child_index}"
            )
            if part is not None:
                parts.append(f"({part})")
                variables.update(child_vars)
            exact = exact and child_exact
        return (" or ".join(parts) if parts else None), variables, exact and bool(parts)

    if not isinstance(criterion, (str, bytes)):
        return None, {}, False

    expected = _as_text(criterion)
    variable_name = f"value_{index}"
    variables = {
        variable_name: (
            " ".join(expected.split())
            if attr_name.lower() in _MULTI_VALUE_ATTRIBUTES
            else expected
        )
    }

    if attr_name.lower() in _MULTI_VALUE_ATTRIBUTES:
        if any(character.isspace() for character in expected):
            return f"normalize-space({attribute}) = ${variable_name}", variables, True
        return (
            f"contains(concat(' ', normalize-space({attribute}), ' '), "
            f"concat(' ', ${variable_name}, ' '))",
            variables,
            True,
        )
    return f"{attribute} = ${variable_name}", variables, True


def build_xpath_plan(
    *,
    name: Any,
    attrs: Mapping[str, Any],
    recursive: bool,
    include_context: bool,
    string: Any,
    limit: int | None,
) -> XPathPlan:
    """Build a safe XPath that narrows candidates without interpolating values."""

    exact = string is None
    variables: dict[str, Any] = {}
    conditions: list[str] = []
    node_test = "*"

    if isinstance(name, bytes):
        name = name.decode("utf-8", errors="replace")
    if isinstance(name, str) and _NAME_RE.fullmatch(name):
        node_test = name
    elif name is None or name is True:
        pass
    elif _is_filter_iterable(name):
        name_items = tuple(name)
        names = [_as_text(item) for item in name_items if isinstance(item, (str, bytes))]
        if (
            names
            and len(names) == len(name_items)
            and all(_NAME_RE.fullmatch(item) for item in names)
        ):
            conditions.append(" or ".join(f"self::{item}" for item in names))
        else:
            exact = False
    else:
        exact = False

    for index, (attr_name, criterion) in enumerate(attrs.items()):
        condition, attr_variables, attr_exact = _simple_xpath_filter(
            attr_name, criterion, str(index)
        )
        if condition:
            conditions.append(condition)
            variables.update(attr_variables)
        exact = exact and attr_exact

    predicate = f"[{' and '.join(f'({item})' for item in conditions)}]" if conditions else ""
    if include_context:
        axis = "descendant-or-self::" if recursive else "self::"
    else:
        axis = ".//" if recursive else "./"
    expression = f"{axis}{node_test}{predicate}"

    if exact and limit is not None and limit > 0:
        expression = f"({expression})[position() <= $result_limit]"
        variables["result_limit"] = limit

    return XPathPlan(expression=expression, variables=variables, exact=exact)
