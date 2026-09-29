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

# Copy every rendered report. Skip only non-reports:
#   * sector_vignette.html: Quarto template artifact
#   * *_country_ir.html:    deprecated naming
copied=0
for pat in "*_ir.html" "*_country.html" "*_country_collapsed.html" "*_country_unconstrained.html"; do
    for html in "$OUTPUT_DIR"/$pat; do
        [ -f "$html" ] || continue
        name=$(basename "$html")
        case "$name" in
            sector_vignette.html|*_country_ir.html)
                continue ;;
        esac
        cp "$html" "./$name"
        echo "  copied: $name ($(ls -lh "$name" | awk '{print $5}'))"
        copied=$((copied + 1))
    done
done
echo "Copied $copied HTML files"

# Regenerate index from whatever reports are present (shared generator)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/update_index.py" "$REPORTS_REPO"

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
