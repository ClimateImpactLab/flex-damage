#!/bin/bash
# Build labor COUNTRY-level input parquet by pop-weight aggregating IR-level
# files ourselves. Methodology validated against the projection system's
# `*-pop-aggregated.nc4` for SSP3 — gives access to SSP2 / SSP4 too, which
# don't have a pre-aggregated reference.
#
# Usage:
#   sbatch slurm/01_prep_labor_country.sbatch
#
#SBATCH --job-name=labor_country_prep
#SBATCH --account=cil
#SBATCH --partition=cil
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=120G
#SBATCH --time=08:00:00
#SBATCH --output=slurm/logs/%x_%j.out
#SBATCH --error=slurm/logs/%x_%j.err

source slurm/_env.sh

OUT_DIR="$SCRATCH_BASE/labor/country_keepmc_full"
mkdir -p "$OUT_DIR"

echo "Output dir: $OUT_DIR"
echo ""

# 8 workers fits ~120 GB (each ~3-4 GB Python proc holding the pop arrays in
# memory + IR nc4 buffers). The IR files are ~10 MB each so reading is fast;
# the bottleneck is per-sim aggregation, parallelized across processes.
python scripts/build_labor_country_input.py \
    --mode full \
    --output-dir "$OUT_DIR" \
    --n-workers 8 \
    --keep-mc

echo ""
echo "Done. Output:"
ls -lh "$OUT_DIR/"
