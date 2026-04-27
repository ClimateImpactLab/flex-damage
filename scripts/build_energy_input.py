#!/usr/bin/env python3
"""
Build energy (median valuation) input parquet for flexdamage.

Walks two parallel trees (electricity + other_energy), pairs sim dirs by
(rcp, gcm, model, ssp), computes fulladapt impact per subsector as:

    impact = main.rebased - histclim.rebased          (CIL rebasing memo 2.3.1)

Produces three y columns in one output parquet:
    energy_electricity      = electricity main - hist
    energy_non_electricity  = other_energy main - hist
    energy_total            = electricity + non_electricity

No batch dimension in the median path (these are median valuation outputs,
not MC draws). Aggregates over GCM x RCP x model x SSP as separate scenarios,
or keeps all as separate rows; the scenario_columns in config are
[rcp, ssp, model] so GCM gets averaged.

Modes
-----
smoke : one sim (rcp45/ACCESS1-0/high/SSP2) for pipeline test
full  : walk entire tree, running mean per (rcp, ssp, model) across GCMs

Units
-----
kWh per capita (physical). Sign: positive = more energy consumed.
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

ELEC_BASE = "/project/cil/gcp/outputs/energy_pixel_interaction/impacts-blueghost/median/electricity-global/median"
OTHER_BASE = "/project/cil/gcp/outputs/energy_pixel_interaction/impacts-blueghost/median/other_energy-global/median"

CLIMATE_CSV = "/project/cil/home_dirs/scadavidsanchez/projects/flex-damage-functions-ir/dataset/climate/gcm_temp_gmst_year_preind1986-2005.csv"
SOCIO_ZARR = "/project/cil/gcp/integration_replication/inputs/econ/raw/integration-econ-bc39.zarr"

IAM_MAPPING = {"IIASA GDP": "low", "OECD Env-Growth": "high"}

TARGET_YEAR_MIN = 2010
TARGET_YEAR_MAX = 2099

SMOKE_SIM = {"rcp": "rcp45", "gcm": "ACCESS1-0", "model": "high", "ssp": "SSP2"}

# file names per subsector (inside each sim dir)
ELEC_MAIN = "FD_FGLS_inter_OTHERIND_electricity_TINV_clim.nc4"
ELEC_HIST = "FD_FGLS_inter_OTHERIND_electricity_TINV_clim-histclim.nc4"
OTHER_MAIN = "FD_FGLS_inter_OTHERIND_other_energy_TINV_clim.nc4"
OTHER_HIST = "FD_FGLS_inter_OTHERIND_other_energy_TINV_clim-histclim.nc4"

IMPACT_COLS = ["energy_electricity", "energy_non_electricity", "energy_total"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)


def _read_rebased(path):
    with xr.open_dataset(path, chunks=None) as ds:
        ds.load()
        return (
            ds["rebased"].values.astype(np.float32),
            ds["year"].values.astype(int),
            ds["regions"].values.astype(str),
        )


def process_one_sim(args):
    """Compute electricity + non_electricity + total impact for one (rcp, gcm, model, ssp) slice."""
    rcp, gcm, model, ssp = args
    try:
        e_dir = os.path.join(ELEC_BASE, rcp, gcm, model, ssp)
        o_dir = os.path.join(OTHER_BASE, rcp, gcm, model, ssp)
        e_main_path = os.path.join(e_dir, ELEC_MAIN)
        e_hist_path = os.path.join(e_dir, ELEC_HIST)
        o_main_path = os.path.join(o_dir, OTHER_MAIN)
        o_hist_path = os.path.join(o_dir, OTHER_HIST)
        for p in (e_main_path, e_hist_path, o_main_path, o_hist_path):
            if not os.path.exists(p):
                log.warning(f"Missing {p}; skipping")
                return None

        e_main, e_years, regions = _read_rebased(e_main_path)
        e_hist, e_hyears, _ = _read_rebased(e_hist_path)
        o_main, o_years, _ = _read_rebased(o_main_path)
        o_hist, o_hyears, _ = _read_rebased(o_hist_path)

        # Slice to target year range via explicit index lookup (robust to any
        # ordering / missing-year mismatches between electricity/other trees).
        target = np.arange(TARGET_YEAR_MIN, TARGET_YEAR_MAX + 1)

        def select(arr, years_arr, label):
            year_to_idx = {int(y): i for i, y in enumerate(years_arr)}
            missing = [y for y in target if int(y) not in year_to_idx]
            if missing:
                return None, missing
            idx = np.array([year_to_idx[int(y)] for y in target])
            return arr[idx], None

        e_main_s, miss = select(e_main, e_years, "e_main")
        if miss:
            log.warning(f"Sim {rcp}/{gcm}/{model}/{ssp}: elec main missing {miss[:3]}; skipping")
            return None
        e_hist_s, miss = select(e_hist, e_hyears, "e_hist")
        if miss:
            log.warning(f"Sim {rcp}/{gcm}/{model}/{ssp}: elec hist missing {miss[:3]}; skipping")
            return None
        o_main_s, miss = select(o_main, o_years, "o_main")
        if miss:
            log.warning(f"Sim {rcp}/{gcm}/{model}/{ssp}: other main missing {miss[:3]}; skipping")
            return None
        o_hist_s, miss = select(o_hist, o_hyears, "o_hist")
        if miss:
            log.warning(f"Sim {rcp}/{gcm}/{model}/{ssp}: other hist missing {miss[:3]}; skipping")
            return None

        elec_impact = e_main_s - e_hist_s
        other_impact = o_main_s - o_hist_s
        total_impact = elec_impact + other_impact

        impacts = np.stack([elec_impact, other_impact, total_impact], axis=-1)  # (ny, nr, 3)

        expected = (len(target), len(regions), len(IMPACT_COLS))
        if impacts.shape != expected:
            log.warning(f"Sim {rcp}/{gcm}/{model}/{ssp}: shape {impacts.shape} vs expected {expected}; skipping")
            return None

        return {
            "scenario": (rcp, ssp, model),
            "impacts": impacts,
            "years": target,
            "regions": regions,
        }
    except Exception as e:
        log.warning(f"Failed on {rcp}/{gcm}/{model}/{ssp}: {e}")
        return None


def discover_sims(mode):
    """Walk electricity tree for sim candidates; other_energy is paired by name."""
    tasks = []
    if mode == "smoke":
        rcp, gcm, model, ssp = SMOKE_SIM["rcp"], SMOKE_SIM["gcm"], SMOKE_SIM["model"], SMOKE_SIM["ssp"]
        if os.path.isdir(os.path.join(ELEC_BASE, rcp, gcm, model, ssp)):
            tasks.append((rcp, gcm, model, ssp))
        return tasks

    for rcp in sorted(os.listdir(ELEC_BASE)):
        r_path = os.path.join(ELEC_BASE, rcp)
        if not os.path.isdir(r_path):
            continue
        for gcm in sorted(os.listdir(r_path)):
            g_path = os.path.join(r_path, gcm)
            if not os.path.isdir(g_path):
                continue
            for model in sorted(os.listdir(g_path)):
                m_path = os.path.join(g_path, model)
                if not os.path.isdir(m_path):
                    continue
                for ssp in sorted(os.listdir(m_path)):
                    s_path = os.path.join(m_path, ssp)
                    # Require the paired other_energy dir to exist too
                    o_path = os.path.join(OTHER_BASE, rcp, gcm, model, ssp)
                    if os.path.isdir(s_path) and os.path.isdir(o_path):
                        tasks.append((rcp, gcm, model, ssp))
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
                    f"Shape mismatch {key}: acc={acc[key]['sum'].shape}, new={r['impacts'].shape}; skipping sim"
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
            "energy_electricity":     mean3[:, :, 0].reshape(-1),
            "energy_non_electricity": mean3[:, :, 1].reshape(-1),
            "energy_total":           mean3[:, :, 2].reshape(-1),
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
        raise RuntimeError(f"No anomaly column in climate CSV. Columns: {list(clim.columns)}")
    clim = clim.rename(columns={anomaly_candidates[0]: "temperature_anomaly"})
    if mode == "smoke":
        clim = clim[clim["gcm"] == SMOKE_SIM["gcm"]]
    elif gcms_used is not None:
        clim = clim[clim["gcm"].isin(gcms_used)]
    T = clim.groupby(["rcp", "year"], as_index=False)["temperature_anomaly"].mean()
    df = df.merge(T, on=["rcp", "year"], how="left")
    n_missing = df["temperature_anomaly"].isna().sum()
    if n_missing > 0:
        log.warning(f"temperature_anomaly NaN in {n_missing:,} rows")
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
        log.warning(f"gdppc NaN in {n_missing:,} rows")
    return df


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", required=True, choices=["smoke", "full"])
    p.add_argument("--output-dir", required=True)
    p.add_argument("--climate-csv", default=CLIMATE_CSV)
    p.add_argument("--econ-zarr", default=SOCIO_ZARR)
    p.add_argument("--n-workers", type=int, default=None)
    p.add_argument("--limit", type=int, default=None, help="First N sims only (for tests)")
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"Mode: {args.mode}")
    log.info(f"Output dir: {output_dir}")

    tasks = discover_sims(args.mode)
    log.info(f"Discovered {len(tasks):,} paired (elec + other_energy) sim directories")
    if args.limit is not None:
        tasks = tasks[: args.limit]
        log.info(f"--limit applied: truncated to first {len(tasks):,}")
    if not tasks:
        log.error("No simulations found")
        sys.exit(1)

    n_workers = args.n_workers or (os.cpu_count() or 4)
    log.info(f"Processing with {n_workers} workers per scenario group")

    gcms_used = {t[1] for t in tasks}
    acc = {}

    if args.mode == "smoke":
        results = (process_one_sim(t) for t in tasks)
        acc = accumulate_impacts(results, total=len(tasks), acc=acc)
    else:
        groups = defaultdict(list)
        for t in tasks:
            groups[(t[0], t[3], t[2])].append(t)  # (rcp, ssp, model)
        log.info(f"Grouping into {len(groups)} scenarios for sequential processing")
        mp_ctx = mp.get_context("spawn")
        for i, (scen, g_tasks) in enumerate(sorted(groups.items()), start=1):
            log.info(f"[{i}/{len(groups)}] scenario {scen}: {len(g_tasks):,} sims (GCMs)")
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

    df = df.sort_values(["rcp", "ssp", "model", "region", "year"]).reset_index(drop=True)
    out_file = output_dir / f"energy_aggregated_{args.mode}.parquet"
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
    for col in IMPACT_COLS:
        s = df[col].dropna()
        log.info(f"  {col}: mean={s.mean():.4f}, std={s.std():.4f}, min={s.min():.4f}, max={s.max():.4f}")


if __name__ == "__main__":
    main()
