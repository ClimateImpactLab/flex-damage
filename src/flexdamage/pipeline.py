"""
FlexDamage Pipeline Orchestrator.

Coordinates the full estimation pipeline:
1. Standardize source → temp parquet (ONCE)
2. Load standardized parquet into DuckDB
3. Estimate gamma (sequential, uses all cores via DuckDB)
4. Parallel: for each gamma quantile → regional + errors
5. Export parameters
6. Cleanup temp files

Key design:
- Workers communicate via parquet files
- DuckDB connections are per-process (never shared)
- Standardization happens ONCE in main process
"""

import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import duckdb
import pandas as pd

from .build.standardize import standardize
from .config import RunConfig, load_config
from .estimation.errors import compute_all_error_terms
from .estimation.gamma import estimate_gamma
from .estimation.regional import fit_regional_polynomials
from .export.parameters import export_parameters

logger = logging.getLogger(__name__)


@contextmanager
def timer(name: str, log: logging.Logger):
    """Context manager for timing code blocks."""
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    log.info(f"{name}: {elapsed:.2f}s")


def _get_available_memory_gb() -> float:
    """Get available system memory in GB."""
    try:
        import psutil
        return psutil.virtual_memory().available / (1024**3)
    except ImportError:
        return 32.0  # Conservative default


