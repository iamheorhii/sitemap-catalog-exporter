"""
Universal Sitemap Catalog Exporter
- Reads sitemap.xml (urlset or sitemapindex; follows child sitemaps)
- Filters product URLs by markers/keywords
- Visits each product page and extracts title, price, stock (best-effort)
- Exports to Excel
"""

from __future__ import annotations

import re
import sys
import time
import json
import argparse
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple, Dict, Set
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
import pandas as pd
from tqdm import tqdm

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (CatalogExporter/1.0; +https://github.com/)"
}

# Common stock phrases (best-effort; extend for your language/shops)
OUT_OF_STOCK_PHRASES = [
    "out of stock",
    "sold out",
    "not in stock",
    "currently unavailable",
    "niet op voorraad",
    "niet meer op voorraad",
    "uitverkocht",
    "niet leverbaar",
    "temporarily unavailable",
]
IN_STOCK_PHRASES = [
    "in stock",
    "op voorraad",
    "available",
    "add to cart",
    "add to basket",
]


@dataclass
class FilterConfig:
    product_marker: str = ""            # e.g. "/a-" or "/product/" or "/p/"
    include_keywords: List[str] = None  # e.g. ["frezen", "frees", "vhm-frezen"]
    exclude_keywords: List[str] = None  # e.g. ["blog", "news"]
    must_contain_any: List[str] = None  # if set, URL must contain at least one of these


def fetch_text(url: str, headers: dict, timeout: int = 30) -> str:
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


def extract_locs_from_xml(xml_text: str) -> List[str]:
    # Robust enough for most sitemaps without full XML parsing dependency.
    return re.findall(r"<loc>\s*(.*?)\s*</loc>", xml_text)


def is_sitemap_index(xml_text: str) -> bool:
    return "<sitemapindex" in xml_text.lower()


def normalize_url(u: str) -> str:
    return u.strip()


def crawl_sitemap_tree(
    sitemap_url: str,
    headers: dict,
    max_sitemaps: int = 500,
    max_urls: int = 500_000,
    polite_delay_s: float = 0.0,
) -> List[str]:
    """
    Returns ALL loc URLs from a sitemap, recursively following sitemapindex children.
    """
    to_visit = [sitemap_url]
    visited: Set[str] = set()
    all_urls: List[str] = []

    with tqdm(total=0, desc="Sitemaps", unit="sitemap") as pbar:
        while to_visit:
            sm = to_visit.pop()
            if sm in visited:
                continue
            visited.add(sm)
            if len(visited) > max_sitemaps:
                print(f"[WARN] Reached max_sitemaps={max_sitemaps}. Stopping sitemap crawl.", file=sys.stderr)
                break

            try:
                xml = fetch_text(sm, headers=headers)
            except Exception as e:
                print(f"[WARN] Failed to fetch sitemap: {sm} ({e})", file=sys.stderr)
                continue

            locs = [normalize_url(x) for x in extract_locs_from_xml(xml)]
            if not locs:
                continue

            if is_sitemap_index(xml):
                # locs here are other sitemap URLs
                for child in locs:
                    if child not in visited:
                        to_visit.append(child)
                pbar.total = len(visited) + len(to_visit)
                pbar.update(1)
            else:
                # locs here are page URLs
                all_urls.extend(locs)
                if len(all_urls) >= max_urls:
                    print(f"[WARN] Reached max_urls={max_urls}. Truncating.", file=sys.stderr)
                    all_urls = all_urls[:max_urls]
                    break
                pbar.total = len(visited) + len(to_visit)
                pbar.update(1)

            if polite_delay_s > 0:
                time.sleep(polite_delay_s)

    # Deduplicate while preserving order
    seen: Set[str] = set()
    deduped: List[str] = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


