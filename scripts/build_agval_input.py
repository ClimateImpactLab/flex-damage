#!/usr/bin/env python3
"""
Build agriculture_value (combined, main_spec) input parquet from raw CIL
projection nc4 files.

Unlike labor/mortality, this source has NO histclim companion file. The
raw file 'disaggregated_damages.nc4' already contains the CC-vs-counterfactual
welfare cost per (region, year) in USD. Variable: wc_no_reallocation.
Sign: negative = welfare loss, positive = gain (paper's DeltaWelfare convention).

Walks the MC tree, reads wc_no_reallocation, aggregates over batch x GCM
(mean), joins with climate and socioeconomic covariates, writes parquet.

Modes
-----
smoke : one sim (batch0/rcp45/ACCESS1-0/high/SSP2) for end-to-end test
full  : walk entire MC tree, running mean per (rcp, ssp, model) scenario
"""

import argparse
import gc
import logging
import multiprocessing as mp
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

BASEPATH = "/project/cil/gcp/outputs/agriculture/agval/main_spec/montecarlo"
CLIMATE_CSV = "/project/cil/home_dirs/scadavidsanchez/projects/flex-damage-functions-ir/dataset/climate/gcm_temp_gmst_year_preind1986-2005.csv"
SOCIO_ZARR = "/project/cil/gcp/integration_replication/inputs/econ/raw/integration-econ-bc39.zarr"

IAM_MAPPING = {"IIASA GDP": "low", "OECD Env-Growth": "high"}

DAMAGES_NC4 = "disaggregated_damages.nc4"
DAMAGE_VAR = "wc_no_reallocation"

# agval year range: raw is 2000-2098. We keep 2010-2098 for the pipeline
# (2010 is the min we've used for mortality/labor; 2098 is the data end).
TARGET_YEAR_MIN = 2010
TARGET_YEAR_MAX = 2098

SMOKE_SIM = {
    "batch": "batch0",
    "rcp": "rcp45",
    "gcm": "ACCESS1-0",
    "model": "high",
    "ssp": "SSP2",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)


def process_one_sim(args):
    """Load disaggregated_damages.nc4 for one sim, return welfare impacts per region/year."""
    sim_dir, batch, rcp, gcm, model, ssp = args
    try:
        path = os.path.join(sim_dir, DAMAGES_NC4)
        if not os.path.exists(path):
            return None

        with xr.open_dataset(path, chunks=None) as ds:
            ds.load()
            # wc_no_reallocation has dims (gcm, model, rcp, ssp, batch, variable, region, year, ...)
            # squeeze size-1 dims to get (region, year)
            arr = ds[DAMAGE_VAR].squeeze().values.astype(np.float32)
            years = ds["year"].values.astype(int)
            regions = ds["region"].values.astype(str)

        if arr.ndim != 2:
            log.warning(f"Sim {sim_dir}: unexpected shape after squeeze {arr.shape}; skipping")
            return None
        # arr may be (region, year) or (year, region) depending on underlying order
        if arr.shape == (len(regions), len(years)):
            impacts_ry = arr  # (region, year)
        elif arr.shape == (len(years), len(regions)):
            impacts_ry = arr.T  # transpose to (region, year)
        else:
            log.warning(f"Sim {sim_dir}: shape {arr.shape} does not match region/year dims; skipping")
            return None

        # Canonical year range (year dim first to match labor/mortality convention)
        target = np.arange(TARGET_YEAR_MIN, TARGET_YEAR_MAX + 1)
        year_to_idx = {int(y): i for i, y in enumerate(years)}
        missing = [y for y in target if int(y) not in year_to_idx]
        if missing:
            log.warning(
                f"Sim {sim_dir} missing years {missing[:3]}"
                f"{'...' if len(missing) > 3 else ''}; skipping"
            )
            return None
        col_idx = np.array([year_to_idx[int(y)] for y in target])
        sliced = impacts_ry[:, col_idx]  # (n_regions, n_target_years)
        # Swap to (n_target_years, n_regions, 1) for consistency with labor builder
        impacts = sliced.T[..., np.newaxis]

        expected_shape = (len(target), len(regions), 1)
        if impacts.shape != expected_shape:
            log.warning(
                f"Sim {sim_dir} produced shape {impacts.shape}, expected {expected_shape}; skipping"
            )
            return None

        return {
            "scenario": (rcp, ssp, model),
            "impacts": impacts,
            "years": target,
            "regions": regions,
        }
    except Exception as e:
        log.warning(f"Failed on {sim_dir}: {e}")
        return None


