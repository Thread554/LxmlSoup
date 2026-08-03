"""Reproducible speed and retained-tree memory benchmark."""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import timeit
from typing import Any, Callable

try:
    import resource
except ImportError:  # pragma: no cover - resource is unavailable on Windows
    resource = None


CARD = """
<article class="product-card catalog-item" data-product-id="{i}">
  <a class="product-card__link" href="/catalog/product-{i}">
    <picture><source srcset="/{i}.webp" type="image/webp">
    <img src="/{i}.jpg" alt="Product {i}" loading="lazy"></picture>
    <h3 class="product-card__title">Product {i} with a catalogue title</h3>
  </a>
  <div class="rating" data-rating="4.8">4.8 <span>128 reviews</span></div>
  <div class="prices"><span class="price">12 990</span><del>15 290</del></div>
  <button class="add-to-cart" data-product-id="{i}">Add to cart</button>
</article>
"""

ENGINE_LABELS = {
    "raw-lxml": "raw lxml",
    "lxmlsoup": "LxmlSoup",
    "beautifulsoup": "BeautifulSoup(lxml)",
}


def make_document(card_count: int) -> str:
    cards = "".join(CARD.format(i=index) for index in range(card_count))
    return f"<!doctype html><html><body><main>{cards}</main></body></html>"


def measure(
    function: Callable[[], Any],
    *,
    target: float,
    repeats: int,
) -> tuple[float, int]:
    timer = timeit.Timer(function)
    iterations = 1
    while timer.timeit(iterations) < target:
        iterations *= 2
    samples = []
    for _ in range(repeats):
        gc.collect()
        gc.enable()
        samples.append(timer.timeit(iterations) / iterations)
    return statistics.median(samples), iterations


def format_duration(seconds: float) -> str:
    if seconds < 0.001:
        return f"{seconds * 1_000_000:,.1f} us"
    return f"{seconds * 1_000:,.3f} ms"


def peak_rss_bytes() -> int | None:
    if resource is None:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == "darwin" else peak * 1024)


def memory_worker(engine: str, *, cards: int, copies: int) -> None:
    """Measure one parser in isolation and emit a machine-readable result."""

    document = make_document(cards)
    parser: Callable[[str], Any]
    if engine == "raw-lxml":
        from lxml import etree

        parser = etree.HTML
    elif engine == "lxmlsoup":
        from LxmlSoup import LxmlSoup

        parser = LxmlSoup
    elif engine == "beautifulsoup":
        from bs4 import BeautifulSoup

        parser = lambda markup: BeautifulSoup(markup, "lxml")
    else:  # pragma: no cover - argparse validates this
        raise ValueError(f"unknown engine: {engine}")

    gc.collect()
    baseline = peak_rss_bytes()
    started = time.process_time()
    trees = [parser(document) for _ in range(copies)]
    cpu_seconds = time.process_time() - started
    peak = peak_rss_bytes()
    if len(trees) != copies:  # Keep retained trees live through the measurement.
        raise AssertionError("memory worker did not retain every parsed tree")

    increase = None if baseline is None or peak is None else max(0, peak - baseline)
    print(
        json.dumps(
            {
                "engine": engine,
                "baseline_bytes": baseline,
                "peak_bytes": peak,
                "increase_bytes": increase,
                "per_document_bytes": None if increase is None else increase / copies,
                "cpu_seconds_per_document": cpu_seconds / copies,
            }
        )
    )


def isolated_memory_measurement(engine: str, *, cards: int, copies: int) -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        "-m",
        "benchmarks.benchmark",
        "--cards",
        str(cards),
        "--memory-copies",
        str(copies),
        "--memory-worker",
        engine,
    ]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def mib(value: int | float | None) -> str:
    return "n/a" if value is None else f"{value / (1024 * 1024):,.1f} MiB"