def _compute_optimal_workers(
    n_quantiles: int,
    config_workers: int,
    config_memory_limit_gb: float,
    memory_per_worker_gb: float,
) -> Tuple[int, int, float]:
    """
    Compute optimal number of workers based on resources.

    Args:
        n_quantiles: Number of gamma quantiles to process
        config_workers: Configured workers (0 = auto)
        config_memory_limit_gb: Total memory limit
        memory_per_worker_gb: Memory per worker

    Returns:
        (n_workers, threads_per_worker, memory_per_worker)
    """
    total_cores = os.cpu_count() or 1
    available_memory = min(_get_available_memory_gb(), config_memory_limit_gb)

    if config_workers == 0:
        # AUTO MODE: balance cores, memory, and work
        max_by_memory = max(1, int(available_memory / memory_per_worker_gb))
        max_by_cores = total_cores
        max_by_quantiles = n_quantiles

        n_workers = min(max_by_memory, max_by_cores, max_by_quantiles)
    else:
        # MANUAL MODE: respect config, but cap at resources
        n_workers = min(config_workers, total_cores, n_quantiles)

    # Compute threads per worker
    threads_per_worker = max(1, total_cores // n_workers)

    # Compute actual memory per worker
    actual_memory = available_memory / n_workers

    logger.info(
        f"Workers: {n_workers} (threads={threads_per_worker}/worker, "
        f"memory={actual_memory:.1f}GB/worker)"
    )

    return n_workers, threads_per_worker, actual_memory


class FlexDamagePipeline:
    """
    Main pipeline orchestrator for flexible damage function estimation.

    Coordinates the full estimation pipeline:
    1. Standardize source data to fixed parquet format
    2. Estimate global income elasticity (gamma)
    3. Fit regional polynomials for each gamma quantile
    4. Compute error structure parameters
    5. Export results to CSV and JSON

    Parameters
    ----------
    config_path : str or Path
        Path to YAML configuration file.

    Attributes
    ----------
    config : RunConfig
        Validated configuration object.
    config_path : Path
        Path to the configuration file.

    Examples
    --------
    >>> pipeline = FlexDamagePipeline("configs/agriculture_corn.yaml")
    >>> result = pipeline.run()
    >>> print(f"Gamma: {result['gamma']:.4f}")
    """

    def __init__(self, config_path: Union[str, Path]):
        """
        Initialize pipeline from config file.

        Parameters
        ----------
        config_path : str or Path
            Path to YAML configuration file.
        """
        self.config_path = Path(config_path)
        self.config = load_config(config_path)
        self.std_parquet: Optional[str] = None

    def run(self) -> Dict:
        """
        Execute full estimation pipeline.

        Runs the complete estimation workflow:
        1. Standardize input data
        2. Estimate gamma via fixed-effects regression
        3. Fit regional polynomials for each gamma quantile
        4. Compute error terms (rho, zeta, eta)
        5. Export parameters to CSV and JSON

        Returns
        -------
        dict
            Summary dictionary containing:

            - gamma : float - Point estimate of income elasticity
            - gamma_se : float - Standard error of gamma
            - n_regions : int - Number of regions processed
            - n_observations : int - Total observations
            - output_csv : str - Path to output CSV file
            - output_json : str - Path to global results JSON
            - timings : dict - Timing for each pipeline stage
        """
        summary = {
            "config": str(self.config_path),
            "run_name": self.config.run.name,
            "timings": {},
        }

        total_start = time.perf_counter()

        try:
            # Step 1: Standardize source data
            with timer("Standardize", logger):
                start = time.perf_counter()
                self.std_parquet = standardize(self.config)
                summary["timings"]["standardize"] = time.perf_counter() - start

            # Step 2: Load into DuckDB for gamma estimation
            con = duckdb.connect()
            n_threads = os.cpu_count() or 1
            con.execute(f"SET threads = {n_threads}")

            try:
                con.execute(f"""
                    CREATE VIEW standardized AS
                    SELECT * FROM read_parquet('{self.std_parquet}')
                """)

                stats = con.execute("""
                    SELECT COUNT(*), COUNT(DISTINCT region)
                    FROM standardized
                """).fetchone()

                summary["n_observations"] = stats[0]
                summary["n_regions"] = stats[1]
                logger.info(f"Loaded: {stats[0]:,} observations, {stats[1]:,} regions")

                # Step 3: Gamma estimation (sequential, DuckDB uses all cores)
                with timer("Gamma estimation", logger):
                    start = time.perf_counter()
                    global_results = estimate_gamma(con, self.config)
                    summary["timings"]["gamma"] = time.perf_counter() - start

                gamma_quantiles = global_results["gamma_quantiles"]
                summary["gamma"] = global_results["gamma"]
                summary["gamma_se"] = global_results["gamma_se"]
                summary["n_quantiles"] = len(gamma_quantiles)

            finally:
                con.close()

            # Step 4-5: Parallel regional estimation
            n_workers, threads_per_worker, memory_per_worker = _compute_optimal_workers(
                n_quantiles=len(gamma_quantiles),
                config_workers=self.config.execution.workers,
                config_memory_limit_gb=self.config.execution.memory_limit_gb,
                memory_per_worker_gb=self.config.execution.memory_per_worker_gb,
            )

            with timer(f"Regional estimation ({len(gamma_quantiles)} quantiles)", logger):
                start = time.perf_counter()
                if n_workers > 1:
                    all_regional = self._run_parallel(
                        gamma_quantiles, n_workers, threads_per_worker, memory_per_worker
                    )
                else:
                    all_regional = self._run_sequential(gamma_quantiles)
                summary["timings"]["regional"] = time.perf_counter() - start

            # Combine results
            regional_results = pd.concat(all_regional, ignore_index=True)
            summary["n_parameter_rows"] = len(regional_results)

            # Step 6: Export
            with timer("Export", logger):
                start = time.perf_counter()
                output_paths = export_parameters(
                    regional_results, global_results, self.config
                )
                summary["timings"]["export"] = time.perf_counter() - start
                summary["output_csv"] = str(output_paths["csv"])
                summary["output_json"] = str(output_paths["json"])

        finally:
            # Step 7: Cleanup
            if self.std_parquet and Path(self.std_parquet).exists():
                Path(self.std_parquet).unlink()
                logger.debug(f"Cleaned up temp parquet: {self.std_parquet}")

        summary["timings"]["total"] = time.perf_counter() - total_start
        summary["status"] = "success"

        # Log summary
        logger.info("=" * 60)
        logger.info(f"Pipeline complete: {self.config.run.name}")
        logger.info(f"  Total time: {summary['timings']['total']:.2f}s")
        logger.info(f"  Observations: {summary['n_observations']:,}")
        logger.info(f"  Regions: {summary['n_regions']:,}")
        logger.info(f"  Gamma: {summary['gamma']:.6f} ± {summary['gamma_se']:.6f}")
        logger.info(f"  Output: {summary['output_csv']}")
        logger.info("=" * 60)

        return summary

    def _run_sequential(self, gamma_quantiles: List[float]) -> List[pd.DataFrame]:
        """Run quantiles sequentially (for single-worker mode)."""
        results = []

        con = duckdb.connect()
        n_threads = os.cpu_count() or 1
        con.execute(f"SET threads = {n_threads}")

        try:
            con.execute(f"""
                CREATE VIEW standardized AS
                SELECT * FROM read_parquet('{self.std_parquet}')
            """)

            for i, gamma_q in enumerate(gamma_quantiles):
                logger.info(f"Processing quantile {i+1}/{len(gamma_quantiles)}: gamma={gamma_q:.6f}")

                # Fit regional polynomials
                regional = fit_regional_polynomials(con, gamma_q, self.config)

                if not regional.empty:
                    # Compute error terms
                    errors = compute_all_error_terms(con, regional, gamma_q, self.config)

                    # Merge
                    regional = regional.merge(errors, on="region", how="left")

                results.append(regional)

        finally:
            con.close()

        return results

    def _run_parallel(
        self,
        gamma_quantiles: List[float],
        n_workers: int,
        threads_per_worker: int,
        memory_per_worker: float,
    ) -> List[pd.DataFrame]:
        """Run quantiles in parallel using ProcessPoolExecutor."""
        # Prepare arguments for workers
        # Workers need: parquet path, gamma value, config dict, resources
        config_dict = self.config.model_dump()

        args_list = [
            (self.std_parquet, gamma_q, config_dict, threads_per_worker, memory_per_worker)
            for gamma_q in gamma_quantiles
        ]

        results = [None] * len(gamma_quantiles)

        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            futures = {
                executor.submit(_process_quantile, args): i
                for i, args in enumerate(args_list)
            }

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    result = future.result()
                    results[idx] = result
                    logger.debug(f"Completed quantile {idx+1}/{len(gamma_quantiles)}")
                except Exception as e:
                    logger.error(f"Worker failed for quantile {idx}: {e}")
                    # Return empty DataFrame for failed quantile
                    results[idx] = pd.DataFrame()

        return results


def _process_quantile(args: Tuple) -> pd.DataFrame:
    """
    Process a single gamma quantile (worker function).

    This runs in a separate process. Each worker:
    1. Creates its own DuckDB connection
    2. Reads the standardized parquet (lazy, instant)
    3. Fits regional polynomials
    4. Computes error terms
    5. Returns merged DataFrame

    Args:
        args: (std_parquet, gamma_q, config_dict, threads, memory_gb)

    Returns:
        DataFrame with regional parameters + error terms
    """
    std_parquet, gamma_q, config_dict, threads, memory_gb = args

    # Reconstruct config from dict
    config = RunConfig.model_validate(config_dict)

    # Create DuckDB connection (per-process!)
    con = duckdb.connect()
    con.execute(f"SET threads = {threads}")
    con.execute(f"SET memory_limit = '{memory_gb:.1f}GB'")

    try:
        # Read standardized parquet (lazy, instant)
        con.execute(f"""
            CREATE VIEW standardized AS
            SELECT * FROM read_parquet('{std_parquet}')
        """)

        # Fit regional polynomials
        regional = fit_regional_polynomials(con, gamma_q, config)

        if regional.empty:
            return regional

        # Compute ALL error terms
        errors = compute_all_error_terms(con, regional, gamma_q, config)

        # Merge
        regional = regional.merge(errors, on="region", how="left")

        return regional

    finally:
        con.close()


def run_pipeline(config_path: Union[str, Path]) -> Dict:
    """
    Convenience function to run pipeline from config path.

    Parameters
    ----------
    config_path : str or Path
        Path to YAML configuration file.

    Returns
    -------
    dict
        Summary dictionary with gamma, timings, and output paths.

    Examples
    --------
    >>> result = run_pipeline("configs/agriculture_corn.yaml")
    >>> print(f"Output: {result['output_csv']}")
    """
    pipeline = FlexDamagePipeline(config_path)
    return pipeline.run()
