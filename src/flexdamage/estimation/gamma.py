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

    # Step 2: dispatch on backend (pyfixest default, R fixest opt-in)
    backend = getattr(gamma_config, "backend", "pyfixest")
    if backend == "fixest":
        try:
            return _estimate_gamma_fixest_r(df, gamma_config, n_quantiles, n_obs, n_groups)
        except Exception as e:
            logger.error(f"R fixest backend failed: {e}; falling back to pyfixest")
            # fall through to pyfixest path

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


_R_GAMMA_SCRIPT = r"""
suppressMessages({
  library(fixest)
  library(jsonlite)
})
args <- commandArgs(trailingOnly = TRUE)
in_file   <- args[1]
out_json  <- args[2]
n_threads <- if (length(args) >= 3) as.integer(args[3]) else parallel::detectCores()
file_kind <- if (length(args) >= 4) args[4] else "csv"
tol       <- if (length(args) >= 5) as.numeric(args[5]) else 1e-10
setFixest_nthreads(n_threads)
t0 <- Sys.time()
if (file_kind == "parquet") {
  suppressMessages({ library(duckdb); library(DBI) })
  con <- dbConnect(duckdb::duckdb())
  dbExecute(con, sprintf("SET threads = %d", n_threads))
  df <- dbGetQuery(con, sprintf("SELECT * FROM read_parquet('%s')", in_file))
  dbDisconnect(con, shutdown = TRUE)
} else {
  suppressMessages(library(data.table))
  setDTthreads(n_threads)
  df <- fread(in_file)
}
df$year     <- as.integer(df$year)
df$fe_group <- as.factor(df$fe_group)
t_read <- as.numeric(Sys.time() - t0, units = "secs")
cat(sprintf("R read (%s): %.2fs (%d rows)\n", file_kind, t_read, nrow(df)))
t1 <- Sys.time()
m_iid     <- feols(y ~ log_income | fe_group + year, data = df, weights = ~w, vcov = "iid",       fixef.tol = tol)
m_hc1     <- feols(y ~ log_income | fe_group + year, data = df, weights = ~w, vcov = "hetero",    fixef.tol = tol)
m_clust   <- feols(y ~ log_income | fe_group + year, data = df, weights = ~w,
                   cluster = ~fe_group + year, fixef.tol = tol)
elapsed <- as.numeric(Sys.time() - t1, units = "secs")
gamma          <- unname(m_iid$coefficients["log_income"])
se_iid         <- unname(sqrt(diag(m_iid$cov.scaled))["log_income"])
se_hc1         <- unname(sqrt(diag(m_hc1$cov.scaled))["log_income"])
se_clustered   <- unname(sqrt(diag(m_clust$cov.scaled))["log_income"])
r2 <- tryCatch(as.numeric(fitstat(m_iid, "r2", simplify = TRUE)), error = function(e) NA_real_)
out <- list(
  gamma              = gamma,
  gamma_se_iid       = se_iid,
  gamma_se_hc1       = se_hc1,
  gamma_se_clustered = se_clustered,
  r_squared          = r2,
  elapsed_sec        = elapsed,
  n_threads_used     = n_threads
)
write(jsonlite::toJSON(out, auto_unbox = TRUE, na = "null", digits = NA), out_json)
cat(sprintf("R fixest: gamma=%.6f, SE_clust=%.6f, elapsed=%.2fs\n", gamma, se_clustered, elapsed))
"""


def _r_has_duckdb(rscript: str = "Rscript") -> bool:
    """Probe whether R has duckdb + DBI for parquet handoff."""
    import subprocess
    code = "q(status = if (requireNamespace('duckdb', quietly=TRUE) && requireNamespace('DBI', quietly=TRUE)) 0 else 1)"
    try:
        r = subprocess.run([rscript, "-e", code], capture_output=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def _estimate_gamma_fixest_r(df, gamma_config, n_quantiles: int, n_obs: int, n_groups: int) -> Dict:
    """Run the gamma FE regression via R fixest (50-200x faster than pyfixest at scale)."""
    import json
    import os
    import subprocess
    import tempfile
    from pathlib import Path

    rscript = "Rscript"
    n_threads = int(os.environ.get("OMP_NUM_THREADS", os.cpu_count() or 4))
    use_parquet = _r_has_duckdb(rscript)
    file_kind = "parquet" if use_parquet else "csv"
    logger.info(f"R fixest backend: handoff via {file_kind}, threads={n_threads}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if use_parquet:
            in_file = tmp / "prepped.parquet"
            df[["y", "log_income", "year", "fe_group", "w"]].to_parquet(
                in_file, index=False, compression="zstd"
            )
        else:
            in_file = tmp / "prepped.csv"
            df[["y", "log_income", "year", "fe_group", "w"]].to_csv(in_file, index=False)
        script_file = tmp / "gamma.R"
        out_json = tmp / "result.json"
        script_file.write_text(_R_GAMMA_SCRIPT)

        cmd = [rscript, str(script_file), str(in_file), str(out_json),
               str(n_threads), file_kind, "1e-10"]
        logger.info(f"Running R fixest: {' '.join(cmd[:3])} ...")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.stdout:
            for line in proc.stdout.strip().splitlines():
                logger.info(f"  [R] {line}")
        if proc.returncode != 0:
            logger.error(proc.stderr)
            raise RuntimeError(f"R fixest exited {proc.returncode}")

        with open(out_json) as f:
            res = json.load(f)

    gamma = float(res["gamma"])
    gamma_se_iid = float(res["gamma_se_iid"])
    gamma_se_hc1 = float(res["gamma_se_hc1"])
    gamma_se_clustered = float(res["gamma_se_clustered"])
    gamma_se = gamma_se_clustered  # primary SE
    r_squared = float(res["r_squared"]) if res.get("r_squared") is not None else 0.0

    logger.info(f"Gamma: {gamma:.6f} (SE: {gamma_se:.6f}, R^2: {r_squared:.4f}) via R fixest")

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
