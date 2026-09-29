#!/bin/bash
# Render every parameter set that has no corresponding report HTML, copy the
# outputs into the flex-damage-reports repo, and refresh index.html.
#
# Discovery-driven and idempotent: compares the parameters directory against
# the reports repo and renders only what's missing, so it can be re-run after
# partial failures. Designed for a SLURM compute node.
#
# Usage:
#   bash scripts/render_missing_reports.sh              # render all missing
#   bash scripts/render_missing_reports.sh --dry-run    # list what would render
#
# Naming convention (matches render_report.py):
#   IR resolution:            {sector}_{subsector}_ir.html
#   country/collapsed/etc.:   {sector}_{subsector}.html
#   (a subsector "contains _country" iff it is non-IR)
set -uo pipefail

FLEXDAMAGE="$(cd "$(dirname "$0")/.." && pwd)"
PARAMS_DIR="${PARAMS_DIR:-/project/cil/gcp/flex_damage_funcs/parameters}"
REPORTS_REPO="${REPORTS_REPO:-/project/cil/home_dirs/scadavidsanchez/projects/ag-flex-damage-functions/flex-damage-reports}"

export PATH="$HOME/quarto-1.6.42/bin:$HOME/bin:$PATH"

DRY_RUN=0
[ "${1:-}" == "--dry-run" ] && DRY_RUN=1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "FlexDamage missing-report generator"
log "  Flexdamage:  $FLEXDAMAGE"
log "  Parameters:  $PARAMS_DIR"
log "  Reports:     $REPORTS_REPO"
log "  Quarto:      $(command -v quarto || echo 'NOT FOUND')"

if ! command -v quarto >/dev/null; then
    log "ERROR: quarto not on PATH"; exit 1
fi
[ -d "$PARAMS_DIR" ]    || { log "ERROR: no parameters dir at $PARAMS_DIR"; exit 1; }
[ -d "$REPORTS_REPO" ]  || { log "ERROR: no reports repo at $REPORTS_REPO"; exit 1; }

# ---------------------------------------------------------------------------
# 1. Discover missing reports
# ---------------------------------------------------------------------------
MISSING=()   # entries: "sector|subsector|report_name"
for csv in "$PARAMS_DIR"/*__regional_parameters.csv; do
    [ -f "$csv" ] || continue
    base=$(basename "$csv" __regional_parameters.csv)   # {sector}__{subsector}
    sector="${base%%__*}"
    subsector="${base#*__}"

    if [[ "$subsector" == *_country* ]]; then
        report_name="${sector}_${subsector}.html"
    else
        report_name="${sector}_${subsector}_ir.html"
    fi

    if [ ! -f "$REPORTS_REPO/$report_name" ]; then
        MISSING+=("${sector}|${subsector}|${report_name}")
    fi
done

if [ ${#MISSING[@]} -eq 0 ]; then
    log "Nothing to do: every parameter set already has a report."
    exit 0
fi

log "Missing reports (${#MISSING[@]}):"
for entry in "${MISSING[@]}"; do
    log "  - ${entry##*|}"
done

if [ "$DRY_RUN" -eq 1 ]; then
    log "DRY RUN: stopping before render."
    exit 0
fi

# ---------------------------------------------------------------------------
# 2-3. Render each missing report directly into the reports repo
# ---------------------------------------------------------------------------
OK=()
FAILED=()

for entry in "${MISSING[@]}"; do
    sector="${entry%%|*}"
    rest="${entry#*|}"
    subsector="${rest%%|*}"
    report_name="${entry##*|}"

    csv="$PARAMS_DIR/${sector}__${subsector}__regional_parameters.csv"
    gjson="$PARAMS_DIR/${sector}__${subsector}__global_results.json"
    output="$REPORTS_REPO/$report_name"

    log "========== ${sector}/${subsector} =========="

    if [ ! -f "$gjson" ]; then
        log "FAIL: no global_results.json at $gjson"
        FAILED+=("${report_name} (no_global_json)")
        continue
    fi

    # Source data: read the `source:` line from this subsector's config.
    # Missing config or missing data => render without --source-data
    # (the vignette then skips the F2 raw-vs-fit comparison section).
    config="$FLEXDAMAGE/configs/${sector}/${subsector}.yaml"
    source_args=()
    if [ -f "$config" ]; then
        src=$(grep -E '^[[:space:]]*source:' "$config" | head -1 | sed 's/.*source:[[:space:]]*//' | tr -d '"')
        if [ -n "$src" ] && [ -e "$src" ]; then
            source_args=(--source-data "$src")
            log "  source data: $src"
        else
            log "  WARNING: source data not found ('$src') - F2 comparison will be skipped"
        fi
    else
        log "  WARNING: no config at $config - F2 comparison will be skipped"
    fi

    start=$SECONDS
    if python "$FLEXDAMAGE/scripts/render_report.py" \
        --sector "$sector" \
        --subsector "$subsector" \
        --params-csv "$csv" \
        --global-json "$gjson" \
        "${source_args[@]}" \
        --output "$output"; then
        size=$(ls -lh "$output" | awk '{print $5}')
        log "OK: $report_name ($size, $((SECONDS - start))s)"
        OK+=("${report_name} ${size}")
    else
        log "FAIL: render failed for $report_name"
        FAILED+=("${report_name} (render_failed)")
        rm -f "$output"   # don't leave partial output masking the failure
    fi
done

# ---------------------------------------------------------------------------
# 4. Regenerate index.html (matrix incl. collapse-MC + agriculture_value)
# ---------------------------------------------------------------------------
log "Regenerating index.html..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/update_index.py" "$REPORTS_REPO"

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
echo ""
log "========================================"
log "Summary: ${#OK[@]} rendered, ${#FAILED[@]} failed (of ${#MISSING[@]} missing)"
if [ ${#OK[@]} -gt 0 ]; then
    log "Succeeded:"
    for r in "${OK[@]}"; do log "  OK   $r"; done
fi
if [ ${#FAILED[@]} -gt 0 ]; then
    log "Failed:"
    for r in "${FAILED[@]}"; do log "  FAIL $r"; done
fi
log "Reports repo: $REPORTS_REPO"
log "NOTE: index.html updated locally; commit + push the reports repo to publish."
log "========================================"

[ ${#FAILED[@]} -eq 0 ] || exit 1
