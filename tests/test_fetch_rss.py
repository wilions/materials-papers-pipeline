#!/usr/bin/env python3
"""Tests for fetch_rss.py — RSS-based new paper detection."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
import fetch_rss as fr


# ── RSS fixture helpers ────────────────────────────────────────────────────────

def _rss(items_xml):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:prism="http://prismstandard.org/namespaces/basic/2.0/">
  <channel>
    <title>Test Journal</title>
    {items_xml}
  </channel>
</rss>""".encode()


def _item(doi, title, url="", pub_date="Thu, 10 Apr 2025 00:00:00 GMT"):
    return f"""
    <item>
      <title>{title}</title>
      <link>{url or f'https://doi.org/{doi}'}</link>
      <dc:identifier>{doi}</dc:identifier>
      <pubDate>{pub_date}</pubDate>
    </item>"""


# ── Tests: parse_rss ──────────────────────────────────────────────────────────

class TestParseRss(unittest.TestCase):

    def test_extracts_doi_and_title(self):
        xml = _rss(_item("10.1016/j.actamat.2025.001", "Alloy Strengthening"))
        rows = list(fr.parse_rss(xml))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doi"], "10.1016/j.actamat.2025.001")
        self.assertEqual(rows[0]["title"], "Alloy Strengthening")

    def test_extracts_year_from_pubdate(self):
        xml = _rss(_item("10.1016/j.test.001", "Paper", pub_date="Mon, 15 Jan 2025 00:00:00 GMT"))
        rows = list(fr.parse_rss(xml))
        self.assertEqual(rows[0]["year"], "2025")
        self.assertEqual(rows[0]["month"], "1")

    def test_doi_from_doi_org_link(self):
        """DOI extracted from https://doi.org/... style link when dc:identifier absent."""
        xml = _rss(f"""
        <item>
          <title>Paper Without DC Identifier</title>
          <link>https://doi.org/10.1016/j.actamat.2025.999</link>
          <pubDate>Mon, 01 Jan 2025 00:00:00 GMT</pubDate>
        </item>""")
        rows = list(fr.parse_rss(xml))
        self.assertEqual(rows[0]["doi"], "10.1016/j.actamat.2025.999")

    def test_empty_feed_returns_no_rows(self):
        xml = _rss("")
        rows = list(fr.parse_rss(xml))
        self.assertEqual(rows, [])


# ── Tests: title filtering ────────────────────────────────────────────────────

class TestTitleFilter(unittest.TestCase):

    def test_filter_keeps_matching_titles(self):
        xml = _rss(
            _item("10.1073/pnas.001", "High-entropy alloy tensile behavior") +
            _item("10.1073/pnas.002", "Protein folding dynamics")
        )
        rows = list(fr.parse_rss(xml, title_filter=fr.STRUCTURAL_ALLOY_PATTERN))
        titles = [r["title"] for r in rows]
        self.assertIn("High-entropy alloy tensile behavior", titles)
        self.assertNotIn("Protein folding dynamics", titles)

    def test_no_filter_keeps_all(self):
        xml = _rss(
            _item("10.1073/pnas.001", "Alloy Paper") +
            _item("10.1073/pnas.002", "Biology Paper")
        )
        rows = list(fr.parse_rss(xml, title_filter=None))
        self.assertEqual(len(rows), 2)


# ── Tests: deduplication and new-output ──────────────────────────────────────

class TestDeduplication(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.main_csv = self.base / "journal_papers.csv"
        self.new_csv = self.base / "journal_new.csv"
        # Pre-populate with one existing paper
        with open(self.main_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fr.FIELDNAMES)
            w.writeheader()
            w.writerow({k: "" for k in fr.FIELDNAMES} | {"doi": "10.1016/existing"})

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, items_xml):
        xml = _rss(items_xml)
        with patch("fetch_rss.fetch_feed", return_value=xml):
            fr.run(
                rss_url="https://fake.rss/feed",
                output=self.main_csv,
                new_output=self.new_csv,
                title_filter=None,
            )

    def test_existing_doi_not_added_again(self):
        self._run(_item("10.1016/existing", "Old Paper") + _item("10.1016/brand-new", "New Paper"))
        with open(self.main_csv, newline="") as f:
            rows = list(csv.DictReader(f))
        dois = [r["doi"] for r in rows]
        self.assertEqual(dois.count("10.1016/existing"), 1)
        self.assertIn("10.1016/brand-new", dois)

    def test_new_output_contains_only_new_rows(self):
        self._run(_item("10.1016/existing", "Old") + _item("10.1016/brand-new", "New"))
        with open(self.new_csv, newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doi"], "10.1016/brand-new")

    def test_new_output_header_only_when_nothing_new(self):
        self._run(_item("10.1016/existing", "Old Paper"))
        with open(self.new_csv, newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows, [])

    def test_new_output_overwrites_stale_content(self):
        # Write stale content first
        with open(self.new_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fr.FIELDNAMES)
            w.writeheader()
            w.writerow({k: "stale" for k in fr.FIELDNAMES})
        self._run(_item("10.1016/fresh", "Fresh Paper"))
        with open(self.new_csv, newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doi"], "10.1016/fresh")


if __name__ == "__main__":
    unittest.main()
