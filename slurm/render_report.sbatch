#!/bin/bash
# Render a Quarto sector report via SLURM.
#
# Usage:
#   sbatch --export=ALL,SECTOR=mortality,SUBSECTOR=allcause,\
# PARAMS_CSV=/path/to/params.csv,\
# GLOBAL_JSON=/path/to/global.json,\
# SOURCE_DATA=/path/to/source.parquet \
#       slurm/render_report.sbatch
#
#SBATCH --job-name=render_report
#SBATCH --account=cil
#SBATCH --partition=amd
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=60G
#SBATCH --time=02:00:00
#SBATCH --output=slurm/logs/%x_%j.out
#SBATCH --error=slurm/logs/%x_%j.err

source slurm/_env.sh

# Quarto binary + user's bin dir on PATH (quarto is NOT a pip package)
export PATH=$HOME/quarto-1.6.42/bin:$HOME/bin:$PATH

: "${SECTOR:?Must set SECTOR via sbatch --export=SECTOR=...}"
: "${SUBSECTOR:?Must set SUBSECTOR via sbatch --export=SUBSECTOR=...}"
: "${PARAMS_CSV:?Must set PARAMS_CSV via sbatch --export=...}"
: "${GLOBAL_JSON:?Must set GLOBAL_JSON via sbatch --export=...}"
: "${SOURCE_DATA:?Must set SOURCE_DATA via sbatch --export=...}"

echo "Sector:       $SECTOR"
echo "Subsector:    $SUBSECTOR"
echo "Params CSV:   $PARAMS_CSV"
echo "Global JSON:  $GLOBAL_JSON"
echo "Source data:  $SOURCE_DATA"

python scripts/render_report.py \
    --sector "$SECTOR" \
    --subsector "$SUBSECTOR" \
    --params-csv "$PARAMS_CSV" \
    --global-json "$GLOBAL_JSON" \
    --source-data "$SOURCE_DATA"

echo ""
echo "Output:"
# Country subsectors omit the `_ir` suffix; IR subsectors keep it.
case "$SUBSECTOR" in
    *_country|*_country_collapsed) ls -lh reports/_output/${SECTOR}_${SUBSECTOR}.html 2>&1 ;;
    *)                              ls -lh reports/_output/${SECTOR}_${SUBSECTOR}_ir.html 2>&1 ;;
esac
