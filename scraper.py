"""
Asian Metal scraper.

Fetches the public daily Change and 30/90/180/360-day percentage moves
for every product across every category page on asianmetal.com and
writes them to a long-format prices.csv. Live Low / Mid / High prices
on the site are subscriber-only and not captured.

Designed to run twice a day from a GitHub Action (12:45 and 22:38 IST).
When the same date is scraped twice, the second run overwrites the
first for any (date, product, spec) tuples — matching asianmetal's
intra-day revision behaviour.

Usage:
    pip install -r requirements.txt
    python scraper.py
"""

from __future__ import annotations

import csv
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ======================================================================
# Config
# ======================================================================

BASE_URL = "https://www.asianmetal.com"
CSV_PATH = Path(__file__).parent / "prices.csv"

# Identify the bot honestly. Change the URL if you fork the repo.
USER_AGENT = (
    "Mozilla/5.0 (compatible; MetalTrendsBot/1.0; "
    "+https://github.com/DikshantArora28/metal-prices-scraper)"
)

REQUEST_TIMEOUT = 30          # seconds per page
DELAY_BETWEEN_REQUESTS = 1.5  # polite spacing between fetches
MAX_RETRIES = 3
IST = timezone(timedelta(hours=5, minutes=30))

# Materials to scrape: (display_name, url_slug, category).
# Pulled directly from asianmetal.com's left product sidebar. URLs follow
# the /{slug}/ pattern. A handful of slugs differ from the display name
# and are noted inline.
MATERIALS: list[tuple[str, str, str]] = [
    # ---- Base Metals -------------------------------------------------
    ("Aluminum",          "Aluminum",          "Base Metals"),
    ("Copper",            "Copper",            "Base Metals"),
    ("Lead",              "Lead",              "Base Metals"),
    ("Nickel",            "Nickel",            "Base Metals"),
    ("Tin",               "Tin",               "Base Metals"),
    ("Zinc",              "Zinc",              "Base Metals"),

    # ---- Minor Metals  (Beryllium has no public page) ---------------
    ("Antimony",          "Antimony",          "Minor Metals"),
    ("Arsenic",           "Arsenic",           "Minor Metals"),
    ("Bismuth",           "Bismuth",           "Minor Metals"),
    ("Cadmium",           "Cadmium",           "Minor Metals"),
    ("Calcium",           "Calcium",           "Minor Metals"),
    ("Chromium",          "Chromium",          "Minor Metals"),
    ("Cobalt",            "Cobalt",            "Minor Metals"),
    ("Gallium",           "Gallium",           "Minor Metals"),
    ("Germanium",         "Germanium",         "Minor Metals"),
    ("Indium",            "Indium",            "Minor Metals"),
    ("Lithium",           "Lithium",           "Minor Metals"),
    ("Magnesium",         "Magnesium",         "Minor Metals"),
    ("Manganese",         "Manganese",         "Minor Metals"),
    ("Mercury",           "Mercury",           "Minor Metals"),
    ("Molybdenum",        "Molybdenum",        "Minor Metals"),
    ("Niobium",           "Niobium",           "Minor Metals"),
    ("Rhenium",           "Rhenium",           "Minor Metals"),
    ("Selenium",          "Selenium",          "Minor Metals"),
    ("Silicon",           "Silicon",           "Minor Metals"),
    ("Strontium",         "Strontium",         "Minor Metals"),
    ("Tantalum",          "Tantalum",          "Minor Metals"),
    ("Tellurium",         "Tellurium",         "Minor Metals"),
    ("Titanium",          "Titanium",          "Minor Metals"),
    ("Tungsten",          "Tungsten",          "Minor Metals"),
    ("Vanadium",          "Vanadium",          "Minor Metals"),
    ("Zirconium",         "Zirconium",         "Minor Metals"),

    # ---- Ferroalloys ------------------------------------------------
    ("Ferroboron",        "Ferroboron",        "Ferroalloys"),
    ("Ferrochrome",       "Ferrochrome",       "Ferroalloys"),
    ("Ferromanganese",    "Ferromanganese",    "Ferroalloys"),
    ("Ferromolybdenum",   "Ferromolybdenum",   "Ferroalloys"),
    ("Ferronickel",       "Ferronickel",       "Ferroalloys"),
    ("Ferroniobium",      "Ferroniobium",      "Ferroalloys"),
    ("Ferrophosphorus",   "Ferrophosphorus",   "Ferroalloys"),
    ("Ferrosilicon",      "Ferrosilicon",      "Ferroalloys"),
    ("Ferrotitanium",     "Ferrotitanium",     "Ferroalloys"),
    ("Ferrotungsten",     "Ferrotungsten",     "Ferroalloys"),
    ("Ferrovanadium",     "Ferrovanadium",     "Ferroalloys"),
    ("Silicomanganese",   "Silicomanganese",   "Ferroalloys"),
    ("Chromium Silicon",  "Chromium-Silicon",  "Ferroalloys"),
    ("Calcium Silicon",   "Calcium-Silicon",   "Ferroalloys"),
    ("Chrome Ore",        "Chrome-Ore",        "Ferroalloys"),
    ("Manganese Ore",     "Manganese-Ore",     "Ferroalloys"),

    # ---- Rare Earths ------------------------------------------------
    ("Cerium",            "Cerium",            "Rare Earths"),
    ("Dysprosium",        "Dysprosium",        "Rare Earths"),
    ("Erbium",            "Erbium",            "Rare Earths"),
    ("Europium",          "Europium",          "Rare Earths"),
    ("Gadolinium",        "Gadolinium",        "Rare Earths"),
    ("Holmium",           "Holmium",           "Rare Earths"),
    ("Lanthanum",         "Lanthanum",         "Rare Earths"),
    ("Lutetium",          "Lutetium",          "Rare Earths"),
    ("Magnets",           "Magnets",           "Rare Earths"),
    ("Neodymium",         "Neodymium",         "Rare Earths"),
    ("Praseodymium",      "Praseodymium",      "Rare Earths"),
    ("Promethium",        "Promethium",        "Rare Earths"),
    ("Samarium",          "Samarium",          "Rare Earths"),
    ("Scandium",          "Scandium",          "Rare Earths"),
    ("Terbium",           "Terbium",           "Rare Earths"),
    ("Thulium",           "Thulium",           "Rare Earths"),
    ("Ytterbium",         "Ytterbium",         "Rare Earths"),
    ("Yttrium",           "Yttrium",           "Rare Earths"),

    # ---- Carbon Steel -----------------------------------------------
    ("Wire Rod",          "Wire-Rod",          "Carbon Steel"),
    ("Rebar",             "Rebar",             "Carbon Steel"),
    ("Sections",          "Sections",          "Carbon Steel"),
    ("Pipe",              "Pipe",              "Carbon Steel"),
    ("Hot Rolled Coil",   "Hot-Rolled",        "Carbon Steel"),
    ("Cold Rolled Coil",  "Cold-Rolled",       "Carbon Steel"),
    ("Plate",             "Plate",             "Carbon Steel"),
    ("Coated",            "Coated",            "Carbon Steel"),
    ("Strip",             "Strip",             "Carbon Steel"),

    # ---- Stainless & Special ----------------------------------------
    ("Stainless Bar",     "Stainless-Bar",     "Stainless & Special"),
    ("Stainless Coil",    "Stainless-Sheet",   "Stainless & Special"),
    ("Stainless Pipe",    "Stainless-Pipe",    "Stainless & Special"),
    ("Stainless Scrap",   "Stainless-Scrap",   "Stainless & Special"),
    ("Bearing Steel",     "Bearing-Steel",     "Stainless & Special"),
    ("Cold Heading Steel","Cold-Heading-Steel","Stainless & Special"),
    ("Gear Steel",        "Gear-Steel",        "Stainless & Special"),
    # NB: asianmetal serves Electrical Steel at /Silicon-Steel/.
    ("Electrical Steel",  "Silicon-Steel",     "Stainless & Special"),
    ("Structural Steel",  "Structural-Steel",  "Stainless & Special"),

    # ---- Steel Raw Materials ----------------------------------------
    ("Coal",              "Coal",              "Steel Raw Materials"),
    ("Coke",              "Coke",              "Steel Raw Materials"),
    ("Iron Ore",          "Iron-Ore",          "Steel Raw Materials"),
    ("Iron",              "Iron",              "Steel Raw Materials"),
    ("Steel Billet",      "Steel-Billet",      "Steel Raw Materials"),
    ("Steel Scrap",       "Steel-Scrap",       "Steel Raw Materials"),

    # ---- Refractories -----------------------------------------------
    ("Carbon",            "Carbon",            "Refractories"),
    ("Graphite",          "Graphite",          "Refractories"),
    ("Calcined Bauxite",  "Calcined-Bauxite",  "Refractories"),
    ("Fused Alumina",     "Fused-Alumina",     "Refractories"),
    ("Magnesia",          "Magnesia",          "Refractories"),
    ("Silicon Carbide",   "Silicon-Carbide",   "Refractories"),
]

