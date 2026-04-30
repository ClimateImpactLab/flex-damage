#!/bin/bash
# Run prep + estimation + render for ONE sector/crop, in keep-MC mode.
# Use this to validate end-to-end on a single sector before launching the
# full orchestrator.
#
# Usage:
#   bash slurm/run_one_sector.sh energy
#   bash slurm/run_one_sector.sh agriculture cassava
#   bash slurm/run_one_sector.sh agriculture corn
#
# Energy: prep + 3 estimations (total/electricity/non_electricity) + 3 renders.
# Agriculture: prep + 1 estimation + 1 render for the named crop.
set -euo pipefail

SECTOR="${1:?Usage: $0 <energy|agriculture> [crop]}"
CROP="${2:-}"

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
[[ -f slurm/_env.sh ]] && source slurm/_env.sh

PARTITION="${PARTITION:-cil}"
EST_PARTITION="${EST_PARTITION:-$PARTITION}"
RENDER_PARTITION="${RENDER_PARTITION:-cil}"
PARAMS_DIR="/project/cil/gcp/flex_damage_funcs/parameters"

mkdir -p slurm/logs

source_data_for() {
    # Read data.source out of the YAML config so paths can't drift.
    local sec="$1" sub="$2"
    local cfg="configs/${sec}/${sub}.yaml"
    if [[ ! -f "$cfg" ]]; then
        echo ""
        return
    fi
    python3 -c "import yaml; print(yaml.safe_load(open('$cfg')).get('data',{}).get('source',''))" 2>/dev/null
}

submit_estimation() {
    local sector="$1" sub="$2" prep_jid="$3"
    local cfg="configs/${sector}/${sub}.yaml"
    [[ -f "$cfg" ]] || { echo "  WARN: missing $cfg"; return 0; }
    local jid
    jid=$(sbatch --parsable \
        --job-name="est_${sector}_${sub}" \
        --account=cil --partition="$EST_PARTITION" --nodes=1 --ntasks=1 --cpus-per-task=12 \
        --mem=80G --time=04:00:00 \
        --output=slurm/logs/%x_%j.out --error=slurm/logs/%x_%j.err \
        --dependency=afterok:$prep_jid \
        --wrap="source slurm/_env.sh && python scripts/run.py $cfg --verbose")
    echo "  est_${sector}_${sub} -> $jid (dep $prep_jid)"
    echo "$jid"
}

submit_render() {
    local sector="$1" sub="$2" est_jid="$3"
    local pcsv="$PARAMS_DIR/${sector}__${sub}__regional_parameters.csv"
    local gjson="$PARAMS_DIR/${sector}__${sub}__global_results.json"
    local sdata; sdata=$(source_data_for "$sector" "$sub")
    local jid
    # Memory budget. Country-resolution renders (ag + labor especially) load
    # ~130M-row keep-MC parquets and need 90G. IR renders fit in 50G.
    local mem="50G"
    [[ "$sub" == *_country* ]] && mem="90G"
    jid=$(sbatch --parsable \
        --job-name="render_${sector}_${sub}" \
        --partition="$RENDER_PARTITION" \
        --mem=$mem --time=02:00:00 \
        --export=ALL,SECTOR=$sector,SUBSECTOR=$sub,PARAMS_CSV=$pcsv,GLOBAL_JSON=$gjson,SOURCE_DATA=$sdata \
        --dependency=afterok:$est_jid \
        slurm/render_report.sbatch)
    echo "  render_${sector}_${sub} -> $jid (dep $est_jid, mem=$mem)"
}

case "$SECTOR" in
    energy)
        echo "=== ENERGY (keep-MC) ==="
        prep_jid=$(sbatch --parsable \
            --job-name="energy_country_prep_v2" \
            --partition="$PARTITION" \
            slurm/01_prep_energy_country.sbatch)
        echo "  prep -> $prep_jid"
        for sub in total electricity non_electricity; do
            est_jid=$(submit_estimation energy "${sub}_country" "$prep_jid" | tail -1)
            submit_render energy "${sub}_country" "$est_jid"
        done ;;
    labor)
        echo "=== LABOR (keep-MC, IR -> country pop-weighted) ==="
        prep_jid=$(sbatch --parsable \
            --job-name="labor_country_prep_v2" \
            --partition="$PARTITION" \
            slurm/01_prep_labor_country.sbatch)
        echo "  prep -> $prep_jid"
        for sub in combined high_risk low_risk; do
            est_jid=$(submit_estimation labor "${sub}_country" "$prep_jid" | tail -1)
            submit_render labor "${sub}_country" "$est_jid"
        done ;;
    agriculture)
        : "${CROP:?Must pass a crop, e.g. cassava or corn}"
        echo "=== AGRICULTURE / $CROP (keep-MC) ==="
        prep_jid=$(sbatch --parsable \
            --job-name="ag_${CROP}_keepmc_prep" \
            --partition="$PARTITION" \
            --export=ALL,CROP=$CROP \
            slurm/01_prep_agriculture_country.sbatch)
        echo "  prep -> $prep_jid"
        est_jid=$(submit_estimation agriculture "${CROP}_country" "$prep_jid" | tail -1)
        submit_render agriculture "${CROP}_country" "$est_jid" ;;
    *) echo "Unknown sector: $SECTOR (expected energy|labor|agriculture)"; exit 2 ;;
esac

echo ""
echo "Done submitting. Watch with: squeue -u \$USER"
