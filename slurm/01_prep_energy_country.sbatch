#!/bin/bash
# Build energy COUNTRY-level input parquet by reading IR-level kWh/pc files
# and aggregating IR -> country with pop weights. Replaces the old build that
# read country-aggregated files in dollar units.
#
# Usage:
#   sbatch slurm/01_prep_energy_country.sbatch
#
# Energy median tree has no batch dim — one realization per (rcp, gcm, model, ssp).
# So keep-MC and collapse-MC would be identical; we write one canonical parquet
# at country_full/ and symlink it from country_keepmc_full/ so the existing
# *_country.yaml and *_country_collapsed.yaml configs both find their inputs.
#
#SBATCH --job-name=energy_country_prep
#SBATCH --account=cil
#SBATCH --partition=cil
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=slurm/logs/%x_%j.out
#SBATCH --error=slurm/logs/%x_%j.err

source slurm/_env.sh

OUT_DIR="$SCRATCH_BASE/energy/country_full"
KEEP_DIR="$SCRATCH_BASE/energy/country_keepmc_full"
mkdir -p "$OUT_DIR" "$KEEP_DIR"

echo "Output dir: $OUT_DIR"
echo ""

# `--collapse-mc` is a no-op here (no batch dim); both modes produce the same
# parquet. Use collapse-MC as the canonical name to make this explicit.
python scripts/build_energy_country_input.py \
    --mode full \
    --collapse-mc \
    --output-dir "$OUT_DIR"

CANON="$OUT_DIR/energy_aggregated_country_full.parquet"
KEEP_LINK="$KEEP_DIR/energy_aggregated_country_keepmc_full.parquet"
if [[ -f "$CANON" ]]; then
    rm -f "$KEEP_LINK"
    ln -s "$CANON" "$KEEP_LINK"
    echo "Symlinked $KEEP_LINK -> $CANON"
fi

echo ""
echo "Done. Output:"
ls -lh "$OUT_DIR/" "$KEEP_DIR/"
