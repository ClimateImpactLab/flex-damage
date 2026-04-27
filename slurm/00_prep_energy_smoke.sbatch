#!/bin/bash
#SBATCH --job-name=energy_prep_smoke
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

mkdir -p "$SCRATCH_BASE/energy/smoke"

python scripts/build_energy_input.py \
    --mode smoke \
    --output-dir "$SCRATCH_BASE/energy/smoke" \
    --n-workers 1

echo "Done. Output:"
ls -lh "$SCRATCH_BASE/energy/smoke/"
