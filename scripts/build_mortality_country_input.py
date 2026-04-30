#!/usr/bin/env python3
"""
Build mortality COUNTRY-level input parquet from the projection MC tree.

Reads the pre-aggregated nc4 files in each sim dir (NOT the IR zarrs). The
projection system already aggregated to a 5716-region hierarchy (countries +
admin1 + admin2 + FUND groups); we filter to the ~250 country codes (region
strings with no dots and not starting with FUND).

Adjusted-mortality formula matches IR build script:
    adjusted = main.rebased - histclim.rebased + (costs_lb + costs_ub) / 2 / 100000
where the costs term's denominator is 100000 because rebased is in
deaths/100k and costs are in portion (deaths/person).

Aggregation across batch x GCM uses streaming-running-mean (memory-bounded).

Usage:
  smoke: python scripts/build_mortality_country_input.py --mode smoke \\
             --output-dir /scratch/.../mortality/country_smoke
  full:  python scripts/build_mortality_country_input.py --mode full \\
             --output-dir /scratch/.../mortality/country_full
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
import pyarrow as pa
import pyarrow.parquet as pq
import xarray as xr
import yaml

BASEPATH = "/project/cil/battuta-shares-S3-archive/gcp/outputs/mortality/impacts-darwin/montecarlo"
CLIMATE_CSV = "/project/cil/home_dirs/scadavidsanchez/projects/flex-damage-functions-ir/dataset/climate/gcm_temp_gmst_year_preind1986-2005.csv"
SOCIO_ZARR = "/project/cil/gcp/integration_replication/inputs/econ/raw/integration-econ-bc39.zarr"

IAM_MAPPING = {"IIASA GDP": "low", "OECD Env-Growth": "high"}

TARGET_YEAR_MIN = 2010
TARGET_YEAR_MAX = 2099

SMOKE_SIM = {"batch": "batch0", "rcp": "rcp45", "gcm": "ACCESS1-0", "model": "high", "ssp": "SSP2"}

MAIN_NC4 = "Agespec_interaction_response-combined-aggregated.nc4"
HIST_NC4 = "Agespec_interaction_response-combined-histclim-aggregated.nc4"
COST_NC4 = "Agespec_interaction_response-combined-costs-aggregated.nc4"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)


def is_country(reg: str) -> bool:
    """A region is country-level if its hierid has no dots and is not a FUND group."""
    return bool(reg) and ("." not in reg) and (not reg.startswith("FUND"))


def process_one_sim_keep_mc(args):
    """Worker for keep-MC mode: returns a per-sim DataFrame with batch and
    gcm preserved as columns. The flexdamage pipeline will see all these
    rows as separate observations."""
    sim_dir, batch, rcp, gcm, model, ssp = args
    res = process_one_sim(args)  # reuse the slicing logic
    if res is None:
        return None
    impacts = res["impacts"]  # shape (n_years, n_countries, 1)
    years = res["years"]
    regs = res["regions"]
    n_y, n_r, _ = impacts.shape
    df = pd.DataFrame({
        "rcp": rcp,
        "ssp": ssp,
        "model": model,
        "batch": batch,
        "gcm": gcm,
        "year": np.repeat(years, n_r),
        "region": np.tile(regs, n_y),
        "adjusted_mortality": impacts[:, :, 0].reshape(-1),
    })
    return df


def process_one_sim(args):
    sim_dir, batch, rcp, gcm, model, ssp = args
    try:
        m_path = os.path.join(sim_dir, MAIN_NC4)
        h_path = os.path.join(sim_dir, HIST_NC4)
        c_path = os.path.join(sim_dir, COST_NC4)
        for p in (m_path, h_path, c_path):
            if not os.path.exists(p):
                return None

        with xr.open_dataset(m_path, chunks=None) as ds:
            ds.load()
            m_rebased = ds["rebased"].values.astype(np.float32)  # (year, region)
            m_years = ds["year"].values.astype(int)
            regions_full = ds["regions"].values.astype(str)

        with xr.open_dataset(h_path, chunks=None) as ds:
            ds.load()
            h_rebased = ds["rebased"].values.astype(np.float32)
            h_years = ds["year"].values.astype(int)

        with xr.open_dataset(c_path, chunks=None) as ds:
            ds.load()
            costs_mid = ((ds["costs_lb"].values + ds["costs_ub"].values) / 2.0).astype(np.float32)
            c_years = ds["year"].values.astype(int)

        # Country mask (force bool dtype - is_country can otherwise yield empty strings)
        country_mask = np.array([is_country(r) for r in regions_full], dtype=bool)
        if not country_mask.any():
            log.warning(f"No country regions in {sim_dir}")
            return None
        country_regs = regions_full[country_mask]

        # Slice to country regions (region axis = axis 1 here)
        m_rebased = m_rebased[:, country_mask]
        h_rebased = h_rebased[:, country_mask]
        costs_mid = costs_mid[:, country_mask]

        # Year alignment to target range
        target = np.arange(TARGET_YEAR_MIN, TARGET_YEAR_MAX + 1)

        def select_years(arr, years_arr):
            year_to_idx = {int(y): i for i, y in enumerate(years_arr)}
            missing = [y for y in target if int(y) not in year_to_idx]
            if missing:
                return None, missing
            idx = np.array([year_to_idx[int(y)] for y in target])
            return arr[idx], None

        m_sliced, miss = select_years(m_rebased, m_years)
        if miss:
            log.warning(f"Sim {sim_dir} main missing years {miss[:3]}; skipping")
            return None
        h_sliced, miss = select_years(h_rebased, h_years)
        if miss:
            log.warning(f"Sim {sim_dir} hist missing years {miss[:3]}; skipping")
            return None
        # costs file may have 1 fewer year than main; if a target year is
        # missing in costs, fall back to zero costs for that year.
        c_year_to_idx = {int(y): i for i, y in enumerate(c_years)}
        c_idx = []
        c_missing_in_target = []
        for y in target:
            if int(y) in c_year_to_idx:
                c_idx.append(c_year_to_idx[int(y)])
            else:
                c_idx.append(-1)
                c_missing_in_target.append(int(y))
        c_sliced = np.zeros_like(m_sliced)
        present = np.array([i for i in c_idx if i >= 0])
        present_mask = np.array([i >= 0 for i in c_idx])
        if len(present) > 0:
            c_sliced[present_mask] = costs_mid[present]
        if c_missing_in_target:
            log.info(f"Sim {sim_dir} costs missing for years {c_missing_in_target[:3]}; using 0")

        # adjusted_mortality (deaths/100k) - matches IR builder formula
        adjusted = m_sliced + (c_sliced / 100000.0) - h_sliced  # (n_years, n_regions)
        impacts = adjusted[..., np.newaxis]  # (n_years, n_regions, 1) for shape consistency

        return {
            "scenario": (rcp, ssp, model),
            "impacts": impacts,
            "years": target,
            "regions": country_regs,
        }
    except Exception as e:
        log.warning(f"Failed on {sim_dir}: {e}")
        return None


def discover_sims(basepath, mode):
    tasks = []
    if mode == "smoke":
        sd = os.path.join(basepath, SMOKE_SIM["batch"], SMOKE_SIM["rcp"],
                          SMOKE_SIM["gcm"], SMOKE_SIM["model"], SMOKE_SIM["ssp"])
        if os.path.isdir(sd):
            tasks.append((sd, SMOKE_SIM["batch"], SMOKE_SIM["rcp"], SMOKE_SIM["gcm"],
                          SMOKE_SIM["model"], SMOKE_SIM["ssp"]))
        return tasks

    batches = sorted(d for d in os.listdir(basepath) if d.startswith("batch"))
    for batch in batches:
        b = os.path.join(basepath, batch)
        if not os.path.isdir(b):
            continue
        for rcp in ("rcp45", "rcp85"):
            r = os.path.join(b, rcp)
            if not os.path.isdir(r):
                continue
            for gcm in sorted(os.listdir(r)):
                g = os.path.join(r, gcm)
                if not os.path.isdir(g):
                    continue
                for model in ("high", "low"):
                    m = os.path.join(g, model)
                    if not os.path.isdir(m):
                        continue
                    for ssp in sorted(os.listdir(m)):
                        sd = os.path.join(m, ssp)
                        if os.path.isdir(sd):
                            tasks.append((sd, batch, rcp, gcm, model, ssp))
    return tasks


def accumulate_impacts(results_iter, total, acc=None):
    if acc is None:
        acc = {}
    processed, skipped = 0, 0
    for r in results_iter:
        processed += 1
        if processed % 50 == 0:
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
                    f"Shape mismatch in {key}: acc={acc[key]['sum'].shape} new={r['impacts'].shape}; skipping sim"
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
            "adjusted_mortality": mean3[:, :, 0].reshape(-1),
        })
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def _load_climate_table(climate_csv, mode, gcms_used=None):
    """Load + pre-filter climate table once for streaming joins."""
    log.info(f"Reading climate (one-time): {climate_csv}")
    clim = pd.read_csv(climate_csv)
    if "scenario" in clim.columns:
        clim = clim.rename(columns={"scenario": "rcp"})
    anomaly = next((c for c in clim.columns if c.lower() in ("anomaly", "anom", "tas", "temperature_anomaly")), None)
    if anomaly is None:
        raise RuntimeError(f"No anomaly column in climate CSV: {list(clim.columns)}")
    clim = clim.rename(columns={anomaly: "temperature_anomaly"})
    if mode == "smoke":
        clim = clim[clim["gcm"] == SMOKE_SIM["gcm"]]
    elif gcms_used is not None:
        clim = clim[clim["gcm"].isin(gcms_used)]
    # Per-(rcp, gcm, year): DON'T aggregate over GCM here. The per-sim
    # rows in keep-MC already carry their gcm column; the join uses (rcp, gcm, year).
    keep_cols = [c for c in ("rcp", "gcm", "year", "temperature_anomaly") if c in clim.columns]
    clim = clim[keep_cols].drop_duplicates()
    log.info(f"  climate table: {len(clim):,} rows, cols={keep_cols}")
    return clim


def _load_econ_table(econ_zarr, mode):
    """Load + aggregate econ to country level once for streaming joins."""
    log.info(f"Opening econ zarr (one-time): {econ_zarr}")
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

    log.info("Aggregating econ from IR to country (one-time)")
    econ["country"] = econ["region"].astype(str).str.split(".").str[0]
    econ = econ[econ["country"].str.len() > 0]
    econ["pop"] = econ["pop"].fillna(0)
    econ["_gdppc_w"] = econ["gdppc"] * econ["pop"]
    grp = ["country", "year"] + [c for c in ("ssp", "model") if c in econ.columns]
    ec = econ.groupby(grp, as_index=False).agg(pop=("pop", "sum"), _gdppc_w=("_gdppc_w", "sum"))
    ec["gdppc"] = ec["_gdppc_w"] / ec["pop"].replace(0, np.nan)
    ec = ec.drop(columns=["_gdppc_w"]).rename(columns={"country": "region"})
    log.info(f"  econ table: {len(ec):,} rows")
    return ec


def _join_scenario(scen_df, clim_table, econ_table):
    """Join climate + econ to a scenario-local DataFrame."""
    # Climate: prefer (rcp, gcm, year) if both have gcm; else fall back to (rcp, year) avg.
    if "gcm" in scen_df.columns and "gcm" in clim_table.columns:
        merged = scen_df.merge(clim_table, on=["rcp", "gcm", "year"], how="left")
    else:
        T = clim_table.groupby(["rcp", "year"], as_index=False)["temperature_anomaly"].mean()
        merged = scen_df.merge(T, on=["rcp", "year"], how="left")
    join_keys = [c for c in ("region", "year", "ssp", "model") if c in econ_table.columns and c in merged.columns]
    merged = merged.merge(econ_table, on=join_keys, how="left")
    return merged


def join_climate(df, climate_csv, mode, gcms_used=None):
    log.info(f"Reading climate: {climate_csv}")
    clim = pd.read_csv(climate_csv)
    if "scenario" in clim.columns:
        clim = clim.rename(columns={"scenario": "rcp"})
    anomaly = next((c for c in clim.columns if c.lower() in ("anomaly", "anom", "tas", "temperature_anomaly")), None)
    if anomaly is None:
        raise RuntimeError(f"No anomaly column in climate CSV: {list(clim.columns)}")
    clim = clim.rename(columns={anomaly: "temperature_anomaly"})
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
    """Join gdppc and pop. The econ zarr is at IR resolution; for country we
    aggregate with pop sum and pop-weighted gdppc."""
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

    # Aggregate IR -> country: pop = sum, gdppc = pop-weighted mean
    log.info("Aggregating econ from IR to country")
    econ["country"] = econ["region"].astype(str).str.split(".").str[0]
    econ = econ[econ["country"].str.len() > 0]
    econ["pop"] = econ["pop"].fillna(0)
    econ["_gdppc_w"] = econ["gdppc"] * econ["pop"]
    grp = ["country", "year"] + [c for c in ("ssp", "model") if c in econ.columns]
    econ_country = econ.groupby(grp, as_index=False).agg(pop=("pop", "sum"), _gdppc_w=("_gdppc_w", "sum"))
    econ_country["gdppc"] = econ_country["_gdppc_w"] / econ_country["pop"].replace(0, np.nan)
    econ_country = econ_country.drop(columns=["_gdppc_w"])
    econ_country = econ_country.rename(columns={"country": "region"})

    join_keys = [c for c in ("region", "year", "ssp", "model") if c in econ_country.columns and c in df.columns]
    df = df.merge(econ_country, on=join_keys, how="left")
    n_missing = df["gdppc"].isna().sum() if "gdppc" in df.columns else 0
    if n_missing > 0:
        log.warning(f"gdppc NaN in {n_missing:,} rows after econ join")
    return df


def _resolve_collapse_mc(args) -> bool:
    """Resolve collapse-mc setting. CLI flag overrides config; default is keep-MC (False)."""
    if args.collapse_mc:
        return True
    if args.keep_mc:
        return False
    if args.config:
        try:
            with open(args.config) as f:
                cfg = yaml.safe_load(f)
            return bool(cfg.get("data", {}).get("collapse_mc", False))
        except Exception as e:
            log.warning(f"Could not read collapse_mc from {args.config}: {e}")
    return False  # default: keep all MC draws


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", required=True, choices=["smoke", "full"])
    p.add_argument("--output-dir", required=True)
    p.add_argument("--basepath", default=BASEPATH)
    p.add_argument("--climate-csv", default=CLIMATE_CSV)
    p.add_argument("--econ-zarr", default=SOCIO_ZARR)
    p.add_argument("--n-workers", type=int, default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--config", default=None,
                   help="Optional flexdamage YAML config; collapse_mc setting is read from data.collapse_mc")
    p.add_argument("--collapse-mc", action="store_true",
                   help="Collapse batch x GCM to scenario means (smaller output, classic flexdamage input)")
    p.add_argument("--keep-mc", action="store_true",
                   help="Keep every MC draw as a separate observation (default; bigger output, full uncertainty)")
    args = p.parse_args()

    collapse_mc = _resolve_collapse_mc(args)
    log.info(f"Mode: {args.mode}, collapse_mc: {collapse_mc}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tasks = discover_sims(args.basepath, args.mode)
    log.info(f"Discovered {len(tasks):,} sim directories")
    if args.limit is not None:
        tasks = tasks[: args.limit]
        log.info(f"--limit applied: {len(tasks):,} sims")
    if not tasks:
        log.error("No sims found")
        sys.exit(1)

    n_workers = args.n_workers or (os.cpu_count() or 4)
    log.info(f"Processing with {n_workers} workers per scenario group")
    gcms_used = {t[3] for t in tasks}

    suffix = "country" if collapse_mc else "country_keepmc"
    out_file = output_dir / f"mortality_aggregated_{suffix}_{args.mode}.parquet"

    if collapse_mc:
        # Small output (~4 MB): build the whole frame in memory, then write.
        df = _run_collapse_mc(tasks, n_workers, mode=args.mode)
        log.info(f"Pre-join rows: {len(df):,}")
        df = join_climate(df, args.climate_csv, args.mode, gcms_used=gcms_used)
        df = join_econ(df, args.econ_zarr, args.mode)
        sort_cols = [c for c in ["rcp", "ssp", "model", "region", "year"] if c in df.columns]
        df = df.sort_values(sort_cols).reset_index(drop=True)
        df.to_parquet(out_file, index=False, compression="zstd")
        log.info(f"Wrote {out_file} ({out_file.stat().st_size / 1e6:.1f} MB, {len(df):,} rows)")
        _summarize(df, out_file)
    else:
        # keep-MC: stream-write per scenario to avoid 100M+ row in-memory concat.
        clim_table = _load_climate_table(args.climate_csv, args.mode, gcms_used=gcms_used)
        econ_table = _load_econ_table(args.econ_zarr, args.mode)
        total_rows, summary_stats = _run_keep_mc_streaming(
            tasks, n_workers, mode=args.mode,
            clim_table=clim_table, econ_table=econ_table, out_file=out_file,
        )
        log.info(f"Wrote {out_file} ({out_file.stat().st_size / 1e6:.1f} MB, {total_rows:,} rows)")
        log.info("=" * 60)
        log.info(f"  Output:    {out_file}")
        log.info(f"  Rows:      {total_rows:,}")
        for k, v in summary_stats.items():
            log.info(f"  {k}: {v}")


def _summarize(df, out_file):
    log.info("=" * 60)
    log.info(f"  Output:    {out_file}")
    log.info(f"  Rows:      {len(df):,}")
    log.info(f"  Countries: {df['region'].nunique()}")
    log.info(f"  Years:     {df['year'].min()}-{df['year'].max()}")
    log.info(f"  RCPs:      {sorted(df['rcp'].unique())}")
    log.info(f"  SSPs:      {sorted(df['ssp'].unique())}")
    log.info(f"  Models:    {sorted(df['model'].unique())}")
    if "batch" in df.columns:
        log.info(f"  Batches:   {df['batch'].nunique()}")
        log.info(f"  GCMs:      {df['gcm'].nunique()}")
    s = df["adjusted_mortality"].dropna()
    log.info(f"  adjusted_mortality: mean={s.mean():.6e}, median={s.median():.6e}, "
             f"min={s.min():.6e}, max={s.max():.6e}")


def _run_keep_mc_streaming(tasks, n_workers, mode, clim_table, econ_table, out_file):
    """Process scenario-by-scenario, join climate + econ, stream-write to parquet.

    Avoids the giant concat that OOMs at 30 GB for ~180M rows. Peak memory
    is one scenario's joined DataFrame (~700 MB for mortality country).
    """
    writer = None
    total_rows = 0
    countries = set()
    years_seen = set()
    rcps_seen = set()
    ssps_seen = set()
    models_seen = set()
    batches_seen = set()
    gcms_seen = set()
    impact_sum = 0.0
    impact_sum_sq = 0.0
    impact_count = 0
    impact_min = float("inf")
    impact_max = float("-inf")

    if mode == "smoke":
        all_dfs = []
        for t in tasks:
            d = process_one_sim_keep_mc(t)
            if d is not None:
                all_dfs.append(d)
        if not all_dfs:
            log.error("No valid sims processed")
            sys.exit(1)
        df = pd.concat(all_dfs, ignore_index=True)
        df = _join_scenario(df, clim_table, econ_table)
        df = df.sort_values(["rcp", "ssp", "model", "batch", "gcm", "region", "year"]).reset_index(drop=True)
        df.to_parquet(out_file, index=False, compression="zstd")
        total_rows = len(df)
        countries.update(df["region"].unique())
        years_seen.update(df["year"].unique())
        rcps_seen.update(df["rcp"].unique())
        ssps_seen.update(df["ssp"].unique())
        models_seen.update(df["model"].unique())
        batches_seen.update(df["batch"].unique())
        gcms_seen.update(df["gcm"].unique())
        s = df["adjusted_mortality"].dropna()
        impact_count = len(s)
        impact_sum = float(s.sum())
        impact_sum_sq = float((s ** 2).sum())
        impact_min = float(s.min()) if impact_count else float("inf")
        impact_max = float(s.max()) if impact_count else float("-inf")
    else:
        groups = defaultdict(list)
        for t in tasks:
            groups[(t[2], t[5], t[4])].append(t)
        log.info(f"Grouping into {len(groups)} scenarios for streaming write")
        mp_ctx = mp.get_context("spawn")
        for i, (scen, g_tasks) in enumerate(sorted(groups.items()), start=1):
            log.info(f"[{i}/{len(groups)}] scenario {scen}: {len(g_tasks):,} sims")
            sim_dfs = []
            with ProcessPoolExecutor(max_workers=n_workers, mp_context=mp_ctx) as pool:
                processed, skipped = 0, 0
                for d in pool.map(process_one_sim_keep_mc, g_tasks, chunksize=2):
                    processed += 1
                    if processed % 50 == 0:
                        log.info(f"  processed {processed:,} / {len(g_tasks):,} sims")
                    if d is None:
                        skipped += 1
                        continue
                    sim_dfs.append(d)
            log.info(f"  group done: {processed - skipped:,} valid / {skipped} skipped")
            if not sim_dfs:
                continue
            scen_df = pd.concat(sim_dfs, ignore_index=True)
            del sim_dfs
            scen_df = _join_scenario(scen_df, clim_table, econ_table)
            scen_df = scen_df.sort_values(
                ["rcp", "ssp", "model", "batch", "gcm", "region", "year"]
            ).reset_index(drop=True)

            table = pa.Table.from_pandas(scen_df, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(out_file, table.schema, compression="zstd")
            writer.write_table(table)

            # Stats accumulation (cheap to do on each scenario)
            total_rows += len(scen_df)
            countries.update(scen_df["region"].unique())
            years_seen.update(scen_df["year"].unique())
            rcps_seen.update(scen_df["rcp"].unique())
            ssps_seen.update(scen_df["ssp"].unique())
            models_seen.update(scen_df["model"].unique())
            batches_seen.update(scen_df["batch"].unique())
            gcms_seen.update(scen_df["gcm"].unique())
            s = scen_df["adjusted_mortality"].dropna()
            impact_count += len(s)
            impact_sum += float(s.sum())
            impact_sum_sq += float((s ** 2).sum())
            if len(s):
                impact_min = min(impact_min, float(s.min()))
                impact_max = max(impact_max, float(s.max()))
            log.info(f"  scenario rows: {len(scen_df):,}; cumulative: {total_rows:,}")
            del scen_df, table
            gc.collect()

        if writer is not None:
            writer.close()

    if total_rows == 0:
        log.error("No valid sims produced any rows")
        sys.exit(1)

    impact_mean = impact_sum / impact_count if impact_count else float("nan")
    impact_var = (impact_sum_sq / impact_count - impact_mean ** 2) if impact_count else float("nan")
    impact_std = impact_var ** 0.5 if impact_var >= 0 else float("nan")
    summary_stats = {
        "Countries": len(countries),
        "Years":     f"{min(years_seen)}-{max(years_seen)}" if years_seen else "(none)",
        "RCPs":      sorted(rcps_seen),
        "SSPs":      sorted(ssps_seen),
        "Models":    sorted(models_seen),
        "Batches":   len(batches_seen),
        "GCMs":      len(gcms_seen),
        "adjusted_mortality": (
            f"mean={impact_mean:.6e}, std={impact_std:.6e}, "
            f"min={impact_min:.6e}, max={impact_max:.6e}, n={impact_count:,}"
        ),
    }
    return total_rows, summary_stats


def _run_collapse_mc(tasks, n_workers, mode):
    """Streaming-mean aggregation over batch x GCM (original behavior)."""
    acc = {}
    if mode == "smoke":
        results = (process_one_sim(t) for t in tasks)
        acc = accumulate_impacts(results, total=len(tasks), acc=acc)
    else:
        groups = defaultdict(list)
        for t in tasks:
            groups[(t[2], t[5], t[4])].append(t)
        log.info(f"Grouping into {len(groups)} scenarios for sequential processing")
        mp_ctx = mp.get_context("spawn")
        for i, (scen, g_tasks) in enumerate(sorted(groups.items()), start=1):
            log.info(f"[{i}/{len(groups)}] scenario {scen}: {len(g_tasks):,} sims")
            with ProcessPoolExecutor(max_workers=n_workers, mp_context=mp_ctx) as pool:
                results = pool.map(process_one_sim, g_tasks, chunksize=2)
                acc = accumulate_impacts(results, total=len(g_tasks), acc=acc)
            gc.collect()
    if not acc:
        log.error("No valid sims processed")
        sys.exit(1)
    log.info("Building long-format frame from accumulators")
    return build_long_frame(acc)


if __name__ == "__main__":
    main()
