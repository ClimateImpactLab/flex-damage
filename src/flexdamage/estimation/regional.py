"""
Regional polynomial estimation: Fit α, β for all regions at a specific gamma.

VECTORIZED — no Python loop over regions. One SQL GROUP BY produces sufficient
statistics, then numpy does vectorized 3×3 matrix inversions.

Following the R reference (alphafit.R):
    y_norm = y * exp(-gamma * log_income)
    y_norm = intercept + alpha*T + beta*T² + residual

IMPORTANT: All SQL uses ONLY the standard columns from 'standardized' VIEW:
region, year, y, T, log_income, w, sdev, scenario, y_sign

No conditional column handling — standardize.py guarantees the schema.
"""

import logging
from typing import List, Tuple

import duckdb
import numpy as np
import pandas as pd

from ..config import Constraint, RunConfig

logger = logging.getLogger(__name__)


def fit_regional_polynomials(
    con: duckdb.DuckDBPyConnection,
    gamma: float,
    config: RunConfig,
) -> pd.DataFrame:
    """
    Fit regional polynomial coefficients (alpha, beta) for all regions.

    Fits the model for each region i::

        y_norm = intercept + alpha_i * T + beta_i * T^2 + epsilon

    where y_norm = y * Y^(-gamma) is the income-normalized outcome.

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
        Active DuckDB connection with 'standardized' view.
    gamma : float
        Income elasticity value (called once per quantile).
    config : RunConfig
        Pipeline configuration with constraints and settings.

    Returns
    -------
    pandas.DataFrame
        Regional parameters with columns:

        - region : str - Region identifier
        - gamma : float - Gamma value used
        - alpha : float - Linear temperature coefficient
        - beta : float - Quadratic temperature coefficient
        - sigma11 : float - Variance of alpha
        - sigma12 : float - Covariance of alpha, beta
        - sigma22 : float - Variance of beta
        - rsqr1 : float - R-squared of polynomial fit
        - n : int - Number of observations

    Notes
    -----
    Uses vectorized OLS via sufficient statistics (no Python loops).
    Constraints (e.g., beta <= 0 for agriculture) are applied post-estimation.
    """
    min_obs = config.estimation.regional.min_observations
    ridge = config.estimation.regional.ridge_lambda

    # Step 1: Compute sufficient statistics per region
    # y_norm = y * exp(-gamma * log_income)  [numerically stable form]
    # We need: n, sum(T), sum(T²), sum(T³), sum(T⁴), sum(y_norm), sum(T*y_norm), sum(T²*y_norm), sum(y_norm²)
    #
    # FIXED SQL — no conditional columns, uses ONLY standard columns
    sql = f"""
        SELECT
            region,
            COUNT(*) AS n,
            SUM(T) AS sum_T,
            SUM(T * T) AS sum_T2,
            SUM(T * T * T) AS sum_T3,
            SUM(T * T * T * T) AS sum_T4,
            SUM(y * EXP(-({gamma}) * log_income)) AS sum_y,
            SUM(T * y * EXP(-({gamma}) * log_income)) AS sum_Ty,
            SUM(T * T * y * EXP(-({gamma}) * log_income)) AS sum_T2y,
            SUM(POWER(y * EXP(-({gamma}) * log_income), 2)) AS sum_y2
        FROM standardized
        WHERE ISFINITE(y) AND ISFINITE(log_income) AND ISFINITE(T)
        GROUP BY region
        HAVING COUNT(*) >= {min_obs}
    """

    logger.debug(f"Regional SQL:\n{sql}")

    try:
        df = con.execute(sql).df()
    except Exception as e:
        logger.error(f"Regional SQL failed: {e}")
        logger.error(f"Full SQL:\n{sql}")
        raise

    if df.empty:
        logger.warning(f"No regions with >= {min_obs} observations")
        return pd.DataFrame(columns=[
            "region", "gamma", "intercept", "alpha", "beta",
            "sigma11", "sigma12", "sigma22", "rsqr1", "n"
        ])

    n_regions = len(df)
    logger.info(f"Fitting regional polynomials for {n_regions} regions (gamma={gamma:.4f})")

    # Extract arrays for vectorized computation
    n = df["n"].values.astype(float)
    sum_T = df["sum_T"].values
    sum_T2 = df["sum_T2"].values
    sum_T3 = df["sum_T3"].values
    sum_T4 = df["sum_T4"].values
    sum_y = df["sum_y"].values
    sum_Ty = df["sum_Ty"].values
    sum_T2y = df["sum_T2y"].values
    sum_y2 = df["sum_y2"].values

    # Step 2: Vectorized OLS
    # Design matrix X = [1, T, T²] (with intercept, matches R's lm())
    # X'X = [[n, sum_T, sum_T2],
    #        [sum_T, sum_T2, sum_T3],
    #        [sum_T2, sum_T3, sum_T4]]
    # X'y = [sum_y, sum_Ty, sum_T2y]

    # Build X'X matrices (n_regions, 3, 3)
    XtX = np.zeros((n_regions, 3, 3))
    XtX[:, 0, 0] = n
    XtX[:, 0, 1] = sum_T
    XtX[:, 0, 2] = sum_T2
    XtX[:, 1, 0] = sum_T
    XtX[:, 1, 1] = sum_T2
    XtX[:, 1, 2] = sum_T3
    XtX[:, 2, 0] = sum_T2
    XtX[:, 2, 1] = sum_T3
    XtX[:, 2, 2] = sum_T4

    # Add ridge regularization for numerical stability
    XtX[:, 0, 0] += ridge
    XtX[:, 1, 1] += ridge
    XtX[:, 2, 2] += ridge

    # Build X'y vectors (n_regions, 3)
    Xty = np.column_stack([sum_y, sum_Ty, sum_T2y])

    # Solve for coefficients: coef = (X'X)^-1 X'y
    # Vectorized solve - reshape Xty for batch solve: (n_regions, 3) -> (n_regions, 3, 1)
    try:
        coef = np.linalg.solve(XtX, Xty[:, :, np.newaxis]).squeeze(-1)
    except np.linalg.LinAlgError:
        # Fallback to per-region solve for singular matrices
        coef = np.zeros((n_regions, 3))
        for i in range(n_regions):
            try:
                coef[i] = np.linalg.solve(XtX[i], Xty[i])
            except np.linalg.LinAlgError:
                coef[i] = np.linalg.lstsq(XtX[i], Xty[i], rcond=None)[0]

    intercept = coef[:, 0]
    alpha = coef[:, 1]
    beta = coef[:, 2]

    # Step 3: Apply constraints vectorized
    alpha, beta, constrained_mask = _apply_constraints_vectorized(
        alpha, beta, config.estimation.constraints,
        n, sum_T, sum_T2, sum_y, sum_Ty, ridge
    )

    # Step 4: Compute residuals and statistics
    # For constrained regions (beta=0), recompute intercept from linear fit
    if constrained_mask.any():
        n_con = constrained_mask.sum()
        idx_con = np.where(constrained_mask)[0]

        # Build batch 2×2 matrices for constrained regions
        XtX_lin = np.zeros((n_con, 2, 2))
        XtX_lin[:, 0, 0] = n[idx_con] + ridge
        XtX_lin[:, 0, 1] = sum_T[idx_con]
        XtX_lin[:, 1, 0] = sum_T[idx_con]
        XtX_lin[:, 1, 1] = sum_T2[idx_con] + ridge

        Xty_lin = np.column_stack([sum_y[idx_con], sum_Ty[idx_con]])

        # Batch solve
        try:
            coef_lin = np.linalg.solve(XtX_lin, Xty_lin[:, :, np.newaxis]).squeeze(-1)
            intercept[idx_con] = coef_lin[:, 0]
            alpha[idx_con] = coef_lin[:, 1]
        except np.linalg.LinAlgError:
            for j, i in enumerate(idx_con):
                try:
                    coef_i = np.linalg.solve(XtX_lin[j], Xty_lin[j])
                    intercept[i] = coef_i[0]
                    alpha[i] = coef_i[1]
                except np.linalg.LinAlgError:
                    pass

    # Compute SST and SSR
    y_mean = sum_y / n
    SST = sum_y2 - n * y_mean**2

    # SSR = sum((y - y_pred)²)
    # y_pred_sum = intercept*n + alpha*sum_T + beta*sum_T2
    y_pred_y_sum = intercept * sum_y + alpha * sum_Ty + beta * sum_T2y

    # sum(y_pred²) = intercept²*n + alpha²*sum_T2 + beta²*sum_T4
    #              + 2*intercept*alpha*sum_T + 2*intercept*beta*sum_T2 + 2*alpha*beta*sum_T3
    sum_y_pred2 = (intercept**2 * n + alpha**2 * sum_T2 + beta**2 * sum_T4
                   + 2*intercept*alpha*sum_T + 2*intercept*beta*sum_T2 + 2*alpha*beta*sum_T3)

    SSR = sum_y2 - 2*y_pred_y_sum + sum_y_pred2

    # R² = 1 - SSR/SST (handle division safely)
    rsqr1 = np.zeros(len(SST))
    valid_sst = SST > 0
    rsqr1[valid_sst] = np.clip(1 - SSR[valid_sst] / SST[valid_sst], 0.0, 1.0)

    # Compute VCV matrix (variance-covariance)
    # sigma² = SSR / (n - k) where k = 3 (intercept, alpha, beta) or 2 if constrained
    k = np.where(constrained_mask, 2, 3)
    dof = n - k

    # Handle division safely
    sigma2 = np.zeros(len(dof))
    valid_dof = dof > 0
    sigma2[valid_dof] = np.maximum(0, SSR[valid_dof]) / dof[valid_dof]

    # VCV = sigma² * (X'X)^-1
    # We only need sigma11 (var(alpha)), sigma12 (cov(alpha, beta)), sigma22 (var(beta))
    sigma11 = np.zeros(n_regions)
    sigma12 = np.zeros(n_regions)
    sigma22 = np.zeros(n_regions)

    # Vectorized VCV for unconstrained regions (3×3 inversion)
    unconstrained = ~constrained_mask
    if unconstrained.any():
        idx_unc = np.where(unconstrained)[0]
        XtX_unc = XtX[idx_unc]
        try:
            XtX_inv_batch = np.linalg.inv(XtX_unc)
            sigma11[idx_unc] = sigma2[idx_unc] * XtX_inv_batch[:, 1, 1]
            sigma12[idx_unc] = sigma2[idx_unc] * XtX_inv_batch[:, 1, 2]
            sigma22[idx_unc] = sigma2[idx_unc] * XtX_inv_batch[:, 2, 2]
        except np.linalg.LinAlgError:
            for i in idx_unc:
                try:
                    XtX_inv = np.linalg.inv(XtX[i])
                    sigma11[i] = sigma2[i] * XtX_inv[1, 1]
                    sigma12[i] = sigma2[i] * XtX_inv[1, 2]
                    sigma22[i] = sigma2[i] * XtX_inv[2, 2]
                except np.linalg.LinAlgError:
                    pass

    # Vectorized VCV for constrained regions (2×2 linear model)
    if constrained_mask.any():
        idx_con = np.where(constrained_mask)[0]
        n_con = len(idx_con)

        XtX_lin = np.zeros((n_con, 2, 2))
        XtX_lin[:, 0, 0] = n[idx_con] + ridge
        XtX_lin[:, 0, 1] = sum_T[idx_con]
        XtX_lin[:, 1, 0] = sum_T[idx_con]
        XtX_lin[:, 1, 1] = sum_T2[idx_con] + ridge

        try:
            XtX_inv_lin = np.linalg.inv(XtX_lin)
            sigma11[idx_con] = sigma2[idx_con] * XtX_inv_lin[:, 1, 1]
        except np.linalg.LinAlgError:
            for j, i in enumerate(idx_con):
                try:
                    XtX_inv = np.linalg.inv(XtX_lin[j])
                    sigma11[i] = sigma2[i] * XtX_inv[1, 1]
                except np.linalg.LinAlgError:
                    pass
        # sigma12, sigma22 remain 0 for constrained

    # Build result DataFrame
    result = pd.DataFrame({
        "region": df["region"].values,
        "gamma": gamma,
        "intercept": intercept,
        "alpha": alpha,
        "beta": beta,
        "sigma11": sigma11,
        "sigma12": sigma12,
        "sigma22": sigma22,
        "rsqr1": rsqr1,
        "n": n.astype(int),
    })

    n_constrained = constrained_mask.sum()
    if n_constrained > 0:
        logger.info(f"  {n_constrained} regions had constraints applied")

    return result


