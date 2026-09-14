#!/usr/bin/env python3
"""
Benchmark: pyfixest (Python) vs fixest (R) for the gamma FE regression.

Replicates the exact specification used in estimation/gamma.py:

    y ~ log_income | fe_group + year
    fe_group = CONCAT(sign(y), region, floor(T/bin_width))
    cluster = fe_group + year  (two-way clustered SE)

For a given input parquet, runs both engines, compares point estimate,
clustered SE, R-squared, and wall-clock runtime. Prints a summary table.

Usage
-----
# Mortality input (the one that's been slow)
python scripts/benchmark_gamma.py \
    --input /project/cil/home_dirs/scadavidsanchez/projects/flex-damages-data/mortality/allcause/ir/mortality_aggregated.parquet \
    --y adjusted_mortality

# Labor smoke input (fast sanity check)
python scripts/benchmark_gamma.py \
    --input /scratch/midway3/cadavidsanchez/flex-damages/labor/smoke/labor_aggregated_smoke.parquet \
    --y labor_combined

# Skip R if you only want to measure pyfixest
python scripts/benchmark_gamma.py --input ... --y ... --skip-r
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)


def prepare_dataframe(
    parquet_path: str,
    y_col: str,
    temp_col: str,
    income_col: str,
    region_col: str,
    year_col: str,
    bin_width: float,
    trim_pct: float,
    include_sign_in_fe: bool,
) -> pd.DataFrame:
    """Standardize + build fe_group + trim. Mirrors estimation/gamma.py logic."""
    con = duckdb.connect()
    con.execute(f"SET threads = {os.cpu_count() or 1}")

    if include_sign_in_fe:
        fe_expr = f"""CONCAT(
            CASE WHEN {y_col} >= 0 THEN 'P' ELSE 'N' END,
            CAST({region_col} AS VARCHAR),
            '_', CAST(FLOOR({temp_col} / {bin_width}) AS INTEGER)
        )"""
    else:
        fe_expr = f"""CONCAT(
            CAST({region_col} AS VARCHAR),
            '_', CAST(FLOOR({temp_col} / {bin_width}) AS INTEGER)
        )"""

    trim_clause = ""
    if trim_pct > 0:
        threshold_q = f"""
            SELECT PERCENTILE_CONT({trim_pct}) WITHIN GROUP (ORDER BY ABS({y_col}))
            FROM read_parquet('{parquet_path}')
            WHERE {y_col} IS NOT NULL
        """
        threshold = con.execute(threshold_q).fetchone()[0]
        trim_clause = f"AND ABS({y_col}) >= {threshold}"
        log.info(f"Trimming: excluding |y| < {threshold:.6f} (bottom {100*trim_pct:.1f}%)")

    q = f"""
        SELECT
            {y_col} AS y,
            LOG({income_col}) AS log_income,
            {year_col} AS year,
            {fe_expr} AS fe_group
        FROM read_parquet('{parquet_path}')
        WHERE {y_col} IS NOT NULL
          AND {income_col} IS NOT NULL
          AND {income_col} > 0
          {trim_clause}
    """
    df = con.execute(q).df()
    con.close()
    log.info(f"Prepared: {len(df):,} rows, {df['fe_group'].nunique():,} fe groups, {df['year'].nunique()} years")
    return df


def run_pyfixest(df: pd.DataFrame, tol: float = 1e-10) -> dict:
    import pyfixest as pf

    # Tighten the demeaning convergence tolerance so results are comparable
    # to fixest at ~1e-10. Arg name varies slightly by pyfixest version.
    feols_kwargs = dict(
        data=df,
        vcov={"CRV1": "fe_group + year"},
    )
    # Try the known tolerance arg names; only one will be accepted
    for arg in ("fixef_tol", "tol", "fe_tol"):
        try:
            t0 = time.perf_counter()
            res = pf.feols("y ~ log_income | fe_group + year",
                           **feols_kwargs, **{arg: tol})
            t1 = time.perf_counter()
            break
        except TypeError:
            continue
    else:
        log.warning("Could not pass tolerance to pyfixest; using its default")
        t0 = time.perf_counter()
        res = pf.feols("y ~ log_income | fe_group + year", **feols_kwargs)
        t1 = time.perf_counter()

    coef = float(res.coef().iloc[0])
    se = float(res.se().iloc[0])

    # R-squared extraction - try newer API first, fall back to older
    r2 = None
    candidates = [
        lambda r: float(r._rsq),
        lambda r: float(r.rsq()["R2"]),
        lambda r: float(r.rsq()) if callable(getattr(r, "rsq", None)) else None,
        lambda r: float(r.summary().tables[0].data.get("R2", None)),
        lambda r: float(getattr(r, "_r2", None)) if getattr(r, "_r2", None) is not None else None,
    ]
    for fn in candidates:
        try:
            r2 = fn(res)
            if r2 is not None:
                break
        except Exception:
            continue

    # N obs used (after singleton drops etc.)
    n_obs = None
    try:
        n_obs = int(res._N) if hasattr(res, "_N") else int(getattr(res, "N", None) or 0) or None
    except Exception:
        pass

    return {
        "engine": "pyfixest",
        "gamma": coef,
        "gamma_se_clustered": se,
        "r_squared": r2,
        "elapsed_sec": t1 - t0,
        "n_obs_used": n_obs,
        "tolerance": tol,
    }


R_SCRIPT = r"""
suppressMessages({
  library(fixest)
  library(jsonlite)
})
args <- commandArgs(trailingOnly = TRUE)
in_file     <- args[1]
out_json    <- args[2]
n_threads   <- if (length(args) >= 3) as.integer(args[3]) else parallel::detectCores()
file_kind   <- if (length(args) >= 4) args[4] else "csv"
tol         <- if (length(args) >= 5) as.numeric(args[5]) else 1e-10
setFixest_nthreads(n_threads)
cat(sprintf("R fixest: using %d threads, fixef.tol=%.0e\n", n_threads, tol))
t0 <- Sys.time()
if (file_kind == "parquet") {
  suppressMessages({ library(duckdb); library(DBI) })
  cat("R input: parquet via duckdb\n")
  con <- dbConnect(duckdb::duckdb())
  dbExecute(con, sprintf("SET threads = %d", n_threads))
  df <- dbGetQuery(con, sprintf("SELECT * FROM read_parquet('%s')", in_file))
  dbDisconnect(con, shutdown = TRUE)
  df$year     <- as.integer(df$year)
  df$fe_group <- as.factor(df$fe_group)
} else {
  suppressMessages(library(data.table))
  cat("R input: csv via data.table::fread\n")
  setDTthreads(n_threads)
  df <- fread(in_file)
  df[, year     := as.integer(year)]
  df[, fe_group := as.factor(fe_group)]
}
t_read <- as.numeric(Sys.time() - t0, units = "secs")
cat(sprintf("R read (%s): %.2fs (%d rows)\n", file_kind, t_read, nrow(df)))
t1 <- Sys.time()
m <- feols(y ~ log_income | fe_group + year,
           data      = df,
           cluster   = ~fe_group + year,
           fixef.tol = tol)
