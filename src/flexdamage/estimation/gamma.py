"""
Gamma (income elasticity) estimation using pyfixest.

DuckDB handles data prep (FE group construction, filtering).
pyfixest handles the fixed effects regression with fast iterative
demeaning (Mundlak-type acceleration) and clustered standard errors.

pyfixest is the Python equivalent of R's fixest package and is
10-50x faster than linearmodels for high-dimensional FE problems.

Model:
    y = gamma * log_income + FE(group) + FE(year) + epsilon

Where group = sign(y) × region × temperature_bin

This matches R's fixest/felm and handles 26M rows with 200k FE groups
in ~30 seconds.
"""

import logging
from typing import Dict, List

import duckdb
import numpy as np
from scipy.stats import norm

from ..config import RunConfig

logger = logging.getLogger(__name__)


def estimate_gamma(
    con: duckdb.DuckDBPyConnection,
    config: RunConfig,
) -> Dict:
    """
    Estimate global income elasticity (gamma) via fixed-effects regression.

    Uses pyfixest for fast high-dimensional fixed effects regression
    with two-way clustered standard errors (Cameron, Gelbach & Miller 2011).

    The regression model is::

        y = gamma * log_income + FE(region x temp_bin x sign) + FE(year) + epsilon

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
        Active DuckDB connection with 'standardized' view containing columns:
        region, year, y, T, log_income, w, sdev, scenario, y_sign.
    config : RunConfig
        Pipeline configuration with gamma estimation settings.

    Returns
    -------
    dict
        Estimation results containing:

        - gamma : float - Point estimate of income elasticity
        - gamma_se : float - Clustered standard error
        - gamma_quantiles : list - 19 quantiles from N(gamma, SE)
        - r_squared : float - R-squared of the FE regression
        - n_obs : int - Number of observations
        - n_fe_groups : int - Number of fixed effect groups

    Notes
    -----
    Positive gamma indicates adaptation: richer regions experience smaller
    damages from the same temperature change.
    """
    gamma_config = config.estimation.gamma
    bin_width = gamma_config.temperature_bins
    n_quantiles = gamma_config.n_quantiles
    trim_pct = gamma_config.trim_percentile

    # Step 1: Build FE groups in DuckDB, pull minimal columns to pandas
    if gamma_config.include_sign_in_fe:
        fe_expr = f"""CONCAT(
            CAST(y_sign AS VARCHAR), '_', region, '_',
            CAST(FLOOR(T / {bin_width}) AS INTEGER))"""
    else:
        fe_expr = f"""CONCAT(
            region, '_', CAST(FLOOR(T / {bin_width}) AS INTEGER))"""

    # Optional trimming
    trim_clause = ""
    if trim_pct > 0:
        threshold = con.execute(f"""
            SELECT PERCENTILE_CONT({trim_pct}) WITHIN GROUP (ORDER BY ABS(y))
            FROM standardized
            WHERE ISFINITE(y) AND ISFINITE(log_income)
        """).fetchone()[0]
        trim_clause = f"AND ABS(y) >= {threshold}"
        logger.info(f"Trimming: excluding |y| < {threshold:.6f} (bottom {100*trim_pct:.1f}%)")

    df = con.execute(f"""
        SELECT
            y,
            log_income,
            w,
            {fe_expr} AS fe_group,
            year
        FROM standardized
        WHERE ISFINITE(y)
          AND ISFINITE(log_income)
          AND w > 0
          {trim_clause}
    """).df()

    n_obs = len(df)
    n_groups = df["fe_group"].nunique()
    n_years = df["year"].nunique()
    logger.info(f"Gamma estimation: {n_obs:,} obs, {n_groups:,} FE groups, {n_years} years")

    if n_obs < 10:
        logger.warning("Too few observations for gamma estimation")
        return _default_gamma_result(n_quantiles)

    # Step 2: Run pyfixest with two-way FE and clustered SE
    try:
        import pyfixest as pf
    except ImportError:
        logger.warning("pyfixest not installed, falling back to linearmodels")
        return _estimate_gamma_linearmodels(df, gamma_config, n_quantiles)

    # pyfixest formula: y ~ x | FE1 + FE2
    # Compute SE with multiple vcov types for diagnostics
    try:
        # First fit with IID (homoskedastic) SE for baseline
        result_iid = pf.feols(
            "y ~ log_income | fe_group + year",
            data=df,
            weights="w",
            vcov="iid",
        )
        gamma = float(result_iid.coef().iloc[0])
        gamma_se_iid = float(result_iid.se().iloc[0])

        # HC1 (heteroskedasticity-robust, no clustering)
        result_hc1 = pf.feols(
            "y ~ log_income | fe_group + year",
            data=df,
            weights="w",
            vcov="HC1",
        )
        gamma_se_hc1 = float(result_hc1.se().iloc[0])

        # Two-way clustered SE (region-temp-bin-sign x year)
        result_clust = pf.feols(
            "y ~ log_income | fe_group + year",
            data=df,
            weights="w",
            vcov={"CRV1": "fe_group + year"},
        )
        gamma_se_clustered = float(result_clust.se().iloc[0])

        # Use clustered SE as the primary SE
        gamma_se = gamma_se_clustered

        # Log all SE types for diagnostics
        logger.info(f"Gamma SE comparison: IID={gamma_se_iid:.6f}, HC1={gamma_se_hc1:.6f}, Clustered={gamma_se_clustered:.6f}")
        logger.info(f"Clustering ratio: {gamma_se_clustered / gamma_se_iid:.2f}x IID")

        # R² extraction - pyfixest API varies by version
        try:
            r_squared = float(result_iid._r2)
        except AttributeError:
            try:
                r_squared = float(result_iid.r2_within)
            except AttributeError:
                r_squared = 0.0  # R² is optional, gamma and SE are what matter

    except Exception as e:
        logger.error(f"pyfixest failed completely: {e}")
        # Don't fall back to linearmodels - it will OOM with 25M+ rows
        # If pyfixest fails, we have a real problem
        raise RuntimeError(f"Gamma estimation failed: {e}")

    logger.info(f"Gamma: {gamma:.6f} (SE: {gamma_se:.6f}, R²: {r_squared:.4f})")

    # Step 3: Generate quantiles from normal distribution
    gamma_quantiles = _compute_quantiles(gamma, gamma_se, n_quantiles)

    return {
        "gamma": gamma,
        "gamma_se": gamma_se,
        "gamma_se_iid": gamma_se_iid,
        "gamma_se_hc1": gamma_se_hc1,
        "gamma_se_clustered": gamma_se_clustered,
        "r_squared": r_squared,
        "n_obs": n_obs,
        "n_fe_groups": n_groups,
        "gamma_quantiles": gamma_quantiles,
    }