def discover_sims(basepath, mode):
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
        b = os.path.join(basepath, batch)
        if not os.path.isdir(b):
            continue
        for rcp in sorted(os.listdir(b)):
            r = os.path.join(b, rcp)
            if not os.path.isdir(r):
                continue
            for gcm in sorted(os.listdir(r)):
                g = os.path.join(r, gcm)
                if not os.path.isdir(g):
                    continue
                for model in sorted(os.listdir(g)):
                    m = os.path.join(g, model)
                    if not os.path.isdir(m):
                        continue
                    for ssp in sorted(os.listdir(m)):
                        s = os.path.join(m, ssp)
                        if os.path.isdir(s):
                            tasks.append((s, batch, rcp, gcm, model, ssp))
    return tasks


def accumulate_impacts(results_iter, total, acc=None):
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
        del r

    log.info(f"  group done: {processed - skipped:,} valid sims, {skipped:,} skipped")
    return acc


def build_long_frame(acc):
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
            "wc_no_reallocation": mean3[:, :, 0].reshape(-1),
        })
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def join_climate(df, climate_csv, mode, gcms_used=None):
    log.info(f"Reading climate: {climate_csv}")
    clim = pd.read_csv(climate_csv)
    if "scenario" in clim.columns:
        clim = clim.rename(columns={"scenario": "rcp"})
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
    df = df.merge(T, on=["rcp", "year"], how="left")
    n_missing = df["temperature_anomaly"].isna().sum()
    if n_missing > 0:
        log.warning(f"temperature_anomaly NaN in {n_missing:,} rows after climate join")
    return df


