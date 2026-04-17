#!/bin/bash
# run_pipeline.sh — Full papers update pipeline
# Fetch new paper metadata via RSS → filter structural alloys → consolidate → download OA PDFs
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

# ── 1. Fetch new papers via RSS (all journals) ──────────────────────────────
# *_new.csv files are committed by the cloud routine — local RSS fetch here
# is a safety net only; cloud-committed files are used for PDF download below.
log "Fetching new papers via RSS..."

FILTER="--filter-structural"  # applied only to general/multidisciplinary journals

# Core structural alloys
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/13596454" --output acta_materialia_papers.csv          --new-output acta_materialia_new.csv
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/13596462" --output scripta_materialia_papers.csv        --new-output scripta_materialia_new.csv
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/09215093" --output msea_papers.csv                      --new-output msea_new.csv
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/09258388" --output jac_papers.csv                       --new-output jac_new.csv
python3 fetch_rss.py --rss "https://link.springer.com/search.rss?facet-journal-id=11661" --output mmta_papers.csv                     --new-output mmta_new.csv
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/09669795" --output intermetallics_papers.csv            --new-output intermetallics_new.csv
python3 fetch_rss.py --rss "https://www.nature.com/nmat.rss"                             --output nature_materials_papers.csv          --new-output nature_materials_new.csv

# Closely related
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/00796425" --output progress_materials_science_papers.csv --new-output progress_materials_science_new.csv
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/02641275" --output materials_design_papers.csv           --new-output materials_design_new.csv
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/0010938X" --output corrosion_science_papers.csv          --new-output corrosion_science_new.csv
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/07496419" --output intl_j_plasticity_papers.csv         --new-output intl_j_plasticity_new.csv
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/22147810" --output additive_manufacturing_papers.csv     --new-output additive_manufacturing_new.csv
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/10445803" --output materials_characterization_papers.csv --new-output materials_characterization_new.csv
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/09270256" --output computational_materials_papers.csv    --new-output computational_materials_new.csv

# Niche / specialized
python3 fetch_rss.py --rss "https://www.nature.com/npjcompumats.rss"                    --output npj_computational_materials_papers.csv --new-output npj_computational_materials_new.csv
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/03649916" --output calphad_papers.csv                    --new-output calphad_new.csv
python3 fetch_rss.py --rss "https://link.springer.com/search.rss?facet-journal-id=43578" --output journal_materials_research_papers.csv --new-output journal_materials_research_new.csv

# General / multidisciplinary (no title filter)
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/10050302" --output jmst_papers.csv                      --new-output jmst_new.csv
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/13697021" --output materials_today_papers.csv            --new-output materials_today_new.csv
python3 fetch_rss.py --rss "https://www.nature.com/npjadvmanuf.rss"                     --output npj_adv_manufacturing_papers.csv      --new-output npj_adv_manufacturing_new.csv

# General / multidisciplinary (title filter applied)
python3 fetch_rss.py --rss "https://www.pnas.org/rss/current.xml"                                                          --output pnas_papers.csv             --new-output pnas_new.csv             $FILTER
python3 fetch_rss.py --rss "https://www.nature.com/ncomms.rss"                                                             --output ncomms_papers.csv            --new-output ncomms_new.csv            $FILTER
python3 fetch_rss.py --rss "https://www.science.org/rss/advancese.xml"                                                     --output science_advances_papers.csv  --new-output science_advances_new.csv  $FILTER
python3 fetch_rss.py --rss "https://onlinelibrary.wiley.com/action/showFeed?jc=21983844&type=etoc&feed=rss"                --output advanced_science_papers.csv  --new-output advanced_science_new.csv  $FILTER

