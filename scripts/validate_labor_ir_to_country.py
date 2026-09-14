#!/usr/bin/env python3
"""
Validate our IR -> country pop-weight aggregation for labor against the
projection system's existing -pop-aggregated.nc4 (which only exists for SSP3).

If our reproduced country values match the reference within float precision,
we have license to apply the same method to SSP2 / SSP4 (where no reference
exists because the projection system never ran the aggregation step there).

Run from the project root. Reads from /project/cil mounts only.
"""
import sys
import numpy as np
import pandas as pd
import xarray as xr
from pathlib import Path

# Allow running on Midway (/project/cil/...) or via the Mac SMB mount (/Volumes/cil/...)
_CIL_ROOT = "/project/cil" if Path("/project/cil").exists() else "/Volumes/cil"
LABOR_BASE = f"{_CIL_ROOT}/gcp/outputs/labor/impacts-woodwork/montecarlo/uninteracted_main_model_27_37_39"
SOCIO_ZARR = f"{_CIL_ROOT}/gcp/integration_replication/inputs/econ/raw/integration-econ-bc39.zarr"
IAM_MAPPING = {"IIASA GDP": "low", "OECD Env-Growth": "high"}

# Single SSP3 sim to validate
SIM = dict(batch="batch0", rcp="rcp85", gcm="MIROC-ESM", model="high", ssp="SSP3")
TARGET_YEAR_MIN, TARGET_YEAR_MAX = 2010, 2099
NC_VARS = {  # builder name -> nc4 variable name
    "labor_combined":  "rebased",
    "labor_high_risk": "highriskimpacts",
    "labor_low_risk":  "lowriskimpacts",
}


def is_country(reg: str) -> bool:
    return bool(reg) and ("." not in reg) and (not reg.startswith("FUND"))


