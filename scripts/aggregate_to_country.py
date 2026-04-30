#!/usr/bin/env python3
"""
Aggregate any sector's IR-level input parquet to country level.

Country = top-level segment of region code (before first dot). Aggregation:
- y columns: population-weighted mean (works for per-capita, fraction-of-GDP,
  log-change, etc. Does NOT work for absolute USD; user must rescale first)
- gdppc:     population-weighted mean
- pop:       sum
- temperature_anomaly: population-weighted mean (in practice nearly identical
  per region within a country since the input already has T at IR level mapped
  from country-level GCM averages)
- scenario columns (rcp, ssp, model): pass-through (groupby key)

Usage:
    python scripts/aggregate_to_country.py \\
        --input  /scratch/.../mortality/full/mortality_aggregated_full.parquet \\
        --output /scratch/.../mortality/full/mortality_aggregated_country_full.parquet \\
        --y-cols adjusted_mortality
"""

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)


def pop_weighted_mean(group: pd.DataFrame, value_col: str, weight_col: str = "pop") -> float:
    """Population-weighted mean of `value_col`, ignoring NaN values + zero/NaN weights."""
    w = group[weight_col].fillna(0)
    v = group[value_col]
    mask = v.notna() & (w > 0)
    if not mask.any():
        return np.nan
    return float((v[mask] * w[mask]).sum() / w[mask].sum())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, help="IR-level parquet")
    p.add_argument("--output", required=True, help="Country-level parquet")
    p.add_argument("--y-cols", required=True, nargs="+",
                   help="One or more y columns to aggregate (e.g. adjusted_mortality, energy_total)")
    p.add_argument("--region-col", default="region")
    p.add_argument("--year-col", default="year")
    p.add_argument("--temp-col", default="temperature_anomaly")
    p.add_argument("--income-col", default="gdppc")
    p.add_argument("--weight-col", default="pop")
    p.add_argument("--scenario-cols", nargs="+", default=["rcp", "ssp", "model"])
    args = p.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    log.info(f"Reading {in_path}")
    df = pd.read_parquet(in_path)
    log.info(f"Input: {len(df):,} rows, {df[args.region_col].nunique():,} regions")

    # Country code = first segment of region
    df["_country"] = df[args.region_col].astype(str).str.split(".").str[0]
    log.info(f"Found {df['_country'].nunique():,} unique countries")

    # Group by (country, year, *scenario_cols)
    group_keys = ["_country", args.year_col] + [c for c in args.scenario_cols if c in df.columns]
    log.info(f"Grouping by {group_keys}")

    # Compute per-group: pop sum, pop-weighted means for y/temp/income
    weighted_cols = list(args.y_cols) + [args.temp_col, args.income_col]
    weighted_cols = [c for c in weighted_cols if c in df.columns]

    log.info(f"Aggregating {len(df):,} rows -> country level")

    # Use vectorized weighted mean where possible
    df_w = df.copy()
    df_w[args.weight_col] = df_w[args.weight_col].fillna(0)
    for c in weighted_cols:
        df_w[f"_{c}_w"] = df_w[c] * df_w[args.weight_col]

    agg_dict = {args.weight_col: "sum"}
    for c in weighted_cols:
        agg_dict[f"_{c}_w"] = "sum"

    grouped = df_w.groupby(group_keys, as_index=False).agg(agg_dict)

    # Convert weighted sums back to weighted means
    for c in weighted_cols:
        with np.errstate(divide="ignore", invalid="ignore"):
            grouped[c] = grouped[f"_{c}_w"] / grouped[args.weight_col].replace(0, np.nan)
        grouped = grouped.drop(columns=[f"_{c}_w"])

    # Rename _country -> region (keeps column name compatible with config)
    grouped = grouped.rename(columns={"_country": args.region_col})

    # Filter out blank country codes if any
    grouped = grouped[grouped[args.region_col].str.len() > 0].reset_index(drop=True)

    # Sort for deterministic output
    sort_cols = [c for c in args.scenario_cols if c in grouped.columns] + [args.region_col, args.year_col]
    grouped = grouped.sort_values(sort_cols).reset_index(drop=True)

    log.info(f"Output: {len(grouped):,} rows, {grouped[args.region_col].nunique():,} countries")
    grouped.to_parquet(out_path, index=False, compression="zstd")
    size_mb = out_path.stat().st_size / 1e6
    log.info(f"Wrote {out_path} ({size_mb:.1f} MB)")

    # Quick sanity check
    log.info("Country sample (first 5 rows):")
    log.info(grouped.head().to_string())
    log.info(f"\nScenario coverage:")
    for c in args.scenario_cols:
        if c in grouped.columns:
            log.info(f"  {c}: {sorted(grouped[c].unique())}")
    log.info(f"  year range: {grouped[args.year_col].min()}-{grouped[args.year_col].max()}")
    for c in args.y_cols:
        if c in grouped.columns:
            s = grouped[c].dropna()
            log.info(f"  {c}: mean={s.mean():.4g}, median={s.median():.4g}, n={len(s):,}")


if __name__ == "__main__":
    main()
