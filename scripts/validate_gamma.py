#!/usr/bin/env python3
"""
Validate DuckDB gamma estimation against linearmodels/statsmodels.

Compares our pipeline's gamma estimate against established econometrics
packages to verify correctness.

Usage:
    pip install linearmodels
    python scripts/validate_gamma.py configs/agriculture/corn.yaml
    python scripts/validate_gamma.py configs/agriculture/corn.yaml --sample 100000
"""

import argparse
import logging
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flexdamage.config import load_config
from flexdamage.build.standardize import standardize
from flexdamage.estimation.gamma import estimate_gamma
from flexdamage.utils import setup_logging
import duckdb

logger = logging.getLogger(__name__)


def run_linearmodels_gamma(
    df: pd.DataFrame,
    bin_width: float,
    include_sign: bool = True,
) -> dict:
    """
    Run gamma estimation using linearmodels PanelOLS.

    This is the "reference" implementation to validate against.
    """
    try:
        from linearmodels.panel import PanelOLS
    except ImportError:
        logger.warning("linearmodels not installed, falling back to statsmodels")
        return run_statsmodels_gamma(df, bin_width, include_sign)

    # Create FE groups (same logic as our pipeline)
    df = df.copy()
    df["temp_bin"] = np.floor(df["T"] / bin_width).astype(int)

    if include_sign:
        df["fe_group"] = (
            df["y_sign"].astype(str) + "_" +
            df["region"].astype(str) + "_" +
            df["temp_bin"].astype(str)
        )
    else:
        df["fe_group"] = (
            df["region"].astype(str) + "_" +
            df["temp_bin"].astype(str)
        )

    # Filter valid observations
    valid = (
        np.isfinite(df["y"]) &
        np.isfinite(df["log_income"]) &
        np.isfinite(df["w"]) &
        (df["w"] > 0)
    )
    df = df[valid].copy()

    n_obs = len(df)
    n_fe = df["fe_group"].nunique()
    n_years = df["year"].nunique()

    logger.info(f"linearmodels: {n_obs:,} obs, {n_fe:,} FE groups, {n_years} years")

    # Set panel index (entity, time)
    df = df.set_index(["fe_group", "year"])

    # Prepare data for PanelOLS
    # Note: PanelOLS expects a DataFrame for exog, not a Series
    exog = df[["log_income"]]

    # Run PanelOLS with entity + time fixed effects
    mod = PanelOLS(
        dependent=df["y"],
        exog=exog,
        weights=df["w"],
        entity_effects=True,
        time_effects=True,
    )

    # Fit with two-way clustered standard errors
    result = mod.fit(cov_type="clustered", cluster_entity=True, cluster_time=True)

    gamma = result.params["log_income"]
    se = result.std_errors["log_income"]
    r2 = result.rsquared

    return {
        "gamma": gamma,
        "se": se,
        "r_squared": r2,
        "n_obs": n_obs,
        "n_fe": n_fe,
        "method": "linearmodels.PanelOLS",
    }


def run_statsmodels_gamma(
    df: pd.DataFrame,
    bin_width: float,
    include_sign: bool = True,
) -> dict:
    """
    Fallback: Run gamma estimation using statsmodels with manual demeaning.

    This implements the within estimator manually:
    1. Create FE groups
    2. Demean y and x by FE group
    3. Demean by year
    4. Run WLS on demeaned data
    """
    import statsmodels.api as sm

    df = df.copy()

    # Create FE groups
    df["temp_bin"] = np.floor(df["T"] / bin_width).astype(int)

    if include_sign:
        df["fe_group"] = (
            df["y_sign"].astype(str) + "_" +
            df["region"].astype(str) + "_" +
            df["temp_bin"].astype(str)
        )
    else:
        df["fe_group"] = (
            df["region"].astype(str) + "_" +
            df["temp_bin"].astype(str)
        )

    # Filter valid observations
    valid = (
        np.isfinite(df["y"]) &
        np.isfinite(df["log_income"]) &
        np.isfinite(df["w"]) &
        (df["w"] > 0)
    )
    df = df[valid].copy()

    n_obs = len(df)
    n_fe = df["fe_group"].nunique()
    n_years = df["year"].nunique()

    logger.info(f"statsmodels: {n_obs:,} obs, {n_fe:,} FE groups, {n_years} years")

    # Step 1: Compute weighted group means
    def weighted_mean(group):
        w = group["w"]
        return pd.Series({
            "y_bar_g": np.average(group["y"], weights=w),
            "x_bar_g": np.average(group["log_income"], weights=w),
        })

    fe_means = df.groupby("fe_group").apply(weighted_mean).reset_index()
    df = df.merge(fe_means, on="fe_group")

    # Step 2: Compute weighted year means
    def weighted_mean_year(group):
        w = group["w"]
        return pd.Series({
            "y_bar_t": np.average(group["y"], weights=w),
            "x_bar_t": np.average(group["log_income"], weights=w),
        })

    year_means = df.groupby("year").apply(weighted_mean_year).reset_index()
    df = df.merge(year_means, on="year")

    # Step 3: Compute global weighted means
    y_bar = np.average(df["y"], weights=df["w"])
    x_bar = np.average(df["log_income"], weights=df["w"])

    # Step 4: Double-demean (within transformation)
    df["y_dm"] = df["y"] - df["y_bar_g"] - df["y_bar_t"] + y_bar
    df["x_dm"] = df["log_income"] - df["x_bar_g"] - df["x_bar_t"] + x_bar

    # Step 5: Run WLS on demeaned data (no constant!)
    valid_dm = np.isfinite(df["y_dm"]) & np.isfinite(df["x_dm"])
    df_dm = df[valid_dm]

    mod = sm.WLS(
        df_dm["y_dm"],
        df_dm["x_dm"],  # No constant for within estimator
        weights=df_dm["w"],
    )
    result = mod.fit()

    gamma = result.params.iloc[0]

    # Compute HC0 robust SE
    result_robust = mod.fit(cov_type="HC0")
    se = result_robust.bse.iloc[0]

    # R² from demeaned regression
    r2 = result.rsquared

    return {
        "gamma": gamma,
        "se": se,
        "r_squared": r2,
        "n_obs": n_obs,
        "n_fe": n_fe,
        "method": "statsmodels.WLS (manual demeaning)",
    }


