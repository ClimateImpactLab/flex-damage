#!/usr/bin/env python3
"""
Build agriculture COUNTRY-level input parquet from MC tree's -aggregated files.

Reads pre-aggregated nc4 files (5716-region hierarchy) under the projection
system's montecarlo tree and filters to country codes (no dots, no FUND
prefix). Single y var `log_yield_impact = main.rebased - histclim.rebased`
where rebased units = "log kg / Ha".

Source layout (per crop):
  <basepath>/<crop>-2025_1pct_winsorization/montecarlo/
      <batch>/<rcp>/<gcm>/<model>/<ssp>/
          <crop>-110221-aggregated.nc4         (main)
          <crop>-110221-histclim-aggregated.nc4 (histclim)

Default: keep all MC draws (batch + GCM as columns). Use --collapse-mc or set
data.collapse_mc: true in config to aggregate to scenario means.
"""

import argparse
import gc
import logging
import multiprocessing as mp
import os
import re
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

BASEPATH_TPL = ("/project/cil/gcp/outputs/agriculture/impacts-mealy/montecarlo/"
                "{crop}-2025_1pct_winsorization/montecarlo")
CLIMATE_CSV = "/project/cil/home_dirs/scadavidsanchez/projects/flex-damage-functions-ir/dataset/climate/gcm_temp_gmst_year_preind1986-2005.csv"
SOCIO_ZARR = "/project/cil/gcp/integration_replication/inputs/econ/raw/integration-econ-bc39.zarr"

IAM_MAPPING = {"IIASA GDP": "low", "OECD Env-Growth": "high"}
TARGET_YEAR_MIN = 2010
TARGET_YEAR_MAX = 2098  # ag aggregated.nc4 ends at 2098 (1981-2098, 118 years)
SMOKE_SIM = {"batch": "batch0", "rcp": "rcp45", "gcm": "ACCESS1-0", "model": "high", "ssp": "SSP3"}

NC_VAR = "rebased"        # variable name inside the nc4
IMPACT_COL = "log_yield_impact"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)


def is_country(reg: str) -> bool:
    return bool(reg) and ("." not in reg) and (not reg.startswith("FUND"))


# nc4 filenames are <crop>-<DDMMYY>-aggregated.nc4. The date stamp differs
# per crop (e.g. cassava=110221, corn/rice/soy/sorghum=160221, wheat*=280823),
# so we discover it once and pass it into each worker via the task tuple.
def _nc4_filenames(crop: str, suffix: str):
    return (f"{crop}-{suffix}-aggregated.nc4",
            f"{crop}-{suffix}-histclim-aggregated.nc4")


def _discover_crop_suffix(basepath: str, crop: str) -> str:
    """Walk one path of the MC tree until we find the <crop>-<NNNNNN>-aggregated.nc4
    file and return its numeric stamp. Excludes -histclim/-fulladaptcosts/etc."""
    pat = re.compile(rf"^{re.escape(crop)}-(\d+)-aggregated\.nc4$")
    for batch in sorted(d for d in os.listdir(basepath) if d.startswith("batch")):
        bdir = os.path.join(basepath, batch)
        if not os.path.isdir(bdir):
            continue
        for rcp in ("rcp45", "rcp85"):
            rdir = os.path.join(bdir, rcp)
            if not os.path.isdir(rdir):
                continue
            for gcm in os.listdir(rdir):
                gdir = os.path.join(rdir, gcm)
                if not os.path.isdir(gdir):
                    continue
                for model in os.listdir(gdir):
                    mdir = os.path.join(gdir, model)
                    if not os.path.isdir(mdir):
                        continue
                    for ssp in os.listdir(mdir):
                        sdir = os.path.join(mdir, ssp)
                        if not os.path.isdir(sdir):
                            continue
                        for f in os.listdir(sdir):
                            m = pat.match(f)
                            if m:
                                return m.group(1)
    return None