# Nuclear journals
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/00223115" --output jnm_papers.csv             --new-output jnm_new.csv
python3 fetch_rss.py --rss "https://iopscience.iop.org/journal/0029-5515/rss"           --output nuclear_fusion_papers.csv  --new-output nuclear_fusion_new.csv
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/09203796" --output fed_papers.csv             --new-output fed_new.csv
python3 fetch_rss.py --rss "https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=unct20" --output fst_papers.csv --new-output fst_new.csv
python3 fetch_rss.py --rss "https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=tnue20" --output jne_papers.csv --new-output jne_new.csv
python3 fetch_rss.py --rss "https://rss.sciencedirect.com/publication/science/23521791" --output nme_papers.csv             --new-output nme_new.csv

log "  RSS fetch done"

# ── 2. Filter all journals for structural alloys ────────────────────────────
log "Filtering structural alloys..."
python3 filter_structural_alloys.py --all
log "  Filter done"

# ── 3. Consolidate all *_structural.csv into one file ───────────────────────
log "Consolidating structural alloy papers..."
python3 consolidate_structural.py
log "  Consolidation done"

# ── 4. Download OA PDFs — new papers only, per journal ──────────────────────
# Uses *_new.csv files committed by cloud routine (pulled at step 0).
log "Downloading OA PDFs for new papers (per journal)..."

dl() {
    local csv="$1" outdir="$2"
    if [ -f "$csv" ] && [ "$(wc -l < "$csv")" -gt 1 ]; then
        python3 download_journal_pdfs.py --input "$csv" --outdir "$outdir" --workers 4
    else
        log "  Skipping $csv (empty or missing)"
    fi
}

# Core structural alloys
dl acta_materialia_new.csv                acta_materialia_pdfs
dl scripta_materialia_new.csv             scripta_materialia_pdfs
dl msea_new.csv                           msea_pdfs
dl jac_new.csv                            jac_pdfs
dl mmta_new.csv                           mmta_pdfs
dl intermetallics_new.csv                 intermetallics_pdfs
dl nature_materials_new.csv               nature_materials_pdfs

# Closely related
dl progress_materials_science_new.csv     progress_materials_science_pdfs
dl materials_design_new.csv               materials_design_pdfs
dl corrosion_science_new.csv              corrosion_science_pdfs
dl intl_j_plasticity_new.csv             intl_j_plasticity_pdfs
dl additive_manufacturing_new.csv         additive_manufacturing_pdfs
dl materials_characterization_new.csv     materials_characterization_pdfs
dl computational_materials_new.csv        computational_materials_pdfs

# Niche / specialized
dl npj_computational_materials_new.csv   npj_computational_materials_pdfs
dl calphad_new.csv                        calphad_pdfs
dl journal_materials_research_new.csv     journal_materials_research_pdfs

# General / multidisciplinary
dl jmst_new.csv                           jmst_pdfs_structural
dl materials_today_new.csv                materials_today_pdfs
dl npj_adv_manufacturing_new.csv         npj_adv_manufacturing_pdfs
dl pnas_new.csv                           pnas_structural_pdfs
dl ncomms_new.csv                         ncomms_pdfs
dl science_advances_new.csv               science_advances_pdfs
dl advanced_science_new.csv               advanced_science_metal_alloys

# Nuclear
dl jnm_new.csv                            jnm_pdfs
dl nuclear_fusion_new.csv                 nuclear_fusion_pdfs
dl fed_new.csv                            fed_pdfs
dl fst_new.csv                            fst_pdfs
dl jne_new.csv                            jne_pdfs
dl nme_new.csv                            nme_pdfs

log "  Per-journal PDF download done"

# ── 5. IAEA FEC (separate schema — unchanged) ────────────────────────────────
log "Fetching IAEA FEC metadata..."
python3 fetch_iaea_fec.py --output iaea_fec_papers.csv
log "Downloading IAEA FEC PDFs..."
python3 download_iaea_fec.py --input iaea_fec_papers.csv --outdir iaea_fec_pdfs --workers 8
log "  IAEA FEC done"

log "=== Pipeline complete ==="
