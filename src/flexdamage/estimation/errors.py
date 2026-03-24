"""
Error term computation: ρ, ζ, η.

THIS IS THE FILE THAT BROKE IN v2. Now it's simple because all columns
are guaranteed by the standardized parquet.

Following the R reference (alphafit.R):
    - ρ: Correlation between regional and global residuals
    - ζ: Slope of |residuals| vs T (NO intercept)
    - η: Std dev of residual noise after removing ζ*T

CRITICAL DESIGN:
- COALESCE(sdev, 0) handles NULL sdev without conditional SQL
- scenario = g.scenario OR (NULL = NULL) handles NULL scenario
- Regional params passed via temp parquet, NOT DataFrame registration
- ONE SQL query computes ALL error terms

IMPORTANT: All SQL uses ONLY the standard columns from 'standardized' VIEW:
region, year, y, T, log_income, w, sdev, scenario, y_sign
"""

import logging
import os
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from ..config import RunConfig

logger = logging.getLogger(__name__)


def compute_all_error_terms(
    con: duckdb.DuckDBPyConnection,
    regional_params: pd.DataFrame,
    gamma: float,
    config: RunConfig,
) -> pd.DataFrame:
    """
    Compute error structure parameters (rho, zeta, eta) for all regions.

    Computes the error decomposition for Monte Carlo sampling::

        epsilon = rho * u_global + zeta * T * v_scenario + eta * noise

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
        Active DuckDB connection with 'standardized' view.
    regional_params : pandas.DataFrame
        Regional parameters with columns [region, intercept, alpha, beta].
    gamma : float
        Gamma value used for income normalization.
    config : RunConfig
        Pipeline configuration.

    Returns
    -------
    pandas.DataFrame
        Error parameters with columns:

        - region : str - Region identifier
        - rho : float - Correlation with global residual process
        - zeta : float - Temperature-dependent error scale
        - eta : float - Residual noise standard deviation
        - rsqr2 : float - R-squared of error model fit
    """
    # Step 1: Write regional params to temp parquet (NEVER register DataFrame!)
    fd, params_path = tempfile.mkstemp(suffix=".parquet", prefix="flexdamage_params_")
    os.close(fd)

    try:
        # Write params to parquet
        regional_params[["region", "intercept", "alpha", "beta"]].to_parquet(
            params_path, index=False
        )

        # Create view from parquet
        con.execute(f"""
            CREATE OR REPLACE VIEW params AS
            SELECT * FROM read_parquet('{params_path}')
        """)

        # Step 2: Compute global polynomial (for rho)
        # Group by scenario + year (scenario is always present, may be NULL)
        con.execute(f"""
            CREATE OR REPLACE VIEW global_agg AS
            SELECT
                year,
                scenario,
                SUM(w * y) / SUM(w) AS y_mean,
                SUM(w * T) / SUM(w) AS T_mean,
                SUM(w * EXP(log_income)) / SUM(w) AS gdp_mean,
                SUM(w) AS total_w
            FROM standardized
            WHERE ISFINITE(y) AND ISFINITE(log_income) AND w > 0
            GROUP BY year, scenario
        """)

        # Normalize global
        con.execute(f"""
            CREATE OR REPLACE VIEW global_normed AS
            SELECT
                year,
                scenario,
                y_mean,
                T_mean,
                gdp_mean,
                total_w,
                y_mean / POWER(gdp_mean, {gamma}) AS y_normed,
                T_mean * T_mean AS T2_mean
            FROM global_agg
            WHERE gdp_mean > 0 AND ISFINITE(y_mean / POWER(gdp_mean, {gamma}))
        """)

        # Fit global polynomial via sufficient statistics
        g_stats = con.execute("""
            SELECT
                SUM(total_w) AS sw,
                SUM(total_w * T_mean) AS swT,
                SUM(total_w * T2_mean) AS swT2,
                SUM(total_w * T_mean * T_mean) AS swTT,
                SUM(total_w * T_mean * T2_mean) AS swTT2,
                SUM(total_w * T2_mean * T2_mean) AS swT2T2,
                SUM(total_w * y_normed) AS swy,
                SUM(total_w * T_mean * y_normed) AS swTy,
                SUM(total_w * T2_mean * y_normed) AS swT2y
            FROM global_normed
        """).fetchone()

        # Check for NULL values (can happen with empty data)
        if any(v is None for v in g_stats):
            logger.warning("Global polynomial stats contain NULL — insufficient data")
            return pd.DataFrame(columns=["region", "rho", "zeta", "eta", "rsqr2"])

        # Solve 3x3 for global polynomial: y_normed = intercept + alpha*T + beta*T²
        XtWX = np.array([
            [g_stats[0], g_stats[1], g_stats[2]],
            [g_stats[1], g_stats[3], g_stats[4]],
            [g_stats[2], g_stats[4], g_stats[5]]
        ])
        XtWy = np.array([g_stats[6], g_stats[7], g_stats[8]])

        # Add small regularization for numerical stability
        try:
            g_coef = np.linalg.solve(XtWX + 1e-10 * np.eye(3), XtWy)
        except np.linalg.LinAlgError:
            g_coef = np.linalg.lstsq(XtWX, XtWy, rcond=None)[0]

        intercept_g, alpha_g, beta_g = g_coef

        # Create global residuals view
        con.execute(f"""
            CREATE OR REPLACE VIEW global_resids AS
            SELECT
                year,
                scenario,
                y_normed - ({intercept_g} + {alpha_g} * T_mean + {beta_g} * T2_mean)
                    AS global_resid
            FROM global_normed
        """)

        # Step 3: ALL error terms in ONE query
        # Key design choices:
        # - COALESCE(sdev, 0) handles NULL sdev without conditional SQL
        # - (scenario = g.scenario OR (scenario IS NULL AND g.scenario IS NULL))
        #   handles NULL scenario comparison
        result = con.execute(f"""
            WITH obs_resids AS (
                SELECT
                    s.region,
                    s.year,
                    s.scenario,
                    s.T,
                    (s.y * EXP(-({gamma}) * s.log_income))
                        - (p.intercept + p.alpha * s.T + p.beta * s.T * s.T)
                        AS resid,
                    SQRT(
                        POWER(
                            (s.y * EXP(-({gamma}) * s.log_income))
                            - (p.intercept + p.alpha * s.T + p.beta * s.T * s.T)
                        , 2)
                        + POWER(COALESCE(s.sdev, 0) * EXP(-({gamma}) * s.log_income), 2)
                    ) AS total_error
                FROM standardized s
                JOIN params p ON s.region = p.region
                WHERE ISFINITE(s.y) AND ISFINITE(s.log_income) AND ISFINITE(s.T)
            ),
            with_global AS (
                SELECT
                    o.region,
                    o.year,
                    o.T,
                    o.resid,
                    o.total_error,
                    g.global_resid
                FROM obs_resids o
                LEFT JOIN global_resids g
                    ON o.year = g.year
                    AND (o.scenario = g.scenario
                         OR (o.scenario IS NULL AND g.scenario IS NULL))
            ),
            per_region AS (
                SELECT
                    region,
                    CORR(resid, global_resid) AS rho,
                    COUNT(*) AS n,
                    SUM(T * total_error) AS sum_TE,
                    SUM(T * T) AS sum_TT,
                    SUM(total_error * total_error) AS sum_EE
                FROM with_global
                WHERE total_error IS NOT NULL
                  AND ISFINITE(total_error)
                  AND global_resid IS NOT NULL
                GROUP BY region
                HAVING COUNT(*) >= 3
            )
            SELECT
                region,
                COALESCE(rho, 0) AS rho,
                CASE WHEN sum_TT > 0 THEN sum_TE / sum_TT ELSE 0 END AS zeta,
                n,
                sum_EE,
                sum_TE,
                sum_TT
            FROM per_region
        """).df()

        if result.empty:
            logger.warning("No regions with sufficient data for error terms")
            return pd.DataFrame(columns=["region", "rho", "zeta", "eta", "rsqr2"])

        # Compute eta and rsqr2 in numpy
        zeta = result["zeta"].values
        sum_EE = result["sum_EE"].values
        sum_TE = result["sum_TE"].values
        sum_TT = result["sum_TT"].values
        n = result["n"].values.astype(float)

        # SSR for no-intercept model: sum((E - zeta*T)²) = sum_EE - 2*zeta*sum_TE + zeta²*sum_TT
        SSR = sum_EE - 2 * zeta * sum_TE + zeta**2 * sum_TT
        SSR = np.maximum(SSR, 0)  # Numerical safety

        # eta = sqrt(SSR / (n-1)) (std dev of residuals)
        eta = np.zeros(len(n))
        valid = n > 1
        eta[valid] = np.sqrt(SSR[valid] / (n[valid] - 1))

        # rsqr2 for no-intercept model: 1 - SSR / sum_EE
        rsqr2 = np.zeros(len(n))
        valid_ee = sum_EE > 0
        rsqr2[valid_ee] = np.clip(1.0 - SSR[valid_ee] / sum_EE[valid_ee], 0, 1)

        return pd.DataFrame({
            "region": result["region"].values,
            "rho": result["rho"].values,
            "zeta": zeta,
            "eta": eta,
            "rsqr2": rsqr2,
        })

    finally:
        # Cleanup temp parquet
        Path(params_path).unlink(missing_ok=True)


