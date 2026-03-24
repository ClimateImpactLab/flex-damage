#!/bin/bash
set -e

FLEXDAMAGE="$(cd "$(dirname "$0")/.." && pwd)"
PARAMS_DIR="${1:-/project/cil/gcp/flex_damage_funcs/parameters}"
DATA_BASE="${2:-/project/cil/home_dirs/scadavidsanchez/projects/flex-damages-data}"
REPORTS_REPO="${3:-/project/cil/home_dirs/scadavidsanchez/projects/ag-flex-damage-functions/flex-damage-reports}"

export PATH=$HOME/quarto-1.6.42/bin:$HOME/bin:$PATH

echo "FlexDamage Report Generator"
echo "Parameters: $PARAMS_DIR"
echo "Source data: $DATA_BASE"
echo "Reports repo: $REPORTS_REPO"
echo ""

# Discover available crops from parameter files
CROPS=$(ls ${PARAMS_DIR}/agriculture__*__regional_parameters.csv 2>/dev/null | \
    sed 's/.*agriculture__//' | sed 's/__regional_parameters.csv//')

if [ -z "$CROPS" ]; then
    echo "No parameter files found in $PARAMS_DIR"
    exit 1
fi

echo "Found crops: $CROPS"
echo ""

FAILED=""
for crop in $CROPS; do
    echo "========== $crop =========="

    CSV="${PARAMS_DIR}/agriculture__${crop}__regional_parameters.csv"
    JSON="${PARAMS_DIR}/agriculture__${crop}__global_results.json"
    ZARR="${DATA_BASE}/agriculture/${crop}/ir/ir.zarr"

    # Check files exist
    if [ ! -f "$CSV" ]; then
        echo "SKIP: no parameters at $CSV"
        FAILED="$FAILED $crop(no_params)"
        continue
    fi

    # Build source data arg
    SOURCE_ARG=""
    if [ -d "$ZARR" ]; then
        SOURCE_ARG="--source-data $ZARR"
    else
        echo "WARNING: no zarr at $ZARR (F2 comparison will be skipped)"
    fi

    # Determine output path
    if [ -d "$REPORTS_REPO" ]; then
        OUTPUT="${REPORTS_REPO}/agriculture_${crop}_ir.html"
    else
        OUTPUT="${FLEXDAMAGE}/reports/_output/agriculture_${crop}_ir.html"
    fi

    # Render using the wrapper script
    if python ${FLEXDAMAGE}/scripts/render_report.py \
        --sector agriculture \
        --subsector $crop \
        --params-csv "$CSV" \
        --global-json "$JSON" \
        $SOURCE_ARG \
        --output "$OUTPUT"; then

        SIZE=$(ls -lh "$OUTPUT" | awk '{print $5}')
        echo "$crop OK ($SIZE)"
    else
        echo "$crop FAILED"
        FAILED="$FAILED $crop(render_failed)"
    fi

    echo ""
done

# Update index in reports repo
if [ -d "$REPORTS_REPO" ]; then
    cd $REPORTS_REPO
    python3 -c "
import os, glob
reports = sorted([f for f in glob.glob('agriculture_*_ir.html')])
html = '''<!DOCTYPE html>
<html><head><title>FlexDamage Reports</title></head>
<body>
<h1>Flexible Damage Function Reports</h1>
<p>Climate Impact Lab</p>
<h2>Agriculture (IR level)</h2>
<ul>
'''
for r in reports:
    name = r.replace('agriculture_','').replace('_ir.html','').replace('_',' ').title()
    html += f'<li><a href=\"{r}\">{name}</a></li>\n'
html += '''</ul>
<p><a href=\"https://zenodo.org/records/19199919\">Parameters (Zenodo)</a> |
<a href=\"https://climateimpactlab.github.io/flex-damage/\">Documentation</a></p>
</body></html>'''
open('index.html','w').write(html)
print('Updated index.html')
"
fi

echo ""
echo "========================================"
echo "Complete. Reports in: $REPORTS_REPO"
if [ -n "$FAILED" ]; then
    echo "Failed:$FAILED"
fi
echo "========================================"