def process_one_sim(args):
    """Read sim's main + histclim, slice to country/years, return impacts dict."""
    sim_dir, batch, rcp, gcm, model, ssp, crop, suffix = args
    main_nc4, hist_nc4 = _nc4_filenames(crop, suffix)
    try:
        m_path = os.path.join(sim_dir, main_nc4)
        h_path = os.path.join(sim_dir, hist_nc4)
        if not (os.path.exists(m_path) and os.path.exists(h_path)):
            return None

        with xr.open_dataset(m_path, chunks=None) as ds:
            ds.load()
            m_arr = ds[NC_VAR].values.astype(np.float32)
            m_years = ds["year"].values.astype(int)
            regions_full = ds["regions"].values.astype(str)

        with xr.open_dataset(h_path, chunks=None) as ds:
            ds.load()
            h_arr = ds[NC_VAR].values.astype(np.float32)
            h_years = ds["year"].values.astype(int)

        country_mask = np.array([is_country(r) for r in regions_full], dtype=bool)
        if not country_mask.any():
            return None
        country_regs = regions_full[country_mask]
        m_arr = m_arr[:, country_mask]
        h_arr = h_arr[:, country_mask]

        target = np.arange(TARGET_YEAR_MIN, TARGET_YEAR_MAX + 1)
        m_yi = {int(y): i for i, y in enumerate(m_years)}
        h_yi = {int(y): i for i, y in enumerate(h_years)}
        miss = [y for y in target if int(y) not in m_yi or int(y) not in h_yi]
        if miss:
            log.warning(f"Sim {sim_dir} missing target years {miss[:3]}; skipping")
            return None
        m_idx = np.array([m_yi[int(y)] for y in target])
        h_idx = np.array([h_yi[int(y)] for y in target])

        impacts = m_arr[m_idx] - h_arr[h_idx]   # (n_year, n_country) log kg/Ha diff
        return {"scenario": (rcp, ssp, model), "impacts": impacts,
                "years": target, "regions": country_regs}
    except Exception as e:
        log.warning(f"Failed on {sim_dir}: {e}")
        return None


def process_one_sim_keep_mc(args):
    sim_dir, batch, rcp, gcm, model, ssp, crop, suffix = args
    res = process_one_sim(args)
    if res is None:
        return None
    impacts = res["impacts"]
    years = res["years"]
    regs = res["regions"]
    n_y, n_r = impacts.shape
    df = pd.DataFrame({
        "rcp": rcp, "ssp": ssp, "model": model,
        "batch": batch, "gcm": gcm,
        "year": np.repeat(years, n_r),
        "region": np.tile(regs, n_y),
        IMPACT_COL: impacts.reshape(-1),
    })
    return df


def discover_sims(basepath, mode, crop, suffix):
    tasks = []
    if mode == "smoke":
        sd = os.path.join(basepath, SMOKE_SIM["batch"], SMOKE_SIM["rcp"],
                          SMOKE_SIM["gcm"], SMOKE_SIM["model"], SMOKE_SIM["ssp"])
        if os.path.isdir(sd):
            tasks.append((sd, SMOKE_SIM["batch"], SMOKE_SIM["rcp"],
                          SMOKE_SIM["gcm"], SMOKE_SIM["model"], SMOKE_SIM["ssp"], crop, suffix))
        return tasks
    for batch in sorted(d for d in os.listdir(basepath) if d.startswith("batch")):
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
                            tasks.append((sd, batch, rcp, gcm, model, ssp, crop, suffix))
    return tasks


def accumulate_impacts(results_iter, total, acc=None):
    if acc is None:
        acc = {}
    processed, skipped = 0, 0
    for r in results_iter:
        processed += 1
        if processed % 50 == 0:
            log.info(f"  processed {processed:,} / {total:,} sims")
        if r is None:
            skipped += 1
            continue
        key = r["scenario"]
        if key not in acc:
            acc[key] = {"sum": r["impacts"].astype(np.float64), "count": 1,
                        "years": r["years"], "regions": r["regions"]}
        else:
            if r["impacts"].shape != acc[key]["sum"].shape:
                skipped += 1
                del r
                continue
            acc[key]["sum"] += r["impacts"].astype(np.float64)
            acc[key]["count"] += 1
        del r
    log.info(f"  group done: {processed - skipped:,} valid, {skipped:,} skipped")
    return acc