def compute_global_residuals(
    con: duckdb.DuckDBPyConnection,
    gamma: float,
) -> dict:
    """
    Fit global (population-weighted) polynomial and return coefficients.

    Creates VIEW 'global_resids' in DuckDB containing:
        year, scenario, global_resid

    This is called internally by compute_all_error_terms, but exposed
    for cases where you need the global polynomial separately.

    Args:
        con: DuckDB connection with 'standardized' VIEW
        gamma: Gamma value to use for normalization

    Returns:
        {"alpha_global": float, "beta_global": float, "r_squared": float}
    """
    # Aggregate to global level
    con.execute(f"""
        CREATE OR REPLACE VIEW _global_agg AS
        SELECT
            year,
            scenario,
            SUM(w * y) / SUM(w) AS y_mean,
            SUM(w * T) / SUM(w) AS T_mean,
            SUM(w * EXP(log_income)) / SUM(w) AS gdp_mean,
            SUM(w) AS total_w
        FROM standardized
        WHERE ISFINITE(y) AND ISFINITE(log_income) AND w > 0
        GROUP BY year, scenario
    """)

    # Normalize
    con.execute(f"""
        CREATE OR REPLACE VIEW _global_normed AS
        SELECT *,
            y_mean / POWER(gdp_mean, {gamma}) AS y_normed,
            T_mean * T_mean AS T2_mean
        FROM _global_agg
        WHERE gdp_mean > 0
    """)

    # Sufficient statistics
    stats = con.execute("""
        SELECT
            COUNT(*) AS n,
            SUM(total_w) AS sum_w,
            SUM(total_w * T_mean) AS sum_wT,
            SUM(total_w * T2_mean) AS sum_wT2,
            SUM(total_w * T_mean * T_mean) AS sum_wT2_raw,
            SUM(total_w * T_mean * T2_mean) AS sum_wT3,
            SUM(total_w * T2_mean * T2_mean) AS sum_wT4,
            SUM(total_w * y_normed) AS sum_wy,
            SUM(total_w * T_mean * y_normed) AS sum_wTy,
            SUM(total_w * T2_mean * y_normed) AS sum_wT2y,
            SUM(total_w * y_normed * y_normed) AS sum_wy2
        FROM _global_normed
    """).fetchone()

    n = stats[0]
    if n < 3:
        logger.warning("Not enough global observations for polynomial fit")
        return {"alpha_global": 0.0, "beta_global": 0.0, "r_squared": 0.0}

    sum_w = stats[1]
    sum_wT = stats[2]
    sum_wT2 = stats[3]
    sum_wT2_raw = stats[4]
    sum_wT3 = stats[5]
    sum_wT4 = stats[6]
    sum_wy = stats[7]
    sum_wTy = stats[8]
    sum_wT2y = stats[9]
    sum_wy2 = stats[10]

    # Solve WLS: [intercept, alpha, beta]
    XtWX = np.array([
        [sum_w, sum_wT, sum_wT2],
        [sum_wT, sum_wT2_raw, sum_wT3],
        [sum_wT2, sum_wT3, sum_wT4]
    ])
    XtWy = np.array([sum_wy, sum_wTy, sum_wT2y])

    try:
        coef = np.linalg.solve(XtWX + 1e-10 * np.eye(3), XtWy)
    except np.linalg.LinAlgError:
        coef = np.linalg.lstsq(XtWX, XtWy, rcond=None)[0]

    intercept_g, alpha_g, beta_g = coef

    # Create residuals view
    con.execute(f"""
        CREATE OR REPLACE VIEW global_resids AS
        SELECT
            year,
            scenario,
            y_normed - ({intercept_g} + {alpha_g} * T_mean + {beta_g} * T2_mean)
                AS global_resid
        FROM _global_normed
    """)

    # Compute R²
    y_mean_global = sum_wy / sum_w
    SST = sum_wy2 - sum_w * y_mean_global**2
    SSR = sum_wy2 - 2 * np.dot(coef, XtWy) + np.dot(coef, XtWX @ coef)

    if SST > 0:
        r_squared = max(0.0, min(1.0, 1 - SSR / SST))
    else:
        r_squared = 0.0

    logger.info(f"Global polynomial: alpha={alpha_g:.6f}, beta={beta_g:.6f}, R²={r_squared:.4f}")

    return {
        "alpha_global": float(alpha_g),
        "beta_global": float(beta_g),
        "r_squared": float(r_squared),
    }
