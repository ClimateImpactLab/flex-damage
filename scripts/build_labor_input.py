#!/usr/bin/env python3
"""
Build labor input parquet from raw CIL projection nc4 files.

Walks the labor Monte Carlo output tree, computes full-adaptation climate-change
impacts (main - histclim) per CIL's "art of rebasing and histclim" memo for three
labor subsectors in one pass (combined, high_risk, low_risk), aggregates over
batch and GCM by running mean (streaming, memory-bounded), joins with climate
and socioeconomic covariates, and writes a single parquet consumed by
flexdamage-v3.

Three y columns live in one output parquet: labor_combined, labor_high_risk,
labor_low_risk. Each labor config selects one of these via columns.y.

Modes
-----
smoke : one sim (batch0/rcp45/ACCESS1-0/high/SSP3) - fast pipeline test
full  : walk entire MC tree, running mean over batch x GCM per scenario

Units
-----
All three labor impact columns are in "portion" (dimensionless fraction of
labor productivity, rebased to 2005). Negative = productivity loss.
"""

import argparse
import gc
import logging
import os
import sys
import multiprocessing as mp
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

BASEPATH = "/project/cil/gcp/outputs/labor/impacts-woodwork/montecarlo/uninteracted_main_model_27_37_39"
CLIMATE_CSV = "/project/cil/home_dirs/scadavidsanchez/projects/flex-damage-functions-ir/dataset/climate/gcm_temp_gmst_year_preind1986-2005.csv"
SOCIO_ZARR = "/project/cil/gcp/integration_replication/inputs/econ/raw/integration-econ-bc39.zarr"

IAM_MAPPING = {"IIASA GDP": "low", "OECD Env-Growth": "high"}

SMOKE_SIM = {
    "batch": "batch0",
    "rcp": "rcp45",
    "gcm": "ACCESS1-0",
    "model": "high",
    "ssp": "SSP3",
}

# Target year range used by the worker to ensure a consistent shape across sims.
# Matches what flexdamage downstream cares about. Years outside this range are dropped.
TARGET_YEAR_MIN = 2010
TARGET_YEAR_MAX = 2099

IMPACT_COLS = ["labor_combined", "labor_high_risk", "labor_low_risk"]
MAIN_NC4 = "uninteracted_main_model.nc4"
HIST_NC4 = "uninteracted_main_model-histclim.nc4"
NC_VARS = {
    "labor_combined": "rebased",
    "labor_high_risk": "highriskimpacts",
    "labor_low_risk": "lowriskimpacts",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)


def process_one_sim(args):
    """Load main and histclim for one sim, return per-region-year adjusted impacts."""
    sim_dir, batch, rcp, gcm, model, ssp = args
    try:
        main_path = os.path.join(sim_dir, MAIN_NC4)
        hist_path = os.path.join(sim_dir, HIST_NC4)
        if not (os.path.exists(main_path) and os.path.exists(hist_path)):
            return None

        with xr.open_dataset(main_path, chunks=None) as ds:
            ds.load()
            m = {k: ds[v].values.astype(np.float32) for k, v in NC_VARS.items()}
            years = ds["year"].values.astype(int)
            regions = ds["regions"].values.astype(str)

        with xr.open_dataset(hist_path, chunks=None) as ds:
            ds.load()
            h = {k: ds[v].values.astype(np.float32) for k, v in NC_VARS.items()}
            hyears = ds["year"].values.astype(int)

        # Always slice to the canonical target year range so every sim returns
        # a guaranteed (len(target), n_regions, 3) shape. Explicit integer index
        # lookup (rather than boolean mask) because different nc4 files can have
        # slightly different year ranges (e.g. some GCMs have 119 vs 120 years).
        target = np.arange(TARGET_YEAR_MIN, TARGET_YEAR_MAX + 1)
        year_to_idx_m = {int(y): i for i, y in enumerate(years)}
        year_to_idx_h = {int(y): i for i, y in enumerate(hyears)}
        missing_main = [y for y in target if int(y) not in year_to_idx_m]
        missing_hist = [y for y in target if int(y) not in year_to_idx_h]
        if missing_main or missing_hist:
            log.warning(
                f"Sim {sim_dir} missing years "
                f"(main: {missing_main[:3]}{'...' if len(missing_main) > 3 else ''}, "
                f"hist: {missing_hist[:3]}{'...' if len(missing_hist) > 3 else ''}); skipping"
            )
            return None
        m_indices = np.array([year_to_idx_m[int(y)] for y in target])
        h_indices = np.array([year_to_idx_h[int(y)] for y in target])
        years = target

        # main - histclim per variable; shape guaranteed (len(target), n_regions)
        impacts = np.stack(
            [m[k][m_indices] - h[k][h_indices] for k in IMPACT_COLS],
            axis=-1,
        )
        expected_shape = (len(target), len(regions), len(IMPACT_COLS))
        if impacts.shape != expected_shape:
            log.warning(
                f"Sim {sim_dir} produced shape {impacts.shape}, "
                f"expected {expected_shape}; skipping"
            )
            return None

        return {
            "scenario": (rcp, ssp, model),
            "impacts": impacts,
            "years": years,
            "regions": regions,
        }
    except Exception as e:
        log.warning(f"Failed on {sim_dir}: {e}")
        return None