def url_passes_filters(url: str, fc: FilterConfig) -> bool:
    u = url.lower()

    if fc.product_marker:
        if fc.product_marker.lower() not in u:
            return False

    if fc.include_keywords:
        # If include_keywords set: require ANY include keyword
        if not any(k.lower() in u for k in fc.include_keywords):
            return False

    if fc.must_contain_any:
        if not any(k.lower() in u for k in fc.must_contain_any):
            return False

    if fc.exclude_keywords:
        if any(k.lower() in u for k in fc.exclude_keywords):
            return False

    return True


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def extract_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1:
        return clean_text(h1.get_text())
    if soup.title:
        return clean_text(soup.title.get_text())
    # og:title fallback
    og = soup.select_one('meta[property="og:title"]')
    if og and og.get("content"):
        return clean_text(og["content"])
    return ""


def extract_price(soup: BeautifulSoup) -> Optional[float]:
    # 1) schema.org price
    meta_price = soup.select_one('[itemprop="price"]')
    if meta_price:
        content = meta_price.get("content") or meta_price.get_text()
        if content:
            m = re.search(r"([0-9]+(?:[.,][0-9]{2})?)", content)
            if m:
                try:
                    return float(m.group(1).replace(",", "."))
                except:
                    pass

    # 2) meta property product:price:amount (OpenGraph)
    ogp = soup.select_one('meta[property="product:price:amount"]')
    if ogp and ogp.get("content"):
        try:
            return float(ogp["content"].replace(",", "."))
        except:
            pass

    # 3) visible €/$/£ price
    text = soup.get_text(" ", strip=True)
    m = re.search(r"(€|\$|£)\s*([0-9]+(?:[.,][0-9]{2})?)", text)
    if m:
        try:
            return float(m.group(2).replace(",", "."))
        except:
            pass

    return None


def extract_currency(soup: BeautifulSoup) -> str:
    # Best-effort: check currency meta
    meta = soup.select_one('[itemprop="priceCurrency"]')
    if meta:
        return clean_text(meta.get("content") or meta.get_text() or "")
    ogc = soup.select_one('meta[property="product:price:currency"]')
    if ogc and ogc.get("content"):
        return clean_text(ogc["content"])
    # fallback: detect common symbols in page text
    t = soup.get_text(" ", strip=True)
    if "€" in t:
        return "EUR"
    if "$" in t:
        return "USD"
    if "£" in t:
        return "GBP"
    return ""


def extract_stock_status(soup: BeautifulSoup) -> str:
    t = soup.get_text(" ", strip=True).lower()
    if any(p in t for p in OUT_OF_STOCK_PHRASES):
        return "out_of_stock"
    if any(p in t for p in IN_STOCK_PHRASES):
        return "in_stock"
    return ""


def guess_category_from_url(url: str) -> Tuple[str, str]:
    # purely from path segments; optional convenience
    path = urlparse(url).path.strip("/")
    parts = [p for p in path.split("/") if p]
    cat = parts[0] if len(parts) > 0 else ""
    sub = "/".join(parts[1:-1]) if len(parts) > 2 else (parts[1] if len(parts) > 1 else "")
    return cat, sub


