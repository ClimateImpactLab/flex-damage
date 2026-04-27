#!/bin/bash
#SBATCH --job-name=labor_prep_mc
#SBATCH --account=cil
#SBATCH --partition=amd
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=120G
#SBATCH --time=08:00:00
#SBATCH --output=slurm/logs/%x_%j.out
#SBATCH --error=slurm/logs/%x_%j.err

source slurm/_env.sh

mkdir -p "$SCRATCH_BASE/labor/full"

# Note: using fewer workers than cpus-per-task on purpose.
# Each worker forks a ~2 GB Python process; 32 workers OOMs at 120 GB.
# 12 workers gives good parallelism without memory blow-up.
python scripts/build_labor_input.py \
    --mode full \
    --output-dir "$SCRATCH_BASE/labor/full" \
    --n-workers 12

echo "Done. Output:"
ls -lh "$SCRATCH_BASE/labor/full/"
