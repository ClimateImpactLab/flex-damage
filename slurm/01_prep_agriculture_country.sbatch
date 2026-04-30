#!/bin/bash
# Build agriculture COUNTRY-level input parquet from MC tree.
#
# Usage:
#   sbatch --export=ALL,CROP=cassava[,COLLAPSE=1] slurm/01_prep_agriculture_country.sbatch
#
# CROP: corn|rice|soy|sorghum|cassava|wheat_combined|wheat_spring|wheat_winter
# COLLAPSE: optional, set to 1 to aggregate over MC (mean per scenario tuple).
#   Output dir + filename are chosen so the existing _country / _country_collapsed
#   configs find their inputs unchanged.
#
#SBATCH --job-name=ag_country_prep
#SBATCH --account=cil
#SBATCH --partition=cil
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=80G
#SBATCH --time=06:00:00
#SBATCH --output=slurm/logs/%x_%j.out
#SBATCH --error=slurm/logs/%x_%j.err

source slurm/_env.sh

: "${CROP:?Must set CROP via sbatch --export (e.g. cassava)}"

# Match the directory layout expected by configs/agriculture/<sub>_country.yaml
# and configs/agriculture/<sub>_country_collapsed.yaml.
if [[ "${COLLAPSE:-0}" == "1" ]]; then
    OUT_DIR="$SCRATCH_BASE/agriculture/country_full"
    EXTRA="--collapse-mc"
    echo "Mode: collapse-MC (mean per scenario)"
else
    OUT_DIR="$SCRATCH_BASE/agriculture/country_keepmc_full"
    EXTRA="--keep-mc"
    echo "Mode: keep-MC (default)"
fi
mkdir -p "$OUT_DIR"

echo "Crop: $CROP"
echo "Output dir: $OUT_DIR"
echo "Extra args: $EXTRA"
echo ""

# 8 workers fits well in 80 GB on the cil partition (each ~2 GB Python proc + accumulator headroom).
python scripts/build_agriculture_country_input.py \
    --crop "$CROP" \
    --mode full \
    --output-dir "$OUT_DIR" \
    --n-workers 8 \
    $EXTRA

echo ""
echo "Done. Output:"
ls -lh "$OUT_DIR/" | grep "$CROP"
