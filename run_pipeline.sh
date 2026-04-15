#!/bin/bash
# run_pipeline.sh — Full papers update pipeline
# Runs: fetch new metadata → filter structural alloys → download OA PDFs
# Idempotent: safe to re-run, skips existing PDFs

set -euo pipefail

PAPERS_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$PAPERS_DIR/pipeline_run.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

cd "$PAPERS_DIR"
log "=== Pipeline started ==="

# ── 0. Pull latest CSVs from GitHub (committed by cloud routine) ────────────
log "Pulling latest CSVs from GitHub..."
git pull origin main
log "  Pull done"

# ── 1. Fetch new papers from Crossref ──────────────────────────────────────
log "Fetching new Crossref metadata..."

python3 fetch_crossref_update.py --issn 1359-6454 --output acta_materialia_papers.csv
log "  acta_materialia done"

python3 fetch_crossref_update.py --issn 1359-6462 --output scripta_materialia_papers.csv
log "  scripta_materialia done"

python3 fetch_crossref_update.py --issn 1005-0302 --output jmst_papers.csv
log "  jmst done"

python3 fetch_crossref_update.py --issn 2198-3844 --output advanced_science_papers.csv
log "  advanced_science done"

python3 fetch_crossref_update.py --issn 2375-2548 --output science_advances_papers.csv
log "  science_advances done"

python3 fetch_crossref_update.py --issn 2057-3960 --output npj_adv_manufacturing_papers.csv
log "  npj_adv_manufacturing done"

# ── 2. Filter all journals for structural alloys ────────────────────────────
log "Filtering structural alloys..."
python3 filter_structural_alloys.py --all
log "  Filter done"

# ── 3. Download OA PDFs ─────────────────────────────────────────────────────
log "Downloading OA PDFs..."

python3 download_nuclear_pdfs.py --input acta_materialia_structural.csv    --outdir acta_materialia_pdfs        --workers 6
log "  acta_materialia PDFs done"

python3 download_nuclear_pdfs.py --input scripta_materialia_structural.csv --outdir scripta_materialia_pdfs     --workers 6
log "  scripta_materialia PDFs done"

python3 download_nuclear_pdfs.py --input jmst_structural.csv               --outdir jmst_pdfs_structural        --workers 6
log "  jmst PDFs done"

python3 download_nuclear_pdfs.py --input pnas_structural.csv               --outdir pnas_structural_pdfs        --workers 6
log "  pnas PDFs done"

python3 download_nuclear_pdfs.py --input science_advances_structural.csv   --outdir science_advances_pdfs       --workers 6
log "  science_advances PDFs done"

python3 download_nuclear_pdfs.py --input npj_adv_manufacturing_structural.csv --outdir npj_adv_manufacturing_pdfs --workers 6
log "  npj_adv_manufacturing PDFs done"

python3 download_nuclear_pdfs.py --input ncomms_structural.csv             --outdir ncomms_pdfs                 --workers 6
log "  ncomms PDFs done"

python3 download_nuclear_pdfs.py --input jnm_metals.csv                   --outdir jnm_pdfs                    --workers 6
log "  jnm PDFs done"

python3 download_nuclear_pdfs.py --input nme_metals.csv                   --outdir nme_pdfs                    --workers 6
log "  nme PDFs done"

python3 download_materials_today.py --input materials_today_structural.csv --outdir materials_today_pdfs
log "  materials_today PDFs done"

python3 download_iaea_fec.py --input iaea_fec_papers.csv --outdir iaea_fec_pdfs --workers 8
log "  iaea_fec PDFs done"

log "=== Pipeline complete ==="