# Flag CSS class `_<id>` → country name. Asian Metal uses the same numeric
# IDs in its country navs (couId=44 = China, couId=225 = US, etc.) so the
# sprite class number matches the country ID directly. Unknown IDs land as
# an empty `country` field — the viewer renders that gracefully.
COUNTRY_BY_ID: dict[str, str] = {
    "14":  "Australia",
    "28":  "Bosnia and Herzegovina",
    "36":  "Brazil",
    "44":  "China",
    "64":  "Egypt",
    "77":  "France",
    "83":  "Greece",
    "86":  "Germany",
    "91":  "Guinea",
    "98":  "Iceland",
    "99":  "India",
    "101": "Indonesia",
    "106": "Italy",
    "108": "Japan",
    "128": "Malaysia",
    "149": "Netherlands",
    "160": "Norway",
    "177": "Russia",
    "199": "South Korea",
    "200": "Spain",
    "207": "Switzerland",
    "217": "Turkey",
    "223": "United Arab Emirates",
    "224": "United Kingdom",
    "225": "United States",
}

CSV_FIELDS = [
    "date", "category", "product", "spec", "country",
    "change", "d30", "d90", "d180", "d360",
]


# ======================================================================
# Scraping
# ======================================================================

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    })
    return s


def fetch(session: requests.Session, url: str) -> str:
    """GET with exponential backoff on transient failures."""
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            last_err = e
            wait = 2 ** attempt
            print(f"  retry {attempt}/{MAX_RETRIES} after {wait}s: {e}",
                  file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"giving up on {url}: {last_err}")