def run_our_gamma(config_path: str, std_parquet: str) -> dict:
    """
    Run our DuckDB-based gamma estimation.
    """
    config = load_config(config_path)
    settings = config.estimation.gamma

    # Create DuckDB connection and load standardized data
    con = duckdb.connect()
    con.execute(f"""
        CREATE VIEW standardized AS
        SELECT * FROM read_parquet('{std_parquet}')
    """)

    # Run our estimation
    result = estimate_gamma(con, settings)

    con.close()

    return {
        "gamma": result["gamma"],
        "se": result.get("se_clustered", result.get("se_hc0", 0)),
        "se_hc0": result.get("se_hc0", 0),
        "r_squared": result.get("r_squared", 0),
        "n_obs": result.get("n_obs", 0),
        "method": "DuckDB (our implementation)",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Validate gamma estimation against linearmodels/statsmodels"
    )
    parser.add_argument("config", type=str, help="Path to config YAML")
    parser.add_argument(
        "--sample", type=int, default=None,
        help="Random sample size for faster testing"
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    args = parser.parse_args()

    setup_logging(level=getattr(logging, args.log_level))

    config = load_config(args.config)
    sector = config.sector.name
    subsector = config.sector.subsector

    print("=" * 60)
    print(f"Gamma Validation: {sector}/{subsector}")
    print("=" * 60)

    # Step 1: Standardize data
    print("\n1. Standardizing data...")
    with tempfile.TemporaryDirectory() as tmpdir:
        std_parquet = Path(tmpdir) / "standardized.parquet"
        standardize(config, output_path=std_parquet)

        # Load standardized data into pandas
        print("\n2. Loading standardized data...")
        df = pd.read_parquet(std_parquet)
        print(f"   Loaded {len(df):,} rows")

        # Optional sampling for faster testing
        if args.sample and len(df) > args.sample:
            print(f"   Sampling {args.sample:,} rows...")
            df = df.sample(n=args.sample, random_state=42)
            # Re-save sampled data for our pipeline
            df.to_parquet(std_parquet, index=False)

        # Step 2: Run reference implementation (linearmodels or statsmodels)
        print("\n3. Running reference implementation...")
        bin_width = config.estimation.gamma.temperature_bins
        include_sign = config.estimation.gamma.include_sign_in_fe

        ref_result = run_linearmodels_gamma(df, bin_width, include_sign)

        # Step 3: Run our implementation
        print("\n4. Running our DuckDB implementation...")
        our_result = run_our_gamma(args.config, str(std_parquet))

    # Step 4: Compare results
    print("\n" + "=" * 60)
    print("RESULTS COMPARISON")
    print("=" * 60)

    print(f"\nOur DuckDB estimate:")
    print(f"  gamma     = {our_result['gamma']:.6f}")
    print(f"  SE (HC0)  = {our_result.get('se_hc0', our_result['se']):.6f}")
    print(f"  SE (clust)= {our_result['se']:.6f}")
    print(f"  R²        = {our_result['r_squared']:.4f}")

    print(f"\n{ref_result['method']}:")
    print(f"  gamma     = {ref_result['gamma']:.6f}")
    print(f"  SE        = {ref_result['se']:.6f}")
    print(f"  R²        = {ref_result['r_squared']:.4f}")

    # Compute differences
    gamma_diff = abs(our_result["gamma"] - ref_result["gamma"])
    gamma_pct_diff = 100 * gamma_diff / abs(ref_result["gamma"]) if ref_result["gamma"] != 0 else 0

    se_diff = abs(our_result["se"] - ref_result["se"])

    print(f"\nDifference:")
    print(f"  gamma: {gamma_diff:.6f} ({gamma_pct_diff:.2f}%)")
    print(f"  SE:    {se_diff:.6f}")

    # Check if they match
    match_gamma = gamma_pct_diff < 1.0  # Within 1%
    match_se = se_diff < 0.01 or (se_diff / ref_result["se"] < 0.1 if ref_result["se"] > 0 else True)

    print("\n" + "=" * 60)
    if match_gamma:
        print(f"GAMMA MATCH: YES (within 1%)")
    else:
        print(f"GAMMA MATCH: NO (difference = {gamma_pct_diff:.2f}%)")

    if match_se:
        print(f"SE MATCH:    YES (within 10%)")
    else:
        print(f"SE MATCH:    NO")
    print("=" * 60)

    # Return exit code based on match
    sys.exit(0 if match_gamma else 1)


if __name__ == "__main__":
    main()
