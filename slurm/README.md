# SLURM jobs for labor pipeline

Submit from the `flexdamage-v3/` directory on Midway3.

## Quick reference

| Script | Purpose | Partition | Memory | Time |
|---|---|---|---|---|
| `00_prep_labor_smoke.sbatch` | Build 1-sim smoke input parquet | default | 16 GB | 0:30 |
| `01_prep_labor_mc.sbatch` | Build full-MC input parquet | amd | 120 GB | 8:00 |
| `02_estimate_labor_smoke.sbatch` | Fit all 3 subsectors against smoke input | default | 32 GB | 1:00 |
| `03_estimate_labor_combined.sbatch` | Fit combined subsector, full MC | amd | 120 GB | 6:00 |
| `03_estimate_labor_high_risk.sbatch` | Fit high_risk subsector, full MC | amd | 120 GB | 6:00 |
| `03_estimate_labor_low_risk.sbatch` | Fit low_risk subsector, full MC | amd | 120 GB | 6:00 |

All jobs use account `cil`. Logs land in `slurm/logs/<jobname>_<jobid>.out`.

## Recommended execution order

```bash
# 0. Create logs dir once
mkdir -p slurm/logs

# 1. Smoke path: confirm pipeline works end-to-end (~1.5 hours)
sbatch slurm/00_prep_labor_smoke.sbatch
# Wait for completion, then:
sbatch slurm/02_estimate_labor_smoke.sbatch

# 2. Full MC path: production (~8 hrs prep + 6 hrs per subsector)
sbatch slurm/01_prep_labor_mc.sbatch
# Wait for completion, then submit all three in parallel:
sbatch slurm/03_estimate_labor_combined.sbatch
sbatch slurm/03_estimate_labor_high_risk.sbatch
sbatch slurm/03_estimate_labor_low_risk.sbatch
```

## Scratch vs permanent paths

Temporary (large, auto-purged after cluster retention period):
- `/scratch/midway3/cadavidsanchez/flex-damages/labor/smoke/labor_aggregated_smoke.parquet`
- `/scratch/midway3/cadavidsanchez/flex-damages/labor/full/labor_aggregated_full.parquet`

Permanent outputs (same location as agriculture and mortality):
- `/project/cil/gcp/flex_damage_funcs/parameters/labor__{combined,high_risk,low_risk}__regional_parameters.csv`
- `+ __global_results.json`
- `+ __metadata.json`

## Monitoring

```bash
squeue -u $USER           # see running jobs
sacct -j <jobid>          # check completion status
tail -f slurm/logs/<jobname>_<jobid>.out
```

## Chaining jobs with dependencies

If you want to launch the full flow in one go (prep then 3 estimations, automatic wait):

```bash
PREP=$(sbatch --parsable slurm/01_prep_labor_mc.sbatch)
sbatch --dependency=afterok:$PREP slurm/03_estimate_labor_combined.sbatch
sbatch --dependency=afterok:$PREP slurm/03_estimate_labor_high_risk.sbatch
sbatch --dependency=afterok:$PREP slurm/03_estimate_labor_low_risk.sbatch
```

## If something fails

- Check the `.err` file in `slurm/logs/`
- Smoke test ALWAYS before full MC — it's the fastest way to catch a bad column mapping, missing dependency, or wrong scratch path.
- If the estimation step throws `KeyError 'json'` at the very end, the outputs are usually still written correctly (known bug in `pipeline.py` summary step). Verify by `ls /project/cil/gcp/flex_damage_funcs/parameters/labor__*`.
