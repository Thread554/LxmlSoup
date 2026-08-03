# LxmlSoup

> Fast, focused HTML querying with a familiar API and the runtime profile of
> `lxml`.

LxmlSoup is a lightweight HTML query layer built directly on top of `lxml`.
It provides the Beautiful Soup methods most commonly used in scrapers—such as
`find()`, `find_all()`, `select()`, text extraction, and DOM navigation—while
also exposing native XPath and the underlying lxml tree.

LxmlSoup is designed for read-heavy scraping where pages are parsed, queried,
and discarded at high volume. It is intentionally smaller than Beautiful Soup
and is not a complete drop-in replacement for it.

## Installation

LxmlSoup requires Python 3.9 or newer.

```bash
python -m pip install LxmlSoup
```

## Quick start

```python
from LxmlSoup import LxmlSoup

html = """
<main id="catalog">
  <article class="product-card featured" data-id="1">
    <h2>Mechanical keyboard</h2>
    <span class="price">12 990 ₽</span>
    <a href="/products/1">Open</a>
  </article>
  <article class="product-card" data-id="2">
    <h2>Wireless mouse</h2>
    <span class="price">4 490 ₽</span>
    <a href="/products/2">Open</a>
  </article>
</main>
"""

document = LxmlSoup(html)

for card in document.find_all("article", class_="product-card", limit=5):
    title = card.find("h2").get_text(strip=True)
    price = card.select_one(".price").get_text(strip=True)
    href = card.find("a").get("href")
    print(title, price, href)
```

## Find, CSS, and XPath

The three query styles can be mixed on the same document:

```python
# Familiar tag and attribute filters
featured = document.find("article", class_="featured")
cards = document.find_all("article", attrs={"data-id": True}, limit=10)

# CSS selectors
prices = document.select("#catalog .product-card > .price")
first_link = document.select_one("article.product-card a")

# XPath, including safely bound variables
matches = document.xpath(
    "//article[@data-id=$product_id]",
    product_id="2",
)
hrefs = document.xpath("//article/a/@href")
```

Raw lxml objects remain available when a query needs lower-level control:

```python
raw_root = document.root
raw_element = featured.element
```

## Why LxmlSoup

Beautiful Soup builds a rich Python object model and supports multiple parser
backends. That flexibility is valuable, but it has a measurable cost when a
scraper only needs common searches and extraction.

LxmlSoup keeps one lxml tree and creates lightweight wrappers on demand. This
makes it useful when:

- many independent pages are parsed per worker;
- selectors and page structure are already known;
- CPU time and retained memory matter;
- a Beautiful Soup-like API is preferred over direct XPath everywhere;
- native XPath or raw lxml access is still required for advanced cases.

Use Beautiful Soup when you need its complete API, Soup Sieve selectors,
selectable parser backends, or its detailed mutation model. Use direct lxml
when maximum control and minimum abstraction are more important than API
familiarity.

## Performance

The repository includes a reproducible benchmark rather than relying on a
single advertised multiplier:

```bash
python -m benchmarks.benchmark
```

The reference results below were measured on arm64 macOS with Python 3.9.6,
LxmlSoup 2.0.0, lxml 6.1.1, and Beautiful Soup 4.15.0. The input is a generated
27,296-character storefront page containing 48 product cards. Timings are
medians of seven samples, with each sample calibrated to run for at least 0.2
seconds.

### Execution time

Lower is better. Direct lxml is included as the lower-overhead baseline; it
does not provide the same high-level API.

| Operation | Direct lxml | LxmlSoup | Beautiful Soup + lxml | LxmlSoup speed-up vs BS4 |
| --- | ---: | ---: | ---: | ---: |
| Parse document | 0.244 ms | 0.283 ms | 4.668 ms | 16.5× |
| Find first card | 0.5 µs | 1.6 µs | 5.0 µs | 3.1× |
| Find all 48 cards | 6.7 µs | 22.7 µs | 94.9 µs | 4.2× |
| Parse and extract all cards | 0.613 ms | 0.857 ms | 6.073 ms | 7.1× |

The end-to-end extraction case includes parsing every page, finding every card,
and reading its title, price, and link. It is usually the most representative
row for scraper workers.

### Retained-tree memory

Memory is measured in a fresh process for each parser. Each process imports its
parser and then retains 64 parsed copies of the same 48-card page. The tree
increase is the difference between peak RSS and the post-import baseline.