_CLEAN_NUM_RE = re.compile(r"[+%\s]")

def _clean_num(s: str) -> str:
    """Strip + / % / whitespace; keep the minus sign so Number() parses."""
    return _CLEAN_NUM_RE.sub("", s or "")


def parse_page(html: str, category: str) -> list[dict]:
    """
    Parse the price table on a category page. Returns one row per product.
    Returns an empty list if the page has no price block (e.g. paywall
    moved, layout changed) — caller logs the empty result.
    """
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("#showpricecn")
    if not container:
        return []

    today = datetime.now(IST).strftime("%Y-%m-%d")
    rows: list[dict] = []

    ul_class_re = re.compile(r"price[Ll]ist(on|off)")

    for ul in container.find_all("ul", class_=ul_class_re):
        item_li = ul.find("li", class_="listitemam")
        if not item_li:
            continue

        spanitem = item_li.find("span", class_="spanitem")
        spanspec = item_li.find("span", class_="spanspec")
        if not spanitem:
            continue

        # Country flag — sprite class like "jack _128".
        flag = spanitem.find("span", class_="jack")
        country = ""
        if flag:
            for c in flag.get("class", []):
                if c.startswith("_") and c[1:].isdigit():
                    country = COUNTRY_BY_ID.get(c[1:], "")
                    break

        product = re.sub(r"\s+", " ", spanitem.get_text(strip=True)).strip()
        spec = (re.sub(r"\s+", " ", spanspec.get_text(strip=True)).strip()
                if spanspec else "")
        if not product:
            continue

        def cell(cls: str) -> str:
            li = ul.find("li", class_=cls)
            return _clean_num(li.get_text(strip=True)) if li else ""

        rows.append({
            "date": today,
            "category": category,
            "product": product,
            "spec": spec,
            "country": country,
            "change": cell("listlatest"),
            "d30":    cell("list30"),
            "d90":    cell("list90"),
            "d180":   cell("list180"),
            "d360":   cell("list360"),
        })

    return rows


# ======================================================================
# CSV merge
# ======================================================================

def merge_into_csv(path: Path, new_rows: list[dict]) -> tuple[int, int]:
    """
    Read existing CSV, overwrite rows that share (date, product, spec) with
    the newly-scraped values (intra-day revisions), append everything else,
    sort and write back. Returns (added, updated) counts.
    """
    existing: list[dict] = []
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as f:
            existing = list(csv.DictReader(f))

    index = {(r["date"], r["product"], r["spec"]): i
             for i, r in enumerate(existing)}
    added = updated = 0

    for row in new_rows:
        key = (row["date"], row["product"], row["spec"])
        if key in index:
            existing[index[key]] = row
            updated += 1
        else:
            index[key] = len(existing)
            existing.append(row)
            added += 1

    existing.sort(key=lambda r: (r["date"], r["category"],
                                  r["product"], r["spec"]))

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(existing)

    return added, updated


# ======================================================================
# Main
# ======================================================================

def main() -> None:
    session = make_session()
    all_rows: list[dict] = []
    failed: list[tuple[str, str]] = []
    empty: list[str] = []
    started = datetime.now(IST)

    total = len(MATERIALS)
    for i, (name, slug, category) in enumerate(MATERIALS, 1):
        url = f"{BASE_URL}/{slug}/"
        print(f"[{i:>3}/{total}] {category:<22} {name:<22} {url}")
        try:
            html = fetch(session, url)
            rows = parse_page(html, category)
            print(f"           → {len(rows)} products")
            if not rows:
                empty.append(name)
            all_rows.extend(rows)
        except Exception as e:
            print(f"           ✗ FAILED: {e}", file=sys.stderr)
            failed.append((name, str(e)))

        if i < total:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    if not all_rows:
        print("No rows scraped; aborting before touching CSV.",
              file=sys.stderr)
        sys.exit(1)

    added, updated = merge_into_csv(CSV_PATH, all_rows)
    elapsed = (datetime.now(IST) - started).total_seconds()

    print()
    print(f"Done in {elapsed:.0f}s — {len(all_rows)} rows from "
          f"{total - len(failed)}/{total} pages "
          f"({added} new, {updated} updated)")
    if empty:
        print(f"Empty pages ({len(empty)}): {', '.join(empty)}")
    if failed:
        print(f"Failed pages ({len(failed)}):")
        for name, err in failed:
            print(f"  - {name}: {err}")
        # Don't exit non-zero just for a few failed pages — partial data
        # is still useful, and the next run will retry. Exit non-zero
        # only if EVERY page failed (handled above by all_rows check).


if __name__ == "__main__":
    main()
