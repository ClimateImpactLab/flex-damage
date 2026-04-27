#!/bin/bash
#SBATCH --job-name=labor_est_low_risk
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

FULL_PARQUET="$SCRATCH_BASE/labor/full/labor_aggregated_full.parquet"
if [ ! -f "$FULL_PARQUET" ]; then
    echo "ERROR: full parquet not found at $FULL_PARQUET"
    echo "Run 01_prep_labor_mc.sbatch first."
    exit 1
fi

python scripts/run.py configs/labor/low_risk.yaml --verbose

echo ""
echo "Outputs:"
ls -lh /project/cil/gcp/flex_damage_funcs/parameters/labor__low_risk__*
