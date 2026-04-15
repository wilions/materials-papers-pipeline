#!/usr/bin/env python3
"""
Download PDFs for IAEA Fusion Energy Conference papers from INIS.

Sources:
  1. INIS-hosted PDFs (~62%): direct download from INIS files API
  2. OSTI URLs (~10%): DOE open access, direct download
  3. Direct IAEA PDF URLs: direct download

Usage:
    python3 download_iaea_fec.py --input papers/iaea_fec_papers.csv --outdir papers/iaea_fec_pdfs
    python3 download_iaea_fec.py --input papers/iaea_fec_papers.csv --outdir papers/iaea_fec_pdfs --workers 8
"""

import argparse
import csv
import json
import os
import threading
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

session_headers = {
    "User-Agent": "AcademiaScraper/1.0 (mailto:research@example.com)",
}


def get_url(url, timeout=30, stream=False):
    req = urllib.request.Request(url, headers=session_headers)
    return urllib.request.urlopen(req, timeout=timeout)


def get_json(url, accept="application/json"):
    headers = dict(session_headers)
    headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def get_inis_pdf_url(inis_id):
    """
    Check INIS files API for a hosted PDF.
    Returns (download_url, filename) or (None, None).
    """
    try:
        data = get_json(f"https://inis.iaea.org/api/records/{inis_id}/files")
        for entry in data.get("entries", []):
            key = entry.get("key", "")
            if key.lower().endswith(".pdf"):
                content_url = entry.get("links", {}).get("content")
                if content_url:
                    return content_url, key
    except Exception:
        pass
    return None, None


def get_external_url(inis_id):
    """
    Check INIS record metadata for external downloadable URLs.
    Returns URL string or None.
    """
    try:
        data = get_json(
            f"https://inis.iaea.org/api/records/{inis_id}",
            accept="application/vnd.inveniordm.v1+json"
        )
        idents = data.get("metadata", {}).get("identifiers", [])
        for ident in idents:
            scheme = ident.get("scheme", "")
            val = ident.get("identifier", "")
            if scheme == "url":
                # Pick first URL that looks like a direct PDF or OSTI
                for part in val.split(","):
                    part = part.strip()
                    if "osti.gov/servlets/purl" in part:
                        return part
                    if part.endswith(".pdf") and ("iaea.org" in part or "pub.iaea" in part):
                        return part
    except Exception:
        pass
    return None


def download_pdf(url, dest_path):
    req = urllib.request.Request(url, headers=session_headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if not data[:4] == b"%PDF":
        raise ValueError(f"Not a PDF (got {data[:20]!r})")
    with open(dest_path, "wb") as f:
        f.write(data)
    return len(data)


def inis_id_to_filename(inis_id, title):
    # Use inis_id as primary key for filename
    safe_id = inis_id.replace("/", "_").replace(":", "_")
    return f"{safe_id}.pdf"


# ── worker ────────────────────────────────────────────────────────────────────

def process_row(row, out_dir, lock, counter, log_rows):
    inis_id = row["inis_id"]
    title   = row.get("title", "")
    fname   = inis_id_to_filename(inis_id, title)
    dest    = out_dir / fname

    if dest.exists():
        with lock:
            counter["skip"] += 1
        return

    status = ""
    note   = ""
    try:
        # Stage 1: INIS-hosted PDF
        pdf_url, pdf_key = get_inis_pdf_url(inis_id)

        if not pdf_url:
            # Stage 2: External URL (OSTI, IAEA direct PDF)
            pdf_url = get_external_url(inis_id)
            pdf_key = "external"

        if not pdf_url:
            status = "no_pdf"
            note   = "no INIS file and no direct URL"
        else:
            size   = download_pdf(pdf_url, dest)
            status = "ok"
            note   = f"{pdf_key}  {size:,}b"

    except Exception as e:
        status = "err"
        note   = str(e)[:120]

    ts = datetime.now().strftime("%H:%M:%S")
    with lock:
        counter[status] += 1
        total = sum(counter.values())
        log_rows.append({"inis_id": inis_id, "status": status, "note": note})
        print(f"[{ts}] {total:5d} {status:8s}  {inis_id}  {note[:60]}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",   required=True)
    parser.add_argument("--outdir",  required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    out_dir  = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = out_dir / "download_log.csv"

    with open(args.input, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows = [r for r in rows if r.get("inis_id")]
    print(f"Input: {len(rows)} records | Output: {out_dir} | Workers: {args.workers}\n")

    lock     = threading.Lock()
    counter  = {"ok": 0, "no_pdf": 0, "err": 0, "skip": 0}
    log_rows = []

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(process_row, row, out_dir, lock, counter, log_rows) for row in rows]
        for f in as_completed(futures):
            f.result()

    with open(log_file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["inis_id", "status", "note"])
        w.writeheader()
        w.writerows(log_rows)

    pdfs = list(out_dir.glob("*.pdf"))
    total_mb = sum(p.stat().st_size for p in pdfs) / 1e6
    print(f"\n{'='*60}")
    print(f"Results: {dict(counter)}")
    print(f"PDFs: {len(pdfs)} files, {total_mb:.1f} MB")
    print(f"Log: {log_file}")


if __name__ == "__main__":
    main()