def build_long_frame_collapse(acc):
    dfs = []
    for (rcp, ssp, model), d in acc.items():
        mean2 = (d["sum"] / d["count"]).astype(np.float32)
        ny, nr = mean2.shape
        df = pd.DataFrame({
            "rcp": rcp, "ssp": ssp, "model": model,
            "year": np.repeat(d["years"], nr),
            "region": np.tile(d["regions"], ny),
            IMPACT_COL: mean2.reshape(-1),
        })
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def _load_climate_table(climate_csv, mode, gcms_used=None):
    log.info(f"Reading climate (one-time): {climate_csv}")
    clim = pd.read_csv(climate_csv)
    if "scenario" in clim.columns:
        clim = clim.rename(columns={"scenario": "rcp"})
    anom = next((c for c in clim.columns if c.lower() in ("anomaly", "anom", "tas", "temperature_anomaly")), None)
    clim = clim.rename(columns={anom: "temperature_anomaly"})
    if mode == "smoke":
        clim = clim[clim["gcm"] == SMOKE_SIM["gcm"]]
    elif gcms_used is not None:
        clim = clim[clim["gcm"].isin(gcms_used)]
    keep = [c for c in ("rcp", "gcm", "year", "temperature_anomaly") if c in clim.columns]
    return clim[keep].drop_duplicates()


def _load_econ_table(econ_zarr, mode):
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
    econ["country"] = econ["region"].astype(str).str.split(".").str[0]
    econ = econ[econ["country"].str.len() > 0]
    econ["pop"] = econ["pop"].fillna(0)
    econ["_gdppc_w"] = econ["gdppc"] * econ["pop"]
    grp = ["country", "year"] + [c for c in ("ssp", "model") if c in econ.columns]
    ec = econ.groupby(grp, as_index=False).agg(pop=("pop", "sum"), _gdppc_w=("_gdppc_w", "sum"))
    ec["gdppc"] = ec["_gdppc_w"] / ec["pop"].replace(0, np.nan)
    return ec.drop(columns=["_gdppc_w"]).rename(columns={"country": "region"})


def _join_scenario(scen_df, clim_table, econ_table):
    if "gcm" in scen_df.columns and "gcm" in clim_table.columns:
        merged = scen_df.merge(clim_table, on=["rcp", "gcm", "year"], how="left")
    else:
        T = clim_table.groupby(["rcp", "year"], as_index=False)["temperature_anomaly"].mean()
        merged = scen_df.merge(T, on=["rcp", "year"], how="left")
    join_keys = [c for c in ("region", "year", "ssp", "model") if c in econ_table.columns and c in merged.columns]
    return merged.merge(econ_table, on=join_keys, how="left")


def _resolve_collapse_mc(args) -> bool:
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
    return False


def _run_collapse_mc(tasks, n_workers, mode):
    acc = {}
    if mode == "smoke":
        results = (process_one_sim(t) for t in tasks)
        acc = accumulate_impacts(results, total=len(tasks), acc=acc)
    else:
        groups = defaultdict(list)
        for t in tasks:
            groups[(t[2], t[5], t[4])].append(t)  # rcp, ssp, model
        log.info(f"Grouping into {len(groups)} scenarios")
        mp_ctx = mp.get_context("spawn")
        for i, (scen, gt) in enumerate(sorted(groups.items()), start=1):
            log.info(f"[{i}/{len(groups)}] scenario {scen}: {len(gt):,} sims")
            with ProcessPoolExecutor(max_workers=n_workers, mp_context=mp_ctx) as pool:
                results = pool.map(process_one_sim, gt, chunksize=2)
                acc = accumulate_impacts(results, total=len(gt), acc=acc)
            gc.collect()
    if not acc:
        log.error("No valid sims")
        sys.exit(1)
    return build_long_frame_collapse(acc)