def discover_sims(basepath, mode):
    """Return list of (sim_dir, batch, rcp, gcm, model, ssp) tuples."""
    tasks = []
    if mode == "smoke":
        sim_dir = os.path.join(
            basepath,
            SMOKE_SIM["batch"], SMOKE_SIM["rcp"],
            SMOKE_SIM["gcm"], SMOKE_SIM["model"], SMOKE_SIM["ssp"],
        )
        if os.path.isdir(sim_dir):
            tasks.append((sim_dir, SMOKE_SIM["batch"], SMOKE_SIM["rcp"],
                          SMOKE_SIM["gcm"], SMOKE_SIM["model"], SMOKE_SIM["ssp"]))
        return tasks

    batches = sorted(d for d in os.listdir(basepath) if d.startswith("batch"))
    for batch in batches:
        b_path = os.path.join(basepath, batch)
        if not os.path.isdir(b_path):
            continue
        for rcp in ("rcp45", "rcp85"):
            r_path = os.path.join(b_path, rcp)
            if not os.path.isdir(r_path):
                continue
            gcms = sorted(d for d in os.listdir(r_path)
                          if os.path.isdir(os.path.join(r_path, d)))
            for gcm in gcms:
                g_path = os.path.join(r_path, gcm)
                for model in ("high", "low"):
                    m_path = os.path.join(g_path, model)
                    if not os.path.isdir(m_path):
                        continue
                    for ssp in sorted(os.listdir(m_path)):
                        sim_dir = os.path.join(m_path, ssp)
                        if os.path.isdir(sim_dir):
                            tasks.append((sim_dir, batch, rcp, gcm, model, ssp))
    return tasks


def accumulate_impacts(results_iter, total, acc=None):
    """Streaming mean over batch x GCM, keyed by (rcp, ssp, model). O(scenarios x ny x nr) memory.

    `acc` can be passed in to accumulate across multiple calls (e.g. per-scenario pools).
    """
    if acc is None:
        acc = {}
    processed = 0
    skipped = 0

    for r in results_iter:
        processed += 1
        if processed % 100 == 0:
            log.info(f"  processed {processed:,} / {total:,} sims in this group")
        if r is None:
            skipped += 1
            continue
        key = r["scenario"]
        if key not in acc:
            acc[key] = {
                "sum": r["impacts"].astype(np.float64),
                "count": 1,
                "years": r["years"],
                "regions": r["regions"],
            }
        else:
            # Defensive: guard against any shape mismatch sneaking through.
            if r["impacts"].shape != acc[key]["sum"].shape:
                log.warning(
                    f"Shape mismatch in scenario {key}: acc={acc[key]['sum'].shape}, "
                    f"new={r['impacts'].shape}; skipping this sim"
                )
                skipped += 1
                del r
                continue
            acc[key]["sum"] += r["impacts"].astype(np.float64)
            acc[key]["count"] += 1
        # Explicitly drop the result so GC can reclaim the ~35MB impacts array
        del r

    log.info(f"  group done: {processed - skipped:,} valid sims, {skipped:,} skipped")
    return acc


