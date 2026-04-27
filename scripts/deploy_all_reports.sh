#!/bin/bash
# Copy all rendered HTMLs from reports/_output into the flex-damage-reports
# GitHub Pages repo, refresh index.html, commit, and push.
#
# Usage:
#   bash scripts/deploy_all_reports.sh
#   bash scripts/deploy_all_reports.sh --dry-run   # copy + update index, skip git push
set -euo pipefail

REPORTS_REPO="/project/cil/home_dirs/scadavidsanchez/projects/ag-flex-damage-functions/flex-damage-reports"
FLEXDAMAGE="/project/cil/home_dirs/scadavidsanchez/projects/ag-flex-damage-functions/flexdamage-v3"

DRY_RUN=0
if [ "${1:-}" == "--dry-run" ]; then
    DRY_RUN=1
    echo "DRY RUN - will not git push"
fi

OUTPUT_DIR="${FLEXDAMAGE}/reports/_output"
if [ ! -d "$OUTPUT_DIR" ]; then
    echo "ERROR: no output dir at $OUTPUT_DIR"; exit 1
fi

cd "$REPORTS_REPO"

# Copy every *_ir.html (skip sector_vignette.html which is a template artifact)
copied=0
for html in "$OUTPUT_DIR"/*_ir.html; do
    [ -f "$html" ] || continue
    name=$(basename "$html")
    cp "$html" "./$name"
    echo "  copied: $name ($(ls -lh $name | awk '{print $5}'))"
    copied=$((copied + 1))
done
echo "Copied $copied HTML files"

# Regenerate index
python3 - <<'PY'
import glob, os
reports = sorted(r for r in glob.glob('*.html') if r != 'index.html')
html = ['<html><head><title>FlexDamage Reports</title>',
        '<style>body{font-family:sans-serif;max-width:800px;margin:2em auto;padding:0 1em}',
        'h1{color:#1f4e79}ul{line-height:1.7}a{color:#2c5c8f;text-decoration:none}',
        'a:hover{text-decoration:underline}.meta{color:#666;font-size:0.9em;margin-top:2em}</style>',
        '</head><body>',
        '<h1>Flexible Damage Function Reports</h1>',
        '<p>Climate Impact Lab &mdash; Impact-Region-level damage function diagnostic reports.</p>',
        '<ul>']
for r in reports:
    name = r.replace('_ir.html','').replace('_',' ').title()
    html.append(f'  <li><a href="{r}">{name}</a></li>')
html += ['</ul>',
         '<p class="meta">',
         '  <a href="https://zenodo.org/records/19225233">Parameters (Zenodo)</a> | ',
         '  <a href="https://climateimpactlab.github.io/flex-damage/">Documentation</a> | ',
         '  <a href="https://github.com/ClimateImpactLab/flex-damage">GitHub</a>',
         '</p></body></html>']
open('index.html','w').write('\n'.join(html))
print(f"Wrote index.html with {len(reports)} entries")
PY

git add -A
if git diff --cached --quiet; then
    echo "No changes to commit."
    exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
    echo ""
    echo "DRY RUN: staged diff (not committed, not pushed):"
    git diff --cached --stat
    git reset --mixed HEAD > /dev/null
    exit 0
fi

git commit -m "deploy: refresh $copied reports"

# Make sure ssh-agent is loaded for the push
eval $(ssh-agent -s) >/dev/null
ssh-add ~/.ssh/id_rsa 2>/dev/null || echo "(ssh-agent: no id_rsa or already added)"
git push origin main

echo ""
echo "Published. Reports live at:"
echo "  https://c1587s.github.io/flex-damage-reports/"
