#!/bin/bash
set -e

FLEXDAMAGE="$(cd "$(dirname "$0")/.." && pwd)"
PARAMS_DIR="${1:-/project/cil/gcp/flex_damage_funcs/parameters}"
DATA_BASE="${2:-/project/cil/home_dirs/scadavidsanchez/projects/flex-damages-data}"
REPORTS_REPO="${3:-/project/cil/home_dirs/scadavidsanchez/projects/ag-flex-damage-functions/flex-damage-reports}"

export PATH=$HOME/quarto-1.6.42/bin:$HOME/bin:$PATH

echo "FlexDamage Full Deploy"
echo ""

# Step 1: Run estimation for all crops
echo "=== Step 1: Estimation ==="
cd $FLEXDAMAGE
for config in configs/agriculture/*.yaml; do
    crop=$(basename $config .yaml)
    echo "Estimating $crop..."
    python scripts/run.py $config 2>&1 | tail -3
done

# Step 2: Generate reports
echo ""
echo "=== Step 2: Reports ==="
bash scripts/generate_all_reports.sh "$PARAMS_DIR" "$DATA_BASE" "$REPORTS_REPO"

# Step 3: Push reports
echo ""
echo "=== Step 3: Push reports ==="
cd $REPORTS_REPO
git add -A
git commit -m "update all reports $(date +%Y-%m-%d)" || echo "nothing to commit"
git push origin main || echo "push failed - do manually"

# Step 4: Update Zenodo (draft)
echo ""
echo "=== Step 4: Zenodo ==="
cd $FLEXDAMAGE
python scripts/zenodo_upload.py --build \
    --input-dir $PARAMS_DIR \
    --version $(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
echo "To upload: python scripts/zenodo_upload.py --draft"

# Step 5: Update docs
echo ""
echo "=== Step 5: Docs ==="
mkdocs build && mkdocs gh-deploy --dirty

echo ""
echo "========================================"
echo "Deploy complete."
echo "Reports: https://c1587s.github.io/flex-damage-reports/"
echo "Docs: https://climateimpactlab.github.io/flex-damage/"
echo "Zenodo: run 'python scripts/zenodo_upload.py --draft' to upload"
echo "========================================"