def build_long_frame(acc):
    """Turn per-scenario accumulators into one long DataFrame."""
    dfs = []
    for (rcp, ssp, model), d in acc.items():
        mean3 = (d["sum"] / d["count"]).astype(np.float32)
        ny, nr, _ = mean3.shape
        df = pd.DataFrame({
            "rcp": rcp,
            "ssp": ssp,
            "model": model,
            "year": np.repeat(d["years"], nr),
            "region": np.tile(d["regions"], ny),
            "labor_combined":  mean3[:, :, 0].reshape(-1),
            "labor_high_risk": mean3[:, :, 1].reshape(-1),
            "labor_low_risk":  mean3[:, :, 2].reshape(-1),
        })
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def join_climate(df, climate_csv, mode, gcms_used=None):
    """Join temperature_anomaly from climate CSV.

    Full mode: mean over GCMs actually used, per (rcp, year).
    Smoke mode: take the single GCM used by the smoke sim.
    """
    log.info(f"Reading climate: {climate_csv}")
    clim = pd.read_csv(climate_csv)
    if "scenario" in clim.columns:
        clim = clim.rename(columns={"scenario": "rcp"})

    # Detect anomaly column
    anomaly_candidates = [c for c in clim.columns if c.lower() in ("anomaly", "anom", "tas", "temperature_anomaly")]
    if not anomaly_candidates:
        raise RuntimeError(f"No anomaly column found in climate CSV. Columns: {list(clim.columns)}")
    anom = anomaly_candidates[0]
    clim = clim.rename(columns={anom: "temperature_anomaly"})

    if mode == "smoke":
        clim = clim[clim["gcm"] == SMOKE_SIM["gcm"]]
    elif gcms_used is not None:
        clim = clim[clim["gcm"].isin(gcms_used)]

    T = clim.groupby(["rcp", "year"], as_index=False)["temperature_anomaly"].mean()
    before = len(df)
    df = df.merge(T, on=["rcp", "year"], how="left")
    n_missing = df["temperature_anomaly"].isna().sum()
    if n_missing > 0:
        log.warning(f"temperature_anomaly NaN in {n_missing:,}/{before:,} rows after climate join")
    return df