def interactive_prompt() -> Tuple[str, FilterConfig, Dict[str, str], bool, float, int]:
    print("\n=== Universal Sitemap Catalog Exporter ===\n")

    print("How to find a sitemap URL:")
    print("  1) Try: https://example.com/sitemap.xml")
    print("  2) Or check: https://example.com/robots.txt (look for 'Sitemap: ...')")
    print("  3) Some sites use an index: sitemap_index.xml\n")

    sitemap_url = input("Enter sitemap URL (e.g. https://shop.com/sitemap.xml): ").strip()
    if not sitemap_url:
        raise SystemExit("No sitemap URL provided.")

    product_marker = input("Product URL marker (optional, e.g. /product/ or /a-). Press Enter to skip: ").strip()

    include = input("Include keywords (optional, comma-separated; URL must contain ANY). Example: frezen,frees. Enter to skip: ").strip()
    include_keywords = [x.strip() for x in include.split(",") if x.strip()] if include else []

    must_any = input("Must contain ANY of these keywords (optional, comma-separated). Enter to skip: ").strip()
    must_contain_any = [x.strip() for x in must_any.split(",") if x.strip()] if must_any else []

    exclude = input("Exclude keywords (optional, comma-separated). Example: blog,news,account. Enter to skip: ").strip()
    exclude_keywords = [x.strip() for x in exclude.split(",") if x.strip()] if exclude else []

    out_only = input("Keep ONLY in-stock products? (y/n, default y): ").strip().lower()
    in_stock_only = (out_only != "n")

    delay = input("Polite delay between product page requests in seconds (default 0.2): ").strip()
    polite_delay = float(delay) if delay else 0.2

    limit = input("Optional limit for number of product pages to fetch (Enter for no limit): ").strip()
    max_products = int(limit) if limit else 0

    fc = FilterConfig(
        product_marker=product_marker,
        include_keywords=include_keywords,
        exclude_keywords=exclude_keywords,
        must_contain_any=must_contain_any,
    )

    # Currency override (optional)
    currency_override = input("Force currency code in output? (e.g. EUR) Enter to auto-detect: ").strip().upper()
    meta = {"currency_override": currency_override}

    return sitemap_url, fc, meta, in_stock_only, polite_delay, max_products


def main():
    parser = argparse.ArgumentParser(description="Universal sitemap to Excel catalog exporter.")
    parser.add_argument("--non-interactive", action="store_true", help="Use CLI args instead of prompts (advanced).")
    args = parser.parse_args()

    headers = dict(DEFAULT_HEADERS)

    if args.non_interactive:
        raise SystemExit("Non-interactive mode not implemented in this snippet. Use interactive mode.")

    sitemap_url, fc, meta, in_stock_only, polite_delay, max_products = interactive_prompt()

    print("\nFetching sitemap tree (this can take a moment)…")
    all_urls = crawl_sitemap_tree(
        sitemap_url=sitemap_url,
        headers=headers,
        polite_delay_s=0.0,
    )
    print(f"Total URLs in sitemap(s): {len(all_urls)}")

    # Filter to product URLs
    filtered = [u for u in all_urls if url_passes_filters(u, fc)]
    print(f"URLs after filters: {len(filtered)}")

    if not filtered:
        print("\nNo URLs matched your filters.")
        print("Try relaxing filters (remove include keywords, remove product marker, etc.).")
        return

    if max_products and len(filtered) > max_products:
        filtered = filtered[:max_products]
        print(f"Truncated to first {max_products} URLs due to limit.")

    rows = []
    errors = 0

    for url in tqdm(filtered, desc="Fetching product pages", unit="page"):
        try:
            html = fetch_text(url, headers=headers)
            soup = BeautifulSoup(html, "lxml")

            title = extract_title(soup)
            price = extract_price(soup)
            currency = meta.get("currency_override") or extract_currency(soup)
            stock = extract_stock_status(soup)

            if in_stock_only and stock == "out_of_stock":
                time.sleep(polite_delay)
                continue

            cat, sub = guess_category_from_url(url)

            rows.append({
                "category": cat,
                "subcategory": sub,
                "title": title,
                "price": price,
                "currency": currency,
                "stock": stock,
                "url": url,
            })

            time.sleep(polite_delay)

        except Exception as e:
            errors += 1
            rows.append({
                "category": "",
                "subcategory": "",
                "title": "",
                "price": None,
                "currency": meta.get("currency_override") or "",
                "stock": "",
                "url": url,
                "error": str(e),
            })
            time.sleep(polite_delay)

    df = pd.DataFrame(rows)

    # Make output filename from domain
    domain = urlparse(sitemap_url).netloc.replace("www.", "")
    out_file = f"{domain}_catalog.xlsx"
    with pd.ExcelWriter(out_file, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="catalog")

    print("\nDone ✅")
    print(f"Excel saved: {out_file}")
    print(f"Rows written: {len(df)}")
    if errors:
        print(f"Warnings: {errors} pages had errors. Check the 'error' column if present.")


if __name__ == "__main__":
    main()