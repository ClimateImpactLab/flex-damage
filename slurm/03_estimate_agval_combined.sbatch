#!/bin/bash
#SBATCH --job-name=agval_est_combined
#SBATCH --account=cil
#SBATCH --partition=amd
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=120G
#SBATCH --time=06:00:00
#SBATCH --output=slurm/logs/%x_%j.out
#SBATCH --error=slurm/logs/%x_%j.err

source slurm/_env.sh

FULL_PARQUET="$SCRATCH_BASE/agval/full/agval_aggregated_full.parquet"
if [ ! -f "$FULL_PARQUET" ]; then
    echo "ERROR: full parquet not found at $FULL_PARQUET"
    echo "Run 01_prep_agval_mc.sbatch first."
    exit 1
fi

python scripts/run.py configs/agriculture_value/combined_main_spec.yaml --verbose

echo ""
echo "Outputs:"
ls -lh /project/cil/gcp/flex_damage_funcs/parameters/agriculture_value__combined_main_spec__*
