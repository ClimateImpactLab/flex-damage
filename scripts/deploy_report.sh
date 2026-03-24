#!/bin/bash
set -e

# Config
REPORTS_REPO="/project/cil/home_dirs/scadavidsanchez/projects/ag-flex-damage-functions/flex-damage-reports"
FLEXDAMAGE="/project/cil/home_dirs/scadavidsanchez/projects/ag-flex-damage-functions/flexdamage-v3"
export PATH=$HOME/quarto-1.6.42/bin:$HOME/bin:$PATH

SECTOR=${1:?"Usage: deploy_report.sh <sector> <subsector>"}
SUBSECTOR=${2:?"Usage: deploy_report.sh <sector> <subsector>"}
PARAMS_DIR=${3:-"/project/cil/gcp/flex_damage_funcs/parameters"}
SOURCE_DATA=${4:-""}

REPORT_NAME="${SECTOR}_${SUBSECTOR}_ir"
PARAMS_CSV="${PARAMS_DIR}/${SECTOR}__${SUBSECTOR}__regional_parameters.csv"
GLOBAL_JSON="${PARAMS_DIR}/${SECTOR}__${SUBSECTOR}__global_results.json"

echo "Building report: ${REPORT_NAME}"

# 1. Render
cd ${FLEXDAMAGE}/reports

QUARTO_ARGS="--to html --embed-resources \
    -P sector:${SECTOR} -P subsector:${SUBSECTOR} \
    -P params_csv:${PARAMS_CSV} \
    -P global_json:${GLOBAL_JSON}"

if [ -n "$SOURCE_DATA" ]; then
    QUARTO_ARGS="${QUARTO_ARGS} -P source_data:${SOURCE_DATA}"
fi

quarto render sector_vignette.qmd ${QUARTO_ARGS}

SIZE=$(ls -lh _output/sector_vignette.html | awk '{print $5}')
echo "Report size: ${SIZE}"

# 2. Copy to reports repo
cp _output/sector_vignette.html ${REPORTS_REPO}/${REPORT_NAME}.html

# 3. Update index
cd ${REPORTS_REPO}
python3 -c "
import os, glob
reports = sorted(glob.glob('*.html'))
reports = [r for r in reports if r != 'index.html']
html = '<html><head><title>FlexDamage Reports</title></head><body>\n'
html += '<h1>Flexible Damage Function Reports</h1>\n'
html += '<p>Climate Impact Lab</p>\n<ul>\n'
for r in reports:
    name = r.replace('.html','').replace('_',' ').title()
    html += f'<li><a href=\"{r}\">{name}</a></li>\n'
html += '</ul>\n'
html += '<p><a href=\"https://zenodo.org/records/19199919\">Parameters (Zenodo)</a> | '
html += '<a href=\"https://climateimpactlab.github.io/flex-damage/\">Documentation</a></p>\n'
html += '</body></html>'
open('index.html','w').write(html)
"

# 4. Push
git add -A
git commit -m "update ${REPORT_NAME}"
eval $(ssh-agent -s) && ssh-add ~/.ssh/id_rsa
git push origin main

echo "Deployed: https://c1587s.github.io/flex-damage-reports/${REPORT_NAME}.html"
