from lxml import etree


class LxmlSoup:
    def __init__(self, html_content):
        self.root = etree.HTML(html_content)

    def findel(self, tag=None, attrs=None, **kwargs):
        attributes = {}
        if attrs:
            attributes.update(attrs)
        attributes.update(kwargs)
        xpath = self._build_xpath(tag, attributes)
        elements = self.root.xpath(xpath)
        return [LxmlElement(element) for element in elements]

    def find_all(self, tag=None, attrs=None, **kwargs):
        return self.findel(tag, attrs, **kwargs)

    def find(self, tag=None, attrs=None, **kwargs):
        elements = self.findel(tag, attrs, **kwargs)
        return elements[0] if elements else None

    def select(self, selector):
        elements = self.root.cssselect(selector)
        return [LxmlElement(element) for element in elements]

    def select_one(self, selector):
        elements = self.root.cssselect(selector)
        return LxmlElement(elements[0]) if elements else None

    def _build_xpath(self, tag=None, attrs=None):
        tag = tag if tag is not None else "*"
        xpath = "//" + tag
        if attrs:
            conditions = []
            for key, value in attrs.items():
                if key in ('class_', 'class'):
                    first_class = value.split()[0]
                    conditions.append(
                        f'contains(concat(" ", normalize-space(@class), " "), " {first_class} ")'
                    )
                else:
                    conditions.append(f'@{key}="{value}"')
            xpath += "[" + " and ".join(conditions) + "]"
        return xpath

    def text(self):
        return ''.join(self.root.xpath(".//text()")).strip()

    @property
    def contents(self):
        return [LxmlElement(child) for child in self.root]

    @property
    def descendants(self):
        return [LxmlElement(el) for el in self.root.iterdescendants()]

    def prettify(self):
        return etree.tostring(self.root, encoding='unicode', pretty_print=True)

    def get_text(self, separator=" ", strip=True):
        text = separator.join(self.root.itertext())
        return text.strip() if strip else text


class LxmlElement:
    def __init__(self, element):
        self.element = element

    def findel(self, tag=None, attrs=None, **kwargs):
        attributes = {}
        if attrs:
            attributes.update(attrs)
        attributes.update(kwargs)
        xpath = self._build_xpath(tag, attributes)
        elements = self.element.xpath(xpath)
        return [LxmlElement(element) for element in elements]

    def find_all(self, tag=None, attrs=None, **kwargs):
        return self.findel(tag, attrs, **kwargs)

    def find(self, tag=None, attrs=None, **kwargs):
        elements = self.findel(tag, attrs, **kwargs)
        return elements[0] if elements else None

    def select(self, selector):
        elements = self.element.cssselect(selector)
        return [LxmlElement(element) for element in elements]

    def select_one(self, selector):
        elements = self.element.cssselect(selector)
        return LxmlElement(elements[0]) if elements else None

    def _build_xpath(self, tag=None, attrs=None):
        tag = tag if tag is not None else "*"
        xpath = ".//" + tag
        if attrs:
            conditions = []
            for key, value in attrs.items():
                if key in ('class_', 'class'):
                    first_class = value.split()[0]
                    conditions.append(
                        f'contains(concat(" ", normalize-space(@class), " "), " {first_class} ")'
                    )
                else:
                    conditions.append(f'@{key}="{value}"')
            xpath += "[" + " and ".join(conditions) + "]"
        return xpath

    def text(self):
        return ''.join(self.element.xpath(".//text()")).strip()

    def get_text(self, separator=" ", strip=True):
        text = separator.join(self.element.itertext())
        return text.strip() if strip else text

    @property
    def stripped_strings(self):
        for s in self.element.itertext():
            stripped = s.strip()
            if stripped:
                yield stripped

    def prettify(self):
        return etree.tostring(self.element, encoding='unicode', pretty_print=True)

    def attribute(self, name):
        return self.element.get(name)

    def get(self, name, default=None):
        return self.element.get(name, default)

    def to_html(self):
        return etree.tostring(self.element, encoding='unicode')

    def __str__(self):
        return etree.tostring(self.element, encoding='unicode')

    def __repr__(self):
        return str(self)

    def __call__(self):
        return ''.join(self.element.itertext())

    def has_attr(self, name):
        return name in self.element.attrib

    def has_class(self, class_name):
        class_attr = self.element.get('class')
        if class_attr:
            return class_name in class_attr.split()
        return False

    def parent(self):
        parent_element = self.element.getparent()
        return LxmlElement(parent_element) if parent_element is not None else None

    def find_parent(self, tag=None, attrs=None, **kwargs):
        attributes = {}
        if attrs:
            attributes.update(attrs)
        attributes.update(kwargs)
        current = self.element.getparent()
        while current is not None:
            candidate = LxmlElement(current)
            if candidate._matches(tag, attributes):
                return candidate
            current = current.getparent()
        return None

    def find_parents(self, tag=None, attrs=None, **kwargs):
        attributes = {}
        if attrs:
            attributes.update(attrs)
        attributes.update(kwargs)
        results = []
        current = self.element.getparent()
        while current is not None:
            candidate = LxmlElement(current)
            if candidate._matches(tag, attributes):
                results.append(candidate)
            current = current.getparent()
        return results

    def _matches(self, tag, attrs):
        if tag and self.element.tag != tag:
            return False
        if attrs:
            for key, value in attrs.items():
                if key in ('class_', 'class'):
                    class_attr = self.element.get('class')
                    if not class_attr or value.split()[0] not in class_attr.split():
                        return False
                else:
                    if self.element.get(key) != value:
                        return False
        return True

    @property
    def contents(self):
        return [LxmlElement(child) for child in self.element]

    @property
    def descendants(self):
        return [LxmlElement(el) for el in self.element.iterdescendants()]

    def children(self):
        return self.contents

    def next_sibling(self):
        next_sibling_element = self.element.getnext()
        return LxmlElement(next_sibling_element) if next_sibling_element is not None else None

    def previous_sibling(self):
        previous_sibling_element = self.element.getprevious()
        return LxmlElement(previous_sibling_element) if previous_sibling_element is not None else None

    def next_siblings(self):
        elements = self.element.xpath("following-sibling::*")
        return [LxmlElement(element) for element in elements]

    def previous_siblings(self):
        elements = self.element.xpath("preceding-sibling::*")
        return [LxmlElement(element) for element in elements]