def kib(value: int | float | None) -> str:
    return "n/a" if value is None else f"{value / 1024:,.1f} KiB"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cards", type=int, default=48, help="cards per HTML document")
    parser.add_argument("--repeats", type=int, default=7, help="median sample count")
    parser.add_argument("--target", type=float, default=0.2, help="seconds per sample")
    parser.add_argument(
        "--memory-copies",
        type=int,
        default=64,
        help="parsed documents retained by each isolated memory worker",
    )
    parser.add_argument(
        "--skip-memory",
        action="store_true",
        help="skip isolated retained-tree memory measurements",
    )
    parser.add_argument(
        "--memory-worker",
        choices=tuple(ENGINE_LABELS),
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    if (
        args.cards <= 0
        or args.repeats <= 0
        or args.target <= 0
        or args.memory_copies <= 0
    ):
        parser.error("cards, repeats, target, and memory-copies must be positive")

    if args.memory_worker:
        memory_worker(args.memory_worker, cards=args.cards, copies=args.memory_copies)
        return

    import bs4
    from bs4 import BeautifulSoup
    import lxml
    from lxml import etree

    from LxmlSoup import LxmlSoup, __version__

    document = make_document(args.cards)
    lxmlsoup_tree = LxmlSoup(document)
    bs4_tree = BeautifulSoup(document, "lxml")
    raw_tree = etree.HTML(document)

    def extract_lxmlsoup() -> list[tuple[str, str, str | None]]:
        page = LxmlSoup(document)
        return [
            (
                card.find("h3").get_text(strip=True),
                card.find("span", class_="price").get_text(strip=True),
                card.find("a").get("href"),
            )
            for card in page.find_all("article", class_="product-card")
        ]

    def extract_bs4() -> list[tuple[str, str, str | None]]:
        soup = BeautifulSoup(document, "lxml")
        return [
            (
                card.find("h3").get_text(strip=True),
                card.find("span", class_="price").get_text(strip=True),
                card.find("a").get("href"),
            )
            for card in soup.find_all("article", class_="product-card")
        ]

    def extract_raw_lxml() -> list[tuple[str, str, str | None]]:
        root = etree.HTML(document)
        cards = root.xpath(
            "//article[contains(concat(' ', normalize-space(@class), ' '), "
            "' product-card ')]"
        )
        return [
            (
                card.find(".//h3").xpath("string()"),
                card.xpath(
                    "string(.//span[contains(concat(' ', normalize-space(@class), ' '), "
                    "' price ')])"
                ).strip(),
                card.find(".//a").get("href"),
            )
            for card in cards
        ]

    cases = {
        "parse / raw lxml": lambda: etree.HTML(document),
        "parse / LxmlSoup": lambda: LxmlSoup(document),
        "parse / BeautifulSoup(lxml)": lambda: BeautifulSoup(document, "lxml"),
        "first match / raw lxml": lambda: raw_tree.find(".//article"),
        "first match / LxmlSoup": lambda: lxmlsoup_tree.find("article"),
        "first match / BeautifulSoup": lambda: bs4_tree.find("article"),
        "all cards / raw lxml": lambda: raw_tree.xpath("//article"),
        "all cards / LxmlSoup": lambda: lxmlsoup_tree.find_all("article"),
        "all cards / BeautifulSoup": lambda: bs4_tree.find_all("article"),
        "parse + extract / raw lxml": extract_raw_lxml,
        "parse + extract / LxmlSoup": extract_lxmlsoup,
        "parse + extract / BeautifulSoup": extract_bs4,
    }

    print(f"Python {platform.python_version()} ({platform.system()} {platform.machine()})")
    print(
        f"LxmlSoup {__version__}; lxml {lxml.__version__}; "
        f"Beautiful Soup {bs4.__version__}"
    )
    print(f"Document: {args.cards} cards, {len(document):,} characters")
    print(f"Median of {args.repeats} samples; target >= {args.target:.2f}s per sample\n")
    for name, function in cases.items():
        duration, iterations = measure(
            function,
            target=args.target,
            repeats=args.repeats,
        )
        print(f"{name:38} {format_duration(duration):>12}  n={iterations}")

    if args.skip_memory:
        return

    print(
        f"\nIsolated retained-tree memory: {args.memory_copies} documents "
        f"x {args.cards} cards"
    )
    print(f"{'engine':24} {'baseline':>12} {'peak':>12} {'increase':>12} {'per doc':>12}")
    for engine, label in ENGINE_LABELS.items():
        result = isolated_memory_measurement(
            engine,
            cards=args.cards,
            copies=args.memory_copies,
        )
        print(
            f"{label:24} "
            f"{mib(result['baseline_bytes']):>12} "
            f"{mib(result['peak_bytes']):>12} "
            f"{mib(result['increase_bytes']):>12} "
            f"{kib(result['per_document_bytes']):>12}"
        )
    print("Memory values are isolated process peak RSS; per-document values are approximate.")


if __name__ == "__main__":
    main()
