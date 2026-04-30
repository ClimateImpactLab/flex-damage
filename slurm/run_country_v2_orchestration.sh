#!/bin/bash
# Orchestrate the v2 country pipeline (keep-MC only).
#
#  1. Submit ENERGY first (cheap; ~10–15 min): prep + 3 estimations + 3 renders.
#  2. Submit AG preps (8 crops; heavier) + their estimations + renders.
#  3. Re-render every existing report (mortality/labor/IR variants) for the
#     QMD y-axis + header fixes (no estimation needed).
#
# Run from project root:
#   bash slurm/run_country_v2_orchestration.sh [--skip-prep] [--skip-est]
#
# Partition policy: jobs go to the `cil` partition by default. To use caslake
# instead, set PARTITION=caslake in the environment.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

SKIP_PREP=0
SKIP_EST=0
for arg in "$@"; do
    case "$arg" in
        --skip-prep) SKIP_PREP=1 ;;
        --skip-est)  SKIP_PREP=1; SKIP_EST=1 ;;
        *) echo "Unknown arg: $arg"; exit 2 ;;
    esac
done

PARTITION="${PARTITION:-cil}"
EST_PARTITION="${EST_PARTITION:-$PARTITION}"
RENDER_PARTITION="${RENDER_PARTITION:-cil}"   # renders default to cil too
echo "Partitions: prep/est=$PARTITION (override w/ PARTITION=...), render=$RENDER_PARTITION"
echo ""

AG_CROPS=(corn rice soy sorghum cassava wheat_combined wheat_spring wheat_winter)
ENERGY_SUBS=(total electricity non_electricity)
LABOR_SUBS=(combined high_risk low_risk)

PARAMS_DIR="/project/cil/gcp/flex_damage_funcs/parameters"

mkdir -p slurm/logs
[[ -f slurm/_env.sh ]] && source slurm/_env.sh

##############################################################################
# Helpers
##############################################################################
source_data_for() {
    local sec="$1" sub="$2"
    case "$sec" in
        mortality)
            if [[ "$sub" == *_country ]]; then
                echo "$SCRATCH_BASE/mortality/country_keepmc_full/mortality_aggregated_country_keepmc_full.parquet"
            elif [[ "$sub" == *_country_collapsed ]]; then
                echo "$SCRATCH_BASE/mortality/country_full/mortality_aggregated_country_full.parquet"
            else
                echo "$SCRATCH_BASE/mortality/full/mortality_aggregated_full.parquet"
            fi ;;
        labor)
            if [[ "$sub" == *_country ]]; then
                echo "$SCRATCH_BASE/labor/country_keepmc_full/labor_aggregated_country_keepmc_full.parquet"
            elif [[ "$sub" == *_country_collapsed ]]; then
                echo "$SCRATCH_BASE/labor/country_full/labor_aggregated_country_full.parquet"
            else
                echo "$SCRATCH_BASE/labor/full/labor_aggregated_full.parquet"
            fi ;;
        energy)
            if [[ "$sub" == *_country ]]; then
                echo "$SCRATCH_BASE/energy/country_keepmc_full/energy_aggregated_country_keepmc_full.parquet"
            elif [[ "$sub" == *_country_collapsed ]]; then
                echo "$SCRATCH_BASE/energy/country_full/energy_aggregated_country_full.parquet"
            else
                echo "$SCRATCH_BASE/energy/full/energy_aggregated_full.parquet"
            fi ;;
        agriculture)
            local crop="${sub%_country*}"
            if [[ "$sub" == *_country ]]; then
                echo "$SCRATCH_BASE/agriculture/country_keepmc_full/agriculture_${crop}_aggregated_country_keepmc_full.parquet"
            elif [[ "$sub" == *_country_collapsed ]]; then
                echo "$SCRATCH_BASE/agriculture/country_full/agriculture_${crop}_aggregated_country_full.parquet"
            else
                echo "/project/cil/home_dirs/scadavidsanchez/projects/flex-damages-data/agriculture/${crop}/ir/ir.zarr"
            fi ;;
    esac
}

declare -A PREP_JOB
declare -A EST_JOB

