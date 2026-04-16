#!/usr/bin/env python3
"""
Download open-access PDFs directly from publisher journal websites.
Uses publisher-specific URL patterns derived from the DOI prefix.
Skips papers whose URLs return non-PDF content (paywall pages).

Usage:
    python3 download_journal_pdfs.py --input acta_materialia_new.csv --outdir acta_materialia_pdfs
    python3 download_journal_pdfs.py --input pnas_new.csv --outdir pnas_structural_pdfs --workers 4

Expected OA yield by publisher:
    Nature Portfolio (fully OA journals: npj, ncomms): ~90%+
    PNAS / Science Advances (fully OA or high OA): ~60-80%
    IOP (Nuclear Fusion, hybrid): ~15-30%
    Elsevier (hybrid, requires PII in URL): ~5-15%
    Springer / Wiley / T&F (hybrid): ~10-25%
"""

import argparse
import csv
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AcademiaFetcher/1.0; mailto:research@imre.a-star.edu.sg)",
    "Accept": "application/pdf,*/*",
}


def get_pdf_urls(doi: str, article_url: str) -> list:
    """
    Return ordered list of candidate PDF URLs for a given DOI.
    Based on DOI prefix → publisher mapping.
    Returns [] if publisher pattern unknown.
    """
    urls = []
    doi_enc = urllib.parse.quote(doi, safe="")

    if doi.startswith("10.1038/"):
        # Nature Portfolio: articles/{id}.pdf works for OA
        article_id = doi.split("10.1038/")[-1]
        urls.append(f"https://www.nature.com/articles/{article_id}.pdf")

    elif doi.startswith("10.1073/"):
        # PNAS
        urls.append(f"https://www.pnas.org/doi/pdf/{doi}")

    elif doi.startswith("10.1126/sciadv"):
        # Science Advances
        urls.append(f"https://www.science.org/doi/pdf/{doi}")

    elif doi.startswith("10.1126/"):
        # Science (other)
        urls.append(f"https://www.science.org/doi/pdf/{doi}")

    elif doi.startswith("10.1088/"):
        # IOP Publishing (Nuclear Fusion, etc.) — DOI as literal path segments
        urls.append(f"https://iopscience.iop.org/article/{doi}/pdf")

    elif doi.startswith("10.1007/"):
        # Springer
        urls.append(f"https://link.springer.com/content/pdf/{doi_enc}.pdf")

    elif doi.startswith("10.1002/") or doi.startswith("10.1111/"):
        # Wiley
        urls.append(f"https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}")
        urls.append(f"https://onlinelibrary.wiley.com/doi/pdf/{doi}")

    elif doi.startswith("10.1080/") or doi.startswith("10.1179/"):
        # Taylor & Francis
        urls.append(f"https://www.tandfonline.com/doi/pdf/{doi}?download=true")

    elif doi.startswith("10.1016/"):
        # Elsevier ScienceDirect — OA PDF requires PII from article URL
        if article_url:
            m = re.search(r"pii/([A-Z0-9]+)", article_url)
            if m:
                pii = m.group(1)
                urls.append(
                    f"https://www.sciencedirect.com/science/article/pii/{pii}/pdfft?download=true"
                )
        # No fallback — Elsevier blocks generic DOI-based PDF access

    elif doi.startswith("10.1017/") or doi.startswith("10.1557/"):
        # Cambridge University Press
        urls.append(f"https://www.cambridge.org/core/services/aop-cambridge-core/content/view/{doi_enc}")

    return urls


def is_pdf_bytes(data: bytes) -> bool:
    """Check if bytes start with PDF magic number."""
    return data[:4] == b"%PDF"


def _try_download(url: str, dest: Path) -> bool:
    """Attempt to download a PDF from url to dest. Returns True on success."""
    tmp = dest.with_suffix(".tmp")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read(50_000_000)  # 50 MB cap — no real PDF exceeds this
        if not is_pdf_bytes(data):
            return False
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)  # atomic on POSIX
        return True
    except Exception:
        if tmp.exists():
            tmp.unlink()
        return False


def doi_to_filename(doi: str) -> str:
    safe = re.sub(r'[^\w\-.]', '_', doi)
    return f"{safe}.pdf"


def _process_row(doi: str, article_url: str, out_dir: Path, lock: threading.Lock,
                 counter: dict, log_rows: list):
    fname = doi_to_filename(doi)
    dest = out_dir / fname

    if dest.exists():
        with lock:
            counter["skip"] += 1
        return

    # Clean up any leftover tmp file from previous interrupted run
    tmp = dest.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()

    candidate_urls = get_pdf_urls(doi, article_url)
    if not candidate_urls:
        with lock:
            counter["no_pattern"] = counter.get("no_pattern", 0) + 1
            log_rows.append({"doi": doi, "status": "no_pattern", "note": "unknown publisher"})
        return

    status, note = "no_oa", "all candidates returned non-PDF"
    for url in candidate_urls:
        if _try_download(url, dest):
            status, note = "ok", url[:100]
            break
        time.sleep(0.3)

    ts = datetime.now().strftime("%H:%M:%S")
    with lock:
        counter[status] = counter.get(status, 0) + 1
        total = sum(counter.values())
        log_rows.append({"doi": doi, "status": status, "note": note})
        print(f"[{ts}] {total:5d} {status:8s}  {doi[:50]}  {note[:55]}")


def main():
    parser = argparse.ArgumentParser(description="Download OA PDFs from publisher websites")
    parser.add_argument("--input", required=True, help="CSV with doi and url columns")
    parser.add_argument("--outdir", required=True, help="Output directory for PDFs")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = out_dir / "download_log.csv"

    with open(args.input, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("Input CSV is empty — nothing to download.")
        return

    papers = [(r["doi"], r.get("url", "")) for r in rows if r.get("doi")]
    pending = [(doi, url) for doi, url in papers
               if not (out_dir / doi_to_filename(doi)).exists()]
    print(f"Input: {len(papers)} | Pending: {len(pending)} | Workers: {args.workers}")

    if not pending:
        print("All papers already downloaded.")
        return

    lock = threading.Lock()
    counter = {"skip": len(papers) - len(pending)}
    log_rows = []

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(_process_row, doi, url, out_dir, lock, counter, log_rows)
                   for doi, url in pending]
        for fut in as_completed(futures):
            fut.result()

    mode = "a" if log_file.exists() else "w"
    with open(log_file, mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["doi", "status", "note"])
        if mode == "w":
            w.writeheader()
        w.writerows(log_rows)

    pdfs = list(out_dir.glob("*.pdf"))
    total_mb = sum(p.stat().st_size for p in pdfs) / 1e6
    print(f"\nResults: {dict(counter)}")
    print(f"PDFs in {out_dir}: {len(pdfs)} files, {total_mb:.1f} MB")
    print(f"Log: {log_file}")


if __name__ == "__main__":
    main()
