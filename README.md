# Metal Trends — Asian Metal scraper + viewer

Scrapes the public daily **Change** and **30 / 90 / 180 / 360-day percentage moves** from [asianmetal.com](https://www.asianmetal.com/) twice a day, and renders them in a single-file HTML dashboard.

## What's in here

| File | Purpose |
|---|---|
| `scraper.py` | Hits every category page on asianmetal.com and appends to `prices.csv`. |
| `audit.py` | After each scrape, compares against `target_products.txt` and writes `coverage_report.md` showing what was captured vs what's missing. |
| `prices.csv` | Long-format data store. One row per (date, product). |
| `target_products.txt` | Catalog of ~590 products to verify the scrape against. Treated as a regression target, not as a scrape input. |
| `coverage_report.md` | Auto-generated each run. Lists missing items grouped by element. |
| `index.html` | The viewer. Open in a browser; reads `prices.csv` next to it. |
| `requirements.txt` | Two pip dependencies: `requests`, `beautifulsoup4`. |
| `.github/workflows/scrape.yml` | Runs `scraper.py` + `audit.py` at 12:45 and 22:38 IST and commits the results. |

## What's scraped

Live Low / Mid / High prices on asianmetal.com are subscriber-only. What's public — and what this captures — is the daily Change (absolute number) and the 30-day, 90-day, 180-day and 360-day percentage moves, for every product on every category page: Base Metals, Minor Metals, Ferroalloys, Rare Earths, Carbon Steel, Stainless & Special, Steel Raw Materials, Refractories. That's around **95 category pages** in total, and depending on the page anywhere from a handful to 30+ products each — typically 500–1000 rows per scrape.

## Running it manually

```bash
pip install -r requirements.txt
python scraper.py
```

The script takes 2–4 minutes per run (one HTTPS request per category page with a 1.5s delay between to stay polite). It writes to `prices.csv` in the same directory.

Each run **merges** into the existing CSV. If a row for today already exists for the same product, it's overwritten with the new values; otherwise it's appended. This matches asianmetal's intra-day revision behaviour — the second daily run picks up any prices revised after the midday snapshot.

## Running it on a schedule (GitHub Actions)

The included workflow handles this automatically once the repo is on GitHub:

1. Push this directory to a GitHub repo.
2. Repo settings → **Actions → General → Workflow permissions** → make sure **"Read and write permissions"** is enabled (needed so the action can commit the updated `prices.csv`).
3. **Actions** tab → enable workflows if prompted.

It will then run at:

- **12:45 IST** — captures the midday snapshot
- **22:38 IST** — re-checks the same day and overwrites any revisions

You can also click **Run workflow** on the *Scrape Asian Metal* page to trigger a run on demand.

## Viewing the data

Open `index.html` in a browser — it reads `prices.csv` from the same folder. If the CSV is missing (or you opened the HTML from `file://`, where browsers block sibling fetches), it falls back to a small embedded sample so the page is never blank — a "Sample data" pill in the header makes that explicit.

To host it: enable **GitHub Pages** on the repo and the viewer picks up new data automatically after every scheduled scrape.

## Notes & gotchas

- **Country flags** on asianmetal are CSS sprites identified by numeric IDs (`_128` for Malaysia, `_91` for Guinea, `_44` for China, etc.). The mapping in `scraper.py` covers ~25 common origins. New ones surface as empty `country` fields and can be added to `COUNTRY_BY_ID` as they show up.
- **Beryllium** is listed in the sidebar but isn't linked — likely no public feed. **Cold Heading Steel** appears under News/Marketplace navs but not the price-page sidebar. Both are excluded from the scrape list; add them to `MATERIALS` if public price pages appear in future.
- **Electrical Steel** is served at `/Silicon-Steel/` on asianmetal even though the display label is "Electrical Steel" — that quirk is already handled.
- The scraper exits non-zero only if *every* page failed. Partial failures (a few pages timing out) still write whatever was scraped and log the failed names — the next run retries them.
