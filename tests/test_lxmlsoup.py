from __future__ import annotations

from io import BytesIO, StringIO
import re

from bs4 import BeautifulSoup
from lxml import etree
import pytest

from LxmlSoup import (
    FeatureNotFound,
    LxmlComment,
    LxmlDoctype,
    LxmlElement,
    LxmlSoup,
    LxmlSoupError,
    LxmlString,
    SelectorError,
    XPathError,
    __version__,
)


HTML = """<!doctype html>
<html>
<head><title>Catalog</title></head>
<body>
  <main id="catalog" data-kind="products">
    lead
    <!--catalog comment-->
    <article class="card featured" data-id="1" title='a"b'>
      <h2>First <em>product</em></h2>
      <a href="/1" rel="next nofollow">Open</a>
      <span class="price">10</span>
    </article>
    between
    <article class="card" data-id="2">
      <h2>Second product</h2>
      <a href="/2">Open</a>
      <span class="price">20</span>
    </article>
    <footer>End</footer>
  </main>
</body>
</html>"""


@pytest.fixture()
def document() -> LxmlSoup:
    return LxmlSoup(HTML)


@pytest.fixture()
def bs() -> BeautifulSoup:
    return BeautifulSoup(HTML, "lxml")


def element_signature(items):
    return [(item.name, item.get("data-id"), item.get_text(strip=True)) for item in items]


def test_public_exports():
    assert __version__ == "2.0.0"
    assert issubclass(FeatureNotFound, LxmlSoupError)


def test_public_types_live_under_the_package():
    assert LxmlSoup.__module__ == "LxmlSoup.soup"
    assert LxmlElement.__module__ == "LxmlSoup.nodes"


def test_empty_document_is_safe():
    document = LxmlSoup("")
    assert document.root is None
    assert document.contents == []
    assert document.find("p") is None
    assert document.find_all() == []
    assert document.select("p") == []
    assert document.get_text() == ""
    assert str(document) == ""


@pytest.mark.parametrize("source", [StringIO("<p>ok</p>"), BytesIO(b"<p>ok</p>")])
def test_file_like_and_bytes_input(source):
    document = LxmlSoup(source)
    assert document.p.text == "ok"


def test_unicode_xml_declaration_and_doctype_detection():
    document = LxmlSoup('<?xml version="1.0" encoding="utf-8"?><p>ok</p>')
    assert document.p.text == "ok"
    assert not str(document).startswith("<!DOCTYPE")

    script = LxmlSoup('<script>"<!DOCTYPE fake>"</script>')
    assert not str(script).startswith("<!DOCTYPE")


def test_doctype_and_document_tree(document):
    assert isinstance(document.contents[0], LxmlDoctype)
    assert str(document.contents[0]).lower() == "html"
    assert document.contents[0].parent is document
    assert document.contents[1].name == "html"
    assert str(document).startswith("<!DOCTYPE html>")


def test_parser_features_are_explicit():
    assert LxmlSoup("<p>x</p>", features="lxml").p.text == "x"
    with pytest.raises(FeatureNotFound):
        LxmlSoup("<p>x</p>", features="html.parser")
    with pytest.raises(FeatureNotFound):
        LxmlSoup("<p>x</p>", parse_only=object())
    with pytest.raises(TypeError):
        LxmlSoup("<p>x</p>", unknown_option=True)


@pytest.mark.parametrize(
    "query",
    [
        lambda tree: tree.find_all("article"),
        lambda tree: tree.find_all(["article", "footer"]),
        lambda tree: tree.find_all(re.compile("^art")),
        lambda tree: tree.find_all(lambda tag: tag.name in {"h2", "footer"}),
        lambda tree: tree.find_all("article", "featured"),
        lambda tree: tree.find_all("article", class_="card"),
        lambda tree: tree.find_all("article", class_="card featured"),
        lambda tree: tree.find_all(attrs={"data-id": ["2", "3"]}),
        lambda tree: tree.find_all(attrs={"data-id": re.compile("^[12]$")}),
        lambda tree: tree.find_all(href=True),
        lambda tree: tree.find_all(attrs={"href": None}),
        lambda tree: tree.find_all("article", limit=1),
        lambda tree: tree.main.find_all(recursive=False),
    ],
)
def test_find_all_matches_beautifulsoup_for_common_filters(document, bs, query):
    assert element_signature(query(document)) == element_signature(query(bs))


