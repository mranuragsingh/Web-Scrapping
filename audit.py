"""
Coverage audit. Compares the latest scrape in prices.csv against the
catalog in target_products.txt and writes coverage_report.md showing
which targets were captured and which are missing.

Run after scraper.py. Designed to be cheap (a few seconds) so it can
sit inside the same GitHub Action as the scrape.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
TARGETS_PATH = HERE / "target_products.txt"
CSV_PATH = HERE / "prices.csv"
REPORT_PATH = HERE / "coverage_report.md"

# Words that don't help disambiguate one product from another — units,
# currencies, formatting words. Stripped from both sides before matching
# so the comparison hinges on the chemical and grade tokens.
STOPWORDS = {
    "rmb", "usd", "eur", "rub", "inr", "myr", "vnd", "thb",
    "mt", "kg", "lb", "lbs", "gt", "mtu", "mtm", "dmtu", "dt", "wt", "kgs",
    "price", "data", "high", "low", "mid", "min", "max",
    "and", "or", "the", "in", "on", "at", "by", "of",
    "ex", "vat", "tc",
}

# Tokenize on alphanumerics. Keeps grade strings like "A356.2" or "Q235B"
# usefully intact (the dot/letter at the end stays attached).
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:\.[0-9]+)?")

MATCH_THRESHOLD = 0.45     # Jaccard score above which we call it a hit.


def tokens(s: str) -> set[str]:
    return {
        w.lower() for w in TOKEN_RE.findall(s or "")
        if w.lower() not in STOPWORDS and len(w) > 1
    }


def parse_target(line: str) -> tuple[str, str] | None:
    """
    Strip the category path and trailing -High/-Low/-Mid suffix, returning
    (element_group, product_description). element_group is the second
    segment (Al, FeCr, Rare Earth, etc.) used for grouping the report.
    """
    line = line.strip()
    if not line:
        return None
    line = re.sub(r"\s*-\s*(High|Low|Mid)\s*$", "", line)
    if "-Price Data-" not in line:
        return None
    path, product = line.split("-Price Data-", 1)
    path_parts = [p.strip() for p in path.split("-") if p.strip()]
    group = path_parts[1] if len(path_parts) >= 2 else (path_parts[0] if path_parts else "Other")
    return group, product.strip()


def main() -> None:
    if not TARGETS_PATH.exists():
        print("No target_products.txt — skipping audit.")
        return
    if not CSV_PATH.exists():
        print("No prices.csv — skipping audit.")
        return

    parsed = [parse_target(l) for l in TARGETS_PATH.read_text(encoding="utf-8").splitlines()]
    targets = [t for t in parsed if t]

    # Dedupe while preserving group association.
    seen = set()
    unique_targets: list[tuple[str, str]] = []
    for group, prod in targets:
        if prod not in seen:
            seen.add(prod)
            unique_targets.append((group, prod))

    with CSV_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        REPORT_PATH.write_text("# Coverage report\n\n_No data in prices.csv yet — run scraper.py first._\n")
        print("Empty CSV; wrote stub report.")
        return

    # Use the latest date in the CSV — we audit one snapshot at a time.
    latest = max(r["date"] for r in rows)
    today_rows = [r for r in rows if r["date"] == latest]
    indexed = [(r, tokens(f"{r.get('product','')} {r.get('spec','')}")) for r in today_rows]

    found: list[tuple[str, str, dict, float]] = []
    missing: list[tuple[str, str, float]] = []

    for group, target in unique_targets:
        ttoks = tokens(target)
        if not ttoks:
            continue
        best_score = 0.0
        best_row = None
        for row, rtoks in indexed:
            if not rtoks:
                continue
            inter = len(ttoks & rtoks)
            if inter == 0:
                continue
            union = len(ttoks | rtoks)
            score = inter / union
            if score > best_score:
                best_score = score
                best_row = row
        if best_score >= MATCH_THRESHOLD:
            found.append((group, target, best_row, best_score))
        else:
            missing.append((group, target, best_score))

    n_total = len(unique_targets)
    n_found = len(found)
    n_missing = len(missing)
    pct = (n_found / n_total * 100) if n_total else 0.0

    # Group missing items by element for easier review.
    by_group: dict[str, list[str]] = defaultdict(list)
    for group, target, _ in missing:
        by_group[group].append(target)

    lines: list[str] = []
    lines.append("# Coverage report")
    lines.append("")
    lines.append(f"Scrape date: **{latest}**")
    lines.append(f"Rows scraped today: **{len(today_rows)}**")
    lines.append(f"Catalog targets: **{n_total}**")
    lines.append(f"Found in scrape: **{n_found} ({pct:.0f}%)**")
    lines.append(f"Missing: **{n_missing}**")
    lines.append("")
    lines.append("Missing items typically fall into one of three buckets:")
    lines.append("")
    lines.append("1. **Subscriber-only products** — most likely. asianmetal hides "
                 "most non-China-warehouse and rare-spec rows behind login. Items "
                 "like *Lead Ingot In warehouse Shanghai*, *Bismuth Ingot Delivered "
                 "Europe*, or *Cobalt Metal In warehouse Baltimore* are not on the "
                 "public pages.")
    lines.append("2. **Spec drift** — asianmetal occasionally retires or renames a "
                 "spec (e.g. the catalog says *Aluminum Scrap Foundry 86%min* but "
                 "the live page now lists *Foundry 85%min*). The scrape captures "
                 "the current spec; the catalog still references the old one.")
    lines.append("3. **Pages the scraper hasn't been pointed at** — uncommon. Add "
                 "the slug to the `MATERIALS` list in `scraper.py` if you spot one.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Missing products by element")
    lines.append("")

    if not by_group:
        lines.append("_None — all catalog targets were found in the scrape._")
    else:
        for group in sorted(by_group):
            items = by_group[group]
            lines.append(f"### {group} ({len(items)})")
            lines.append("")
            for t in items:
                lines.append(f"- {t}")
            lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_PATH.name}: {n_found}/{n_total} found "
          f"({pct:.0f}%), {n_missing} missing")


if __name__ == "__main__":
    main()