def join_econ(df, econ_zarr, mode):
    log.info(f"Opening econ zarr: {econ_zarr}")
    ds = xr.open_zarr(econ_zarr)
    for v in ("gdp",):
        if v in ds:
            ds = ds.drop_vars(v)
    ds["year"] = ds.year.astype(int)
    if "model" in ds.coords:
        new_models = [IAM_MAPPING.get(str(m), str(m)) for m in ds.model.values]
        ds = ds.assign_coords(model=new_models)
    if mode == "smoke":
        ds = ds.sel(ssp=SMOKE_SIM["ssp"], model=SMOKE_SIM["model"])
    keep = [v for v in ("gdppc", "pop") if v in ds.data_vars]
    ds = ds[keep]
    econ = ds.to_dataframe().reset_index()
    if mode == "smoke":
        econ["ssp"] = SMOKE_SIM["ssp"]
        econ["model"] = SMOKE_SIM["model"]
    join_keys = [c for c in ("region", "year", "ssp", "model") if c in econ.columns and c in df.columns]
    df = df.merge(econ, on=join_keys, how="left")
    n_missing = df["gdppc"].isna().sum() if "gdppc" in df.columns else 0
    if n_missing > 0:
        log.warning(f"gdppc NaN in {n_missing:,} rows after econ join")
    return df


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", required=True, choices=["smoke", "full"])
    p.add_argument("--output-dir", required=True)
    p.add_argument("--basepath", default=BASEPATH)
    p.add_argument("--climate-csv", default=CLIMATE_CSV)
    p.add_argument("--econ-zarr", default=SOCIO_ZARR)
    p.add_argument("--n-workers", type=int, default=None)
    p.add_argument("--limit", type=int, default=None,
                   help="Truncate discovered sims to first N (for tests)")
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"Mode: {args.mode}")
    log.info(f"Output dir: {output_dir}")
    log.info(f"Basepath: {args.basepath}")

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

    gcms_used = set()
    for t in tasks:
        gcms_used.add(t[3])

    acc = {}
    if args.mode == "smoke":
        results = (process_one_sim(t) for t in tasks)
        acc = accumulate_impacts(results, total=len(tasks), acc=acc)
    else:
        groups = defaultdict(list)
        for t in tasks:
            groups[(t[2], t[5], t[4])].append(t)  # (rcp, ssp, model)
        log.info(f"Grouping into {len(groups)} scenarios for sequential processing")
        mp_ctx = mp.get_context("spawn")
        for i, (scen, g_tasks) in enumerate(sorted(groups.items()), start=1):
            log.info(f"[{i}/{len(groups)}] scenario {scen}: {len(g_tasks):,} sims")
            with ProcessPoolExecutor(max_workers=n_workers, mp_context=mp_ctx) as pool:
                results = pool.map(process_one_sim, g_tasks, chunksize=2)
                acc = accumulate_impacts(results, total=len(g_tasks), acc=acc)
            gc.collect()
            log.info(f"[{i}/{len(groups)}] done. Accumulator scenarios so far: {len(acc)}")

    if not acc:
        log.error("No valid sims processed")
        sys.exit(1)

    log.info("Building long-format frame from accumulators")
    df = build_long_frame(acc)
    log.info(f"Aggregated rows: {len(df):,}")

    df = join_climate(df, args.climate_csv, args.mode, gcms_used=gcms_used)
    df = join_econ(df, args.econ_zarr, args.mode)

    # Rescale welfare cost to per-capita (USD/person). Raw values are in
    # millions-to-billions of absolute USD, which blows up the gamma FE
    # regression (gamma absorbs the scale and overflows Y^gamma downstream).
    # Per-capita puts y on the same scale as log(Y), so gamma stays in [-1, 1].
    if "pop" in df.columns:
        before_nan = df["wc_no_reallocation"].isna().sum()
        df["wc_no_reallocation"] = df["wc_no_reallocation"] / df["pop"].replace(0, np.nan)
        after_nan = df["wc_no_reallocation"].isna().sum()
        log.info(f"Rescaled wc_no_reallocation to per-capita (added {after_nan - before_nan:,} NaN from pop=0)")
    else:
        log.warning("pop column missing; cannot rescale to per-capita - gamma estimation likely to fail")

    df = df.sort_values(["rcp", "ssp", "model", "region", "year"]).reset_index(drop=True)
    out_file = output_dir / f"agval_aggregated_{args.mode}.parquet"
    df.to_parquet(out_file, index=False, compression="zstd")
    size_mb = out_file.stat().st_size / 1e6
    log.info(f"Wrote {out_file} ({size_mb:.1f} MB, {len(df):,} rows)")

    log.info("=" * 60)
    log.info("Summary:")
    log.info(f"  Output:   {out_file}")
    log.info(f"  Rows:     {len(df):,}")
    log.info(f"  Regions:  {df['region'].nunique():,}")
    log.info(f"  Years:    {df['year'].min()}-{df['year'].max()}")
    log.info(f"  RCPs:     {sorted(df['rcp'].unique())}")
    log.info(f"  SSPs:     {sorted(df['ssp'].unique())}")
    log.info(f"  Models:   {sorted(df['model'].unique())}")
    s = df["wc_no_reallocation"].dropna()
    log.info(f"  wc_no_reallocation: mean={s.mean():.4g}, median={s.median():.4g}, "
             f"min={s.min():.4g}, max={s.max():.4g}")
    log.info(f"  gdppc (mean): {df['gdppc'].mean():.2f}" if "gdppc" in df.columns else "  gdppc: missing")


if __name__ == "__main__":
    main()