def test_attribute_callable_matches_multivalue_tokens(document, bs):
    predicate = lambda value: value == "featured"
    assert element_signature(document.find_all(class_=predicate)) == element_signature(
        bs.find_all(class_=predicate)
    )


def test_one_shot_iterable_filters_are_repeatable(document):
    names = (name for name in ("article", "footer"))
    identifiers = (value for value in ("1", "2"))
    assert [item.name for item in document.find_all(names)] == ["article", "article", "footer"]
    assert [item.get("data-id") for item in document.find_all(attrs={"data-id": identifiers})] == [
        "1",
        "2",
    ]


def test_combined_iterable_attributes_do_not_share_xpath_variables():
    document = LxmlSoup(
        '<i data-a="x" data-b="z"></i><i data-a="y" data-b="x"></i>'
    )
    found = document.find_all(attrs={"data-a": ["x", "y"], "data-b": "z"})
    assert [item.get("data-a") for item in found] == ["x"]


def test_string_filters_and_legacy_text_alias(document, bs):
    expected = [str(item) for item in bs.find_all(string=re.compile("product|End"))]
    assert [str(item) for item in document.find_all(string=re.compile("product|End"))] == expected
    assert [str(item) for item in document.find_all(text="End")] == ["End"]
    assert document.find("footer", string="End").name == "footer"
    with pytest.raises(TypeError):
        document.find_all(string=True, text=True)


def test_find_and_limit_stop_at_first_match(document):
    assert document.find("article").get("data-id") == "1"
    assert [item.get("data-id") for item in document.find_all("article", limit=1)] == ["1"]
    assert len(document.find_all("article", limit=0)) == 2
    with pytest.raises(ValueError):
        document.find_all(limit=-1)
    with pytest.raises(TypeError):
        document.find_all(limit="1")


def test_class_filter_uses_the_complete_multiclass_value():
    document = LxmlSoup('<div class="a"></div><div class="a b"></div>')
    assert len(document.find_all("div", class_="a b")) == 1


def test_xpath_values_are_not_interpolated(document):
    assert len(document.find_all("article", title='a"b')) == 1
    payload = '"] | //* | //*[@x="'
    assert document.find_all(attrs={"x": payload}) == []


def test_callable_and_invalid_tag_names_cannot_inject_xpath(document):
    assert [item.name for item in document.find_all(lambda tag: tag.name == "footer")] == ["footer"]
    assert document.find_all('article | //*') == []


def test_css_selection_matches_beautifulsoup(document, bs):
    selector = 'main > article.card[data-id] span.price'
    assert [item.text for item in document.select(selector)] == [item.text for item in bs.select(selector)]
    assert document.select_one("article.featured").get("data-id") == "1"
    assert len(document.select("article", limit=1)) == 1
    assert len(document.main.select("article")) == 2
    assert document.main.select("main") == []


def test_invalid_and_unsupported_css_is_wrapped(document):
    with pytest.raises(SelectorError):
        document.select("div[")
    with pytest.raises(TypeError):
        document.select("div", unsupported=True)


def test_xpath_elements_variables_and_relative_context(document):
    articles = document.xpath("//article[@data-id=$identifier]", identifier="2")
    assert len(articles) == 1
    assert isinstance(articles[0], LxmlElement)
    assert articles[0].get("data-id") == "2"
    assert [item.get("data-id") for item in document.main.xpath("./article")] == ["1", "2"]
    payload = "2' or @data-id='1"
    assert document.xpath("//article[@data-id=$identifier]", identifier=payload) == []


def test_xpath_text_attributes_comments_and_scalars(document):
    text_nodes = document.xpath("//article[1]/h2/text()")
    assert len(text_nodes) == 1
    assert isinstance(text_nodes[0], LxmlString)
    assert text_nodes[0].parent.name == "h2"
    assert str(text_nodes[0]).strip() == "First"

    assert document.xpath("//article/@data-id") == ["1", "2"]
    assert document.xpath("count(//article)") == 2.0
    assert document.xpath("boolean(//footer)") is True
    assert isinstance(document.xpath("//comment()")[0], LxmlComment)


