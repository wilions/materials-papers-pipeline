#!/usr/bin/env python3
"""
Fetch new/updated paper metadata from Crossref API for a given journal (by ISSN).
Appends only rows not already present in the existing CSV (deduped by DOI).

Usage:
    python3 fetch_crossref_update.py --issn 1359-6454 --output acta_materialia_papers.csv
    python3 fetch_crossref_update.py --issn 1359-6462 --output scripta_materialia_papers.csv --from-date 2026-01-01
    python3 fetch_crossref_update.py --issn 1005-0302 --output jmst_papers.csv

Journal ISSNs:
    Acta Materialia          1359-6454
    Scripta Materialia       1359-6462
    JMST                     1005-0302
    Materials Today          1369-7021
    Advanced Science         2198-3844
    Science Advances         2375-2548
    npj Advanced Manufact.   2731-0175
    Nature Communications    2041-1723
    PNAS                     0027-8424 (print) / 1091-6490 (online)
"""

import argparse
import csv
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HEADERS = {"User-Agent": "AcademiaFetcher/1.0 (mailto:research@imre.a-star.edu.sg)"}
CROSSREF_BASE = "https://api.crossref.org/works"


def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch_journal(issn, from_date=None, rows_per_page=1000):
    """
    Generator — yields one paper dict per Crossref item.
    Paginates via cursor until exhausted.
    """
    params = {
        "filter": f"issn:{issn}",
        "select": "DOI,title,author,published,volume,issue,page,article-number,type,subject,URL",
        "rows": rows_per_page,
        "cursor": "*",
    }
    if from_date:
        params["filter"] += f",from-update-date:{from_date}"

    page = 0
    total_results = None
    while True:
        url = CROSSREF_BASE + "?" + urllib.parse.urlencode(params)
        try:
            data = get_json(url)
        except Exception as e:
            print(f"  Crossref error (page {page}): {e}. Retrying in 5s...")
            time.sleep(5)
            continue

        msg = data.get("message", {})
        if total_results is None:
            total_results = msg.get("total-results", 0)
            print(f"  Total results from Crossref: {total_results:,}")

        items = msg.get("items", [])
        if not items:
            break

        for item in items:
            yield parse_item(item)

        next_cursor = msg.get("next-cursor")
        if not next_cursor or len(items) < rows_per_page:
            break

        params["cursor"] = next_cursor
        page += 1
        time.sleep(0.2)  # polite rate limiting


def parse_item(item):
    """Convert a Crossref work item to our CSV schema."""
    doi = item.get("DOI", "")

    title = ""
    titles = item.get("title", [])
    if titles:
        title = titles[0]

    authors = []
    for a in item.get("author", []):
        name = f"{a.get('given', '')} {a.get('family', '')}".strip()
        if name:
            authors.append(name)
    authors_str = "; ".join(authors)

    pub = item.get("published", {}) or item.get("published-print", {}) or item.get("published-online", {})
    date_parts = pub.get("date-parts", [[]])[0] if pub else []
    year = str(date_parts[0]) if len(date_parts) >= 1 else ""
    month = str(date_parts[1]) if len(date_parts) >= 2 else ""

    return {
        "doi": doi,
        "title": title,
        "authors": authors_str,
        "year": year,
        "month": month,
        "volume": item.get("volume", ""),
        "issue": item.get("issue", ""),
        "page": item.get("page", ""),
        "article_number": item.get("article-number", ""),
        "type": item.get("type", ""),
        "subject": "; ".join(item.get("subject", [])),
        "url": item.get("URL", f"https://doi.org/{doi}" if doi else ""),
    }


FIELDNAMES = ["doi", "title", "authors", "year", "month", "volume", "issue",
              "page", "article_number", "type", "subject", "url"]


def main():
    parser = argparse.ArgumentParser(description="Fetch/update journal papers from Crossref")
    parser.add_argument("--issn", required=True, help="Journal ISSN")
    parser.add_argument("--output", required=True, help="Output CSV path")
    parser.add_argument("--from-date", default=None,
                        help="Only fetch papers updated after this date (YYYY-MM-DD). "
                             "Defaults to 30 days before the latest entry in existing CSV.")
    args = parser.parse_args()

    out_path = Path(args.output)

    # Load existing DOIs to avoid duplicates
    existing_dois = set()
    if out_path.exists():
        with open(out_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("doi"):
                    existing_dois.add(row["doi"].lower())
        print(f"Existing records: {len(existing_dois):,} (in {out_path.name})")

        # Auto-detect from_date if not specified: 30 days before latest entry
        if args.from_date is None:
            years = []
            with open(out_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        y = int(row.get("year") or 0)
                        m = int(row.get("month") or 1)
                        if y > 2000:
                            years.append((y, m))
                    except Exception:
                        pass
            if years:
                latest_y, latest_m = max(years)
                latest = datetime(latest_y, latest_m, 1)
                from_dt = latest - timedelta(days=30)
                args.from_date = from_dt.strftime("%Y-%m-%d")
                print(f"Auto from-date: {args.from_date} (30 days before latest {latest_y}/{latest_m:02d})")
    else:
        print(f"New file: {out_path.name}")

    print(f"Fetching ISSN {args.issn} from Crossref (from-date: {args.from_date or 'all'})...")

    new_rows = []
    seen_in_fetch = set()
    for row in fetch_journal(args.issn, from_date=args.from_date):
        doi_key = row["doi"].lower()
        if doi_key in existing_dois or doi_key in seen_in_fetch:
            continue
        seen_in_fetch.add(doi_key)
        new_rows.append(row)

    print(f"New papers to add: {len(new_rows):,}")

    if not new_rows:
        print("Nothing to add — CSV is up to date.")
        return

    # Append (or create) the CSV
    mode = "a" if out_path.exists() else "w"
    with open(out_path, mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if mode == "w":
            w.writeheader()
        w.writerows(new_rows)

    print(f"Added {len(new_rows):,} new rows to {out_path}")


if __name__ == "__main__":
    main()
