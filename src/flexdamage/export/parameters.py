"""
Parameter export: Regional results to standardized CSV + JSON files.

Output files (per sector/subsector):
    {sector}__{subsector}__regional_parameters.csv   12-column parameter file
    {sector}__{subsector}__global_results.json       gamma estimation results
    {sector}__{subsector}__metadata.json             run configuration and statistics

CSV format (12 columns, one row per region x gamma quantile):
    region      : VARCHAR   region identifier
    gamma       : DOUBLE    gamma quantile value used
    alpha       : DOUBLE    linear temperature coefficient
    beta        : DOUBLE    quadratic temperature coefficient
    sigma11     : DOUBLE    variance of alpha
    sigma12     : DOUBLE    covariance of alpha, beta
    sigma22     : DOUBLE    variance of beta
    rho         : DOUBLE    correlation with global residuals
    zeta        : DOUBLE    slope of |residuals| vs T
    eta         : DOUBLE    std dev of residual noise
    rsqr1       : DOUBLE    R^2 of regional polynomial fit
    rsqr2       : DOUBLE    R^2 of error term fit
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd

from ..config import RunConfig

logger = logging.getLogger(__name__)

# Standard column order for output CSV
PARAMETER_COLUMNS = [
    "region",
    "gamma",
    "alpha",
    "beta",
    "sigma11",
    "sigma12",
    "sigma22",
    "rho",
    "zeta",
    "eta",
    "rsqr1",
    "rsqr2",
]


def export_parameters(
    regional_results: pd.DataFrame,
    global_results: Dict,
    config: RunConfig,
    output_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Path]:
    """
    Export estimation results to standardized CSV and JSON files.

    Creates three output files:

    - ``{sector}__{subsector}__regional_parameters.csv`` - 12-column parameter file
    - ``{sector}__{subsector}__global_results.json`` - Gamma estimation results
    - ``{sector}__{subsector}__metadata.json`` - Run configuration and statistics

    Parameters
    ----------
    regional_results : pandas.DataFrame
        Regional parameters for all gamma quantiles.
    global_results : dict
        Global estimation results from estimate_gamma().
    config : RunConfig
        Pipeline configuration.
    output_dir : str or Path, optional
        Output directory. Defaults to config.output.parameters_dir.

    Returns
    -------
    dict
        Paths to output files:

        - csv : Path - Regional parameters CSV
        - global_json : Path - Global results JSON
        - metadata_json : Path - Run metadata JSON
    """
    if output_dir is None:
        output_dir = Path(config.output.parameters_dir)
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate output filename base: sector__subsector
    filename_base = config.output_filename_base

    # Define paths
    csv_path = output_dir / f"{filename_base}__regional_parameters.csv"
    global_json_path = output_dir / f"{filename_base}__global_results.json"
    metadata_json_path = output_dir / f"{filename_base}__metadata.json"

    # Ensure all required columns exist
    df = regional_results.copy()

    for col in PARAMETER_COLUMNS:
        if col not in df.columns:
            if col == "gamma":
                logger.warning(f"Missing column '{col}', filling with 0.0")
            df[col] = 0.0

    # Select and order columns
    df = df[PARAMETER_COLUMNS]

    # Write CSV
    df.to_csv(csv_path, index=False, float_format="%.10g")

    n_regions = df["region"].nunique()
    n_quantiles = df["gamma"].nunique()
    n_rows = len(df)

    logger.info(f"Exported {n_rows} rows ({n_regions} regions × {n_quantiles} quantiles) to {csv_path}")

    # Write global results JSON
    global_results_data = {
        "gamma": global_results.get("gamma"),
        "gamma_se": global_results.get("gamma_se"),
        "gamma_se_iid": global_results.get("gamma_se_iid"),
        "gamma_se_hc1": global_results.get("gamma_se_hc1"),
        "gamma_se_clustered": global_results.get("gamma_se_clustered"),
        "r_squared": global_results.get("r_squared"),
        "n_obs": global_results.get("n_obs"),
        "n_fe_groups": global_results.get("n_fe_groups"),
        "gamma_quantiles": global_results.get("gamma_quantiles", []),
    }

    with open(global_json_path, "w") as f:
        json.dump(global_results_data, f, indent=2, default=str)

    logger.info(f"Exported global results to {global_json_path}")

    # Prepare metadata
    metadata = {
        "flexdamage_version": "1.0.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "run": {
            "name": config.run.name,
            "description": config.run.description,
        },
        "sector": config.sector.model_dump(exclude_none=True),
        "estimation": {
            "formula": config.estimation.formula,
            "gamma_method": config.estimation.gamma.method,
            "temperature_bins": config.estimation.gamma.temperature_bins,
            "n_quantiles": config.estimation.gamma.n_quantiles,
            "min_observations": config.estimation.regional.min_observations,
            "constraints": [
                {"parameter": c.parameter, "type": c.type, "value": c.value}
                for c in config.estimation.constraints
            ],
        },
        "output_stats": {
            "n_regions": n_regions,
            "n_gamma_quantiles": n_quantiles,
            "n_rows": n_rows,
        },
        "summary_statistics": _compute_summary_stats(df),
    }

    # Write metadata JSON
    with open(metadata_json_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)

    logger.info(f"Exported metadata to {metadata_json_path}")

    return {
        "csv": csv_path,
        "global_json": global_json_path,
        "metadata_json": metadata_json_path,
    }


def _compute_summary_stats(df: pd.DataFrame) -> Dict:
    """
    Compute summary statistics for parameter distributions.

    Returns dict with mean, median, std, min, max for key parameters.
    """
    stats = {}

    for col in ["alpha", "beta", "rho", "zeta", "eta", "rsqr1", "rsqr2"]:
        if col in df.columns:
            s = df[col].dropna()
            if len(s) > 0:
                stats[col] = {
                    "mean": float(s.mean()),
                    "median": float(s.median()),
                    "std": float(s.std()),
                    "min": float(s.min()),
                    "max": float(s.max()),
                    "n_valid": int(len(s)),
                }

    return stats


def load_parameters(path: Union[str, Path]) -> pd.DataFrame:
    """
    Load parameter CSV file.

    Args:
        path: Path to parameter CSV

    Returns:
        DataFrame with 12 columns
    """
    df = pd.read_csv(path)

    # Validate columns
    missing = set(PARAMETER_COLUMNS) - set(df.columns)
    if missing:
        logger.warning(f"Missing columns in {path}: {missing}")

    return df


def load_global_results(path: Union[str, Path]) -> Dict:
    """
    Load global results JSON file.

    Args:
        path: Path to global results JSON

    Returns:
        Global results dict with gamma, gamma_se, r_squared, etc.
    """
    with open(path, "r") as f:
        return json.load(f)


def load_metadata(path: Union[str, Path]) -> Dict:
    """
    Load metadata JSON file.

    Args:
        path: Path to metadata JSON

    Returns:
        Metadata dict
    """
    with open(path, "r") as f:
        return json.load(f)


def extract_global_results_from_metadata(metadata_path: Union[str, Path]) -> Dict:
    """
    Extract global results from old-format metadata JSON.

    Used for migrating old files that embedded global_results in metadata.

    Args:
        metadata_path: Path to old metadata JSON

    Returns:
        Global results dict
    """
    metadata = load_metadata(metadata_path)

    # Old format had global_results embedded in metadata
    if "global_results" in metadata:
        gr = metadata["global_results"]
        return {
            "gamma": gr.get("gamma"),
            "gamma_se": gr.get("gamma_se"),
            "gamma_se_iid": gr.get("gamma_se_iid"),
            "gamma_se_hc1": gr.get("gamma_se_hc1"),
            "gamma_se_clustered": gr.get("gamma_se_clustered"),
            "r_squared": gr.get("r_squared"),
            "n_obs": gr.get("n_obs"),
            "n_fe_groups": gr.get("n_fe_groups"),
            "gamma_quantiles": [],  # Old format didn't save quantiles
        }

    return {}
