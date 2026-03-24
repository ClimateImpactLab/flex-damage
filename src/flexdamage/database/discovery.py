"""
Result discovery: Scan directories for estimation results in any format.

Finds:
- v3 parameter files: *.csv with 12-column schema
- v2 regional_results.csv + global_results.json
- v1 alphafit-*.csv from R
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)

# Expected columns for each format version
V3_COLUMNS = {"region", "gamma", "alpha", "beta", "sigma11", "sigma12", "sigma22",
              "rho", "zeta", "eta", "rsqr1", "rsqr2"}
V2_COLUMNS = {"region", "alpha", "beta", "sigma11", "sigma12", "sigma22",
              "rho", "zeta", "eta", "rsqr1", "rsqr2"}
V1_COLUMNS = {"region", "gamma", "alpha", "beta"}  # Minimal R output


def discover_results(
    input_dirs: Union[str, Path, List[Union[str, Path]]],
    recursive: bool = True,
) -> List[Dict]:
    """
    Scan directories for estimation results.

    Finds:
    - v3 parameter files: parameters/{sector}/*.csv
    - v2 regional_results.csv + global_results.json
    - v1 alphafit-*.csv from R

    Args:
        input_dirs: Directory or list of directories to scan
        recursive: Search recursively (default True)

    Returns:
        List of dicts with: path, format_version, sector, subsector,
        n_regions, n_gamma_quantiles, etc.
    """
    if isinstance(input_dirs, (str, Path)):
        input_dirs = [input_dirs]

    results = []

    for input_dir in input_dirs:
        input_dir = Path(input_dir)
        if not input_dir.exists():
            logger.warning(f"Directory not found: {input_dir}")
            continue

        # Find CSV files
        pattern = "**/*.csv" if recursive else "*.csv"
        for csv_path in input_dir.glob(pattern):
            result = _analyze_csv(csv_path)
            if result:
                results.append(result)

    logger.info(f"Discovered {len(results)} result files")
    return results


def _analyze_csv(path: Path) -> Optional[Dict]:
    """
    Analyze a CSV file to determine format and extract metadata.

    Returns None if file is not a recognized result format.
    """
    try:
        # Read just the header first
        df = pd.read_csv(path, nrows=0)
        columns = set(df.columns)

        # Detect format version
        if V3_COLUMNS.issubset(columns):
            version = "v3"
        elif V2_COLUMNS.issubset(columns) and "gamma" not in columns:
            version = "v2"
        elif V1_COLUMNS.issubset(columns):
            version = "v1"
        else:
            # Not a recognized result file
            return None

        # Read full file for stats
        df = pd.read_csv(path)

        # Extract metadata
        result = {
            "path": str(path),
            "format_version": version,
            "n_rows": len(df),
            "n_regions": df["region"].nunique() if "region" in df.columns else 0,
        }

        # Version-specific metadata
        if "gamma" in df.columns:
            result["n_gamma_quantiles"] = df["gamma"].nunique()
            result["gamma_min"] = float(df["gamma"].min())
            result["gamma_max"] = float(df["gamma"].max())
        else:
            result["n_gamma_quantiles"] = 0

        # Try to extract sector info from path or filename
        sector_info = _extract_sector_from_path(path)
        result.update(sector_info)

        # Check for companion metadata JSON
        json_path = path.with_suffix(".json")
        if not json_path.exists():
            json_path = path.parent / f"{path.stem}_metadata.json"
        if json_path.exists():
            result["metadata_path"] = str(json_path)
            try:
                with open(json_path) as f:
                    metadata = json.load(f)
                if "sector" in metadata:
                    result.update(metadata["sector"])
                if "global_results" in metadata:
                    result["gamma"] = metadata["global_results"].get("gamma")
            except Exception as e:
                logger.debug(f"Could not read metadata: {e}")

        return result

    except Exception as e:
        logger.debug(f"Could not analyze {path}: {e}")
        return None


def _extract_sector_from_path(path: Path) -> Dict:
    """
    Extract sector information from file path.

    Expected patterns:
    - .../agriculture/corn/...
    - agriculture_corn_physical_na.csv
    """
    result = {}

    # Try path components
    parts = path.parts
    for i, part in enumerate(parts):
        if part in ("agriculture", "mortality", "energy", "labor"):
            result["sector"] = part
            if i + 1 < len(parts):
                result["subsector"] = parts[i + 1]
            break

    # Try filename pattern: {sector}_{subsector}_{units}_{adaptation}.csv
    stem = path.stem
    if "_" in stem:
        filename_parts = stem.split("_")
        if len(filename_parts) >= 2:
            if filename_parts[0] in ("agriculture", "mortality", "energy", "labor"):
                result["sector"] = filename_parts[0]
                result["subsector"] = filename_parts[1]
            if len(filename_parts) >= 3:
                result["units"] = filename_parts[2]
            if len(filename_parts) >= 4:
                result["adaptation"] = filename_parts[3]

    return result


def find_companion_files(csv_path: Union[str, Path]) -> Dict[str, Path]:
    """
    Find companion files for a result CSV.

    Looks for:
    - *_metadata.json
    - global_results.json (v2)
    - Diagnostic PNGs in sibling directories

    Args:
        csv_path: Path to result CSV

    Returns:
        Dict with file types as keys and paths as values
    """
    csv_path = Path(csv_path)
    companions = {}

    # Metadata JSON
    for pattern in [
        csv_path.with_suffix(".json"),
        csv_path.parent / f"{csv_path.stem}_metadata.json",
        csv_path.parent / "metadata.json",
    ]:
        if pattern.exists():
            companions["metadata"] = pattern
            break

    # v2 global results
    global_json = csv_path.parent / "global_results.json"
    if global_json.exists():
        companions["global_results"] = global_json

    # Diagnostics directory
    for diag_dir in [
        csv_path.parent / "diagnostics",
        csv_path.parent.parent / "diagnostics",
    ]:
        if diag_dir.is_dir():
            companions["diagnostics_dir"] = diag_dir
            break

    # Maps directory
    for maps_dir in [
        csv_path.parent / "maps",
        csv_path.parent.parent / "maps",
    ]:
        if maps_dir.is_dir():
            companions["maps_dir"] = maps_dir
            break

    return companions
