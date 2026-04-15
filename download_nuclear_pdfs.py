#!/usr/bin/env python3
"""
Download OA PDFs for nuclear journal papers via:
  1. Semantic Scholar batch API (openAccessPdf) — 500 DOIs/request, fast
  2. Unpaywall API — comprehensive OA location finder (free, no auth)

Expected yield:
  JNM (Elsevier subscription): ~5-15%
  NME (Elsevier OA): ~20-40% (OA but Elsevier blocks direct download; S2 finds repos)
  Nuclear Fusion (IOP): ~15-25% (many arXiv preprints)
  FED (Elsevier subscription): ~5-15%
  FST (T&F subscription): ~5-10%

Usage:
    python3 download_nuclear_pdfs.py --input jnm_metals.csv --outdir jnm_pdfs
    python3 download_nuclear_pdfs.py --input jnm_metals.csv --outdir jnm_pdfs --workers 6
"""

import argparse
import csv
import json
import threading
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

HEADERS = {"User-Agent": "AcademiaScraper/1.0 (mailto:research@example.com)"}
EMAIL = "research@example.com"

BLOCKED_DOMAINS = (
    "sciencedirect.com",
    "linkinghub.elsevier.com",
    "manuscript.elsevier.com",
    "doi.org", "dx.doi.org",
    "tandfonline.com",
    "iop.org/EJ",
)


def get_json(url, timeout=20, extra_headers=None):
    headers = dict(HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def s2_batch_lookup(dois):
    """
    Semantic Scholar batch API: up to 500 DOIs per call.
    Returns {doi: pdf_url} for papers with openAccessPdf.
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/batch"
    payload = json.dumps({
        "ids": [f"DOI:{d}" for d in dois],
        "fields": "openAccessPdf,externalIds",
    }).encode()
    req = urllib.request.Request(
        url + "?fields=openAccessPdf,externalIds",
        data=payload,
        headers={**HEADERS, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())

    result = {}
    for item in data:
        if not item:
            continue
        ext = (item.get("externalIds") or {})
        doi = ext.get("DOI", "")
        oa = (item.get("openAccessPdf") or {}).get("url", "")
        if doi and oa and not any(b in oa for b in BLOCKED_DOMAINS):
            result[doi.lower()] = oa
    return result


def unpaywall_lookup(doi):
    """
    Unpaywall: returns best OA PDF URL or "" if none.
    Skips blocked publisher domains.
    """
    try:
        d = get_json(
            f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi, safe='')}?email={EMAIL}",
            timeout=15,
        )
        loc = d.get("best_oa_location") or {}
        url = loc.get("url_for_pdf") or loc.get("url") or ""
        if url and not any(b in url for b in BLOCKED_DOMAINS):
            return url
    except Exception:
        pass
    return ""


def download_pdf(url, dest_path):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
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

def process_row(doi, pdf_url_s2, out_dir, lock, counter, log_rows):
    fname = doi_to_filename(doi)
    dest = out_dir / fname

    if dest.exists():
        with lock:
            counter["skip"] += 1
        return

    status = ""
    note = ""
    source = ""

    try:
        pdf_url = pdf_url_s2  # already resolved from batch

        # Stage 2: Unpaywall if S2 had nothing
        if not pdf_url:
            pdf_url = unpaywall_lookup(doi)
            source = "unpaywall"
            time.sleep(0.05)  # Unpaywall is generous but be polite

        if not pdf_url:
            status = "no_oa"
            note = "no OA PDF found in S2 or Unpaywall"
        else:
            if not source:
                source = "s2"
            size = download_pdf(pdf_url, dest)
            status = "ok"
            note = f"{source}  {size:,}b"

    except Exception as e:
        status = "err"
        note = str(e)[:120]

    ts = datetime.now().strftime("%H:%M:%S")
    with lock:
        counter[status] += 1
        total = sum(counter.values())
        log_rows.append({"doi": doi, "status": status, "note": note})
        print(f"[{ts}] {total:5d} {status:8s}  {doi[:50]}  {note[:55]}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = out_dir / "download_log.csv"

    with open(args.input, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    dois = [r["doi"] for r in rows if r.get("doi")]
    print(f"Input: {len(dois)} papers | Output: {out_dir} | Workers: {args.workers}")

    # Filter already-downloaded
    pending = [d for d in dois if not (out_dir / doi_to_filename(d)).exists()]
    print(f"Pending: {len(pending)} (skipping {len(dois)-len(pending)} already downloaded)\n")

    # Stage 1: Semantic Scholar batch lookup (500 DOIs/request)
    print("Looking up OA PDFs via Semantic Scholar batch API...")
    s2_map = {}
    batch_size = 500
    for i in range(0, len(pending), batch_size):
        batch = pending[i:i + batch_size]
        try:
            result = s2_batch_lookup(batch)
            s2_map.update(result)
            found = sum(1 for d in batch if d.lower() in result)
            print(f"  Batch {i//batch_size + 1}: {found}/{len(batch)} found in S2")
        except Exception as e:
            print(f"  Batch {i//batch_size + 1}: S2 error ({e}), will fall back to Unpaywall")
        time.sleep(1.0)  # S2 batch: be polite

    print(f"\nS2 found OA PDFs for {len(s2_map)}/{len(pending)} papers ({len(s2_map)/max(len(pending),1)*100:.1f}%)")
    print(f"Remaining {len(pending)-len(s2_map)} will be checked via Unpaywall\n")

    lock = threading.Lock()
    counter = {"ok": 0, "no_oa": 0, "err": 0, "skip": len(dois) - len(pending)}
    log_rows = []

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [
            ex.submit(process_row, doi, s2_map.get(doi.lower(), ""), out_dir, lock, counter, log_rows)
            for doi in pending
        ]
        for fut in as_completed(futures):
            fut.result()

    # Append to existing log if present
    mode = "a" if log_file.exists() else "w"
    with open(log_file, mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["doi", "status", "note"])
        if mode == "w":
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
