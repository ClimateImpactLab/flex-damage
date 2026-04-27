#!/bin/bash
#SBATCH --job-name=labor_est_smoke
#SBATCH --account=cil
#SBATCH --partition=caslake
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=slurm/logs/%x_%j.out
#SBATCH --error=slurm/logs/%x_%j.err

source slurm/_env.sh

# Smoke parquet has only one scenario; pipeline still runs but with limited F2 coverage.
# Temporarily point each config at the smoke parquet by using a sed override.
SMOKE_PARQUET="$SCRATCH_BASE/labor/smoke/labor_aggregated_smoke.parquet"
if [ ! -f "$SMOKE_PARQUET" ]; then
    echo "ERROR: smoke parquet not found at $SMOKE_PARQUET"
    echo "Run 00_prep_labor_smoke.sbatch first."
    exit 1
fi

# Generate temp configs pointing at smoke parquet
TMPCFG=$(mktemp -d)
trap 'rm -rf "$TMPCFG"' EXIT

for sub in combined high_risk low_risk; do
    sed "s|labor_aggregated_full.parquet|labor_aggregated_smoke.parquet|g; s|/full/|/smoke/|g" \
        "configs/labor/${sub}.yaml" > "$TMPCFG/${sub}.yaml"
done

for sub in combined high_risk low_risk; do
    echo ""
    echo "=============================="
    echo "Estimating labor ${sub} (smoke)"
    echo "=============================="
    python scripts/run.py "$TMPCFG/${sub}.yaml" --verbose || echo "WARNING: ${sub} exited non-zero (check outputs)"
done

echo ""
echo "Outputs:"
ls -lh /project/cil/gcp/flex_damage_funcs/parameters/labor__*
