#!/usr/bin/env python3
"""
Download PDFs for Materials Today structural alloy papers.

Materials Today is a subscription Elsevier journal — PMC won't work.
Uses Semantic Scholar openAccessPdf + NCBI E-utilities PMC fallback.

Expected yield: ~5–15% (only gold OA / green repo deposits).
Blocked sources (sciencedirect.com, linkinghub.elsevier.com, manuscript.elsevier.com,
doi.org redirects) are skipped automatically.

Usage:
    python3 download_materials_today.py \
        --input  papers/materials_today_structural.csv \
        --outdir papers/materials_today_pdfs
    python3 download_materials_today.py \
        --input  papers/materials_today_structural.csv \
        --outdir papers/materials_today_pdfs \
        --workers 4
"""

import argparse
import csv
import os
import threading
import time
import xml.etree.ElementTree as ET
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


HEADERS = {"User-Agent": "AcademiaScraper/1.0 (mailto:research@example.com)"}

# URLs that are behind Cloudflare or otherwise not directly downloadable
BLOCKED_DOMAINS = (
    "sciencedirect.com",
    "linkinghub.elsevier.com",
    "manuscript.elsevier.com",
    "doi.org",
    "dx.doi.org",
)


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req, timeout=timeout)


def get_json(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        import json
        return json.loads(r.read())


# ── PDF source discovery ───────────────────────────────────────────────────────

def find_via_semantic_scholar(doi):
    """
    Returns direct PDF URL from Semantic Scholar openAccessPdf, or "".
    Filters out blocked domains (publisher Cloudflare, doi.org redirects).
    Also returns PMC ID if found in externalIds.
    """
    try:
        d = get_json(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
            f"?fields=externalIds,openAccessPdf",
            timeout=20,
        )
        pmc = d.get("externalIds", {}).get("PubMedCentral", "")
        oa  = (d.get("openAccessPdf") or {}).get("url", "")
        if oa and not any(b in oa for b in BLOCKED_DOMAINS):
            return oa, pmc
        return "", pmc
    except Exception:
        return "", ""


def find_via_ncbi(doi):
    """NCBI E-utilities fallback for PMC ID."""
    try:
        d = get_json(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pmc&term={urllib.parse.quote(doi)}[doi]&retmode=json",
        )
        time.sleep(0.1)  # NCBI: max 10 req/s
        ids = d.get("esearchresult", {}).get("idlist", [])
        return ids[0] if ids else ""
    except Exception:
        return ""


def get_pmc_pdf_url(pmc_num):
    """
    Query PMC OA service. Returns https PDF URL or "".
    Some Elsevier papers are in PMC (CC BY gold OA) but not all have a PDF link.
    """
    pmc_id = f"PMC{pmc_num}"
    try:
        with get(f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmc_id}") as r:
            root = ET.fromstring(r.read())
        link = root.find(".//link[@format='pdf']")
        if link is None:
            return "", pmc_id
        ftp = link.get("href", "")
        return ftp.replace("ftp://ftp.ncbi.nlm.nih.gov", "https://ftp.ncbi.nlm.nih.gov"), pmc_id
    except Exception:
        return "", pmc_id


# ── download ──────────────────────────────────────────────────────────────────

def download_pdf(url, dest_path):
    with get(url, timeout=60) as r:
        data = r.read()
    if data[:4] != b"%PDF":
        raise ValueError(f"Not a PDF (got {data[:20]!r})")
    with open(dest_path, "wb") as f:
        f.write(data)
    return len(data)


def doi_to_filename(doi):
    safe = doi.replace("/", "_").replace(":", "_").replace("(", "").replace(")", "")
    return f"{safe}.pdf"


# ── worker ────────────────────────────────────────────────────────────────────

def process_row(doi, out_dir, lock, counter, log_rows):
    fname = doi_to_filename(doi)
    dest  = out_dir / fname

    if dest.exists():
        with lock:
            counter["skip"] += 1
        return

    status = ""; note = ""
    try:
        # Stage 1: Semantic Scholar — fast, finds repo-hosted OA PDFs
        pdf_url, pmc_num = find_via_semantic_scholar(doi)
        source = "s2"
        time.sleep(1.0)  # Semantic Scholar: ~1 req/s

        # Stage 2: PMC via Semantic Scholar externalIds or NCBI lookup
        if not pdf_url:
            if not pmc_num:
                pmc_num = find_via_ncbi(doi)
            if pmc_num:
                pdf_url, pmc_id = get_pmc_pdf_url(pmc_num)
                source = "pmc"
                if not pdf_url:
                    status = "no_pdf"
                    note   = f"{pmc_id}: in PMC but not OA subset"
            else:
                status = "no_oa"
                note   = "no OA PDF found"

        if pdf_url:
            size   = download_pdf(pdf_url, dest)
            status = "ok"
            note   = f"{source}  {size:,}b"

    except Exception as e:
        status = "err"
        note   = str(e)[:120]

    ts = datetime.now().strftime("%H:%M:%S")
    with lock:
        counter[status] += 1
        total = sum(counter.values())
        log_rows.append({"doi": doi, "status": status, "note": note})
        print(f"[{ts}] {total:4d} {status:8s}  {doi[:50]}  {note[:55]}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",   required=True)
    parser.add_argument("--outdir",  required=True)
    parser.add_argument("--workers", type=int, default=3,
                        help="Threads (default 3; Semantic Scholar rate-limits at ~1 req/s)")
    args = parser.parse_args()

    out_dir  = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = out_dir / "download_log.csv"

    with open(args.input, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    dois = [r["doi"] for r in rows if r.get("doi")]
    print(f"Input: {len(dois)} papers | Output: {out_dir} | Workers: {args.workers}")
    print("Note: Materials Today is a subscription journal — expect ~5–15% yield.\n")

    lock     = threading.Lock()
    counter  = {"ok": 0, "no_oa": 0, "no_pdf": 0, "err": 0, "skip": 0}
    log_rows = []

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(process_row, doi, out_dir, lock, counter, log_rows) for doi in dois]
        for f in as_completed(futures):
            f.result()

    with open(log_file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["doi", "status", "note"])
        w.writeheader()
        w.writerows(log_rows)

    pdfs = list(out_dir.glob("*.pdf"))
    total_mb = sum(p.stat().st_size for p in pdfs) / 1e6
    print(f"\n{'='*60}")
    print(f"Results: {dict(counter)}")
    print(f"PDFs: {len(pdfs)} files, {total_mb:.1f} MB")
    print(f"Log:  {log_file}")
    print("\nStatus codes:")
    print("  ok      — PDF downloaded")
    print("  no_oa   — no OA version found (typical for subscription papers)")
    print("  no_pdf  — found in PMC but not in OA subset (embargo)")
    print("  err     — network/download error (retry)")


if __name__ == "__main__":
    main()
