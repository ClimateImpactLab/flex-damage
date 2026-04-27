#!/bin/bash
# Benchmark pyfixest vs R fixest for the gamma FE regression.
#
# Usage:
#   sbatch --export=ALL,INPUT=/path/to.parquet,YCOL=adjusted_mortality slurm/bench_gamma.sbatch
#   sbatch --export=ALL,INPUT=/path/to.parquet,YCOL=labor_combined  slurm/bench_gamma.sbatch
#
#SBATCH --job-name=bench_gamma
#SBATCH --account=cil
#SBATCH --partition=cil
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --mem=30G
#SBATCH --time=02:00:00
#SBATCH --output=slurm/logs/%x_%j.out
#SBATCH --error=slurm/logs/%x_%j.err

source slurm/_env.sh

# Load R for fixest (packages live in user's ~/R/x86_64-pc-linux-gnu-library)
module load R || echo "WARNING: module load R failed; fixest portion will skip"

: "${INPUT:?Must set INPUT via sbatch --export=INPUT=/path.parquet}"
: "${YCOL:?Must set YCOL via sbatch --export=YCOL=<column>}"

# Save comparison artifact alongside the log (unique per job)
OUT_DIR="${PROJECT_ROOT}/slurm/logs/bench_results"
mkdir -p "$OUT_DIR"
OUT_JSON="${OUT_DIR}/bench_${YCOL}_${SLURM_JOB_ID}.json"

python scripts/benchmark_gamma.py \
    --input "$INPUT" \
    --y "$YCOL" \
    --r-threads "${SLURM_CPUS_PER_TASK:-32}" \
    --output-json "$OUT_JSON"

echo ""
echo "Benchmark JSON saved to: $OUT_JSON"
