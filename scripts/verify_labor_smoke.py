#!/usr/bin/env python3
"""
Verify the smoke-mode labor parquet matches the raw nc4 files for one
specific (region, year, scenario) case, and sanity-check covariates against
their sources.

Usage:
  python scripts/verify_labor_smoke.py
  python scripts/verify_labor_smoke.py --region ABW --year 2050
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

SMOKE_PARQUET = "/scratch/midway3/cadavidsanchez/flex-damages/labor/smoke/labor_aggregated_smoke.parquet"
SMOKE_SIM_DIR = "/project/cil/gcp/outputs/labor/impacts-woodwork/montecarlo/uninteracted_main_model_27_37_39/batch0/rcp45/ACCESS1-0/high/SSP3"
CLIMATE_CSV = "/project/cil/home_dirs/scadavidsanchez/projects/flex-damage-functions-ir/dataset/climate/gcm_temp_gmst_year_preind1986-2005.csv"
ECON_ZARR = "/project/cil/gcp/integration_replication/inputs/econ/raw/integration-econ-bc39.zarr"

SCENARIO = {"rcp": "rcp45", "ssp": "SSP3", "model": "high", "gcm": "ACCESS1-0"}

IAM_MAPPING = {"IIASA GDP": "low", "OECD Env-Growth": "high"}


def banner(msg):
    print("\n" + "=" * 70)
    print(f" {msg}")
    print("=" * 70)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--region", default="ABW", help="Region to check")
    p.add_argument("--year", type=int, default=2050, help="Year to check")
    p.add_argument("--parquet", default=SMOKE_PARQUET)
    args = p.parse_args()

    region, year = args.region, args.year

    banner(f"Loading parquet: {args.parquet}")
    df = pd.read_parquet(args.parquet)
    print(f"Shape:   {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print(f"Regions: {df['region'].nunique():,}")
    print(f"Years:   {df['year'].min()}-{df['year'].max()}")
    print(f"RCPs:    {sorted(df['rcp'].unique())}")
    print(f"SSPs:    {sorted(df['ssp'].unique())}")
    print(f"Models:  {sorted(df['model'].unique())}")

    banner("Impact column stats")
    for c in ["labor_combined", "labor_high_risk", "labor_low_risk"]:
        s = df[c].dropna()
        print(f"  {c}: mean={s.mean():.5f}, std={s.std():.5f}, min={s.min():.5f}, max={s.max():.5f}, n={len(s):,}")

    banner("Covariate stats")
    for c in ["temperature_anomaly", "gdppc", "pop"]:
        if c in df.columns:
            s = df[c].dropna()
            na = df[c].isna().sum()
            print(f"  {c}: mean={s.mean():.3f}, min={s.min():.3f}, max={s.max():.3f}, n_nan={na}")
        else:
            print(f"  {c}: MISSING")

    # Find the case row
    case = df[(df["region"] == region) & (df["year"] == year)]
    if case.empty:
        print(f"\nNo row for region={region}, year={year}")
        print(f"Sample regions: {df['region'].unique()[:5]}")
        return
    if len(case) > 1:
        print(f"Warning: {len(case)} rows for this (region, year). Scenario filter applied below.")
        case = case[
            (case["rcp"] == SCENARIO["rcp"])
            & (case["ssp"] == SCENARIO["ssp"])
            & (case["model"] == SCENARIO["model"])
        ]
    row = case.iloc[0]

    banner(f"Parquet row for region={region}, year={year}")
    for k in ["rcp", "ssp", "model", "region", "year",
              "labor_combined", "labor_high_risk", "labor_low_risk",
              "temperature_anomaly", "gdppc", "pop"]:
        if k in row.index:
            print(f"  {k}: {row[k]}")

    # --- Verify impact values against raw nc4 ---
    banner(f"Recomputing from raw nc4 at {SMOKE_SIM_DIR}")
    main_ds = xr.open_dataset(f"{SMOKE_SIM_DIR}/uninteracted_main_model.nc4")
    hist_ds = xr.open_dataset(f"{SMOKE_SIM_DIR}/uninteracted_main_model-histclim.nc4")

    regions_raw = main_ds["regions"].values.astype(str)
    if region not in regions_raw:
        print(f"ERROR: region {region} not found in raw regions array")
        main_ds.close()
        hist_ds.close()
        return

    r_idx = np.where(regions_raw == region)[0][0]
    y_sel = main_ds["year"].values.astype(int)
    if year not in y_sel:
        print(f"ERROR: year {year} not in raw years {y_sel[:5]}...{y_sel[-5:]}")
        main_ds.close()
        hist_ds.close()
        return
    y_idx_m = np.where(y_sel == year)[0][0]
    y_idx_h = np.where(hist_ds["year"].values.astype(int) == year)[0][0]

    for parq_col, nc_var in [
        ("labor_combined", "rebased"),
        ("labor_high_risk", "highriskimpacts"),
        ("labor_low_risk", "lowriskimpacts"),
    ]:
        m_val = float(main_ds[nc_var].values[y_idx_m, r_idx])
        h_val = float(hist_ds[nc_var].values[y_idx_h, r_idx])
        raw_impact = m_val - h_val
        parq_val = float(row[parq_col])
        diff = parq_val - raw_impact
        ok = abs(diff) < 1e-5
        mark = "OK" if ok else "MISMATCH"
        print(f"  [{mark}] {parq_col}: parquet={parq_val:.8f}, raw(main-hist)={raw_impact:.8f}, diff={diff:.2e}")
        print(f"         main.{nc_var}={m_val:.8f}, histclim.{nc_var}={h_val:.8f}")

    main_ds.close()
    hist_ds.close()

    # --- Verify temperature against climate CSV ---
    banner("Verifying temperature_anomaly against climate CSV")
    clim = pd.read_csv(CLIMATE_CSV)
    if "scenario" in clim.columns:
        clim = clim.rename(columns={"scenario": "rcp"})
    anom_cols = [c for c in clim.columns if c.lower() in ("anomaly", "anom", "tas", "temperature_anomaly")]
    anom = anom_cols[0]
    sel = clim[(clim["gcm"] == SCENARIO["gcm"]) & (clim["rcp"] == SCENARIO["rcp"]) & (clim["year"] == year)]
    if sel.empty:
        print(f"  No climate row for gcm={SCENARIO['gcm']}, rcp={SCENARIO['rcp']}, year={year}")
    else:
        raw_T = float(sel[anom].iloc[0])
        parq_T = float(row["temperature_anomaly"]) if "temperature_anomaly" in row.index else None
        if parq_T is not None:
            diff = parq_T - raw_T
            ok = abs(diff) < 1e-5
            mark = "OK" if ok else "MISMATCH"
            print(f"  [{mark}] temperature_anomaly: parquet={parq_T:.6f}, raw csv={raw_T:.6f}, diff={diff:.2e}")

    # --- Verify gdppc and pop against econ zarr ---
    banner("Verifying gdppc and pop against econ zarr")
    ds = xr.open_zarr(ECON_ZARR)
    if "model" in ds.coords:
        new_models = [IAM_MAPPING.get(str(m), str(m)) for m in ds.model.values]
        ds = ds.assign_coords(model=new_models)
    try:
        econ_case = ds.sel(ssp=SCENARIO["ssp"], model=SCENARIO["model"], region=region, year=year)
        for c in ["gdppc", "pop"]:
            if c in econ_case.data_vars:
                raw_val = float(econ_case[c].values)
                parq_val = float(row[c]) if c in row.index else None
                if parq_val is not None:
                    diff = parq_val - raw_val
                    rel = abs(diff) / max(abs(raw_val), 1e-9)
                    ok = rel < 1e-4
                    mark = "OK" if ok else "MISMATCH"
                    print(f"  [{mark}] {c}: parquet={parq_val:.4f}, raw zarr={raw_val:.4f}, rel_diff={rel:.2e}")
    except Exception as e:
        print(f"  Could not look up econ values: {e}")

    banner("Verification complete")


if __name__ == "__main__":
    main()
