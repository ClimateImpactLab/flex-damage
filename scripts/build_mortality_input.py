#!/usr/bin/env python3
"""
Build mortality input by aggregating over batch and GCM dimensions.

The raw mortality zarr files have 7D structure:
  (batch, ssp, rcp, gcm, model, year, region)

This script aggregates over batch and gcm to produce a manageable parquet
file that can be used with flexdamage's standardize.py.

Output columns:
  - region: impact region identifier
  - year: year (2010-2099)
  - adjusted_mortality: deaths per 100k, aggregated
  - temperature_anomaly: temperature change in C
  - gdppc: GDP per capita
  - pop: population weight
  - rcp: RCP scenario (rcp45, rcp85)
  - ssp: SSP scenario (SSP1-SSP5)
  - model: economic model (high, low)

Usage:
    python scripts/build_mortality_input.py \\
        --input-dir /path/to/mortality/damages/ \\
        --output /path/to/output.parquet

Example:
    python scripts/build_mortality_input.py \\
        --input-dir /project/cil/home_dirs/scadavidsanchez/projects/flex-damage-functions-ir/dataset/mortality/damages/ \\
        --output /project/cil/home_dirs/scadavidsanchez/projects/flex-damages-data/mortality/allcause/ir/mortality_aggregated.parquet
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def aggregate_mortality_zarr(
    input_dir: Path,
    output_path: Path,
    chunk_size: int = 5000,
) -> pd.DataFrame:
    """
    Load mortality zarr files and aggregate over batch and GCM dimensions.

    Parameters
    ----------
    input_dir : Path
        Directory containing mortality_SSP*.zarr files
    output_path : Path
        Output parquet path
    chunk_size : int
        Number of regions to process at once (for memory management)

    Returns
    -------
    pd.DataFrame
        Aggregated mortality data
    """
    input_dir = Path(input_dir)
    output_path = Path(output_path)

    # Find all SSP zarr files
    zarr_files = sorted(input_dir.glob("mortality_SSP*.zarr"))
    if not zarr_files:
        raise FileNotFoundError(f"No mortality_SSP*.zarr files found in {input_dir}")

    logger.info(f"Found {len(zarr_files)} zarr files: {[f.name for f in zarr_files]}")

    all_dfs = []

    for zarr_path in zarr_files:
        ssp_name = zarr_path.stem.replace("mortality_", "")
        logger.info(f"Processing {ssp_name}...")

        # Open zarr (lazy loading)
        ds = xr.open_zarr(zarr_path)

        # Log structure
        logger.info(f"  Variables: {list(ds.data_vars)}")
        logger.info(f"  Coordinates: {list(ds.coords)}")
        for var in ds.data_vars:
            logger.info(f"    {var}: {ds[var].dims} shape={ds[var].shape}")

        # Get dimension sizes
        n_batches = ds.dims.get("batch", 1)
        n_gcms = ds.dims.get("gcm", 1)
        n_rcps = ds.dims.get("rcp", 2)
        n_models = ds.dims.get("model", 2)
        n_years = ds.dims.get("year", 90)
        n_regions = ds.dims.get("region", 24378)

        logger.info(f"  Dimensions: batch={n_batches}, gcm={n_gcms}, rcp={n_rcps}, "
                    f"model={n_models}, year={n_years}, region={n_regions}")

        # Aggregate over batch and gcm dimensions
        # This reduces the data significantly while preserving scenario structure
        logger.info(f"  Aggregating over batch ({n_batches}) and gcm ({n_gcms})...")

        # Mean over batch and gcm
        ds_agg = ds.mean(dim=["batch", "gcm"], skipna=True)

        # Log resulting dimensions
        logger.info(f"  After aggregation: {dict(ds_agg.dims)}")

        # Convert to DataFrame
        # Remaining dims should be: (rcp, model, year, region) or similar
        logger.info(f"  Converting to DataFrame...")
        df = ds_agg.to_dataframe().reset_index()

        # Add SSP from filename
        df["ssp"] = ssp_name

        logger.info(f"  Rows: {len(df):,}")
        logger.info(f"  Columns: {list(df.columns)}")

        all_dfs.append(df)
        ds.close()

    # Combine all SSPs
    logger.info("Combining all SSPs...")
    combined = pd.concat(all_dfs, ignore_index=True)

    # Log summary statistics
    logger.info(f"Combined DataFrame:")
    logger.info(f"  Total rows: {len(combined):,}")
    logger.info(f"  Columns: {list(combined.columns)}")
    logger.info(f"  Unique regions: {combined['region'].nunique():,}")
    logger.info(f"  Unique years: {combined['year'].nunique()}")
    logger.info(f"  Year range: {combined['year'].min()} - {combined['year'].max()}")

    # Check for rcp column (might be named differently)
    rcp_col = "rcp" if "rcp" in combined.columns else None
    if rcp_col:
        logger.info(f"  Unique RCPs: {sorted(combined[rcp_col].unique())}")

    logger.info(f"  Unique SSPs: {sorted(combined['ssp'].unique())}")

    model_col = "model" if "model" in combined.columns else None
    if model_col:
        logger.info(f"  Unique models: {sorted(combined[model_col].unique())}")

    # Validate required columns
    required_cols = ["adjusted_mortality", "temperature_anomaly", "gdppc", "pop", "region", "year"]
    missing = [c for c in required_cols if c not in combined.columns]
    if missing:
        logger.warning(f"Missing columns: {missing}")
        logger.info(f"Available columns: {list(combined.columns)}")

    # Sample of data
    logger.info(f"Sample of data:")
    logger.info(combined.head(3).to_string())

    # Memory estimate
    mem_mb = combined.memory_usage(deep=True).sum() / 1e6
    logger.info(f"  Memory usage: {mem_mb:.1f} MB")

    # Save output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save as parquet with compression
    logger.info(f"Saving to {output_path}...")
    combined.to_parquet(output_path, index=False, compression="zstd")

    file_size_mb = output_path.stat().st_size / 1e6
    logger.info(f"Saved: {file_size_mb:.1f} MB")

    return combined


def main():
    parser = argparse.ArgumentParser(
        description="Build mortality input by aggregating over batch and GCM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing mortality_SSP*.zarr files",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output parquet path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be done, don't write output",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_path = Path(args.output)

    if not input_dir.exists():
        logger.error(f"Input directory not found: {input_dir}")
        sys.exit(1)

    if args.dry_run:
        logger.info("DRY RUN - not writing output")
        # Just open one file to show structure
        zarr_files = list(input_dir.glob("mortality_SSP*.zarr"))
        if zarr_files:
            ds = xr.open_zarr(zarr_files[0])
            logger.info(f"Sample zarr structure ({zarr_files[0].name}):")
            logger.info(f"  Variables: {list(ds.data_vars)}")
            logger.info(f"  Dimensions: {dict(ds.dims)}")
            for var in ds.data_vars:
                logger.info(f"    {var}: {ds[var].dims}")
            ds.close()
        return

    # Run aggregation
    df = aggregate_mortality_zarr(input_dir, output_path)

    logger.info("Done!")
    logger.info(f"Output: {output_path}")
    logger.info(f"Rows: {len(df):,}")


if __name__ == "__main__":
    main()