| Parser | Import baseline RSS | Peak RSS | Tree increase | Approx. per page |
| --- | ---: | ---: | ---: | ---: |
| Direct lxml | 17.2 MiB | 41.2 MiB | 24.0 MiB | 384.0 KiB |
| LxmlSoup | 17.9 MiB | 42.4 MiB | 24.4 MiB | 390.8 KiB |
| Beautiful Soup + lxml | 21.0 MiB | 68.8 MiB | 47.8 MiB | 764.2 KiB |

In this run, LxmlSoup used about **49% less incremental memory** than
Beautiful Soup and stayed close to direct lxml.

These figures are reference measurements, not universal guarantees. Results
change with Python and parser versions, hardware, document structure, selector
complexity, and object lifetime. They also exclude HTTP requests, proxy latency,
rate limiting, retries, JavaScript execution, and data storage—all of which can
dominate a production scraper.

## Supported API

### Searching

- `find()` and `find_all()` / `findAll()`
- tag names, iterables, regular expressions, callables, and `True`
- `attrs`, attribute keywords, `class_`, and presence filters
- `recursive`, `string` / legacy `text`, and `limit`
- `select()` and `select_one()` using cssselect-supported selectors
- `xpath()` with namespaces, extension functions, smart strings, and variables
- parent, sibling, and forward/backward document searches
- calling a document or element as shorthand for `find_all()`

### Extraction and navigation

- `name`, live `attrs`, `get()`, `has_attr()`, and `get_attribute_list()`
- `text`, `string`, `strings`, `stripped_strings`, and `get_text()`
- `contents`, `children`, `descendants`, `parent`, and `parents`
- sibling and document-order navigation, including text and comment nodes
- `decode()`, `encode()`, `prettify()`, and content serialization

### Common mutations

- attribute assignment and deletion
- `append()`, `extend()`, and `insert()`
- `extract()`, `decompose()`, `clear()`, and `unwrap()`
- `replace_with()`, `insert_before()`, `insert_after()`, and `wrap()`
- `new_tag()` and `new_string()`

## Parser options

```python
document = LxmlSoup(
    html_bytes,
    from_encoding="utf-8",
    recover=True,
    remove_comments=False,
    huge_tree=False,
    no_network=True,
    base_url="https://example.com/",
)
```

LxmlSoup accepts strings, bytes, bytearrays, and readable file-like objects.
Empty input produces an empty document. Parser diagnostics are exposed through
`document.errors`.

## Compatibility boundaries

LxmlSoup deliberately implements a focused subset of Beautiful Soup:

- parsing always uses lxml's HTML parser;
- CSS support follows `cssselect`, not Soup Sieve;
- `html.parser`, html5lib, custom builders, and custom element classes are not
  supported;
- `SoupStrainer` / `parse_only` and formatter plug-ins are not implemented;
- malformed-HTML recovery and serialization follow libxml2 and may differ from
  Beautiful Soup;
- adjacent strings can be coalesced because lxml stores element text and tails
  rather than a separate Python node for every string;
- unsupported constructor and selector arguments raise explicit errors.

The callable legacy form `element.text()` remains available, although
`element.text` or `element.get_text()` is preferred.

## Migrating from 1.x

The recommended top-level import remains unchanged:

```python
from LxmlSoup import LxmlSoup
document = LxmlSoup(html)
```

Additional migration notes:

- `findel()` remains an alias for `find_all()`;
- `parent`, `children`, `descendants`, and sibling navigation are properties or
  generators and are no longer called as methods;
- calling a document or element performs `find_all(...)`;
- `contents` and `descendants` include text and comment nodes;
- `get_text()` defaults to `separator=""` and `strip=False`.

See [CHANGELOG.md](CHANGELOG.md) for the complete list of changes.

## Development

```bash
git clone https://github.com/Thread554/LxmlSoup.git
cd LxmlSoup
python -m pip install -e '.[dev]'
pytest
python -m benchmarks.benchmark
```

The test suite includes differential checks against Beautiful Soup for the
documented compatibility subset.

## License and project status

LxmlSoup is distributed under the MIT License. Third-party dependency notices
are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

LxmlSoup is an independent project. It is not affiliated with or endorsed by
the lxml project, Beautiful Soup, or their maintainers.
