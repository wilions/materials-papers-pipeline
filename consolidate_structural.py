#!/usr/bin/env python3
"""
Consolidate all *_structural.csv files into all_structural_alloys.csv.
Deduplicates by DOI (case-insensitive). Rows without a DOI are included once.
"""

import csv
from pathlib import Path

OUTPUT = "all_structural_alloys.csv"
FIELDNAMES = ["doi", "title", "authors", "year", "month", "volume", "issue",
              "page", "article_number", "type", "subject", "url"]


def main():
    base = Path(__file__).parent
    structural_files = sorted(
        p for p in base.glob("*_structural.csv")
        if p.name != OUTPUT
    )

    if not structural_files:
        print("No *_structural.csv files found.")
        return

    seen_dois = set()
    all_rows = []

    for path in structural_files:
        count = 0
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    doi = (row.get("doi") or "").strip().lower()
                    key = doi if doi else f"__notitle__{row.get('title','').lower()}"
                    if key in seen_dois:
                        continue
                    seen_dois.add(key)
                    # Normalize to expected fieldnames
                    out = {fn: row.get(fn, "") for fn in FIELDNAMES}
                    all_rows.append(out)
                    count += 1
        except Exception as e:
            print(f"  WARNING: could not read {path.name}: {e}")
            continue
        print(f"  {path.name}: {count:,} rows added")

    out_path = base / OUTPUT
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nTotal: {len(all_rows):,} unique rows → {out_path}")


if __name__ == "__main__":
    main()