def test_xpath_namespaces_plain_strings_and_errors():
    root = etree.fromstring('<x:root xmlns:x="urn:test"><x:item>ok</x:item></x:root>')
    document = LxmlElement(root)
    result = document.xpath(".//x:item", namespaces={"x": "urn:test"})
    assert len(result) == 1
    assert result[0].get_text() == "ok"

    plain = document.xpath("string(.//x:item)", namespaces={"x": "urn:test"})
    assert type(plain) is str
    text = document.xpath(
        ".//x:item/text()",
        namespaces={"x": "urn:test"},
        smart_strings=False,
    )
    assert text == ["ok"]
    assert type(text[0]) is str
    doubled = document.xpath(
        "double(21)",
        extensions={(None, "double"): lambda _context, value: value * 2},
    )
    assert doubled == 42.0
    with pytest.raises(XPathError):
        document.xpath("//*[")


def test_xpath_on_empty_document_is_safe():
    assert LxmlSoup("").xpath("//p") == []


def test_xpath_text_and_tail_nodes_are_live():
    document = LxmlSoup("<p>A<b>B</b>C</p>")
    text = document.xpath("//p/text()[1]")[0]
    tail = document.xpath("//b/following-sibling::text()[1]")[0]
    assert text.parent.name == "p"
    assert tail.parent.name == "p"
    text.replace_with("X")
    tail.replace_with("Y")
    assert str(document.p) == "<p>X<b>B</b>Y</p>"


def test_text_contract_matches_beautifulsoup(document, bs):
    assert document.main.get_text("|", strip=True) == bs.main.get_text("|", strip=True)
    assert list(document.main.stripped_strings) == list(bs.main.stripped_strings)
    inline = LxmlSoup("<p>First <em>product</em></p>")
    assert inline.p.get_text() == "First product"
    assert inline.p.text == "First product"
    assert inline.p.text() == "First product"  # 1.x compatibility


def test_embedded_code_text_matches_beautifulsoup_defaults():
    html = "<div>a<script>b</script><style>c</style><template>d</template><p>e</p></div>"
    document = LxmlSoup(html)
    bs = BeautifulSoup(html, "lxml")
    assert list(map(str, document.div.strings)) == list(map(str, bs.div.strings))
    assert document.div.get_text() == bs.div.get_text() == "ae"
    assert document.script.get_text() == bs.script.get_text() == "b"


def test_string_property_is_recursive_like_beautifulsoup(document):
    assert document.footer.string == "End"
    assert document.find("h2", string="Second product").string == "Second product"
    assert document.main.string is None


def test_contents_children_descendants_and_comments(document, bs):
    ours = document.main.contents
    theirs = bs.main.contents
    assert len(ours) == len(theirs)
    assert [type(item).__name__ for item in ours] == [
        "LxmlComment"
        if type(item).__name__ == "Comment"
        else ("LxmlElement" if type(item).__name__ == "Tag" else "LxmlString")
        for item in theirs
    ]
    assert isinstance(next(item for item in ours if isinstance(item, LxmlComment)), LxmlComment)
    assert list(document.main.children) == document.main.contents
    assert len(list(document.main.descendants)) == len(list(bs.main.descendants))
    assert all(not isinstance(item, LxmlComment) for item in document.main.strings)


def test_parent_and_ancestor_navigation(document):
    price = document.find("span", class_="price")
    assert price.parent.name == "article"
    assert [item.name for item in price.parents] == ["article", "main", "body", "html", "[document]"]
    assert price.find_parent("main").get("id") == "catalog"
    assert [item.name for item in price.find_parents(["article", "main"])] == ["article", "main"]


def test_sibling_navigation_includes_strings(document):
    first = document.find("article")
    assert isinstance(first.next_sibling, LxmlString)
    assert first.find_next_sibling("article").get("data-id") == "2"
    second = document.find("article", attrs={"data-id": "2"})
    assert second.find_previous_sibling("article").get("data-id") == "1"
    assert [item.get("data-id") for item in first.find_next_siblings("article")] == ["2"]


def test_document_order_navigation(document):
    first = document.find("article")
    assert first.find_next("h2").get_text(" ", strip=True) == "First product"
    assert first.find_next("footer").text == "End"
    footer = document.footer
    assert footer.find_previous("article").get("data-id") == "2"
    assert footer.previous_element is not None


