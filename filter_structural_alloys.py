#!/usr/bin/env python3
"""
Filter papers related to metal alloys for structural applications
from any journal CSV using keyword matching on title.

Usage:
    python3 filter_structural_alloys.py --input acta_materialia_papers.csv --output acta_materialia_structural.csv
    python3 filter_structural_alloys.py --input scripta_materialia_papers.csv --output scripta_materialia_structural.csv
    python3 filter_structural_alloys.py  # legacy: runs Acta Materialia with hardcoded paths

Batch (all journals):
    python3 filter_structural_alloys.py --all
"""

import argparse
import polars as pl
from pathlib import Path

# Keywords covering metal alloys for structural applications
# Categories: alloy families, structural properties, processing, applications
KEYWORDS = [
    # Alloy families
    r"\balloy\b", r"\balloys\b",
    r"\bsteel\b", r"\bsteels\b",
    r"\baluminum\b", r"\baluminium\b",
    r"\btitanium\b",
    r"\bnickel.based\b", r"\bni.based\b", r"\bsuperalloy\b", r"\bsuperalloys\b",
    r"\bmagnesium\b",
    r"\bcopper\b",
    r"\btungsten\b",
    r"\bchromium\b",
    r"\bmolybdenum\b",
    r"\bzirconium\b",
    r"\bnobium\b", r"\bniobium\b",
    r"\bvanadium\b",
    r"\bmaraging\b",
    r"\bduplex\b",
    r"\bhigh.entropy\b", r"\bHEA\b", r"\bmulti.principal\b",
    r"\bintermetallic\b", r"\bintermetallics\b",
    r"\bAl.alloy\b", r"\bTi.alloy\b", r"\bFe.alloy\b", r"\bMg.alloy\b",
    r"\bAlMg\b", r"\bAlCu\b", r"\bAlSi\b", r"\bAlZn\b",
    r"\bTiAl\b", r"\bTiZr\b", r"\bTiNb\b",
    r"\bNiAl\b", r"\bNiFe\b", r"\bNiTi\b",
    r"\bFeMn\b", r"\bFeCr\b", r"\bFeMnAl\b",
    r"\bLow.alloy\b", r"\bhigh.alloy\b",
    r"\bWC\b",  # tungsten carbide
    r"\bODS\b",  # oxide dispersion strengthened
    r"\bCoCrFeNi\b", r"\bCoCrNi\b",  # common HEA compositions
    r"\bInconel\b", r"\bIN718\b", r"\bIN625\b",
    r"\bstainless\b",
    r"\bTi-6Al-4V\b", r"\bTC4\b",
    # Structural properties & failure modes
    r"\bstructural\b",
    r"\bmechanical properties\b",
    r"\btensile\b",
    r"\byield strength\b",
    r"\bultimate strength\b",
    r"\bductility\b",
    r"\btoughness\b",
    r"\bhardness\b",
    r"\bfatigue\b",
    r"\bfracture\b",
    r"\bcreep\b",
    r"\bcorrosion\b",
    r"\bwear\b",
    r"\bdeformation\b",
    r"\bplasticity\b",
    r"\bstrengthening\b",
    r"\bhigh.strength\b",
    r"\blightweight\b",
    r"\bspecific strength\b",
    r"\bstiffness\b",
    r"\belastic modulus\b",
    r"\bimpact\b",
    # Microstructure relevant to structural alloys
    r"\bprecipitation.hardening\b", r"\bage.hardening\b", r"\bprecipitate\b",
    r"\bgrain.boundary\b", r"\bgrain refinement\b",
    r"\bdislocation\b", r"\bslip\b",
    r"\bphase transformation\b",
    r"\bmartensitic\b", r"\bmartensite\b",
    r"\bbainite\b", r"\baustenite\b", r"\bferrite\b", r"\bpearlite\b",
    r"\bgamma.prime\b", r"\bgamma prime\b",
    r"\bsolid solution\b",
    r"\bnanostructure\b", r"\bnanocrystalline\b", r"\bnano.structured\b",
    r"\bamorphous\b",
    # Processing routes relevant to structural alloys
    r"\bhot rolling\b", r"\bcold rolling\b",
    r"\bforging\b",
    r"\bextrusion\b",
    r"\banneal\b", r"\bannealing\b",
    r"\bquench\b", r"\bquenching\b",
    r"\btemper\b", r"\btempering\b",
    r"\bwelding\b", r"\bweld\b",
    r"\badditive manufacturing\b", r"\bLPBF\b", r"\bSLM\b", r"\bDED\b",
    r"\bpowder metallurgy\b",
    r"\bsintering\b",
    r"\bSPD\b", r"\bECAP\b", r"\bHPT\b",  # severe plastic deformation
    r"\bhot pressing\b", r"\bhot isostatic\b",
    # Application keywords
    r"\baerospace\b",
    r"\bautomotive\b",
    r"\bload.bearing\b",
    r"\bweight.saving\b",
    r"\barmor\b", r"\barmour\b",
    r"\bnuclear\b",
    r"\bpressure vessel\b",
]

# Build single regex pattern (case-insensitive)
PATTERN = "|".join(KEYWORDS)

# Journal input→output mapping for --all mode
JOURNAL_MAP = {
    "acta_materialia_papers.csv":        "acta_materialia_structural.csv",
    "scripta_materialia_papers.csv":     "scripta_materialia_structural.csv",
    "jmst_papers.csv":                   "jmst_structural.csv",
    "materials_today_papers.csv":        "materials_today_structural.csv",
    "advanced_science_papers.csv":       "advanced_science_structural.csv",
    "science_advances_papers.csv":       "science_advances_structural.csv",
    "npj_adv_manufacturing_papers.csv":  "npj_adv_manufacturing_structural.csv",
    "pnas_papers.csv":                   "pnas_structural.csv",
    "nature_metals_alloys_ncomms.csv":   "ncomms_structural.csv",
}


def filter_file(input_path: Path, output_path: Path):
    print(f"\n{'='*60}")
    print(f"Input:  {input_path.name}")
    print(f"Output: {output_path.name}")

    lf = pl.scan_csv(input_path, infer_schema_length=10000, truncate_ragged_lines=True)
    result = (
        lf.filter(pl.col("title").str.contains(PATTERN, literal=False))
        .collect()
    )
    total = lf.select(pl.len()).collect().item()
    matched = len(result)
    pct = matched / total * 100 if total else 0
    print(f"  {total:,} total → {matched:,} matched ({pct:.1f}%)")
    result.write_csv(output_path)
    print(f"  Saved to {output_path}")
    return matched


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  default=None, help="Input CSV path")
    parser.add_argument("--output", default=None, help="Output CSV path")
    parser.add_argument("--all",    action="store_true",
                        help="Run filter on all known journals (JOURNAL_MAP)")
    args = parser.parse_args()

    base = Path(__file__).parent

    if args.all:
        for inp_name, out_name in JOURNAL_MAP.items():
            inp = base / inp_name
            out = base / out_name
            if not inp.exists():
                print(f"Skipping {inp_name} (not found)")
                continue
            filter_file(inp, out)
    elif args.input and args.output:
        filter_file(Path(args.input), Path(args.output))
    else:
        # Legacy: hardcoded Acta Materialia
        filter_file(base / "acta_materialia_papers.csv",
                    base / "structural_alloy_papers.csv")


if __name__ == "__main__":
    main()
