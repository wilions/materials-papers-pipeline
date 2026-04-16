#!/usr/bin/env python3
"""Tests for download_journal_pdfs.py — publisher PDF URL patterns and OA detection."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import download_journal_pdfs as djp


class TestPublisherUrlPatterns(unittest.TestCase):

    def test_nature_portfolio_doi(self):
        urls = djp.get_pdf_urls("10.1038/s41563-025-01234-5", "")
        self.assertTrue(any("nature.com/articles" in u and u.endswith(".pdf") for u in urls))

    def test_pnas_doi(self):
        urls = djp.get_pdf_urls("10.1073/pnas.2500001122", "")
        self.assertTrue(any("pnas.org/doi/pdf" in u for u in urls))

    def test_science_advances_doi(self):
        urls = djp.get_pdf_urls("10.1126/sciadv.ado1234", "")
        self.assertTrue(any("science.org/doi/pdf" in u for u in urls))

    def test_iop_doi(self):
        urls = djp.get_pdf_urls("10.1088/1741-4326/acxxxx", "")
        self.assertTrue(any("iopscience.iop.org" in u and "/pdf" in u for u in urls))

    def test_springer_doi(self):
        urls = djp.get_pdf_urls("10.1007/s11661-025-07000-0", "")
        self.assertTrue(any("link.springer.com/content/pdf" in u for u in urls))

    def test_wiley_doi(self):
        urls = djp.get_pdf_urls("10.1002/advs.202500001", "")
        self.assertTrue(any("onlinelibrary.wiley.com/doi/pdf" in u for u in urls))

    def test_tandf_doi(self):
        urls = djp.get_pdf_urls("10.1080/00295450.2025.001", "")
        self.assertTrue(any("tandfonline.com/doi/pdf" in u for u in urls))

    def test_elsevier_doi_with_pii_in_url(self):
        article_url = "https://www.sciencedirect.com/science/article/pii/S1359645425001234"
        urls = djp.get_pdf_urls("10.1016/j.actamat.2025.001", article_url)
        self.assertTrue(any("pdfft" in u and "S1359645425001234" in u for u in urls))

    def test_elsevier_doi_without_pii(self):
        urls = djp.get_pdf_urls("10.1016/j.actamat.2025.001", "")
        self.assertEqual(urls, [])

    def test_unknown_doi_prefix_returns_empty(self):
        urls = djp.get_pdf_urls("10.9999/unknown.journal.001", "")
        self.assertEqual(urls, [])


class TestIsPdf(unittest.TestCase):

    def test_pdf_magic_bytes_detected(self):
        self.assertTrue(djp.is_pdf_bytes(b"%PDF-1.4 header content"))

    def test_html_not_detected_as_pdf(self):
        self.assertFalse(djp.is_pdf_bytes(b"<html><body>Paywall</body></html>"))

    def test_empty_bytes_not_pdf(self):
        self.assertFalse(djp.is_pdf_bytes(b""))


if __name__ == "__main__":
    unittest.main()
