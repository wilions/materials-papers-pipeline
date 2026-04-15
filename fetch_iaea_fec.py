#!/usr/bin/env python3
"""
Fetch all IAEA Fusion Energy Conference papers from INIS InvenioRDM API.

Total: ~8,689 records
Query: "Fusion Energy Conference" source:"IAEA"
API: https://inis.iaea.org/api/records

Usage:
    python3 fetch_iaea_fec.py --output papers/iaea_fec_papers.csv
"""

import argparse
import csv
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime

FIELDNAMES = ["inis_id", "title", "authors", "year", "description", "subject_category", "descriptors", "url"]

HEADERS = {
    "User-Agent": "AcademiaScraper/1.0 (mailto:research@example.com)",
    "Accept": "application/vnd.inveniordm.v1+json",
}

BASE_URL = "https://inis.iaea.org/api/records"
QUERY = '"Fusion Energy Conference" source:"IAEA"'
PAGE_SIZE = 100


def parse_record(rec):
    meta = rec.get("metadata", {})
    custom = rec.get("custom_fields", {})

    # Title
    title = meta.get("title", "")

    # Authors — creators list
    creators = meta.get("creators", [])
    author_parts = []
    for c in creators:
        po = c.get("person_or_org", {})
        name = po.get("name", "")
        if name:
            author_parts.append(name)
    authors = "; ".join(author_parts)

    # Year from publication_date (YYYY or YYYY-MM-DD)
    pub_date = meta.get("publication_date", "")
    year = pub_date[:4] if pub_date else ""

    # Description / abstract
    description = meta.get("description", "")
    if isinstance(description, list):
        description = " ".join(description)
    # Truncate very long descriptions for CSV readability
    if len(description) > 2000:
        description = description[:2000] + "..."

    # IAEA custom fields
    subject_category_raw = custom.get("iaea:subject_category", [])
    if isinstance(subject_category_raw, list):
        subject_category = "; ".join(
            item.get("title", {}).get("en", "") if isinstance(item, dict) else str(item)
            for item in subject_category_raw
        )
    else:
        subject_category = str(subject_category_raw)

    descriptors_raw = custom.get("iaea:descriptors_cai_text", "")
    if isinstance(descriptors_raw, list):
        descriptors = "; ".join(
            item.get("title", {}).get("en", "") if isinstance(item, dict) else str(item)
            for item in descriptors_raw
        )
    else:
        descriptors = str(descriptors_raw)

    # URL
    rec_id = rec.get("id", "")
    url = f"https://inis.iaea.org/records/{rec_id}" if rec_id else ""

    return {
        "inis_id": rec_id,
        "title": title,
        "authors": authors,
        "year": year,
        "description": description,
        "subject_category": subject_category,
        "descriptors": descriptors,
        "url": url,
    }


def fetch_all(output_file):
    total_written = 0
    page = 1

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting INIS FEC fetch → {output_file}")

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        while True:
            params = {
                "q": QUERY,
                "size": PAGE_SIZE,
                "page": page,
                "sort": "bestmatch",
            }
            url = BASE_URL + "?" + urllib.parse.urlencode(params)

            for attempt in range(3):
                try:
                    req = urllib.request.Request(url, headers=HEADERS)
                    with urllib.request.urlopen(req, timeout=30) as r:
                        data = json.loads(r.read().decode())
                    break
                except Exception as e:
                    print(f"  Retry {attempt + 1}: {e}")
                    time.sleep(5)
            else:
                print("  FATAL after 3 retries, stopping.")
                break

            hits = data.get("hits", {})
            total = hits.get("total", 0)
            if isinstance(total, dict):
                total = total.get("value", 0)

            records = hits.get("hits", [])
            if not records:
                break

            rows = [parse_record(r) for r in records]
            writer.writerows(rows)
            f.flush()
            total_written += len(rows)

            print(f"  Page {page}: {total_written}/{total}")

            if total_written >= total or len(records) < PAGE_SIZE:
                break

            page += 1
            time.sleep(0.3)  # polite delay

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Done: {total_written} records → {output_file}")
    return total_written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="papers/iaea_fec_papers.csv")
    args = parser.parse_args()

    fetch_all(args.output)


if __name__ == "__main__":
    main()
