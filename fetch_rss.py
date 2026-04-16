#!/usr/bin/env python3
"""
Fetch new paper metadata from a journal RSS feed.
Appends only rows not already present in the existing CSV (deduped by DOI).
Writes newly added rows to --new-output (overwritten each run).

Usage:
    python3 fetch_rss.py \\
        --rss https://rss.sciencedirect.com/publication/science/13596454 \\
        --output acta_materialia_papers.csv \\
        --new-output acta_materialia_new.csv

    # With title filter (general journals):
    python3 fetch_rss.py \\
        --rss https://www.pnas.org/rss/current.xml \\
        --output pnas_papers.csv \\
        --new-output pnas_new.csv \\
        --filter-structural
"""

import argparse
import csv
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


FIELDNAMES = ["doi", "title", "authors", "year", "month", "volume", "issue",
              "page", "article_number", "type", "subject", "url"]

HEADERS = {"User-Agent": "AcademiaFetcher/1.0 (mailto:research@imre.a-star.edu.sg)"}

# Structural alloy title filter — applied to general/multidisciplinary journals
STRUCTURAL_ALLOY_PATTERN = (
    r"\b(?:alloy|alloys|steel|steels|aluminum|aluminium|titanium|nickel.based|"
    r"ni.based|superalloy|superalloys|magnesium|copper|tungsten|chromium|"
    r"molybdenum|zirconium|niobium|vanadium|maraging|duplex|high.entropy|HEA|"
    r"multi.principal|intermetallic|intermetallics|stainless|Inconel|IN718|IN625|"
    r"Ti.6Al.4V|TC4|CoCrFeNi|CoCrNi|ODS|tensile|yield strength|ductility|"
    r"toughness|hardness|fatigue|fracture|creep|corrosion|deformation|"
    r"plasticity|strengthening|high.strength|lightweight|martensitic|martensite|"
    r"bainite|austenite|ferrite|pearlite|dislocation|precipitation.hardening|"
    r"age.hardening|grain.boundary|grain refinement|phase transformation|"
    r"hot rolling|cold rolling|forging|quench|anneal|weld|additive manufacturing|"
    r"LPBF|SLM|DED|powder metallurgy|sintering|aerospace|automotive|nuclear)\b"
)


def fetch_feed(rss_url: str) -> bytes:
    req = urllib.request.Request(rss_url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_rss(xml_data: bytes, title_filter: str = None):
    """Parse RSS/Atom feed bytes, yield paper dicts. Applies title_filter if set."""
    root = ET.fromstring(xml_data)

    # Support both RSS 2.0 <item> and Atom <entry>
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    for item in items:
        row = _parse_item(item)
        if not row["title"]:
            continue
        if title_filter and not re.search(title_filter, row["title"], re.IGNORECASE):
            continue
        yield row


def _parse_item(item: ET.Element) -> dict:
    """Extract paper fields from one RSS <item> element."""

    def _text(*tags):
        """Return first non-empty text found among tag variations."""
        ns_uris = [
            None,
            "http://purl.org/dc/elements/1.1/",
            "http://prismstandard.org/namespaces/basic/2.0/",
            "http://www.w3.org/2005/Atom",
        ]
        for tag in tags:
            for ns in ns_uris:
                el = item.find(f"{{{ns}}}{tag}") if ns else item.find(tag)
                if el is not None and el.text:
                    return el.text.strip()
        return ""

    # DOI — try dc:identifier, prism:doi, then extract from link
    doi = ""
    for val in [_text("identifier"), _text("doi")]:
        if val.startswith("10."):
            doi = val
            break
        if "doi.org/" in val:
            doi = val.split("doi.org/")[-1].strip()
            break

    link = _text("link", "guid")
    # Atom feeds use self-closing <link href="..."/> — .text is always None
    atom_link_el = item.find("{http://www.w3.org/2005/Atom}link")
    if not link and atom_link_el is not None:
        link = atom_link_el.get("href", "")
    if not doi and "doi.org/" in link:
        doi = link.split("doi.org/")[-1].strip()

    # Date — parse from pubDate or dc:date
    year, month = "", ""
    pub_date = _text("pubDate", "date", "updated", "published")
    if pub_date:
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
                    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(pub_date.strip(), fmt)
                year, month = str(dt.year), str(dt.month)
                break
            except ValueError:
                pass
        if not year:
            m = re.search(r"\b(20\d{2})\b", pub_date)
            if m:
                year = m.group(1)

    # Atom <author> wraps name in a <name> child element — .text on <author> is whitespace
    authors = _text("creator", "author")
    if not authors:
        atom_author = item.find("{http://www.w3.org/2005/Atom}author")
        if atom_author is not None:
            name_el = atom_author.find("{http://www.w3.org/2005/Atom}name")
            if name_el is not None and name_el.text:
                authors = name_el.text.strip()

    return {
        "doi": doi,
        "title": _text("title"),
        "authors": authors,
        "year": year,
        "month": month,
        "volume": _text("volume"),
        "issue": _text("number", "issue"),
        "page": _text("startingPage", "page"),
        "article_number": "",
        "type": "journal-article",
        "subject": _text("subject"),
        "url": link or (f"https://doi.org/{doi}" if doi else ""),
    }


def run(rss_url: str, output: Path, new_output: Path = None, title_filter: str = None):
    """Core logic — separated from CLI for testability."""
    out_path = Path(output)

    existing_dois = set()
    if out_path.exists():
        with open(out_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("doi"):
                    existing_dois.add(row["doi"].lower())
        print(f"Existing records: {len(existing_dois):,} ({out_path.name})")

    print(f"Fetching RSS: {rss_url}")
    try:
        xml_data = fetch_feed(rss_url)
    except Exception as e:
        print(f"ERROR fetching RSS: {e}")
        if new_output:
            _write_csv(Path(new_output), [])
        return

    new_rows, seen = [], set()
    for row in parse_rss(xml_data, title_filter=title_filter):
        key = row["doi"].lower() if row["doi"] else row["url"]
        if not key or key in existing_dois or key in seen:
            continue
        seen.add(key)
        new_rows.append(row)

    print(f"New papers found: {len(new_rows):,}")

    if new_rows:
        mode = "a" if out_path.exists() else "w"
        with open(out_path, mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if mode == "w":
                w.writeheader()
            w.writerows(new_rows)
        print(f"Added {len(new_rows):,} rows to {out_path}")

    if new_output:
        _write_csv(Path(new_output), new_rows)


def _write_csv(path: Path, rows: list):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)
    print(f"New-output: {len(rows):,} rows → {path}")


def main():
    parser = argparse.ArgumentParser(description="Fetch new papers from journal RSS feed")
    parser.add_argument("--rss", required=True, help="RSS feed URL")
    parser.add_argument("--output", required=True, help="Cumulative CSV path (appended)")
    parser.add_argument("--new-output", default=None, help="New-rows-only CSV (overwritten each run)")
    parser.add_argument("--filter-structural", action="store_true",
                        help="Apply structural alloy title filter (for general journals)")
    args = parser.parse_args()

    title_filter = STRUCTURAL_ALLOY_PATTERN if args.filter_structural else None
    run(
        rss_url=args.rss,
        output=Path(args.output),
        new_output=Path(args.new_output) if args.new_output else None,
        title_filter=title_filter,
    )


if __name__ == "__main__":
    main()