def test_attribute_mapping_is_live_and_bs4_like(document):
    article = document.article
    assert article["class"] == ["card", "featured"]
    assert article.get_attribute_list("class") == ["card", "featured"]
    assert article.get_attribute_list("missing") == []
    assert article.get("missing", "fallback") == "fallback"
    assert article.has_attr("data-id")
    assert article.has_class("featured")
    article["class"] = ["card", "sale"]
    article["data-new"] = 42
    assert article.get("class") == ["card", "sale"]
    assert article.element.get("class") == "card sale"
    assert article.get("data-new") == "42"
    del article["data-new"]
    assert "data-new" not in article


def test_serialization_and_raw_escape_hatches(document):
    article = document.article
    assert str(article) == article.decode() == article.to_html()
    assert article.encode().decode() == article.decode()
    assert "<h2>" in article.decode_contents()
    assert article.element.tag == "article"
    assert document.root.tag == "html"
    assert "\n" in article.prettify()


def test_new_tag_and_new_string(document):
    tag = document.new_tag("strong", attrs={"class": ["notice"]}, string="Hello")
    assert tag.name == "strong"
    assert tag["class"] == ["notice"]
    assert tag.string == "Hello"
    assert str(document.new_string("text")) == "text"


def test_append_extend_and_insert():
    document = LxmlSoup("<div>A<span>B</span>C</div>")
    strong = document.new_tag("strong", string="D")
    assert document.div.append(strong) == strong
    assert len(document.div.extend(["E", document.new_tag("i", string="F")])) == 2
    assert [str(item) for item in document.div.insert(1, "X")] == ["X"]
    assert str(document.div) == "<div>AX<span>B</span>C<strong>D</strong>E<i>F</i></div>"


def test_extract_decompose_clear_and_unwrap():
    document = LxmlSoup("<div>A<span>B</span>C<em>D</em>E</div>")
    extracted = document.span.extract()
    assert str(extracted) == "<span>B</span>"
    assert str(document.div) == "<div>AC<em>D</em>E</div>"
    document.em.decompose()
    assert str(document.div) == "<div>ACE</div>"

    document = LxmlSoup("<div>A<span><b>B</b></span>C</div>")
    document.span.unwrap()
    assert str(document.div) == "<div>A<b>B</b>C</div>"
    document.div.clear()
    assert str(document.div) == "<div></div>"


def test_replace_insert_around_and_wrap():
    document = LxmlSoup("<div><b>B</b>C</div>")
    bold = document.b
    bold.insert_before("A")
    bold.insert_after("X")
    wrapper = document.new_tag("i", attrs={"class": "wrapper"})
    bold.wrap(wrapper)
    assert str(document.div) == '<div>A<i class="wrapper"><b>B</b></i>XC</div>'
    replacement = document.new_tag("strong", string="R")
    document.b.replace_with(replacement)
    assert str(document.div) == '<div>A<i class="wrapper"><strong>R</strong></i>XC</div>'
    document.div.contents[-1].replace_with("Z")
    assert str(document.div).endswith("Z</div>")


def test_moving_existing_elements_and_self_replacement_matches_bs4():
    document = LxmlSoup("<div><a>A</a><b>B</b><c>C</c></div>")
    old = document.b
    assert old.replace_with(document.a) == old
    assert str(document.div) == "<div><a>A</a><c>C</c></div>"
    link = document.a
    assert link.replace_with(link) == link
    assert str(document.div) == "<div><a>A</a><c>C</c></div>"


def test_extracting_document_root_detaches_it():
    document = LxmlSoup("<!doctype html><p>x</p>")
    root = document.html
    assert root.extract() == root
    assert root.parent is None
    assert document.root is None
    assert document.find("p") is None


def test_cyclic_mutations_fail_without_changing_the_tree():
    document = LxmlSoup("<div><span>x</span></div>")
    before = str(document)
    with pytest.raises(ValueError):
        document.span.append(document.div)
    assert str(document) == before

    with pytest.raises(ValueError):
        document.span.replace_with(document.div)
    assert str(document) == before


def test_malformed_html_is_recovered():
    document = LxmlSoup("<div><p>one<p>two")
    assert [item.text for item in document.find_all("p")] == ["one", "two"]
