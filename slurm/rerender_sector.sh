#!/bin/bash
# Re-render existing reports for a sector (no prep, no estimation).
# Picks up QMD fixes (y-axis, header format) using already-written params.
#
# Usage:
#   bash slurm/rerender_sector.sh mortality           # IR + country (keep-MC)
#   bash slurm/rerender_sector.sh labor               # IR + country, all 3 subs
#   bash slurm/rerender_sector.sh energy              # IR + country, all 3 subs
#   bash slurm/rerender_sector.sh agriculture         # IR + country, all 8 crops
#
# Pass --include-collapsed to also re-render the *_country_collapsed reports.
set -euo pipefail

SECTOR="${1:?Usage: $0 <sector> [--include-collapsed]}"
INCLUDE_COLLAPSED=0
shift || true
for a in "$@"; do
    [[ "$a" == "--include-collapsed" ]] && INCLUDE_COLLAPSED=1
done

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
[[ -f slurm/_env.sh ]] && source slurm/_env.sh

RENDER_PARTITION="${RENDER_PARTITION:-cil}"
PARAMS_DIR="/project/cil/gcp/flex_damage_funcs/parameters"

mkdir -p slurm/logs

source_data_for() {
    # Read data.source straight out of the YAML config so paths can't drift.
    local sec="$1" sub="$2"
    local cfg="configs/${sec}/${sub}.yaml"
    if [[ ! -f "$cfg" ]]; then
        echo ""
        return
    fi
    python3 -c "import yaml,sys; print(yaml.safe_load(open('$cfg')).get('data',{}).get('source',''))" 2>/dev/null
}

submit_render() {
    local sector="$1" sub="$2"
    local pcsv="$PARAMS_DIR/${sector}__${sub}__regional_parameters.csv"
    local gjson="$PARAMS_DIR/${sector}__${sub}__global_results.json"
    if [[ ! -f "$pcsv" ]]; then
        echo "  SKIP $sector/$sub (no params at $pcsv)"
        return
    fi
    local sdata; sdata=$(source_data_for "$sector" "$sub")
    local jid
    # Memory budget. IR renders fit in 50G. Country-resolution renders for
    # the big keep-MC parquets (agriculture ~130M rows, labor ~133M rows
    # after IR-pop-weight aggregation) need 90G. Energy/mortality country are
    # small enough for 50G but we use 90G across the board for country to
    # keep this simple and avoid the labor OOM we saw at 50G.
    local mem="50G"
    [[ "$sub" == *_country* ]] && mem="90G"
    jid=$(sbatch --parsable \
        --job-name="render_${sector}_${sub}" \
        --partition="$RENDER_PARTITION" \
        --mem=$mem --time=02:00:00 \
        --export=ALL,SECTOR=$sector,SUBSECTOR=$sub,PARAMS_CSV=$pcsv,GLOBAL_JSON=$gjson,SOURCE_DATA=$sdata \
        slurm/render_report.sbatch)
    echo "  render_${sector}_${sub} -> $jid (mem=$mem)"
}

# Per-sector subsector lists
case "$SECTOR" in
    mortality)   SUBS=(allcause) ;;
    labor)       SUBS=(combined high_risk low_risk) ;;
    energy)      SUBS=(total electricity non_electricity) ;;
    agriculture) SUBS=(corn rice soy sorghum cassava wheat_combined wheat_spring wheat_winter) ;;
    *) echo "Unknown sector: $SECTOR"; exit 2 ;;
esac

echo "=== RE-RENDER $SECTOR (partition=$RENDER_PARTITION) ==="
echo "  -- IR --"
for s in "${SUBS[@]}"; do submit_render "$SECTOR" "$s"; done
echo "  -- country (keep-MC) --"
for s in "${SUBS[@]}"; do submit_render "$SECTOR" "${s}_country"; done
if [[ "$INCLUDE_COLLAPSED" == "1" ]]; then
    echo "  -- country (collapsed) --"
    for s in "${SUBS[@]}"; do submit_render "$SECTOR" "${s}_country_collapsed"; done
fi

echo ""
echo "Done submitting. Watch with: squeue -u \$USER"
