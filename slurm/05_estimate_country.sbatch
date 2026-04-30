#!/bin/bash
# Run flexdamage estimation on a country-level config.
# Country data is tiny (~250 regions x 90 years x scenarios) so this is fast.
#
# Usage:
#   sbatch --export=ALL,CONFIG=configs/mortality/allcause_country.yaml \
#       slurm/05_estimate_country.sbatch
#
#SBATCH --job-name=estimate_country
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

: "${CONFIG:?Must set CONFIG via sbatch --export (e.g. configs/mortality/allcause_country.yaml)}"

echo "Config: $CONFIG"
python scripts/run.py "$CONFIG" --verbose

echo ""
echo "Outputs (filtered by config):"
SUB=$(python -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['sector']['subsector'])")
SEC=$(python -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['sector']['name'])")
ls -lh /project/cil/gcp/flex_damage_funcs/parameters/${SEC}__${SUB}__* 2>&1