submit_estimation() {
    local sector="$1" sub="$2"          # sub already includes _country (no _collapsed in this run)
    local jobname="est_${sector}_${sub}"
    local cfg="configs/${sector}/${sub}.yaml"
    if [[ ! -f "$cfg" ]]; then
        echo "  WARN: missing config $cfg (skipping)"
        return 0
    fi
    local depopt=""
    if [[ "$SKIP_PREP" == "0" ]]; then
        local base="${sub%_country*}"
        local pj=${PREP_JOB["${sector}__${base}"]:-}
        [[ -n "$pj" ]] && depopt="--dependency=afterok:$pj"
    fi
    local jid
    jid=$(sbatch --parsable \
        --job-name="$jobname" \
        --account=cil --partition="$EST_PARTITION" --nodes=1 --ntasks=1 --cpus-per-task=12 \
        --mem=80G --time=04:00:00 \
        --output=slurm/logs/%x_%j.out --error=slurm/logs/%x_%j.err \
        $depopt \
        --wrap="source slurm/_env.sh && python scripts/run.py $cfg --verbose")
    EST_JOB["${sector}__${sub}"]=$jid
    echo "  $jobname -> $jid${depopt:+ (dep $depopt)}"
}

submit_render() {
    local sector="$1" sub="$2"
    local jobname="render_${sector}_${sub}"
    local depopt=""
    local est_key="${sector}__${sub}"
    [[ -n "${EST_JOB[$est_key]:-}" ]] && depopt="--dependency=afterok:${EST_JOB[$est_key]}"
    local pcsv="$PARAMS_DIR/${sector}__${sub}__regional_parameters.csv"
    local gjson="$PARAMS_DIR/${sector}__${sub}__global_results.json"
    local sdata
    sdata=$(source_data_for "$sector" "$sub")
    local jid
    jid=$(sbatch --parsable \
        --job-name="$jobname" \
        --partition="$RENDER_PARTITION" \
        --export=ALL,SECTOR=$sector,SUBSECTOR=$sub,PARAMS_CSV=$pcsv,GLOBAL_JSON=$gjson,SOURCE_DATA=$sdata \
        $depopt \
        slurm/render_report.sbatch)
    echo "  $jobname -> $jid${depopt:+ (dep $depopt)}"
}

##############################################################################
# Step 1: ENERGY first (lighter)
##############################################################################
echo "=== ENERGY (prep + 3 est + 3 renders) ==="
if [[ "$SKIP_PREP" == "0" ]]; then
    jid=$(sbatch --parsable \
        --job-name="energy_country_prep_v2" \
        --partition="$PARTITION" \
        slurm/01_prep_energy_country.sbatch)
    for sub in "${ENERGY_SUBS[@]}"; do
        PREP_JOB["energy__${sub}"]=$jid
    done
    echo "  energy_country_prep_v2 -> $jid"
fi
if [[ "$SKIP_EST" == "0" ]]; then
    for sub in "${ENERGY_SUBS[@]}"; do submit_estimation energy "${sub}_country"; done
fi
for sub in "${ENERGY_SUBS[@]}"; do submit_render energy "${sub}_country"; done

##############################################################################
# Step 2: AG (heavier — 8 preps in parallel)
##############################################################################
echo ""
echo "=== AGRICULTURE (8 preps + 8 est + 8 renders) ==="
if [[ "$SKIP_PREP" == "0" ]]; then
    for crop in "${AG_CROPS[@]}"; do
        jobname="ag_${crop}_keepmc_prep"
        jid=$(sbatch --parsable \
            --job-name="$jobname" \
            --partition="$PARTITION" \
            --export=ALL,CROP=$crop \
            slurm/01_prep_agriculture_country.sbatch)
        PREP_JOB["agriculture__${crop}"]=$jid
        echo "  $jobname -> $jid"
    done
fi
if [[ "$SKIP_EST" == "0" ]]; then
    for crop in "${AG_CROPS[@]}"; do submit_estimation agriculture "${crop}_country"; done
fi
for crop in "${AG_CROPS[@]}"; do submit_render agriculture "${crop}_country"; done

##############################################################################
# Step 3 (re-render of unchanged sectors) intentionally disabled for the
# two-sector test run. Re-enable later by un-commenting once the new energy
# + ag results are validated.
##############################################################################
# submit_render mortality allcause
# for sub in "${LABOR_SUBS[@]}"; do submit_render labor "$sub"; done
# for sub in "${ENERGY_SUBS[@]}"; do submit_render energy "$sub"; done
# for crop in "${AG_CROPS[@]}"; do submit_render agriculture "$crop"; done
# submit_render mortality allcause_country
# for sub in "${LABOR_SUBS[@]}"; do submit_render labor "${sub}_country"; done

echo ""
echo "=== All jobs submitted ==="
echo "Watch with: squeue -u $USER --partition=$PARTITION,$RENDER_PARTITION"
