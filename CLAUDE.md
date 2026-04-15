# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Directory Is

A materials-science literature pipeline: fetch paper metadata from journal APIs → filter by topic keywords → download open-access PDFs. No package infrastructure — scripts are standalone and run directly with `python3`.

## Dependencies

```bash
pip install polars   # used by filter_structural_alloys.py
# All other scripts use stdlib only (urllib, csv, json, threading)
```

## Scripts and Their Role

| Script | Purpose |
|--------|---------|
| `fetch_iaea_fec.py` | Fetch IAEA Fusion Energy Conference metadata from INIS InvenioRDM API → CSV |
| `fetch_crossref_update.py` | Fetch new/updated papers for any journal from Crossref API by ISSN; deduplicates against existing CSV |
| `download_iaea_fec.py` | Download PDFs for IAEA FEC papers (INIS files API → OSTI → direct IAEA URL) |
| `download_materials_today.py` | Download OA PDFs for Elsevier papers via Semantic Scholar (per-DOI, 1 req/s) + PMC fallback |
| `download_nuclear_pdfs.py` | Download OA PDFs via Semantic Scholar batch API (500 DOIs/req) → Unpaywall fallback. Works for any journal. |
| `filter_structural_alloys.py` | Filter any journal CSV by structural-alloy keyword regex on title. Supports `--all` to run all journals at once. |

## Common Commands

```bash
# Update paper list for a journal (fetch new papers since last entry via Crossref)
python3 fetch_crossref_update.py --issn 1359-6454 --output acta_materialia_papers.csv
python3 fetch_crossref_update.py --issn 1359-6462 --output scripta_materialia_papers.csv
python3 fetch_crossref_update.py --issn 1005-0302 --output jmst_papers.csv
python3 fetch_crossref_update.py --issn 2198-3844 --output advanced_science_papers.csv
python3 fetch_crossref_update.py --issn 2375-2548 --output science_advances_papers.csv

# Filter ALL journals for structural alloy papers (re-run after updating CSVs)
python3 filter_structural_alloys.py --all

# Filter a single journal
python3 filter_structural_alloys.py --input acta_materialia_papers.csv --output acta_materialia_structural.csv

# Download OA PDFs (batch S2 + Unpaywall — use for any journal)
python3 download_nuclear_pdfs.py --input acta_materialia_structural.csv --outdir acta_materialia_pdfs --workers 6
python3 download_nuclear_pdfs.py --input scripta_materialia_structural.csv --outdir scripta_materialia_pdfs --workers 6
python3 download_nuclear_pdfs.py --input jmst_structural.csv --outdir jmst_pdfs_structural --workers 6
python3 download_nuclear_pdfs.py --input pnas_structural.csv --outdir pnas_structural_pdfs --workers 6
python3 download_nuclear_pdfs.py --input science_advances_structural.csv --outdir science_advances_pdfs --workers 6

# Download nuclear journal PDFs
python3 download_nuclear_pdfs.py --input jnm_metals.csv --outdir jnm_pdfs
python3 download_nuclear_pdfs.py --input nme_metals.csv --outdir nme_pdfs --workers 6

# Fetch IAEA FEC metadata
python3 fetch_iaea_fec.py --output iaea_fec_papers.csv
python3 download_iaea_fec.py --input iaea_fec_papers.csv --outdir iaea_fec_pdfs --workers 8
```

## CSV Schema

All journal CSVs share a common schema: `doi, title, authors, year, month, volume, issue, page, article_number, type, subject, url`

IAEA CSVs use a different schema: `inis_id, title, authors, year, description, subject_category, descriptors, url`

The `*_structural.csv` files are keyword-filtered subsets of the full `*_papers.csv` files.

## Download Architecture

Both download scripts use the same pattern:
- Threaded (`ThreadPoolExecutor`) with a shared `lock`/`counter`/`log_rows`
- Skip existing files (idempotent re-runs)
- Write a `download_log.csv` inside the output directory with per-paper status
- Status codes: `ok`, `no_oa`/`no_pdf`, `err`, `skip`

**IAEA downloader** hits three sources in order: INIS files API → OSTI URL → direct IAEA PDF URL. Filename = `{inis_id_sanitized}.pdf`.

**Materials Today downloader** is rate-limited (1 req/s) against Semantic Scholar. Elsevier papers yield ~5–15% OA coverage. Blocked domains (sciencedirect.com, linkinghub, etc.) are skipped automatically. Filename = `{doi_sanitized}.pdf`.

**Nuclear PDF downloader** (`download_nuclear_pdfs.py`) does a two-stage lookup: (1) Semantic Scholar batch API (500 DOIs/request, fast) to build a `doi → pdf_url` map, then (2) Unpaywall per-DOI for any misses. Expected OA yields: JNM/FED/FST ~5–15%, NME ~20–40%, Nuclear Fusion ~15–25%. The `EMAIL` constant at the top of the script is sent to Unpaywall as required by their API terms.

## Structural Alloy Filtered CSVs (metal alloys for structural applications)

| CSV | Papers | Source journal |
|-----|--------|---------------|
| `acta_materialia_structural.csv` | ~11,970 | Acta Materialia (1996–2026) |
| `scripta_materialia_structural.csv` | ~9,875 | Scripta Materialia (1996–2026) |
| `jmst_structural.csv` | ~3,717 | J. Materials Science & Technology (2010–2026) |
| `pnas_structural.csv` | ~3,694 | PNAS (all years) |
| `science_advances_structural.csv` | ~858 | Science Advances (2015–2026) |
| `ncomms_structural.csv` | ~292 | Nature Communications (pre-filtered) |
| `materials_today_structural.csv` | ~341 | Materials Today (1998–2026) |
| `npj_adv_manufacturing_structural.csv` | ~36 | npj Advanced Manufacturing |
| `advanced_science_structural.csv` | ~15 | Advanced Science (general journal, low yield) |

## PDF Directory Layout

```
acta_materialia_pdfs/       ← Acta Materialia structural (~5–15% OA yield)
scripta_materialia_pdfs/    ← Scripta Materialia structural (~5–15%)
jmst_pdfs_structural/       ← JMST structural (~20–40%, Chinese journal)
pnas_structural_pdfs/       ← PNAS structural (~40–70% OA)
science_advances_pdfs/      ← Science Advances structural (~40–60%)
npj_adv_manufacturing_pdfs/ ← npj Advanced Manufacturing
ncomms_pdfs/                ← Nature Communications metals (428 PDFs)
materials_today_pdfs/       ← Materials Today structural (~5–15%)
iaea_fec_pdfs/              ← IAEA FEC papers (~62% yield from INIS)
jnm_pdfs/                   ← Journal of Nuclear Materials (~5–15%)
nme_pdfs/                   ← Nuclear Materials and Energy (~20–40%)
nuclear_fusion_pdfs/        ← Nuclear Fusion journal (~15–25%)
fed_pdfs/                   ← Fusion Engineering and Design (~5–15%)
fst_pdfs/                   ← Fusion Science and Technology (~5–10%)
pnas_pdfs/                  ← PNAS (older general download)
advanced_science_metal_alloys/ ← Advanced Science metals (24 PDFs)
```
