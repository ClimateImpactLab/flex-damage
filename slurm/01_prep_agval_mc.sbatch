#!/bin/bash
#SBATCH --job-name=agval_prep_mc
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

mkdir -p "$SCRATCH_BASE/agval/full"

# Note: 12 workers to avoid OOM from process fork memory inheritance.
python scripts/build_agval_input.py \
    --mode full \
    --output-dir "$SCRATCH_BASE/agval/full" \
    --n-workers 12

echo "Done. Output:"
ls -lh "$SCRATCH_BASE/agval/full/"