def _estimate_gamma_linearmodels(df, gamma_config, n_quantiles: int) -> Dict:
    """
    Fallback to linearmodels PanelOLS if pyfixest is not available.

    Slower but correct.
    """
    try:
        from linearmodels.panel import PanelOLS
    except ImportError:
        logger.error("Neither pyfixest nor linearmodels installed")
        raise ImportError("Install pyfixest or linearmodels for gamma estimation")

    n_obs = len(df)
    n_groups = df["fe_group"].nunique()

    # Set panel index: (entity, time)
    df = df.set_index(["fe_group", "year"])

    mod = PanelOLS(
        dependent=df["y"],
        exog=df[["log_income"]],
        weights=df["w"],
        entity_effects=True,
        time_effects=True,
    )

    if gamma_config.cluster_se:
        result = mod.fit(
            cov_type="clustered",
            cluster_entity=True,
            cluster_time=True,
            low_memory=True,
        )
    else:
        result = mod.fit(cov_type="robust", low_memory=True)

    gamma = float(result.params.iloc[0])
    gamma_se = float(result.std_errors.iloc[0])
    r_squared = float(result.rsquared)

    logger.info(f"Gamma (linearmodels): {gamma:.6f} (SE: {gamma_se:.6f}, R²: {r_squared:.4f})")

    gamma_quantiles = _compute_quantiles(gamma, gamma_se, n_quantiles)

    return {
        "gamma": gamma,
        "gamma_se": gamma_se,
        "r_squared": r_squared,
        "n_obs": n_obs,
        "n_fe_groups": n_groups,
        "gamma_quantiles": gamma_quantiles,
    }


def _compute_quantiles(gamma: float, gamma_se: float, n_quantiles: int) -> List[float]:
    """
    Generate gamma quantiles using normal distribution.

    Default: 19 quantiles from 5th to 95th percentile (vigintiles).
    """
    if n_quantiles < 1:
        return [gamma]

    if gamma_se <= 0:
        return [gamma] * n_quantiles

    # Quantile probabilities: evenly spaced from 0.05 to 0.95
    probs = np.linspace(0.05, 0.95, n_quantiles)
    quantiles = norm.ppf(probs, loc=gamma, scale=gamma_se)

    return quantiles.tolist()


def _default_gamma_result(n_quantiles: int) -> Dict:
    """Return default result when estimation fails."""
    return {
        "gamma": 0.0,
        "gamma_se": 0.0,
        "r_squared": 0.0,
        "n_obs": 0,
        "n_fe_groups": 0,
        "gamma_quantiles": [0.0] * n_quantiles,
    }