def main():
    s = SIM
    sim_dir = f"{LABOR_BASE}/{s['batch']}/{s['rcp']}/{s['gcm']}/{s['model']}/{s['ssp']}"
    ir_main_p   = f"{sim_dir}/uninteracted_main_model.nc4"
    ir_hist_p   = f"{sim_dir}/uninteracted_main_model-histclim.nc4"
    ref_main_p  = f"{sim_dir}/uninteracted_main_model-pop-aggregated.nc4"
    ref_hist_p  = f"{sim_dir}/uninteracted_main_model-histclim-pop-aggregated.nc4"

    for p in (ir_main_p, ir_hist_p, ref_main_p, ref_hist_p):
        if not Path(p).exists():
            print(f"MISSING: {p}")
            sys.exit(1)

    print(f"Validating sim: {sim_dir}\n")

    # 1) Load IR-level files
    print("Loading IR-level main + histclim ...")
    with xr.open_dataset(ir_main_p) as ds:
        ds.load()
        ir_main = {k: ds[v].values.astype(np.float64) for k, v in NC_VARS.items()}
        ir_years = ds["year"].values.astype(int)
        ir_regs = ds["regions"].values.astype(str)

    with xr.open_dataset(ir_hist_p) as ds:
        ds.load()
        ir_hist = {k: ds[v].values.astype(np.float64) for k, v in NC_VARS.items()}

    print(f"  IR shape: {ir_main['labor_combined'].shape}, years {ir_years.min()}-{ir_years.max()}")

    # 2) Load reference (projection system's pop-aggregated)
    print("Loading reference -pop-aggregated.nc4 ...")
    with xr.open_dataset(ref_main_p) as ds:
        ds.load()
        ref_main = {k: ds[v].values.astype(np.float64) for k, v in NC_VARS.items()}
        ref_years = ds["year"].values.astype(int)
        ref_regs = ds["regions"].values.astype(str)

    with xr.open_dataset(ref_hist_p) as ds:
        ds.load()
        ref_hist = {k: ds[v].values.astype(np.float64) for k, v in NC_VARS.items()}

    print(f"  Ref shape: {ref_main['labor_combined'].shape}, years {ref_years.min()}-{ref_years.max()}\n")

    # 3) Slice both to target years and to country rows on the reference
    target = np.arange(TARGET_YEAR_MIN, TARGET_YEAR_MAX + 1)
    ir_yi  = {int(y): i for i, y in enumerate(ir_years)}
    ref_yi = {int(y): i for i, y in enumerate(ref_years)}
    ir_idx  = np.array([ir_yi[int(y)]  for y in target])
    ref_idx = np.array([ref_yi[int(y)] for y in target])

    country_mask = np.array([is_country(r) for r in ref_regs], dtype=bool)
    countries = ref_regs[country_mask]
    print(f"Reference: {len(countries)} country codes\n")

    # Build reference impact (main - histclim) at country level for all 3 vars
    ref_impact = {k: (ref_main[k][ref_idx] - ref_hist[k][ref_idx])[:, country_mask]
                  for k in NC_VARS}                            # (n_year, n_country)
    ir_impact = {k: ir_main[k][ir_idx] - ir_hist[k][ir_idx]
                 for k in NC_VARS}                             # (n_year, n_hierid)

    # 4) Load pop per (hierid, year) for this (ssp, model)
    print(f"Loading pop for ({s['ssp']}, {s['model']}) from integration zarr ...")
    ds = xr.open_zarr(SOCIO_ZARR)
    if "model" in ds.coords:
        ds = ds.assign_coords(model=[IAM_MAPPING.get(str(m), str(m)) for m in ds.model.values])
    ds = ds.sel(ssp=s["ssp"], model=s["model"])
    pop_df = ds["pop"].to_dataframe().reset_index()
    pop_df["year"] = pop_df["year"].astype(int)
    pop_df = pop_df.rename(columns={"region": "hierid"})
    pop_df["pop"] = pop_df["pop"].fillna(0).astype(np.float64)
    pop_df = pop_df[(pop_df["year"] >= TARGET_YEAR_MIN) & (pop_df["year"] <= TARGET_YEAR_MAX)]
    pop_pivot = pop_df.pivot(index="year", columns="hierid", values="pop").reindex(
        index=target, columns=ir_regs, fill_value=0.0).values   # (n_year, n_hierid)
    print(f"  Pop array: {pop_pivot.shape}, total pop year 2050: {pop_pivot[40].sum():.2e}\n")

    # 5) Build the IR -> country aggregator (S matrix)
    country_codes = np.array([h.split(".")[0] for h in ir_regs])
    uniq, inv = np.unique(country_codes, return_inverse=True)
    n_c, n_ir = len(uniq), len(ir_regs)
    S = np.zeros((n_c, n_ir), dtype=np.float64)
    S[inv, np.arange(n_ir)] = 1.0

    # 6) Pop-weight aggregate IR impact -> country
    print(f"Aggregating IR -> country (n_ir={n_ir} -> n_country={n_c}) ...\n")
    our_impact = {}
    den = (S @ pop_pivot.T).T                                   # (n_year, n_c)
    for k in NC_VARS:
        num = (S @ (ir_impact[k] * pop_pivot).T).T              # (n_year, n_c)
        our_impact[k] = num / np.maximum(den, 1e-12)

    # 7) Align our country list with the reference's country list
    our_idx = {c: i for i, c in enumerate(uniq)}
    common = [c for c in countries if c in our_idx]
    miss_in_ours = [c for c in countries if c not in our_idx]
    miss_in_ref  = [c for c in uniq if c not in set(countries)]
    print(f"Country alignment: {len(common)} common, {len(miss_in_ours)} only-in-ref, {len(miss_in_ref)} only-in-ours")
    if miss_in_ours[:10]:
        print(f"  only-in-ref examples: {miss_in_ours[:10]}")
    if miss_in_ref[:10]:
        print(f"  only-in-ours examples: {miss_in_ref[:10]}")
    print()

    # 8) Compare per variable
    print("=" * 70)
    print(f"{'var':<20} {'mean_abs_diff':>14} {'max_abs_diff':>14} {'rel_max':>10} {'corr':>8}")
    print("-" * 70)
    for k in NC_VARS:
        ours = np.array([our_impact[k][:, our_idx[c]] for c in common]).T   # (n_year, n_common)
        refs = np.array([ref_impact[k][:, list(countries).index(c)] for c in common]).T
        diff = ours - refs
        # Skip cells where either side is NaN (countries with 0 pop in zarr).
        valid = np.isfinite(ours) & np.isfinite(refs)
        n_skipped = (~valid).sum()
        d = np.abs(diff[valid])
        r = np.abs(refs[valid])
        ref_scale = r.mean() if r.size else 0.0
        rel_max = d.max() / max(ref_scale, 1e-12) if d.size else float("nan")
        corr = np.corrcoef(ours[valid].flatten(), refs[valid].flatten())[0, 1] if d.size else float("nan")
        print(f"{k:<20} {d.mean():>14.6e} {d.max():>14.6e} "
              f"{rel_max:>10.3e} {corr:>8.5f}  (skipped {n_skipped} NaN cells)")

    # Spot-check a couple of countries (USA, CHN, IND if present)
    print("\nSpot-check (year 2050):")
    yi = list(target).index(2050)
    for c in ("USA", "CHN", "IND", "BRA", "DEU"):
        if c in our_idx and c in countries:
            our_v = our_impact["labor_combined"][yi, our_idx[c]]
            ref_v = ref_impact["labor_combined"][yi, list(countries).index(c)]
            print(f"  {c} labor_combined: ours={our_v:.6f}  ref={ref_v:.6f}  diff={our_v-ref_v:+.2e}")


if __name__ == "__main__":
    main()