def _run_keep_mc_streaming(tasks, n_workers, mode, clim_table, econ_table, out_file):
    """Stream per-scenario joined frames to a single parquet via pyarrow."""
    writer = None
    total_rows = 0
    countries, years_seen, rcps_seen, ssps_seen, models_seen, batches_seen, gcms_seen = (
        set(), set(), set(), set(), set(), set(), set()
    )
    impact_stats = {col: {"sum": 0.0, "sum_sq": 0.0, "count": 0,
                          "min": float("inf"), "max": float("-inf")} for col in [IMPACT_COL]}

    def update_stats(df):
        nonlocal total_rows
        total_rows += len(df)
        countries.update(df["region"].unique())
        years_seen.update(df["year"].unique())
        rcps_seen.update(df["rcp"].unique())
        ssps_seen.update(df["ssp"].unique())
        models_seen.update(df["model"].unique())
        if "batch" in df.columns:
            batches_seen.update(df["batch"].unique())
            gcms_seen.update(df["gcm"].unique())
        for col in [IMPACT_COL]:
            s = df[col].dropna()
            if len(s):
                impact_stats[col]["count"] += len(s)
                impact_stats[col]["sum"] += float(s.sum())
                impact_stats[col]["sum_sq"] += float((s ** 2).sum())
                impact_stats[col]["min"] = min(impact_stats[col]["min"], float(s.min()))
                impact_stats[col]["max"] = max(impact_stats[col]["max"], float(s.max()))

    if mode == "smoke":
        all_dfs = [d for t in tasks for d in [process_one_sim_keep_mc(t)] if d is not None]
        if not all_dfs:
            log.error("No valid sims")
            sys.exit(1)
        df = pd.concat(all_dfs, ignore_index=True)
        df = _join_scenario(df, clim_table, econ_table)
        df = df.sort_values(["rcp", "ssp", "model", "batch", "gcm", "region", "year"]).reset_index(drop=True)
        df.to_parquet(out_file, index=False, compression="zstd")
        update_stats(df)
    else:
        groups = defaultdict(list)
        for t in tasks:
            groups[(t[2], t[5], t[4])].append(t)
        log.info(f"Grouping into {len(groups)} scenarios for streaming write")
        mp_ctx = mp.get_context("spawn")
        for i, (scen, gt) in enumerate(sorted(groups.items()), start=1):
            log.info(f"[{i}/{len(groups)}] scenario {scen}: {len(gt):,} sims")
            sim_dfs = []
            with ProcessPoolExecutor(max_workers=n_workers, mp_context=mp_ctx) as pool:
                proc, skip = 0, 0
                for d in pool.map(process_one_sim_keep_mc, gt, chunksize=2):
                    proc += 1
                    if proc % 50 == 0:
                        log.info(f"  processed {proc:,} / {len(gt):,} sims")
                    if d is None:
                        skip += 1
                        continue
                    sim_dfs.append(d)
            log.info(f"  group done: {proc - skip:,} valid, {skip} skipped")
            if not sim_dfs:
                continue
            scen_df = pd.concat(sim_dfs, ignore_index=True)
            del sim_dfs
            scen_df = _join_scenario(scen_df, clim_table, econ_table)
            scen_df = scen_df.sort_values(["rcp", "ssp", "model", "batch", "gcm", "region", "year"]).reset_index(drop=True)
            tbl = pa.Table.from_pandas(scen_df, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(out_file, tbl.schema, compression="zstd")
            writer.write_table(tbl)
            update_stats(scen_df)
            log.info(f"  scenario rows: {len(scen_df):,}; cumulative: {total_rows:,}")
            del scen_df, tbl
            gc.collect()
        if writer is not None:
            writer.close()

    if total_rows == 0:
        log.error("No rows produced")
        sys.exit(1)

    summary = {"Countries": len(countries),
               "Years": f"{min(years_seen)}-{max(years_seen)}" if years_seen else "(none)",
               "RCPs": sorted(rcps_seen), "SSPs": sorted(ssps_seen),
               "Models": sorted(models_seen),
               "Batches": len(batches_seen), "GCMs": len(gcms_seen)}
    for col, s in impact_stats.items():
        if s["count"]:
            mean = s["sum"] / s["count"]
            var = max(0.0, s["sum_sq"] / s["count"] - mean ** 2)
            summary[col] = (f"mean={mean:.4e}, std={var**0.5:.4e}, "
                            f"min={s['min']:.4e}, max={s['max']:.4e}, n={s['count']:,}")
    return total_rows, summary


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--crop", required=True,
                   help="corn, rice, soy, sorghum, cassava, wheat_combined, wheat_spring, wheat_winter")
    p.add_argument("--mode", required=True, choices=["smoke", "full"])
    p.add_argument("--output-dir", required=True)
    p.add_argument("--basepath", default=None,
                   help="If unset, derived from --crop using BASEPATH_TPL")
    p.add_argument("--climate-csv", default=CLIMATE_CSV)
    p.add_argument("--econ-zarr", default=SOCIO_ZARR)
    p.add_argument("--n-workers", type=int, default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--config", default=None)
    p.add_argument("--collapse-mc", action="store_true")
    p.add_argument("--keep-mc", action="store_true")
    args = p.parse_args()

    basepath = args.basepath or BASEPATH_TPL.format(crop=args.crop)
    if not os.path.isdir(basepath):
        log.error(f"Basepath not found: {basepath}")
        sys.exit(1)

    collapse_mc = _resolve_collapse_mc(args)
    log.info(f"Crop: {args.crop}, mode: {args.mode}, collapse_mc: {collapse_mc}")
    log.info(f"Basepath: {basepath}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_kind = "country" if collapse_mc else "country_keepmc"
    out_file = output_dir / f"agriculture_{args.crop}_aggregated_{out_kind}_{args.mode}.parquet"

    crop_suffix = _discover_crop_suffix(basepath, args.crop)
    if crop_suffix is None:
        log.error(f"Could not discover nc4 date stamp for crop {args.crop} under {basepath}")
        sys.exit(1)
    log.info(f"Discovered nc4 date stamp for {args.crop}: {crop_suffix}")

    tasks = discover_sims(basepath, args.mode, args.crop, crop_suffix)
    log.info(f"Discovered {len(tasks):,} sim directories")
    if args.limit is not None:
        tasks = tasks[: args.limit]
    if not tasks:
        log.error("No sims found")
        sys.exit(1)

    n_workers = args.n_workers or (os.cpu_count() or 4)
    gcms_used = {t[3] for t in tasks}

    if collapse_mc:
        df = _run_collapse_mc(tasks, n_workers, mode=args.mode)
        clim_table = _load_climate_table(args.climate_csv, args.mode, gcms_used=gcms_used)
        econ_table = _load_econ_table(args.econ_zarr, args.mode)
        if "gcm" in clim_table.columns:
            clim_table = clim_table.groupby(["rcp", "year"], as_index=False)["temperature_anomaly"].mean()
        df = _join_scenario(df, clim_table, econ_table)
        df = df.sort_values(["rcp", "ssp", "model", "region", "year"]).reset_index(drop=True)
        df.to_parquet(out_file, index=False, compression="zstd")
        log.info(f"Wrote {out_file} ({out_file.stat().st_size / 1e6:.1f} MB, {len(df):,} rows)")
        s = df[IMPACT_COL].dropna()
        log.info(f"  {IMPACT_COL}: mean={s.mean():.4e}, std={s.std():.4e}, n={len(s):,}")
    else:
        clim_table = _load_climate_table(args.climate_csv, args.mode, gcms_used=gcms_used)
        econ_table = _load_econ_table(args.econ_zarr, args.mode)
        total_rows, summary = _run_keep_mc_streaming(
            tasks, n_workers, mode=args.mode,
            clim_table=clim_table, econ_table=econ_table, out_file=out_file,
        )
        log.info(f"Wrote {out_file} ({out_file.stat().st_size / 1e6:.1f} MB, {total_rows:,} rows)")
        log.info("=" * 60)
        for k, v in summary.items():
            log.info(f"  {k}: {v}")


if __name__ == "__main__":
    main()
