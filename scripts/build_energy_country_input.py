#!/usr/bin/env python3
"""
Build energy COUNTRY-level input parquet from IR-level kWh/pc files.

Reads IR-level (24378 hierids) main + histclim nc4 files, computes per-IR
impact = main.rebased - histclim.rebased (units kWh/pc), then aggregates
IR -> country with pop-weighted mean.

Why IR-level rather than the existing country-aggregated nc4: the projection
system's country-aggregated energy file (`*-global-price014-aggregated.nc4`)
has units = "dollar" (climate-attributable energy *cost*), which is a
different physical quantity than the IR pipeline regresses on (kWh/pc).
To stay methodologically consistent across IR and country resolutions, we
build the country aggregation ourselves from the same IR-level inputs.

Source layout (per scenario):
  <base>/<rcp>/<gcm>/<model>/<ssp>/
      FD_FGLS_inter_OTHERIND_<type>_TINV_clim.nc4               (main, IR)
      FD_FGLS_inter_OTHERIND_<type>_TINV_clim-histclim.nc4      (histclim, IR)

Energy median dir has no batch dim. There's one realization per scenario
tuple (rcp x gcm x model x ssp). So `--collapse-mc` is a no-op for energy
and the output schema does not include a `batch` column. The IR pipeline
has the same limitation.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import yaml

ELEC_BASE = "/project/cil/gcp/outputs/energy_pixel_interaction/impacts-blueghost/median/electricity-global/median"
OTHER_BASE = "/project/cil/gcp/outputs/energy_pixel_interaction/impacts-blueghost/median/other_energy-global/median"
CLIMATE_CSV = "/project/cil/home_dirs/scadavidsanchez/projects/flex-damage-functions-ir/dataset/climate/gcm_temp_gmst_year_preind1986-2005.csv"
SOCIO_ZARR = "/project/cil/gcp/integration_replication/inputs/econ/raw/integration-econ-bc39.zarr"

IAM_MAPPING = {"IIASA GDP": "low", "OECD Env-Growth": "high"}
TARGET_YEAR_MIN = 2010
TARGET_YEAR_MAX = 2099
SMOKE_SIM = {"rcp": "rcp45", "gcm": "ACCESS1-0", "model": "high", "ssp": "SSP2"}

ELEC_MAIN = "FD_FGLS_inter_OTHERIND_electricity_TINV_clim.nc4"
ELEC_HIST = "FD_FGLS_inter_OTHERIND_electricity_TINV_clim-histclim.nc4"
OTHER_MAIN = "FD_FGLS_inter_OTHERIND_other_energy_TINV_clim.nc4"
OTHER_HIST = "FD_FGLS_inter_OTHERIND_other_energy_TINV_clim-histclim.nc4"
IMPACT_COLS = ["energy_electricity", "energy_non_electricity", "energy_total"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)


def is_country_code(reg: str) -> bool:
    return bool(reg) and ("." not in reg) and (not reg.startswith("FUND"))


def _read_rebased(path):
    """Return (rebased[year, region], years[year], regions[region])."""
    with xr.open_dataset(path, chunks=None) as ds:
        ds.load()
        return (ds["rebased"].values.astype(np.float32),
                ds["year"].values.astype(int),
                ds["regions"].values.astype(str))


def _build_country_aggregator(hierids):
    """Precompute IR -> country aggregation matrix.

    Returns (countries: array[n_c], S: ndarray[n_c, n_ir] dtype=float32)
    where S[c, i] == 1.0 iff hierids[i] belongs to country c. Pop-weighting
    is applied later: country_value = (S @ (pop * value)) / (S @ pop).
    """
    country_codes = np.array([h.split(".")[0] for h in hierids])
    countries, inv = np.unique(country_codes, return_inverse=True)
    n_c, n_ir = len(countries), len(hierids)
    S = np.zeros((n_c, n_ir), dtype=np.float32)
    S[inv, np.arange(n_ir)] = 1.0
    return countries, S


def _build_pop_lookup(econ_zarr, mode):
    """Load pop table indexed by (ssp, model). Each entry is a DataFrame with
    columns [hierid, year, pop]. Country prefix is irrelevant here; we'll
    align to the hierid order from the nc4 files at use time."""
    log.info(f"Opening econ zarr: {econ_zarr}")
    ds = xr.open_zarr(econ_zarr)
    if "model" in ds.coords:
        new_models = [IAM_MAPPING.get(str(m), str(m)) for m in ds.model.values]
        ds = ds.assign_coords(model=new_models)
    if mode == "smoke":
        ds = ds.sel(ssp=SMOKE_SIM["ssp"], model=SMOKE_SIM["model"])
    df = ds["pop"].to_dataframe().reset_index()
    df["year"] = df["year"].astype(int)
    df = df.rename(columns={"region": "hierid"})
    df["pop"] = df["pop"].fillna(0).astype(np.float32)

    if mode == "smoke":
        df["ssp"] = SMOKE_SIM["ssp"]
        df["model"] = SMOKE_SIM["model"]

    keep_years = (df["year"] >= TARGET_YEAR_MIN) & (df["year"] <= TARGET_YEAR_MAX)
    df = df[keep_years]

    out = {}
    for (ssp, model), grp in df.groupby(["ssp", "model"], as_index=False):
        out[(str(ssp), str(model))] = grp[["hierid", "year", "pop"]].copy()
    log.info(f"Loaded pop for {len(out)} (ssp, model) combos")
    return out


def _aggregate_to_country(impact_ir, hierids, pop_df, target_years, S):
    """Pop-weight aggregate IR-level impact (n_year, n_ir) -> country (n_year, n_c).

    pop_df has columns hierid, year, pop and is restricted to one (ssp, model).
    """
    pivot = pop_df.pivot(index="year", columns="hierid", values="pop")
    pop_arr = pivot.reindex(index=target_years, columns=hierids, fill_value=0.0).values.astype(np.float32)
    weighted = impact_ir * pop_arr            # (n_year, n_ir)
    num = weighted @ S.T                       # (n_year, n_c)
    den = pop_arr @ S.T                        # (n_year, n_c)
    return num / np.maximum(den, 1e-9)         # NaN-free per-capita country values


def process_one_sim(args, pop_lookup, S, countries, hierids):
    rcp, gcm, model, ssp = args
    try:
        e_main_path = os.path.join(ELEC_BASE, rcp, gcm, model, ssp, ELEC_MAIN)
        e_hist_path = os.path.join(ELEC_BASE, rcp, gcm, model, ssp, ELEC_HIST)
        o_main_path = os.path.join(OTHER_BASE, rcp, gcm, model, ssp, OTHER_MAIN)
        o_hist_path = os.path.join(OTHER_BASE, rcp, gcm, model, ssp, OTHER_HIST)
        for p in (e_main_path, e_hist_path, o_main_path, o_hist_path):
            if not os.path.exists(p):
                return None

        e_m, e_yrs, regs_e = _read_rebased(e_main_path)
        e_h, _,     _      = _read_rebased(e_hist_path)
        o_m, _,     regs_o = _read_rebased(o_main_path)
        o_h, _,     _      = _read_rebased(o_hist_path)
        if not np.array_equal(regs_e, regs_o):
            log.warning(f"Sim {rcp}/{gcm}/{model}/{ssp}: elec/other regions differ; skipping")
            return None
        if not np.array_equal(regs_e, hierids):
            log.warning(f"Sim {rcp}/{gcm}/{model}/{ssp}: hierid order changed; skipping")
            return None

        # IR-level impacts (kWh/pc) at IR resolution
        target = np.arange(TARGET_YEAR_MIN, TARGET_YEAR_MAX + 1)
        e_yi = {int(y): i for i, y in enumerate(e_yrs)}
        miss = [y for y in target if int(y) not in e_yi]
        if miss:
            log.warning(f"Sim {rcp}/{gcm}/{model}/{ssp} missing years {miss[:3]}; skipping")
            return None
        idx = np.array([e_yi[int(y)] for y in target])
        elec_ir  = (e_m - e_h)[idx]                # (n_year, n_ir)
        other_ir = (o_m - o_h)[idx]
        total_ir = elec_ir + other_ir

        pop_df = pop_lookup.get((ssp, model))
        if pop_df is None:
            log.warning(f"Sim {rcp}/{gcm}/{model}/{ssp}: no pop for ({ssp},{model}); skipping")
            return None

        elec_c  = _aggregate_to_country(elec_ir,  hierids, pop_df, target, S)
        other_c = _aggregate_to_country(other_ir, hierids, pop_df, target, S)
        total_c = _aggregate_to_country(total_ir, hierids, pop_df, target, S)
        impacts = np.stack([elec_c, other_c, total_c], axis=-1).astype(np.float32)  # (n_year, n_c, 3)

        return {"scenario": (rcp, ssp, model), "gcm": gcm,
                "impacts": impacts, "years": target, "regions": countries}
    except Exception as e:
        log.warning(f"Failed on {rcp}/{gcm}/{model}/{ssp}: {e}")
        return None


def discover_sims(mode):
    tasks = []
    if mode == "smoke":
        rcp, gcm, model, ssp = SMOKE_SIM["rcp"], SMOKE_SIM["gcm"], SMOKE_SIM["model"], SMOKE_SIM["ssp"]
        if os.path.isdir(os.path.join(ELEC_BASE, rcp, gcm, model, ssp)):
            tasks.append((rcp, gcm, model, ssp))
        return tasks
    for rcp in sorted(os.listdir(ELEC_BASE)):
        r = os.path.join(ELEC_BASE, rcp)
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
                    o = os.path.join(OTHER_BASE, rcp, gcm, model, ssp)
                    if os.path.isdir(s) and os.path.isdir(o):
                        tasks.append((rcp, gcm, model, ssp))
    return tasks


def _bootstrap_hierids(tasks):
    """Read one nc4 to get the canonical hierid order; reused for all sims."""
    for (rcp, gcm, model, ssp) in tasks:
        p = os.path.join(ELEC_BASE, rcp, gcm, model, ssp, ELEC_MAIN)
        if os.path.exists(p):
            _, _, regs = _read_rebased(p)
            return regs
    log.error("Could not locate any sim to bootstrap hierids")
    sys.exit(1)


def _load_climate_table(climate_csv, mode, gcms_used=None):
    log.info(f"Reading climate: {climate_csv}")
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
    """Country-level gdppc + pop for the join. Same logic as labor builder."""
    log.info(f"Loading country econ from {econ_zarr}")
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


def _build_long_frame(results):
    """Collect per-sim country-level results into one long DataFrame.

    Energy median has no MC, so each scenario tuple (rcp, gcm, model, ssp)
    contributes exactly one observation per (region, year). No collapsing.
    """
    dfs = []
    for r in results:
        impacts = r["impacts"]   # (n_year, n_c, 3)
        years = r["years"]
        regs = r["regions"]
        rcp, ssp, model = r["scenario"]
        gcm = r["gcm"]
        ny, nc, _ = impacts.shape
        df = pd.DataFrame({
            "rcp": rcp, "ssp": ssp, "model": model, "gcm": gcm,
            "year": np.repeat(years, nc),
            "region": np.tile(regs, ny),
            "energy_electricity":     impacts[:, :, 0].reshape(-1),
            "energy_non_electricity": impacts[:, :, 1].reshape(-1),
            "energy_total":           impacts[:, :, 2].reshape(-1),
        })
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


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


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", required=True, choices=["smoke", "full"])
    p.add_argument("--output-dir", required=True)
    p.add_argument("--climate-csv", default=CLIMATE_CSV)
    p.add_argument("--econ-zarr", default=SOCIO_ZARR)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--config", default=None)
    p.add_argument("--collapse-mc", action="store_true",
                   help="No-op for energy: median tree has no batch dim.")
    p.add_argument("--keep-mc", action="store_true")
    args = p.parse_args()

    collapse_mc = _resolve_collapse_mc(args)
    log.info(f"Mode: {args.mode}, collapse_mc={collapse_mc} (note: no batch dim in energy median)")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "country" if collapse_mc else "country_keepmc"
    out_file = output_dir / f"energy_aggregated_{suffix}_{args.mode}.parquet"

    tasks = discover_sims(args.mode)
    log.info(f"Discovered {len(tasks):,} sims")
    if args.limit is not None:
        tasks = tasks[: args.limit]
    if not tasks:
        log.error("No sims found")
        sys.exit(1)
    gcms_used = {t[1] for t in tasks}

    hierids = _bootstrap_hierids(tasks)
    log.info(f"Bootstrapped hierids: {len(hierids):,} (will pop-weight aggregate to country)")
    countries, S = _build_country_aggregator(hierids)
    log.info(f"Country aggregator: {len(countries)} countries; S shape={S.shape}")

    pop_lookup = _build_pop_lookup(args.econ_zarr, args.mode)

    # Process all sims sequentially: ~660 scenarios x ~1s each = ~10-15 min
    results = []
    for i, t in enumerate(tasks, start=1):
        if i % 25 == 0 or i == 1 or i == len(tasks):
            log.info(f"  processing {i:,}/{len(tasks):,}: {t}")
        r = process_one_sim(t, pop_lookup, S, countries, hierids)
        if r is not None:
            results.append(r)

    log.info(f"Got {len(results):,} valid sim results out of {len(tasks):,}")
    if not results:
        log.error("No valid sims")
        sys.exit(1)

    df = _build_long_frame(results)
    log.info(f"Long frame: {len(df):,} rows ({df['region'].nunique()} countries, "
             f"{df['year'].nunique()} years, {df['gcm'].nunique()} gcms)")

    clim_table = _load_climate_table(args.climate_csv, args.mode, gcms_used=gcms_used)
    econ_table = _load_econ_country_table(args.econ_zarr, args.mode)
    df = _join_scenario(df, clim_table, econ_table)
    df = df.sort_values(["rcp", "ssp", "model", "gcm", "region", "year"]).reset_index(drop=True)
    df.to_parquet(out_file, index=False, compression="zstd")

    log.info(f"Wrote {out_file} ({out_file.stat().st_size/1e6:.1f} MB, {len(df):,} rows)")
    for col in IMPACT_COLS:
        s = df[col].dropna()
        log.info(f"  {col}: mean={s.mean():.4e}, std={s.std():.4e}, "
                 f"min={s.min():.4e}, max={s.max():.4e}, n={len(s):,}")


if __name__ == "__main__":
    main()
