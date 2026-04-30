#!/bin/bash
# Aggregate any sector's IR parquet to country level.
#
# Usage:
#   sbatch --export=ALL,SECTOR=mortality,SUBSECTOR=allcause,\
# IR_PARQUET=/path/to/ir.parquet,YCOLS="adjusted_mortality" \
#       slurm/04_aggregate_to_country.sbatch
#
#SBATCH --job-name=aggregate_to_country
#SBATCH --account=cil
#SBATCH --partition=caslake
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --output=slurm/logs/%x_%j.out
#SBATCH --error=slurm/logs/%x_%j.err

source slurm/_env.sh

: "${SECTOR:?Must set SECTOR via sbatch --export}"
: "${IR_PARQUET:?Must set IR_PARQUET via sbatch --export (path to existing IR parquet)}"
: "${YCOLS:?Must set YCOLS via sbatch --export (space-separated y column names)}"

OUT_DIR="$SCRATCH_BASE/${SECTOR}/country"
mkdir -p "$OUT_DIR"
OUT_PARQUET="$OUT_DIR/${SECTOR}_aggregated_country_full.parquet"

echo "Sector:       $SECTOR"
echo "IR parquet:   $IR_PARQUET"
echo "Y columns:    $YCOLS"
echo "Output:       $OUT_PARQUET"

python scripts/aggregate_to_country.py \
    --input "$IR_PARQUET" \
    --output "$OUT_PARQUET" \
    --y-cols $YCOLS

echo ""
ls -lh "$OUT_PARQUET"
