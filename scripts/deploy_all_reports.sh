#!/bin/bash
# Copy all rendered HTMLs (IR + country + country_unconstrained) into the
# flex-damage-reports GitHub Pages repo, refresh index.html, commit, push.
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

# Copy IR + country + country_unconstrained reports. Skip:
#   * sector_vignette.html: Quarto template artifact
#   * agriculture_value*:   agval (excluded per project decision)
#   * *_country_collapsed*: superseded by _country / _country_unconstrained
#   * *_country_ir.html:    deprecated naming
copied=0
for pat in "*_ir.html" "*_country.html" "*_country_unconstrained.html"; do
    for html in "$OUTPUT_DIR"/$pat; do
        [ -f "$html" ] || continue
        name=$(basename "$html")
        case "$name" in
            sector_vignette.html|agriculture_value*|*_country_collapsed*|*_country_ir.html)
                continue ;;
        esac
        cp "$html" "./$name"
        echo "  copied: $name ($(ls -lh "$name" | awk '{print $5}'))"
        copied=$((copied + 1))
    done
done
echo "Copied $copied HTML files"

# Regenerate index, grouped by sector with sub-resolution links.
python3 - <<'PY'
import glob
import re
import os

# Parse each html into (sector, sub, resolution, label)
RES_LABEL = {
    "ir":                  "Impact Region",
    "country":             "Country",
    "country_unconstrained": "Country (unconstrained, diagnostic)",
}
def parse(name):
    stem = name.replace(".html","")
    # strip leading _ir / _country / _country_unconstrained / _country_collapsed
    for suffix, res in [
        ("_country_unconstrained", "country_unconstrained"),
        ("_country_collapsed",     "country_collapsed"),
        ("_country",               "country"),
        ("_ir",                    "ir"),
    ]:
        if stem.endswith(suffix):
            base = stem[: -len(suffix)]
            # base = "<sector>_<sub>" or "<sector>_<multi_word_sub>"
            parts = base.split("_", 1)
            if len(parts) == 2:
                return parts[0], parts[1], res
    return None

groups = {}  # (sector) -> list of (sub, res, file)
for r in sorted(r for r in glob.glob('*.html') if r != 'index.html'):
    p = parse(r)
    if not p:
        continue
    sector, sub, res = p
    groups.setdefault(sector, []).append((sub, res, r))

html = ['<html><head><title>FlexDamage Reports</title>',
        '<style>body{font-family:sans-serif;max-width:980px;margin:2em auto;padding:0 1em}',
        'h1{color:#1f4e79}h2{color:#1f4e79;border-bottom:1px solid #d0d7de;padding-bottom:.3em;margin-top:2em}',
        'table{border-collapse:collapse;width:100%;margin:0.5em 0}',
        'th,td{padding:6px 10px;border-bottom:1px solid #eee;text-align:left}',
        'th{background:#f6f8fa;font-weight:600;font-size:.95em}',
        'a{color:#2c5c8f;text-decoration:none}a:hover{text-decoration:underline}',
        '.meta{color:#666;font-size:0.9em;margin-top:3em;border-top:1px solid #d0d7de;padding-top:1em}</style>',
        '</head><body>',
        '<h1>Flexible Damage Function Reports</h1>',
        '<p>Climate Impact Lab &mdash; diagnostic reports for region-specific damage functions, '
        'estimated at impact-region and country resolutions. '
        '<a href="https://climateimpactlab.github.io/flex-damage/units/">Units &amp; methodology</a> | '
        '<a href="https://zenodo.org/concept/19199919">Parameters on Zenodo</a></p>']

# Build a (sector, sub) → {res: file} map, then render rows
for sector in sorted(groups):
    by_sub = {}
    for sub, res, f in groups[sector]:
        by_sub.setdefault(sub, {})[res] = f
    html.append(f'<h2>{sector.title()}</h2>')
    html.append('<table><thead><tr><th>Subsector</th>'
                '<th>Impact Region</th><th>Country</th>'
                '<th>Country (unconstrained, diagnostic)</th></tr></thead><tbody>')
    for sub in sorted(by_sub):
        ir   = by_sub[sub].get("ir")
        co   = by_sub[sub].get("country")
        un   = by_sub[sub].get("country_unconstrained")
        cells = [
            f'<td>{sub.replace("_"," ").title()}</td>',
            f'<td>{("<a href="+chr(34)+ir+chr(34)+">view</a>") if ir else "n/a"}</td>',
            f'<td>{("<a href="+chr(34)+co+chr(34)+">view</a>") if co else "n/a"}</td>',
            f'<td>{("<a href="+chr(34)+un+chr(34)+">view</a>") if un else "n/a"}</td>',
        ]
        html.append('<tr>' + ''.join(cells) + '</tr>')
    html.append('</tbody></table>')

html += ['<p class="meta">',
         '  <a href="https://climateimpactlab.github.io/flex-damage/">Documentation</a> | ',
         '  <a href="https://github.com/ClimateImpactLab/flex-damage">GitHub repo</a> | ',
         '  <a href="https://zenodo.org/concept/19199919">Zenodo concept</a>',
         '</p></body></html>']
open('index.html','w').write('\n'.join(html))
print(f"Wrote index.html with {sum(len(g) for g in groups.values())} entries across {len(groups)} sectors")
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

eval $(ssh-agent -s) >/dev/null
ssh-add ~/.ssh/id_rsa 2>/dev/null || echo "(ssh-agent: no id_rsa or already added)"
git push origin main

echo ""
echo "Published. Reports live at:"
echo "  https://c1587s.github.io/flex-damage-reports/"
