#!/bin/bash
#SBATCH --job-name=energy_prep_mc
#SBATCH --account=cil
#SBATCH --partition=amd
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=120G
#SBATCH --time=04:00:00
#SBATCH --output=slurm/logs/%x_%j.out
#SBATCH --error=slurm/logs/%x_%j.err

source slurm/_env.sh

mkdir -p "$SCRATCH_BASE/energy/full"

# 12 workers to avoid fork-inherit OOM. Scenario-by-scenario processing
# inside the script releases memory between scenario groups.
python scripts/build_energy_input.py \
    --mode full \
    --output-dir "$SCRATCH_BASE/energy/full" \
    --n-workers 12

echo "Done. Output:"
ls -lh "$SCRATCH_BASE/energy/full/"