def _apply_constraints_vectorized(
    alpha: np.ndarray,
    beta: np.ndarray,
    constraints: List[Constraint],
    n: np.ndarray,
    sum_T: np.ndarray,
    sum_T2: np.ndarray,
    sum_y: np.ndarray,
    sum_Ty: np.ndarray,
    ridge: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Apply constraints to parameters vectorized.

    For constraints on beta (most common):
    - "max" with value=0: beta <= 0 (concavity, agriculture)
    - "min" with value=0: beta >= 0 (convexity, mortality)

    When constraint is violated, set beta to boundary value.
    Alpha is refitted in the main function.

    Returns:
        (alpha, beta, constrained_mask)
    """
    constrained_mask = np.zeros(len(alpha), dtype=bool)

    for constraint in constraints:
        if constraint.parameter == "beta":
            if constraint.type == "max" and constraint.value is not None:
                # beta <= value
                violated = beta > constraint.value
                if violated.any():
                    beta[violated] = constraint.value
                    constrained_mask[violated] = True

            elif constraint.type == "min" and constraint.value is not None:
                # beta >= value
                violated = beta < constraint.value
                if violated.any():
                    beta[violated] = constraint.value
                    constrained_mask[violated] = True

            elif constraint.type == "bounds":
                if constraint.min is not None:
                    violated = beta < constraint.min
                    beta[violated] = constraint.min
                    constrained_mask[violated] = True
                if constraint.max is not None:
                    violated = beta > constraint.max
                    beta[violated] = constraint.max
                    constrained_mask[violated] = True

        elif constraint.parameter == "alpha":
            if constraint.type == "max" and constraint.value is not None:
                alpha[alpha > constraint.value] = constraint.value

            elif constraint.type == "min" and constraint.value is not None:
                alpha[alpha < constraint.value] = constraint.value

            elif constraint.type == "bounds":
                if constraint.min is not None:
                    alpha[alpha < constraint.min] = constraint.min
                if constraint.max is not None:
                    alpha[alpha > constraint.max] = constraint.max

    return alpha, beta, constrained_mask