def join_econ(df, econ_zarr, mode):
    """Join gdppc and pop from integration-econ-bc39.zarr."""
    log.info(f"Opening econ zarr: {econ_zarr}")
    ds = xr.open_zarr(econ_zarr)
    # Drop unused variables to save memory
    for v in ("gdp",):
        if v in ds:
            ds = ds.drop_vars(v)
    ds["year"] = ds.year.astype(int)
    # Map IAM names
    if "model" in ds.coords:
        new_models = [IAM_MAPPING.get(str(m), str(m)) for m in ds.model.values]
        ds = ds.assign_coords(model=new_models)

    if mode == "smoke":
        ds = ds.sel(ssp=SMOKE_SIM["ssp"], model=SMOKE_SIM["model"])
    # Keep only needed vars
    keep = [v for v in ("gdppc", "pop") if v in ds.data_vars]
    missing = [v for v in ("gdppc", "pop") if v not in ds.data_vars]
    if missing:
        log.warning(f"Missing econ variables: {missing}. Available: {list(ds.data_vars)}")
    ds = ds[keep]

    econ = ds.to_dataframe().reset_index()
    if mode == "smoke":
        # Add scalar ssp/model back
        econ["ssp"] = SMOKE_SIM["ssp"]
        econ["model"] = SMOKE_SIM["model"]

    join_keys = [c for c in ("region", "year", "ssp", "model") if c in econ.columns and c in df.columns]
    before = len(df)
    df = df.merge(econ, on=join_keys, how="left")
    n_missing = df["gdppc"].isna().sum() if "gdppc" in df.columns else 0
    if n_missing > 0:
        log.warning(f"gdppc NaN in {n_missing:,}/{before:,} rows after econ join")
    return df


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", required=True, choices=["smoke", "full"])
    p.add_argument("--output-dir", required=True, help="Directory for output parquet (e.g. /scratch/.../labor/full)")
    p.add_argument("--basepath", default=BASEPATH)
    p.add_argument("--climate-csv", default=CLIMATE_CSV)
    p.add_argument("--econ-zarr", default=SOCIO_ZARR)
    p.add_argument("--n-workers", type=int, default=None, help="Parallel workers (default: cpu_count)")
    p.add_argument("--year-min", type=int, default=2010, help="Drop years before this")
    p.add_argument("--limit", type=int, default=None,
                   help="Truncate discovered sims to first N (for end-to-end sanity tests)")
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"Mode: {args.mode}")
    log.info(f"Output dir: {output_dir}")
    log.info(f"Basepath: {args.basepath}")

    # 1. Discover sims
    tasks = discover_sims(args.basepath, args.mode)
    log.info(f"Discovered {len(tasks):,} sim directories")
    if args.limit is not None:
        tasks = tasks[: args.limit]
        log.info(f"--limit applied: truncated to first {len(tasks):,} sims")
    if not tasks:
        log.error("No simulations found")
        sys.exit(1)

    n_workers = args.n_workers or (os.cpu_count() or 4)
    log.info(f"Processing with {n_workers} workers per scenario group")

    # 2. Process sims and accumulate (streaming mean)
    gcms_used = set()
    for t in tasks:
        gcms_used.add(t[3])

    acc = {}

    if args.mode == "smoke":
        results = (process_one_sim(t) for t in tasks)
        acc = accumulate_impacts(results, total=len(tasks), acc=acc)
    else:
        # Group tasks by scenario tuple (rcp, ssp, model).
        # Process each group with its own short-lived pool so that netcdf4
        # caches, worker xarray state, and pool pipe buffers are released
        # between groups. Avoids the slow memory creep that blew past 120 GB.
        groups = defaultdict(list)
        for t in tasks:
            # t = (sim_dir, batch, rcp, gcm, model, ssp)
            groups[(t[2], t[5], t[4])].append(t)  # (rcp, ssp, model)

        log.info(f"Grouping into {len(groups)} scenarios for sequential processing")
        mp_ctx = mp.get_context("spawn")
        for i, (scen, g_tasks) in enumerate(sorted(groups.items()), start=1):
            log.info(f"[{i}/{len(groups)}] scenario {scen}: {len(g_tasks):,} sims")
            with ProcessPoolExecutor(max_workers=n_workers, mp_context=mp_ctx) as pool:
                results = pool.map(process_one_sim, g_tasks, chunksize=2)
                acc = accumulate_impacts(results, total=len(g_tasks), acc=acc)
            # Pool is gone; force release of any lingering references.
            gc.collect()
            log.info(f"[{i}/{len(groups)}] done. Accumulator scenarios so far: {len(acc)}")

    if not acc:
        log.error("No valid sims processed")
        sys.exit(1)

    # 3. Build long-format DataFrame
    log.info("Building long-format frame from accumulators")
    df = build_long_frame(acc)
    log.info(f"Aggregated rows: {len(df):,}")

    # 4. Year filter
    if args.year_min is not None:
        df = df[df["year"] >= args.year_min]
        log.info(f"After year>={args.year_min} filter: {len(df):,}")

    # 5. Join climate
    df = join_climate(df, args.climate_csv, args.mode, gcms_used=gcms_used)

    # 6. Join econ
    df = join_econ(df, args.econ_zarr, args.mode)

    # 7. Sort and write
    df = df.sort_values(["rcp", "ssp", "model", "region", "year"]).reset_index(drop=True)
    out_file = output_dir / f"labor_aggregated_{args.mode}.parquet"
    df.to_parquet(out_file, index=False, compression="zstd")
    size_mb = out_file.stat().st_size / 1e6
    log.info(f"Wrote {out_file} ({size_mb:.1f} MB, {len(df):,} rows)")

    # 8. Summary
    log.info("=" * 60)
    log.info("Summary:")
    log.info(f"  Output:   {out_file}")
    log.info(f"  Rows:     {len(df):,}")
    log.info(f"  Regions:  {df['region'].nunique():,}")
    log.info(f"  Years:    {df['year'].min()}-{df['year'].max()}")
    log.info(f"  RCPs:     {sorted(df['rcp'].unique())}")
    log.info(f"  SSPs:     {sorted(df['ssp'].unique())}")
    log.info(f"  Models:   {sorted(df['model'].unique())}")
    for col in IMPACT_COLS:
        log.info(f"  {col}: mean={df[col].mean():.5f}, std={df[col].std():.5f}, "
                 f"min={df[col].min():.5f}, max={df[col].max():.5f}")
    log.info(f"  gdppc (mean): {df['gdppc'].mean():.2f}" if "gdppc" in df.columns else "  gdppc: missing")
    log.info(f"  pop (mean):   {df['pop'].mean():.2f}" if "pop" in df.columns else "  pop: missing")


if __name__ == "__main__":
    main()
