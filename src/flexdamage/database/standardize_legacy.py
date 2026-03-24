"""
Legacy format standardization: Convert v1/v2 results to v3 schema.

Handles:
- v1 (R alphafit): has gamma per row, different column order
- v2 (old Python): missing gamma column, has intercept, has s2
- v3 (new): already correct format

Output: 12 columns exactly:
region, gamma, alpha, beta, sigma11, sigma12, sigma22,
rho, zeta, eta, rsqr1, rsqr2
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)

# Standard column order for v3 output
V3_COLUMNS = [
    "region", "gamma", "alpha", "beta",
    "sigma11", "sigma12", "sigma22",
    "rho", "zeta", "eta", "rsqr1", "rsqr2"
]


def standardize_to_v3(
    result_info: Dict,
    output_dir: Path,
) -> Path:
    """
    Convert any result format to v3 standardized 12-column CSV.

    Args:
        result_info: Dict from discover_results() with path, format_version, etc.
        output_dir: Directory to write standardized output

    Returns:
        Path to standardized CSV file
    """
    input_path = Path(result_info["path"])
    format_version = result_info.get("format_version", "unknown")

    logger.info(f"Standardizing {input_path} (format: {format_version})")

    # Read input
    df = pd.read_csv(input_path)

    # Convert based on version
    if format_version == "v3":
        df_out = _standardize_v3(df)
    elif format_version == "v2":
        df_out = _standardize_v2(df, result_info)
    elif format_version == "v1":
        df_out = _standardize_v1(df)
    else:
        raise ValueError(f"Unknown format version: {format_version}")

    # Generate output filename
    sector = result_info.get("sector", "unknown")
    subsector = result_info.get("subsector", "unknown")
    units = result_info.get("units", "physical")
    adaptation = result_info.get("adaptation", "na")

    output_name = f"{sector}_{subsector}_{units}_{adaptation}.csv"
    output_path = output_dir / output_name

    # Write output
    output_dir.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(output_path, index=False, float_format="%.10g")

    logger.info(f"Wrote standardized output: {output_path} ({len(df_out)} rows)")

    return output_path


def _standardize_v3(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize v3 format (already correct, just ensure column order).
    """
    # Fill any missing columns with 0
    for col in V3_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0

    return df[V3_COLUMNS].copy()


def _standardize_v2(df: pd.DataFrame, result_info: Dict) -> pd.DataFrame:
    """
    Standardize v2 format (missing gamma column).

    v2 has one row per region (no gamma quantiles).
    Need to get gamma from companion global_results.json.
    """
    # Try to get gamma from metadata
    gamma = None

    if "metadata_path" in result_info:
        try:
            with open(result_info["metadata_path"]) as f:
                metadata = json.load(f)
            gamma = metadata.get("global_results", {}).get("gamma")
        except Exception:
            pass

    # Try global_results.json in same directory
    if gamma is None:
        global_json = Path(result_info["path"]).parent / "global_results.json"
        if global_json.exists():
            try:
                with open(global_json) as f:
                    global_results = json.load(f)
                gamma = global_results.get("gamma")
            except Exception:
                pass

    if gamma is None:
        logger.warning(f"Could not find gamma for v2 file, using 0.0")
        gamma = 0.0

    # Add gamma column
    df_out = df.copy()
    df_out["gamma"] = gamma

    # Rename columns if needed
    column_map = {
        "rsqr": "rsqr1",  # Old name for rsqr1
    }
    df_out = df_out.rename(columns=column_map)

    # Fill missing columns
    for col in V3_COLUMNS:
        if col not in df_out.columns:
            df_out[col] = 0.0

    return df_out[V3_COLUMNS].copy()


def _standardize_v1(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize v1 format (R alphafit output).

    v1 has gamma per row but may have different column names.
    """
    df_out = df.copy()

    # Common R column name mappings
    column_map = {
        "tas.preind": "T",  # Temperature variable name in R
        "coef.alpha": "alpha",
        "coef.beta": "beta",
        "se.alpha": "sigma11",  # May need sqrt transform
        "se.beta": "sigma22",
    }

    df_out = df_out.rename(columns=column_map)

    # Fill missing columns
    for col in V3_COLUMNS:
        if col not in df_out.columns:
            df_out[col] = 0.0

    return df_out[V3_COLUMNS].copy()


def validate_v3_output(path: Path) -> bool:
    """
    Validate that a CSV file conforms to v3 schema.

    Args:
        path: Path to CSV file

    Returns:
        True if valid, False otherwise
    """
    try:
        df = pd.read_csv(path)

        # Check all required columns exist
        missing = set(V3_COLUMNS) - set(df.columns)
        if missing:
            logger.error(f"Missing columns: {missing}")
            return False

        # Check no unexpected columns
        extra = set(df.columns) - set(V3_COLUMNS)
        if extra:
            logger.warning(f"Extra columns (will be ignored): {extra}")

        # Check data types
        for col in ["gamma", "alpha", "beta", "sigma11", "sigma12", "sigma22",
                    "rho", "zeta", "eta", "rsqr1", "rsqr2"]:
            if not pd.api.types.is_numeric_dtype(df[col]):
                logger.error(f"Column {col} is not numeric")
                return False

        # Check value ranges
        if (df["rsqr1"] < 0).any() or (df["rsqr1"] > 1).any():
            logger.warning("rsqr1 values outside [0, 1] range")

        if (df["rsqr2"] < 0).any() or (df["rsqr2"] > 1).any():
            logger.warning("rsqr2 values outside [0, 1] range")

        if (df["rho"] < -1).any() or (df["rho"] > 1).any():
            logger.warning("rho values outside [-1, 1] range")

        return True

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return False
