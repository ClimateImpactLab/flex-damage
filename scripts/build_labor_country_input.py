#!/usr/bin/env python3
"""
Build labor COUNTRY-level input parquet by pop-weight aggregating IR-level
files ourselves (instead of reading the projection system's pre-aggregated
country file, which only exists for SSP3).

Methodology validated against the projection system's `*-pop-aggregated.nc4`
for SSP3: our reproduction matches to ~1e-7 relative tolerance, so applying
the same method to SSP2 / SSP4 (where the projection system never ran the
aggregation step) gives values on the same scale and methodology as SSP3.

Source layout (per sim):
  <basepath>/<batch>/<rcp>/<gcm>/<model>/<ssp>/
      uninteracted_main_model.nc4               (main, 24378 IRs, 3 vars)
      uninteracted_main_model-histclim.nc4      (histclim baseline)

The two nc4 files contain three variables we use:
  rebased        -> labor_combined
  highriskimpacts-> labor_high_risk
  lowriskimpacts -> labor_low_risk

Default: keep all MC draws (batch + GCM as columns). Use --collapse-mc or
set data.collapse_mc: true in config to mean-collapse over MC.
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

BASEPATH = "/project/cil/gcp/outputs/labor/impacts-woodwork/montecarlo/uninteracted_main_model_27_37_39"
CLIMATE_CSV = "/project/cil/home_dirs/scadavidsanchez/projects/flex-damage-functions-ir/dataset/climate/gcm_temp_gmst_year_preind1986-2005.csv"
SOCIO_ZARR = "/project/cil/gcp/integration_replication/inputs/econ/raw/integration-econ-bc39.zarr"

IAM_MAPPING = {"IIASA GDP": "low", "OECD Env-Growth": "high"}
TARGET_YEAR_MIN = 2010
TARGET_YEAR_MAX = 2099
SMOKE_SIM = {"batch": "batch0", "rcp": "rcp45", "gcm": "ACCESS1-0", "model": "high", "ssp": "SSP3"}

MAIN_NC4 = "uninteracted_main_model.nc4"            # IR-level (24378 hierids)
HIST_NC4 = "uninteracted_main_model-histclim.nc4"   # IR-level
NC_VARS = {                                          # builder col -> nc4 var
    "labor_combined":  "rebased",
    "labor_high_risk": "highriskimpacts",
    "labor_low_risk":  "lowriskimpacts",
}
IMPACT_COLS = list(NC_VARS.keys())

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# Globals populated by initializer for multiprocessing workers
_HIERIDS = None       # ndarray[str], length n_ir = 24378
_S = None             # ndarray[float32, (n_country, n_ir)]
_COUNTRIES = None     # ndarray[str], length n_country
_POP_LOOKUP = None    # dict[(ssp, model)] -> ndarray[float32, (n_year, n_ir)]


def is_country(reg: str) -> bool:
    return bool(reg) and ("." not in reg) and (not reg.startswith("FUND"))


def _build_country_aggregator(hierids):
    """S[c, i] = 1 iff hierids[i] belongs to country c."""
    country_codes = np.array([h.split(".")[0] for h in hierids])
    countries, inv = np.unique(country_codes, return_inverse=True)
    n_c, n_ir = len(countries), len(hierids)
    S = np.zeros((n_c, n_ir), dtype=np.float32)
    S[inv, np.arange(n_ir)] = 1.0
    return countries, S


def _build_pop_lookup(econ_zarr, mode, hierids, target_years):
    """Pre-build pop arrays aligned to (target_years, hierids) per (ssp, model).
    Returns dict[(ssp, model)] -> ndarray[float32, (n_year, n_ir)].
    """
    log.info(f"Loading pop tables from {econ_zarr}")
    ds = xr.open_zarr(econ_zarr)
    if "model" in ds.coords:
        ds = ds.assign_coords(model=[IAM_MAPPING.get(str(m), str(m)) for m in ds.model.values])
    if mode == "smoke":
        ds = ds.sel(ssp=SMOKE_SIM["ssp"], model=SMOKE_SIM["model"])
    df = ds["pop"].to_dataframe().reset_index()
    df["year"] = df["year"].astype(int)
    df = df.rename(columns={"region": "hierid"})
    df["pop"] = df["pop"].fillna(0).astype(np.float32)
    df = df[(df["year"] >= int(min(target_years))) & (df["year"] <= int(max(target_years)))]
    if mode == "smoke":
        df["ssp"] = SMOKE_SIM["ssp"]
        df["model"] = SMOKE_SIM["model"]

    out = {}
    for (ssp, model), grp in df.groupby(["ssp", "model"], as_index=False):
        pivot = grp.pivot(index="year", columns="hierid", values="pop")
        arr = pivot.reindex(index=target_years, columns=hierids, fill_value=0.0).values.astype(np.float32)
        out[(str(ssp), str(model))] = arr
    log.info(f"  loaded pop arrays for {len(out)} (ssp, model) combos")
    return out


def _worker_init(hierids, S, countries, pop_lookup):
    global _HIERIDS, _S, _COUNTRIES, _POP_LOOKUP
    _HIERIDS = hierids
    _S = S
    _COUNTRIES = countries
    _POP_LOOKUP = pop_lookup


def _read_ir_vars(path):
    """Return dict[k]=ndarray[(n_year, n_ir)] for the 3 NC_VARS, plus years and regions."""
    with xr.open_dataset(path, chunks=None) as ds:
        ds.load()
        vals = {k: ds[v].values.astype(np.float32) for k, v in NC_VARS.items()}
        years = ds["year"].values.astype(int)
        regs = ds["regions"].values.astype(str)
    return vals, years, regs


def _aggregate(impact_ir, pop_arr, S):
    """Pop-weight IR -> country: country = (S @ (pop * impact)) / (S @ pop)."""
    weighted = impact_ir * pop_arr                 # (n_year, n_ir)
    num = weighted @ S.T                            # (n_year, n_country)
    den = pop_arr @ S.T
    return num / np.maximum(den, 1e-9)


def process_one_sim(args):
    sim_dir, batch, rcp, gcm, model, ssp = args
    try:
        m_path = os.path.join(sim_dir, MAIN_NC4)
        h_path = os.path.join(sim_dir, HIST_NC4)
        if not (os.path.exists(m_path) and os.path.exists(h_path)):
            return None

        m_vals, m_years, m_regs = _read_ir_vars(m_path)
        h_vals, h_years, h_regs = _read_ir_vars(h_path)

        if not np.array_equal(m_regs, _HIERIDS):
            log.warning(f"Sim {sim_dir}: hierid order differs from bootstrap; skipping")
            return None

        target = np.arange(TARGET_YEAR_MIN, TARGET_YEAR_MAX + 1)
        m_yi = {int(y): i for i, y in enumerate(m_years)}
        h_yi = {int(y): i for i, y in enumerate(h_years)}
        # Use intersection of available target years (some sims drop tail years)
        available = [y for y in target if int(y) in m_yi and int(y) in h_yi]
        if len(available) < 10:
            log.warning(f"Sim {sim_dir}: only {len(available)} target years available; skipping")
            return None
        target = np.array(available)
        m_idx = np.array([m_yi[int(y)] for y in target])
        h_idx = np.array([h_yi[int(y)] for y in target])

        pop_arr = _POP_LOOKUP.get((ssp, model))
        if pop_arr is None:
            log.warning(f"Sim {sim_dir}: no pop for ({ssp},{model}); skipping")
            return None

        # If our pop array was built for the *full* target range and the sim
        # drops trailing years, slice pop accordingly.
        full_target = np.arange(TARGET_YEAR_MIN, TARGET_YEAR_MAX + 1)
        idx_in_full = np.array([list(full_target).index(int(y)) for y in target])
        pop_used = pop_arr[idx_in_full]

        impacts_country = np.empty((len(target), _S.shape[0], len(IMPACT_COLS)), dtype=np.float32)
        for vi, k in enumerate(IMPACT_COLS):
            ir_impact = m_vals[k][m_idx] - h_vals[k][h_idx]   # (n_year, n_ir)
            impacts_country[:, :, vi] = _aggregate(ir_impact, pop_used, _S)

        return {"scenario": (rcp, ssp, model),
                "impacts": impacts_country,
                "years": target,
                "regions": _COUNTRIES,
                "batch": batch, "gcm": gcm}
    except Exception as e:
        log.warning(f"Failed on {sim_dir}: {e}")
        return None


def process_one_sim_keep_mc(args):
    sim_dir, batch, rcp, gcm, model, ssp = args
    res = process_one_sim(args)
    if res is None:
        return None
    impacts = res["impacts"]
    years = res["years"]
    regs = res["regions"]
    n_y, n_r, _ = impacts.shape
    df = pd.DataFrame({
        "rcp": rcp, "ssp": ssp, "model": model,
        "batch": batch, "gcm": gcm,
        "year": np.repeat(years, n_r),
        "region": np.tile(regs, n_y),
        "labor_combined":  impacts[:, :, 0].reshape(-1),
        "labor_high_risk": impacts[:, :, 1].reshape(-1),
        "labor_low_risk":  impacts[:, :, 2].reshape(-1),
    })
    return df


def discover_sims(basepath, mode):
    tasks = []
    if mode == "smoke":
        sd = os.path.join(basepath, SMOKE_SIM["batch"], SMOKE_SIM["rcp"],
                          SMOKE_SIM["gcm"], SMOKE_SIM["model"], SMOKE_SIM["ssp"])
        if os.path.isdir(sd):
            tasks.append((sd, SMOKE_SIM["batch"], SMOKE_SIM["rcp"], SMOKE_SIM["gcm"],
                          SMOKE_SIM["model"], SMOKE_SIM["ssp"]))
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
                            tasks.append((sd, batch, rcp, gcm, model, ssp))
    return tasks


def _bootstrap_hierids(tasks):
    """Read one IR nc4 to lock in canonical hierid order."""
    for (sd, *_) in tasks:
        p = os.path.join(sd, MAIN_NC4)
        if os.path.exists(p):
            with xr.open_dataset(p, chunks=None) as ds:
                return ds["regions"].values.astype(str)
    log.error("Could not locate any sim to bootstrap hierids")
    sys.exit(1)


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
        mean3 = (d["sum"] / d["count"]).astype(np.float32)
        ny, nr, _ = mean3.shape
        df = pd.DataFrame({
            "rcp": rcp, "ssp": ssp, "model": model,
            "year": np.repeat(d["years"], nr),
            "region": np.tile(d["regions"], ny),
            "labor_combined":  mean3[:, :, 0].reshape(-1),
            "labor_high_risk": mean3[:, :, 1].reshape(-1),
            "labor_low_risk":  mean3[:, :, 2].reshape(-1),
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


def _load_econ_country_table(econ_zarr, mode):
    log.info(f"Loading country econ from {econ_zarr}")
    ds = xr.open_zarr(econ_zarr)
    for v in ("gdp",):
        if v in ds:
            ds = ds.drop_vars(v)
    ds["year"] = ds.year.astype(int)
    if "model" in ds.coords:
        ds = ds.assign_coords(model=[IAM_MAPPING.get(str(m), str(m)) for m in ds.model.values])
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


def _run_collapse_mc(tasks, n_workers, mode, hierids, S, countries, pop_lookup):
    acc = {}
    if mode == "smoke":
        # init globals in the parent for serial run
        _worker_init(hierids, S, countries, pop_lookup)
        results = (process_one_sim(t) for t in tasks)
        acc = accumulate_impacts(results, total=len(tasks), acc=acc)
    else:
        groups = defaultdict(list)
        for t in tasks:
            groups[(t[2], t[5], t[4])].append(t)  # (rcp, ssp, model)
        log.info(f"Grouping into {len(groups)} scenarios")
        mp_ctx = mp.get_context("spawn")
        for i, (scen, gt) in enumerate(sorted(groups.items()), start=1):
            log.info(f"[{i}/{len(groups)}] scenario {scen}: {len(gt):,} sims")
            with ProcessPoolExecutor(
                max_workers=n_workers, mp_context=mp_ctx,
                initializer=_worker_init,
                initargs=(hierids, S, countries, pop_lookup),
            ) as pool:
                results = pool.map(process_one_sim, gt, chunksize=2)
                acc = accumulate_impacts(results, total=len(gt), acc=acc)
            gc.collect()
    if not acc:
        log.error("No valid sims")
        sys.exit(1)
    return build_long_frame_collapse(acc)


def _run_keep_mc_streaming(tasks, n_workers, mode, hierids, S, countries, pop_lookup,
                           clim_table, econ_table, out_file):
    writer = None
    total_rows = 0
    cset, ys, rcps_seen, ssps_seen, models_seen, batches_seen, gcms_seen = (
        set(), set(), set(), set(), set(), set(), set()
    )
    impact_stats = {col: {"sum": 0.0, "sum_sq": 0.0, "count": 0,
                          "min": float("inf"), "max": float("-inf")} for col in IMPACT_COLS}

    def update_stats(df):
        nonlocal total_rows
        total_rows += len(df)
        cset.update(df["region"].unique())
        ys.update(df["year"].unique())
        rcps_seen.update(df["rcp"].unique())
        ssps_seen.update(df["ssp"].unique())
        models_seen.update(df["model"].unique())
        if "batch" in df.columns:
            batches_seen.update(df["batch"].unique())
            gcms_seen.update(df["gcm"].unique())
        for col in IMPACT_COLS:
            s = df[col].dropna()
            if len(s):
                impact_stats[col]["count"] += len(s)
                impact_stats[col]["sum"] += float(s.sum())
                impact_stats[col]["sum_sq"] += float((s ** 2).sum())
                impact_stats[col]["min"] = min(impact_stats[col]["min"], float(s.min()))
                impact_stats[col]["max"] = max(impact_stats[col]["max"], float(s.max()))

    if mode == "smoke":
        _worker_init(hierids, S, countries, pop_lookup)
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
            with ProcessPoolExecutor(
                max_workers=n_workers, mp_context=mp_ctx,
                initializer=_worker_init,
                initargs=(hierids, S, countries, pop_lookup),
            ) as pool:
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

    summary = {"Countries": len(cset),
               "Years": f"{min(ys)}-{max(ys)}" if ys else "(none)",
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
    p.add_argument("--mode", required=True, choices=["smoke", "full"])
    p.add_argument("--output-dir", required=True)
    p.add_argument("--basepath", default=BASEPATH)
    p.add_argument("--climate-csv", default=CLIMATE_CSV)
    p.add_argument("--econ-zarr", default=SOCIO_ZARR)
    p.add_argument("--n-workers", type=int, default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--config", default=None)
    p.add_argument("--collapse-mc", action="store_true")
    p.add_argument("--keep-mc", action="store_true")
    args = p.parse_args()

    collapse_mc = _resolve_collapse_mc(args)
    log.info(f"Mode: {args.mode}, collapse_mc: {collapse_mc}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "country" if collapse_mc else "country_keepmc"
    out_file = output_dir / f"labor_aggregated_{suffix}_{args.mode}.parquet"

    tasks = discover_sims(args.basepath, args.mode)
    log.info(f"Discovered {len(tasks):,} sim directories")
    if args.limit is not None:
        tasks = tasks[: args.limit]
    if not tasks:
        log.error("No sims found")
        sys.exit(1)

    n_workers = args.n_workers or (os.cpu_count() or 4)
    gcms_used = {t[3] for t in tasks}

    # Bootstrap hierid order, build country aggregator + pop lookup once
    hierids = _bootstrap_hierids(tasks)
    log.info(f"Bootstrapped hierids: {len(hierids):,}")
    countries, S = _build_country_aggregator(hierids)
    log.info(f"Country aggregator: {len(countries)} countries; S shape={S.shape}")
    target_years = np.arange(TARGET_YEAR_MIN, TARGET_YEAR_MAX + 1)
    pop_lookup = _build_pop_lookup(args.econ_zarr, args.mode, hierids, target_years)

    if collapse_mc:
        df = _run_collapse_mc(tasks, n_workers, args.mode, hierids, S, countries, pop_lookup)
        clim_table = _load_climate_table(args.climate_csv, args.mode, gcms_used=gcms_used)
        econ_table = _load_econ_country_table(args.econ_zarr, args.mode)
        if "gcm" in clim_table.columns:
            clim_table = clim_table.groupby(["rcp", "year"], as_index=False)["temperature_anomaly"].mean()
        df = _join_scenario(df, clim_table, econ_table)
        df = df.sort_values(["rcp", "ssp", "model", "region", "year"]).reset_index(drop=True)
        df.to_parquet(out_file, index=False, compression="zstd")
        log.info(f"Wrote {out_file} ({out_file.stat().st_size / 1e6:.1f} MB, {len(df):,} rows)")
        for col in IMPACT_COLS:
            s = df[col].dropna()
            log.info(f"  {col}: mean={s.mean():.4e}, std={s.std():.4e}, n={len(s):,}")
    else:
        clim_table = _load_climate_table(args.climate_csv, args.mode, gcms_used=gcms_used)
        econ_table = _load_econ_country_table(args.econ_zarr, args.mode)
        total_rows, summary = _run_keep_mc_streaming(
            tasks, n_workers, args.mode, hierids, S, countries, pop_lookup,
            clim_table, econ_table, out_file,
        )
        log.info(f"Wrote {out_file} ({out_file.stat().st_size / 1e6:.1f} MB, {total_rows:,} rows)")
        log.info("=" * 60)
        for k, v in summary.items():
            log.info(f"  {k}: {v}")


if __name__ == "__main__":
    main()