elapsed <- as.numeric(Sys.time() - t1, units = "secs")
# Pull exact numeric values (not the rounded printed ones)
coef_val <- unname(m$coefficients["log_income"])
se_val   <- unname(sqrt(diag(m$cov.scaled))["log_income"])
r2_val   <- tryCatch(as.numeric(fitstat(m, "r2", simplify = TRUE)), error = function(e) NA_real_)
out <- list(
  engine             = "fixest",
  gamma              = coef_val,
  gamma_se_clustered = se_val,
  r_squared          = r2_val,
  elapsed_sec        = elapsed,
  n_threads_used     = n_threads,
  n_obs_used         = m$nobs,
  tolerance          = tol
)
write(jsonlite::toJSON(out, auto_unbox = TRUE, na = "null"), out_json)
cat(sprintf("R fixest done in %.2fs (%d threads)\n", elapsed, n_threads))
"""


def _probe_r_has_duckdb(rscript_path: str) -> bool:
    """Return True if R's duckdb + DBI are available."""
    code = (
        "q(status = if ("
        "  requireNamespace('duckdb', quietly=TRUE) && "
        "  requireNamespace('DBI',    quietly=TRUE)"
        ") 0 else 1)"
    )
    try:
        result = subprocess.run([rscript_path, "-e", code], capture_output=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def run_fixest_r(df: pd.DataFrame, r_threads: int, rscript_path: str = "Rscript", tol: float = 1e-10) -> dict:
    use_parquet = _probe_r_has_duckdb(rscript_path)
    file_kind = "parquet" if use_parquet else "csv"
    log.info(f"R handoff format: {file_kind}" + (" (duckdb available)" if use_parquet else " (duckdb not available, using data.table::fread)"))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if use_parquet:
            in_file = tmp / "prepped.parquet"
            log.info(f"Writing prepped data to parquet ({len(df):,} rows) for R handoff")
            df.to_parquet(in_file, index=False, compression="zstd")
        else:
            in_file = tmp / "prepped.csv"
            log.info(f"Writing prepped data to CSV ({len(df):,} rows) for R handoff")
            df.to_csv(in_file, index=False)

        script_file = tmp / "bench.R"
        out_json = tmp / "result.json"
        script_file.write_text(R_SCRIPT)

        cmd = [rscript_path, str(script_file), str(in_file), str(out_json),
               str(r_threads), file_kind, str(tol)]
        log.info(f"Running R: {' '.join(cmd)}")
        t0 = time.perf_counter()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        t1 = time.perf_counter()
        if proc.stdout:
            for line in proc.stdout.strip().splitlines():
                log.info(f"  [R] {line}")
        if proc.returncode != 0:
            log.error(f"R script failed (exit {proc.returncode})")
            log.error(proc.stderr)
            raise RuntimeError("R fixest failed; see above")

        with open(out_json) as f:
            res = json.load(f)
        res["elapsed_wallclock_sec"] = t1 - t0
        return res


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, help="Input parquet (aggregated sector data)")
    p.add_argument("--y", required=True, help="Name of the y column (e.g. adjusted_mortality, labor_combined)")
    p.add_argument("--temp", default="temperature_anomaly", help="Temperature column name")
    p.add_argument("--income", default="gdppc", help="Income column name (absolute levels)")
    p.add_argument("--region", default="region", help="Region column name")
    p.add_argument("--year", default="year", help="Year column name")
    p.add_argument("--bin-width", type=float, default=0.5, help="Temperature bin width for FE")
    p.add_argument("--trim-pct", type=float, default=0.05, help="Bottom percentile of |y| to drop")
    p.add_argument("--no-sign-in-fe", action="store_true", help="Exclude sign(y) from fe_group")
    p.add_argument("--skip-r", action="store_true", help="Only run pyfixest, skip R fixest")
    p.add_argument("--r-threads", type=int, default=int(os.environ.get("SLURM_CPUS_PER_TASK", os.cpu_count() or 1)))
    p.add_argument("--rscript", default="Rscript", help="Path to Rscript binary (default: Rscript on PATH)")
    p.add_argument("--output-json", default=None,
                   help="Optional path to save the comparison as JSON (for record-keeping)")
    p.add_argument("--probe-only", action="store_true",
                   help="Skip the actual benchmark; just report which R handoff format will be used and exit")
    p.add_argument("--sample-regions", type=int, default=None,
                   help="Randomly subsample to N regions before regression (quick sanity test)")
    p.add_argument("--year-min", type=int, default=None, help="Drop years before this (default: no filter)")
    p.add_argument("--year-max", type=int, default=None, help="Drop years after this (default: no filter)")
    p.add_argument("--random-seed", type=int, default=42, help="Seed for region subsampling")
    p.add_argument("--tol", type=float, default=1e-10,
                   help="FE demeaning tolerance passed to both engines (default 1e-10)")
    args = p.parse_args()

    if args.probe_only:
        has_duckdb = _probe_r_has_duckdb(args.rscript)
        print(f"R binary:          {args.rscript}")
        print(f"duckdb + DBI in R: {'yes' if has_duckdb else 'no'}")
        print(f"Handoff format:    {'parquet (fast)' if has_duckdb else 'csv (fallback)'}")
        sys.exit(0)

    log.info("=" * 70)
    log.info("Preparing dataframe (one-time cost, shared between engines)")
    log.info("=" * 70)
    df = prepare_dataframe(
        parquet_path=args.input,
        y_col=args.y,
        temp_col=args.temp,
        income_col=args.income,
        region_col=args.region,
        year_col=args.year,
        bin_width=args.bin_width,
        trim_pct=args.trim_pct,
        include_sign_in_fe=not args.no_sign_in_fe,
    )

    # Optional subsetting for quick sanity tests
    if args.year_min is not None:
        df = df[df["year"] >= args.year_min]
        log.info(f"After year>={args.year_min} filter: {len(df):,} rows")
    if args.year_max is not None:
        df = df[df["year"] <= args.year_max]
        log.info(f"After year<={args.year_max} filter: {len(df):,} rows")

    if args.sample_regions is not None:
        # fe_group format is "<sign_letter><region>_<bin>"; recover region code
        region_series = df["fe_group"].str.replace(r"^[PN]", "", regex=True).str.replace(r"_-?\d+$", "", regex=True)
        unique_regions = region_series.unique()
        keep_regions = pd.Series(unique_regions).sample(
            n=min(args.sample_regions, len(unique_regions)),
            random_state=args.random_seed,
        ).tolist()
        df = df[region_series.isin(keep_regions)].reset_index(drop=True)
        log.info(f"After --sample-regions={args.sample_regions}: {len(df):,} rows, {len(keep_regions)} regions")

    results = []

    log.info("=" * 70)
    log.info(f"Running pyfixest (tolerance={args.tol:.0e})")
    log.info("=" * 70)
    try:
        results.append(run_pyfixest(df, tol=args.tol))
    except Exception as e:
        log.error(f"pyfixest failed: {e}")

    if not args.skip_r:
        log.info("=" * 70)
        log.info(f"Running R fixest (Rscript={args.rscript}, threads={args.r_threads}, tolerance={args.tol:.0e})")
        log.info("=" * 70)
        try:
            results.append(run_fixest_r(df, r_threads=args.r_threads,
                                        rscript_path=args.rscript, tol=args.tol))
        except FileNotFoundError:
            log.error(f"Rscript binary not found at '{args.rscript}'. On Midway3: module load R")
        except Exception as e:
            log.error(f"R fixest failed: {e}")

    # Summary
    log.info("=" * 70)
    log.info("Summary")
    log.info("=" * 70)

    if not results:
        log.error("No engines completed successfully")
        sys.exit(1)

    header = f"{'engine':<10}  {'gamma':>12}  {'SE (cluster)':>14}  {'R^2':>8}  {'elapsed (s)':>12}"
    print("\n" + header)
    print("-" * len(header))
    for r in results:
        gm = r.get("gamma")
        se = r.get("gamma_se_clustered")
        r2 = r.get("r_squared")
        el = r.get("elapsed_sec")
        gm_s = f"{gm:.6f}" if gm is not None else "   n/a    "
        se_s = f"{se:.6e}" if se is not None else "    n/a      "
        r2_s = f"{r2:.4f}" if r2 is not None else "  n/a "
        el_s = f"{el:.2f}" if el is not None else "  n/a "
        print(f"{r['engine']:<10}  {gm_s:>12}  {se_s:>14}  {r2_s:>8}  {el_s:>12}")
    print()

    comparison = {
        "input": args.input,
        "y_column": args.y,
        "n_rows_prepped": int(len(df)),
        "n_fe_groups": int(df["fe_group"].nunique()),
        "n_years": int(df["year"].nunique()),
        "bin_width": args.bin_width,
        "trim_pct": args.trim_pct,
        "results": results,
    }

    if len(results) >= 2:
        py = next((r for r in results if r["engine"] == "pyfixest"), None)
        rf = next((r for r in results if r["engine"] == "fixest"), None)
        if py and rf:
            d_gamma = rf["gamma"] - py["gamma"]
            d_se = rf["gamma_se_clustered"] - py["gamma_se_clustered"]
            speedup = py["elapsed_sec"] / rf["elapsed_sec"] if rf["elapsed_sec"] > 0 else float("inf")
            print(f"Delta gamma (R - py): {d_gamma:+.2e}")
            print(f"Delta SE (R - py):    {d_se:+.2e}")
            print(f"Speedup (py / R):     {speedup:.1f}x")
            comparison["delta_gamma"] = d_gamma
            comparison["delta_se"] = d_se
            comparison["speedup_py_over_r"] = speedup

    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(comparison, f, indent=2, default=str)
        log.info(f"Comparison saved to {out}")


if __name__ == "__main__":
    main()
