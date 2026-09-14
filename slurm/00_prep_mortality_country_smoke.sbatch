#!/bin/bash
#SBATCH --job-name=mortality_country_prep_smoke
#SBATCH --account=cil
#SBATCH --partition=caslake
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=slurm/logs/%x_%j.out
#SBATCH --error=slurm/logs/%x_%j.err

source slurm/_env.sh

OUT_DIR="$SCRATCH_BASE/mortality/country_smoke"
mkdir -p "$OUT_DIR"

python scripts/build_mortality_country_input.py \
    --mode smoke \
    --output-dir "$OUT_DIR" \
    --n-workers 1

echo "Done. Output:"
ls -lh "$OUT_DIR/"
