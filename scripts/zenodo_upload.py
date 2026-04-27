#!/usr/bin/env python3
"""
Upload FlexDamage parameter database to Zenodo.

Creates a professional release with:
- README.md (visible on Zenodo page)
- manifest.json (machine-readable index)
- flexdamage-parameters-v{version}.zip (organized data)

Usage:
    # Build the ZIP with proper structure
    python scripts/zenodo_upload.py --build \
        --input-dir /path/to/parameters --version 1.0.0-alpha

    # Dry run (preview what would be uploaded)
    python scripts/zenodo_upload.py --sandbox --dry-run --version 1.0.0-alpha

    # Upload to sandbox as draft
    python scripts/zenodo_upload.py --sandbox --draft --version 1.0.0-alpha

    # Publish
    python scripts/zenodo_upload.py --sandbox --publish

    # Delete a draft
    python scripts/zenodo_upload.py --sandbox --delete 473052
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

def _load_env():
    """Load .env file for API tokens."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().strip().split('\n'):
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

_load_env()

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flexdamage.utils import setup_logging

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

logger = logging.getLogger("zenodo_upload")

ZENODO_URL = "https://zenodo.org/api"
ZENODO_SANDBOX_URL = "https://sandbox.zenodo.org/api"
ZENODO_STATE_FILE = ".zenodo.json"

# Impact Regions shapefile (included in Zenodo ZIP)
IR_SHAPEFILE = Path("/project/cil/sacagawea_shares/gcp/climate/_spatial_data/world-combo-new-nytimes/new_shapefile.shp")

# Sector configurations (used for placeholder .gitkeep and sector READMEs;
# actual datasets are discovered from filenames via parse_input_filename).
SECTORS = {
    "agriculture": {
        "subsectors": ["corn", "rice", "soy", "sorghum", "cassava",
                       "wheat_combined", "wheat_spring", "wheat_winter"],
        "resolutions": ["ir"],
    },
    "agriculture_value": {
        "subsectors": ["combined_main_spec"],
        "resolutions": ["ir"],
    },
    "mortality": {
        "subsectors": ["allcause"],
        "resolutions": ["ir"],
    },
    "energy": {
        "subsectors": ["total", "electricity", "non_electricity"],
        "resolutions": ["ir"],
    },
    "labor": {
        "subsectors": ["combined", "high_risk", "low_risk"],
        "resolutions": ["ir"],
    },
}


def get_api_url(sandbox: bool) -> str:
    return ZENODO_SANDBOX_URL if sandbox else ZENODO_URL


def get_token(sandbox: bool) -> str:
    """Get API token from environment."""
    var_name = "ZENODO_SANDBOX_TOKEN" if sandbox else "ZENODO_TOKEN"
    token = os.environ.get(var_name)
    if not token:
        raise ValueError(
            f"Missing environment variable: {var_name}\n"
            f"Get your token from: {'sandbox.' if sandbox else ''}zenodo.org/account/settings/applications/"
        )
    return token


def load_state() -> dict:
    """Load persisted Zenodo state."""
    state_path = Path(ZENODO_STATE_FILE)
    if state_path.exists():
        with open(state_path) as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    """Save Zenodo state."""
    with open(ZENODO_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def compute_sha256(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_sha256_bytes(data: bytes) -> str:
    """Compute SHA256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()


def format_size(size_bytes: int) -> str:
    """Format file size for display."""
    if size_bytes >= 1_000_000_000:
        return f"{size_bytes / 1_000_000_000:.1f} GB"
    elif size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.1f} MB"
    elif size_bytes >= 1_000:
        return f"{size_bytes / 1_000:.1f} KB"
    else:
        return f"{size_bytes} B"


def parse_input_filename(filename: str) -> Optional[Tuple[str, str]]:
    """
    Parse input filename to extract sector and subsector.

    Handles both formats:
    - New: agriculture__corn__regional_parameters.csv
    - Old: agriculture_corn_physical.csv
    """
    stem = Path(filename).stem

    # New format: sector__subsector__filetype
    if "__" in stem:
        parts = stem.split("__")
        if len(parts) >= 2:
            return parts[0], parts[1]

    # Old format: sector_subsector_units[_metadata]
    if stem.endswith("_metadata"):
        stem = stem[:-9]

    parts = stem.split("_")
    if len(parts) >= 2 and parts[0] in SECTORS:
        # Handle multi-word subsectors
        if parts[0] == "agriculture" and len(parts) >= 3:
            if parts[1] == "wheat" and parts[2] in ("spring", "winter", "combined"):
                return parts[0], f"{parts[1]}_{parts[2]}"
        return parts[0], parts[1]

    return None


def collect_datasets(input_dir: Path) -> List[dict]:
    """
    Collect all datasets from input directory.

    Returns list of dataset info with paths to CSV, global_results, metadata.
    """
    datasets = []
    seen = set()

    # Find all CSV files
    for csv_path in sorted(input_dir.glob("*.csv")):
        parsed = parse_input_filename(csv_path.name)
        if not parsed:
            continue

        sector, subsector = parsed
        key = (sector, subsector)
        if key in seen:
            continue
        seen.add(key)

        # Find associated files
        stem = csv_path.stem

        # Try new format first
        if "__" in stem:
            base = "__".join(stem.split("__")[:2])
            global_path = input_dir / f"{base}__global_results.json"
            meta_path = input_dir / f"{base}__metadata.json"
        else:
            # Old format
            base = "_".join(stem.split("_")[:-1]) if "_physical" in stem else stem
            global_path = None  # Old format might not have separate global_results
            meta_path = input_dir / f"{base}_metadata.json"
            if not meta_path.exists():
                # Try with _physical suffix
                meta_path = input_dir / f"{stem}_metadata.json"

        # Load metadata to get stats
        n_regions = 0
        n_quantiles = 19
        gamma = None
        gamma_se = None
        r_squared = None
        n_obs = None

        if global_path and global_path.exists():
            with open(global_path) as f:
                gr = json.load(f)
            gamma = gr.get("gamma")
            gamma_se = gr.get("gamma_se")
            r_squared = gr.get("r_squared")
            n_obs = gr.get("n_obs")
        elif meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            if "global_results" in meta:
                gr = meta["global_results"]
                gamma = gr.get("gamma")
                gamma_se = gr.get("gamma_se")
                r_squared = gr.get("r_squared")
                n_obs = gr.get("n_obs")
            if "output_stats" in meta:
                n_regions = meta["output_stats"].get("n_regions", 0)
                n_quantiles = meta["output_stats"].get("n_gamma_quantiles", 19)

        datasets.append({
            "sector": sector,
            "subsector": subsector,
            "resolution": "ir",  # Default, can be extended
            "csv_path": csv_path,
            "global_path": global_path if global_path and global_path.exists() else None,
            "meta_path": meta_path if meta_path.exists() else None,
            "gamma": gamma,
            "gamma_se": gamma_se,
            "r_squared": r_squared,
            "n_obs": n_obs,
            "n_regions": n_regions,
            "n_quantiles": n_quantiles,
        })

    return datasets


def generate_readme(version: str, datasets: List[dict]) -> str:
    """Generate README.md content (pure ASCII only, no Unicode)."""

    return f"""# Flexible Damage Function Parameters for Climate Impact Assessment

Version {version}

## Abstract

Region-specific damage function parameters estimated from projected climate
impact data. A distinct emulation function is calibrated for each region,
with globally common income elasticities capturing the benefits of income-driven
adaptation. The damage function takes the form:

    M_it = (alpha_i * T_t + beta_i * T_t^2) * Y_it^gamma

where T is global mean temperature anomaly from pre-industrial (degrees C),
Y is GDP per capita, and gamma is the income elasticity. Parameters are
provided at impact region resolution with 19 gamma quantiles per region
for uncertainty propagation.

## File Organization

The archive contains sector-specific subdirectories organized by spatial
resolution:

    flexdamage-parameters-v{version}/
    |-- README.md
    |-- manifest.json
    |-- shapefiles/
    |   |-- impact_regions.shp
    |   |-- impact_regions.shx
    |   |-- impact_regions.dbf
    |   |-- impact_regions.prj
    |-- agriculture/
    |   |-- README.md
    |   |-- ir/
    |       |-- corn/
    |       |   |-- regional_parameters.csv
    |       |   |-- global_results.json
    |       |   |-- metadata.json
    |       |-- rice/
    |           |-- ...

## Shapefile

The shapefiles/ directory contains the Impact Regions shapefile for mapping
parameters to geographic locations. The 'hierid' field matches the 'region'
column in the parameter CSV files. Load with geopandas:

    import geopandas as gpd
    gdf = gpd.read_file("shapefiles/impact_regions.shp")

Each subsector directory contains three files:

1. regional_parameters.csv: Regional polynomial coefficients with 12 columns
   and 19 rows per region (one per gamma quantile).

2. global_results.json: Results from income elasticity estimation including
   point estimate, standard error, R-squared, sample size, and 19 quantile values.

3. metadata.json: Run configuration including estimation settings, constraint
   specifications, and summary statistics.

## Variable Definitions

Each row in the regional parameters file contains 12 fields: region identifies
the location, gamma is the income elasticity quantile, alpha and beta are the
linear and quadratic temperature coefficients. sigma11, sigma12, sigma22 form
the variance-covariance matrix of (alpha, beta). rho is the correlation with
global residuals. zeta and eta describe the temperature-dependent and residual
error scales. rsqr1 and rsqr2 measure the polynomial and error model fit.

## License

CC-BY-4.0

## Contact

Climate Impact Lab: https://github.com/ClimateImpactLab/flex-damage
"""


def generate_sector_readme(sector: str, datasets: List[dict]) -> str:
    """Generate sector-specific README.md content (pure ASCII only)."""

    sector_datasets = [d for d in datasets if d["sector"] == sector]
    if not sector_datasets:
        return ""

    # Sector-specific configurations
    sector_configs = {
        "agriculture": {
            "units": "log yield impact (dimensionless, relative to baseline)",
            "outcome": "Log change in crop yield relative to a no-climate-change baseline",
            "constraint": "beta <= 0 (concavity enforced, damages accelerate with warming)",
            "notes": [
                "Impacts are relative to historical climate baseline (1980-2010)",
                "Negative values indicate yield loss, positive values indicate gain",
            ],
        },
        "agriculture_value": {
            "units": "USD welfare cost per capita (DeltaWelfare = DeltaCS + DeltaPS)",
            "outcome": "Change in agricultural welfare (across all crops, main_spec)",
            "constraint": "beta <= 0 (concavity enforced)",
            "notes": [
                "Aggregated across rice, sorghum, cassava, soy, corn, wheat",
                "Negative values indicate welfare loss (paper's DeltaWelfare convention)",
                "Source: paper main_spec (eps_S=0.1, eps_D=-0.04, country markets, CO2 fert on)",
            ],
        },
        "mortality": {
            "units": "deaths per 100,000 population",
            "outcome": "Change in all-cause mortality rate from temperature exposure",
            "constraint": "beta >= 0 (convexity, U-shaped response with adaptation costs)",
            "notes": [
                "All-cause all-age mortality",
                "Full adaptation with costs (Carleton et al. 2022 convention)",
            ],
        },
        "energy": {
            "units": "kWh per capita (rebased to 2005 baseline)",
            "outcome": "Change in energy consumption from temperature deviation",
            "constraint": "beta >= 0 (convexity)",
            "notes": [
                "Three subsectors: total, electricity, non_electricity",
                "Positive values indicate more energy consumption",
                "Fulladapt scenario (main - histclim)",
            ],
        },
        "labor": {
            "units": "portion (fraction of labor productivity, rebased to 2005)",
            "outcome": "Change in labor productivity from heat exposure",
            "constraint": "beta <= 0 (concavity)",
            "notes": [
                "Three subsectors: combined, high_risk, low_risk",
                "Negative values indicate productivity loss",
                "Fulladapt scenario",
            ],
        },
    }

    config = sector_configs.get(sector, {
        "units": "sector-specific units",
        "outcome": "Sector-specific outcome measure",
        "constraint": "See metadata.json for details",
        "notes": [],
    })

    # Build subsector table
    rows = []
    for d in sorted(sector_datasets, key=lambda x: x["subsector"]):
        gamma = f"{d['gamma']:.4f}" if d.get("gamma") else "--"
        se = f"{d['gamma_se']:.4f}" if d.get("gamma_se") else "--"
        r2 = f"{d['r_squared']:.3f}" if d.get("r_squared") else "--"
        regions = f"{d['n_regions']:,}" if d.get("n_regions") else "--"
        quantiles = d.get("n_quantiles", 19)
        rows.append(
            f"| {d['subsector'].replace('_', ' ').title()} | {gamma} | {se} | "
            f"{regions} | {quantiles} | {r2} |"
        )

    subsector_table = "\n".join(rows)

    notes_text = "\n".join(f"- {note}" for note in config.get("notes", []))
    if not notes_text:
        notes_text = "- See metadata.json for sector-specific details"

    return f"""# {sector.title()} Sector Parameters

## Units

Outcome variable: {config['outcome']}

Units: {config['units']}

## Input Variables

- Temperature (T): Global mean temperature anomaly from pre-industrial
  (degrees Celsius)
- Income (Y): GDP per capita (2020 USD PPP)

## Constraint Applied

{config['constraint']}

## Subsectors

| Subsector | gamma | SE(gamma) | Regions | Quantiles | R^2 |
|-----------|-------|-----------|---------|-----------|-----|
{subsector_table}

## Notes

{notes_text}

## File Structure

Each subsector directory contains:

- regional_parameters.csv: 12 columns, 19 rows per region
- global_results.json: gamma estimate, SE, R-squared, quantiles
- metadata.json: run configuration and summary statistics

## Usage Example

    import pandas as pd

    # Load corn parameters
    df = pd.read_csv("ir/corn/regional_parameters.csv")

    # Filter to median gamma
    median_gamma = df["gamma"].median()
    df_med = df[abs(df["gamma"] - median_gamma) < 0.0001]

    # Compute impact for region USA.14.648 at T=3C, Y=$50,000
    row = df_med[df_med["region"] == "USA.14.648"].iloc[0]
    T, Y = 3.0, 50000
    M = (row["alpha"] * T + row["beta"] * T**2) * Y**row["gamma"]
    print(f"Impact: {{M:.4f}}")
"""


def generate_manifest(version: str, datasets: List[dict], zip_contents: List[dict]) -> dict:
    """Generate manifest.json."""

    manifest = {
        "version": version,
        "flexdamage_version": "1.0.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "description": "Flexible damage function parameters for climate impact assessment",
        "license": "CC-BY-4.0",
        "datasets": [],
        "files": [],
        "statistics": {
            "total_datasets": len(datasets),
            "total_files": len(zip_contents),
            "sectors": list(set(d["sector"] for d in datasets)),
        },
    }

    # Add dataset summaries
    for d in sorted(datasets, key=lambda x: (x["sector"], x["subsector"])):
        manifest["datasets"].append({
            "sector": d["sector"],
            "subsector": d["subsector"],
            "resolution": d["resolution"],
            "path": f"{d['sector']}/{d['resolution']}/{d['subsector']}/",
            "gamma": d.get("gamma"),
            "gamma_se": d.get("gamma_se"),
            "r_squared": d.get("r_squared"),
            "n_obs": d.get("n_obs"),
            "n_regions": d.get("n_regions"),
            "n_quantiles": d.get("n_quantiles"),
        })

    # Add file details
    for f in zip_contents:
        manifest["files"].append({
            "path": f["archive_path"],
            "size_bytes": f["size"],
            "sha256": f["sha256"],
            "sector": f.get("sector"),
            "subsector": f.get("subsector"),
            "filetype": f.get("filetype"),
        })

    return manifest


def build_zip(
    input_dir: Path,
    version: str,
    output_dir: Path,
    datasets: List[dict],
) -> Tuple[Path, List[dict], str]:
    """
    Build the structured ZIP file.

    Returns (zip_path, zip_contents, manifest_json).
    """
    zip_name = f"flexdamage-parameters-v{version}.zip"
    zip_path = output_dir / zip_name
    base_dir = f"flexdamage-parameters-v{version}"

    zip_contents = []

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add each dataset
        for d in datasets:
            sector = d["sector"]
            subsector = d["subsector"]
            resolution = d["resolution"]
            dir_path = f"{base_dir}/{sector}/{resolution}/{subsector}"

            # Add CSV
            if d["csv_path"]:
                archive_path = f"{dir_path}/regional_parameters.csv"
                content = d["csv_path"].read_bytes()
                zf.writestr(archive_path, content)
                zip_contents.append({
                    "archive_path": archive_path,
                    "size": len(content),
                    "sha256": compute_sha256_bytes(content),
                    "sector": sector,
                    "subsector": subsector,
                    "filetype": "regional_parameters",
                })

            # Add global_results.json
            if d["global_path"]:
                archive_path = f"{dir_path}/global_results.json"
                content = d["global_path"].read_bytes()
                zf.writestr(archive_path, content)
                zip_contents.append({
                    "archive_path": archive_path,
                    "size": len(content),
                    "sha256": compute_sha256_bytes(content),
                    "sector": sector,
                    "subsector": subsector,
                    "filetype": "global_results",
                })
            elif d["meta_path"]:
                # Extract global_results from metadata
                with open(d["meta_path"]) as f:
                    meta = json.load(f)
                if "global_results" in meta:
                    gr_content = json.dumps(meta["global_results"], indent=2).encode()
                    archive_path = f"{dir_path}/global_results.json"
                    zf.writestr(archive_path, gr_content)
                    zip_contents.append({
                        "archive_path": archive_path,
                        "size": len(gr_content),
                        "sha256": compute_sha256_bytes(gr_content),
                        "sector": sector,
                        "subsector": subsector,
                        "filetype": "global_results",
                    })

            # Add metadata.json
            if d["meta_path"]:
                archive_path = f"{dir_path}/metadata.json"
                content = d["meta_path"].read_bytes()
                zf.writestr(archive_path, content)
                zip_contents.append({
                    "archive_path": archive_path,
                    "size": len(content),
                    "sha256": compute_sha256_bytes(content),
                    "sector": sector,
                    "subsector": subsector,
                    "filetype": "metadata",
                })

        # Add per-sector README files
        sectors_with_data = set(d["sector"] for d in datasets)
        for sector in sectors_with_data:
            sector_readme = generate_sector_readme(sector, datasets)
            if sector_readme:
                readme_path = f"{base_dir}/{sector}/README.md"
                zf.writestr(readme_path, sector_readme)
                zip_contents.append({
                    "archive_path": readme_path,
                    "size": len(sector_readme),
                    "sha256": compute_sha256_bytes(sector_readme.encode()),
                    "sector": sector,
                    "subsector": None,
                    "filetype": "sector_readme",
                })

        # Add top-level README to ZIP
        top_readme = generate_readme(version, datasets)
        top_readme_path = f"{base_dir}/README.md"
        zf.writestr(top_readme_path, top_readme)
        zip_contents.append({
            "archive_path": top_readme_path,
            "size": len(top_readme),
            "sha256": compute_sha256_bytes(top_readme.encode()),
            "sector": None,
            "subsector": None,
            "filetype": "readme",
        })

        # Create empty placeholder directories for future sectors
        for sector, config in SECTORS.items():
            for res in config["resolutions"]:
                # Add .gitkeep to ensure directory exists in zip
                placeholder_path = f"{base_dir}/{sector}/{res}/.gitkeep"
                if not any(c["archive_path"].startswith(f"{base_dir}/{sector}/{res}/")
                          for c in zip_contents):
                    zf.writestr(placeholder_path, "")

        # Add Impact Regions shapefile
        shapefile_added = False
        if IR_SHAPEFILE.exists():
            shapefile_dir = IR_SHAPEFILE.parent
            shapefile_stem = IR_SHAPEFILE.stem
            shapefile_extensions = [".shp", ".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx"]
            for ext in shapefile_extensions:
                src_file = shapefile_dir / f"{shapefile_stem}{ext}"
                if src_file.exists():
                    archive_path = f"{base_dir}/shapefiles/impact_regions{ext}"
                    content = src_file.read_bytes()
                    zf.writestr(archive_path, content)
                    zip_contents.append({
                        "archive_path": archive_path,
                        "size": len(content),
                        "sha256": compute_sha256_bytes(content),
                        "sector": None,
                        "subsector": None,
                        "filetype": "shapefile",
                    })
                    shapefile_added = True
            logger.info(f"Added shapefile ({sum(1 for e in shapefile_extensions if (shapefile_dir / f'{shapefile_stem}{e}').exists())} files)")
        else:
            logger.warning(f"Shapefile not found: {IR_SHAPEFILE}")

        # Generate and add manifest.json inside zip
        manifest = generate_manifest(version, datasets, zip_contents)
        manifest_json = json.dumps(manifest, indent=2)
        manifest_path = f"{base_dir}/manifest.json"
        zf.writestr(manifest_path, manifest_json)
        zip_contents.append({
            "archive_path": manifest_path,
            "size": len(manifest_json),
            "sha256": compute_sha256_bytes(manifest_json.encode()),
            "sector": None,
            "subsector": None,
            "filetype": "manifest",
        })

    return zip_path, zip_contents, manifest_json


def build_zenodo_metadata(version: str, readme_content: str) -> dict:
    """Build Zenodo deposit metadata."""

    description = (
        "Region-specific damage function parameters estimated from projected "
        "climate impact data. A distinct emulation function is calibrated for "
        "each region, with globally common income elasticities capturing the "
        "benefits of income-driven adaptation. The damage function takes the "
        "form M_it = (alpha_i * T_t + beta_i * T_t^2) * Y_it^gamma, where T "
        "is global mean temperature anomaly from pre-industrial (degrees C), "
        "Y is GDP per capita, and gamma is the income elasticity. Parameters "
        "are provided at impact region resolution with 19 gamma quantiles per "
        "region for uncertainty propagation."
    )

    return {
        "title": "Flexible Damage Function Parameters for Climate Impact Assessment",
        "description": description,
        "upload_type": "dataset",
        "version": version,
        "access_right": "open",
        "license": "cc-by-4.0",
        "creators": [
            {"name": "Climate Impact Lab"}
        ],
        "keywords": [
            "climate change",
            "damage functions",
            "integrated assessment models",
            "social cost of carbon",
            "agriculture",
            "climate economics",
            "econometrics",
        ],
        "related_identifiers": [],
        "notes": "",
    }


# Zenodo API functions

def delete_deposit(token: str, api_url: str, deposit_id: int) -> bool:
    """Delete an existing draft deposit."""
    response = requests.delete(
        f"{api_url}/deposit/depositions/{deposit_id}",
        params={"access_token": token},
    )
    if response.status_code == 204:
        return True
    elif response.status_code == 404:
        return False
    else:
        response.raise_for_status()
        return False


def create_deposit(token: str, api_url: str, metadata: dict) -> dict:
    """Create a new deposit on Zenodo."""
    response = requests.post(
        f"{api_url}/deposit/depositions",
        params={"access_token": token},
        json={"metadata": metadata},
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()
    return response.json()


def create_new_version(token: str, api_url: str, parent_id: int) -> dict:
    """
    Create a new version of an existing PUBLISHED deposit, linked via concept DOI.

    Zenodo returns the new draft deposit object, including its bucket URL for
    uploading files. The new draft shares a concept DOI with `parent_id`, so
    once published, the concept DOI resolves to the latest version.
    """
    # Step 1: trigger newversion action on parent
    r = requests.post(
        f"{api_url}/deposit/depositions/{parent_id}/actions/newversion",
        params={"access_token": token},
    )
    r.raise_for_status()
    parent = r.json()
    # The new draft URL is in latest_draft
    draft_url = parent["links"]["latest_draft"]
    # Fetch it
    r2 = requests.get(draft_url, params={"access_token": token})
    r2.raise_for_status()
    draft = r2.json()
    # New drafts inherit the parent's files. Delete them so we can upload fresh.
    for f in draft.get("files", []):
        fid = f["id"]
        rd = requests.delete(
            f"{api_url}/deposit/depositions/{draft['id']}/files/{fid}",
            params={"access_token": token},
        )
        rd.raise_for_status()
    # Re-fetch to get an updated (empty-files) view
    r3 = requests.get(draft_url, params={"access_token": token})
    r3.raise_for_status()
    return r3.json()


def update_deposit_metadata(token: str, api_url: str, deposit_id: int, metadata: dict) -> dict:
    """Update metadata on an existing draft deposit."""
    r = requests.put(
        f"{api_url}/deposit/depositions/{deposit_id}",
        params={"access_token": token},
        json={"metadata": metadata},
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    return r.json()


def upload_file_to_bucket(token: str, bucket_url: str, filename: str, data: bytes) -> dict:
    """Upload a file to a deposit bucket."""
    response = requests.put(
        f"{bucket_url}/{filename}",
        params={"access_token": token},
        data=data,
    )
    response.raise_for_status()
    return response.json()


def upload_file_from_path(token: str, bucket_url: str, file_path: Path, filename: str) -> dict:
    """Upload a file from disk to a deposit bucket."""
    with open(file_path, "rb") as f:
        response = requests.put(
            f"{bucket_url}/{filename}",
            params={"access_token": token},
            data=f,
        )
    response.raise_for_status()
    return response.json()


def publish_deposit(token: str, api_url: str, deposit_id: int) -> dict:
    """Publish a deposit."""
    response = requests.post(
        f"{api_url}/deposit/depositions/{deposit_id}/actions/publish",
        params={"access_token": token},
    )
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(
        description="Upload FlexDamage parameters to Zenodo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Build ZIP only
    python scripts/zenodo_upload.py --build \\
        --input-dir /path/to/parameters --version 1.0.0-alpha

    # Preview upload
    python scripts/zenodo_upload.py --sandbox --dry-run --version 1.0.0-alpha \\
        --input-dir /path/to/parameters

    # Upload to sandbox
    python scripts/zenodo_upload.py --sandbox --draft --version 1.0.0-alpha \\
        --input-dir /path/to/parameters

    # Publish
    python scripts/zenodo_upload.py --sandbox --publish

    # Delete draft
    python scripts/zenodo_upload.py --sandbox --delete 473052
        """,
    )

    parser.add_argument("--sandbox", action="store_true",
                        help="Use Zenodo sandbox for testing")
    parser.add_argument("--build", action="store_true",
                        help="Build ZIP file only (no upload)")
    parser.add_argument("--draft", action="store_true",
                        help="Create/update draft without publishing")
    parser.add_argument("--publish", action="store_true",
                        help="Publish existing draft")
    parser.add_argument("--delete", type=int, metavar="ID",
                        help="Delete an existing draft deposit")
    parser.add_argument("--new-version-of", type=int, metavar="ID",
                        help="Create a new version linked to an existing published record. "
                             "Produces a draft that shares the concept DOI. Use with --draft.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be uploaded")
    parser.add_argument("--version", type=str,
                        help="Version string (e.g., 1.0.0-alpha)")
    parser.add_argument("--input-dir", type=str, default="./parameters",
                        help="Directory containing parameter files")
    parser.add_argument("--output-dir", type=str, default=".",
                        help="Directory to write ZIP file")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose logging")

    args = parser.parse_args()

    setup_logging(level=logging.INFO if args.verbose else logging.WARNING)
    logger.setLevel(logging.INFO)

    # Validate arguments
    if not any([args.build, args.draft, args.publish, args.delete, args.dry_run]):
        parser.error("Must specify --build, --draft, --publish, --delete, or --dry-run")

    if (args.build or args.draft or args.dry_run) and not args.version:
        parser.error("--version required")

    # Handle delete
    if args.delete:
        if not HAS_REQUESTS:
            logger.error("requests library required: pip install requests")
            sys.exit(1)

        api_url = get_api_url(args.sandbox)
        token = get_token(args.sandbox)

        logger.info(f"Deleting deposit {args.delete}...")
        if delete_deposit(token, api_url, args.delete):
            print(f"Deleted deposit {args.delete}")
            state = load_state()
            if state.get("deposit_id") == args.delete:
                state.pop("deposit_id", None)
                save_state(state)
        else:
            print(f"Deposit {args.delete} not found")
        return

    # Handle publish
    if args.publish:
        if not HAS_REQUESTS:
            logger.error("requests library required: pip install requests")
            sys.exit(1)

        state = load_state()
        if not state.get("deposit_id"):
            logger.error("No draft to publish. Run with --draft first.")
            sys.exit(1)

        api_url = get_api_url(args.sandbox)
        token = get_token(args.sandbox)
        deposit_id = state["deposit_id"]

        logger.info(f"Publishing deposit {deposit_id}...")
        result = publish_deposit(token, api_url, deposit_id)

        print("\n" + "=" * 70)
        print("Published!")
        print("=" * 70)
        print(f"  DOI: {result.get('doi')}")
        print(f"  URL: {result['links']['html']}")
        print("=" * 70)

        state.pop("deposit_id", None)
        save_state(state)
        return

    # For build, draft, dry-run: need input directory
    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        logger.error(f"Input directory not found: {input_dir}")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect datasets
    datasets = collect_datasets(input_dir)
    if not datasets:
        logger.error(f"No datasets found in {input_dir}")
        sys.exit(1)

    logger.info(f"Found {len(datasets)} datasets")

    # Generate README
    readme_content = generate_readme(args.version, datasets)

    # Build ZIP — skip if a fresh one already exists (saves ~2 min on re-runs).
    # "Fresh" means the zip exists AND is newer than every input CSV.
    expected_zip = output_dir / f"flexdamage-parameters-v{args.version}.zip"
    skip_build = False
    if expected_zip.exists() and not args.build:
        zip_mtime = expected_zip.stat().st_mtime
        newer_inputs = [d["csv_path"] for d in datasets
                        if d["csv_path"].stat().st_mtime > zip_mtime]
        if not newer_inputs:
            skip_build = True
            zip_path = expected_zip
            zip_size = zip_path.stat().st_size
            logger.info(f"Reusing existing ZIP: {zip_path} ({format_size(zip_size)})")
            # We still need zip_contents and manifest_json for Zenodo upload.
            # Rebuild the manifest by reading from the existing zip.
            zip_contents = []
            with zipfile.ZipFile(zip_path, "r") as zf:
                for name in zf.namelist():
                    info = zf.getinfo(name)
                    if not info.is_dir():
                        zip_contents.append({
                            "archive_path": name,
                            "size": info.file_size,
                            "sha256": None,  # not recomputing; draft upload doesn't need it
                            "sector": None,
                            "subsector": None,
                            "filetype": None,
                        })
                manifest_json = zf.read(f"flexdamage-parameters-v{args.version}/manifest.json").decode()

    if not skip_build:
        logger.info("Building ZIP file...")
        zip_path, zip_contents, manifest_json = build_zip(
            input_dir, args.version, output_dir, datasets
        )
        zip_size = zip_path.stat().st_size
        logger.info(f"Created {zip_path} ({format_size(zip_size)})")

    # Build only
    if args.build:
        # Also write README and manifest to output dir
        readme_path = output_dir / "README.md"
        manifest_path = output_dir / "manifest.json"

        readme_path.write_text(readme_content)
        manifest_path.write_text(manifest_json)

        print("\n" + "=" * 70)
        print("Build Complete")
        print("=" * 70)
        print(f"  ZIP: {zip_path} ({format_size(zip_size)})")
        print(f"  README: {readme_path}")
        print(f"  Manifest: {manifest_path}")
        print(f"  Datasets: {len(datasets)}")
        print(f"  Files in ZIP: {len(zip_contents)}")
        print("=" * 70)
        return

    # Dry run
    if args.dry_run:
        print(f"\nDry run for version {args.version}")
        print("=" * 80)

        # Datasets table
        print(f"\nDatasets ({len(datasets)}):\n")
        print(f"  {'Sector':<12} {'Subsector':<15} {'Gamma':>8} {'SE':>8} {'R2':>7} {'Regions':>10}")
        print(f"  {'-'*12} {'-'*15} {'-'*8} {'-'*8} {'-'*7} {'-'*10}")
        for d in sorted(datasets, key=lambda x: (x["sector"], x["subsector"])):
            gamma = f"{d['gamma']:.4f}" if d.get("gamma") else "--"
            se = f"{d['gamma_se']:.4f}" if d.get("gamma_se") else "--"
            r2 = f"{d['r_squared']:.3f}" if d.get("r_squared") else "--"
            regions = f"{d['n_regions']:,}" if d.get("n_regions") else "--"
            print(f"  {d['sector']:<12} {d['subsector']:<15} {gamma:>8} {se:>8} {r2:>7} {regions:>10}")

        # Upload summary
        print(f"\nFiles to upload:\n")
        print(f"  {'File':<50} {'Size':>12}")
        print(f"  {'-'*50} {'-'*12}")
        print(f"  {'README.md':<50} {'~15 KB':>12}")
        print(f"  {'manifest.json':<50} {'~5 KB':>12}")
        print(f"  {f'flexdamage-parameters-v{args.version}.zip':<50} {format_size(zip_size):>12}")
        print(f"  {'-'*50} {'-'*12}")

        # ZIP contents
        print(f"\nZIP contents ({len(zip_contents)} files):\n")
        for c in sorted(zip_contents, key=lambda x: x["archive_path"])[:20]:
            print(f"  {c['archive_path']:<60} {format_size(c['size']):>10}")
        if len(zip_contents) > 20:
            print(f"  ... and {len(zip_contents) - 20} more files")

        print("\n" + "=" * 80)
        base = "sandbox.zenodo.org" if args.sandbox else "zenodo.org"
        print(f"\nWould upload to: https://{base}")
        print("=" * 80)
        return

    # Draft upload
    if args.draft:
        if not HAS_REQUESTS:
            logger.error("requests library required: pip install requests")
            sys.exit(1)

        api_url = get_api_url(args.sandbox)
        token = get_token(args.sandbox)

        zenodo_metadata = build_zenodo_metadata(args.version, readme_content)

        if args.new_version_of:
            logger.info(f"Creating NEW VERSION of existing record {args.new_version_of}...")
            deposit = create_new_version(token, api_url, args.new_version_of)
            deposit_id = deposit["id"]
            # Apply updated metadata (version string, etc.)
            update_deposit_metadata(token, api_url, deposit_id, zenodo_metadata)
            logger.info(f"Linked to concept DOI of {args.new_version_of}. New draft id: {deposit_id}")
        else:
            logger.info("Creating Zenodo deposit (new record)...")
            deposit = create_deposit(token, api_url, zenodo_metadata)
            deposit_id = deposit["id"]

        bucket_url = deposit["links"]["bucket"]

        logger.info(f"Deposit ID: {deposit_id}")

        # Upload README
        logger.info("Uploading README.md...")
        upload_file_to_bucket(token, bucket_url, "README.md", readme_content.encode())

        # Upload manifest
        logger.info("Uploading manifest.json...")
        upload_file_to_bucket(token, bucket_url, "manifest.json", manifest_json.encode())

        # Upload ZIP
        logger.info(f"Uploading {zip_path.name} ({format_size(zip_size)})...")
        upload_file_from_path(token, bucket_url, zip_path, zip_path.name)

        # Save state
        state = load_state()
        state["deposit_id"] = deposit_id
        state["sandbox"] = args.sandbox
        state["version"] = args.version
        state["uploaded_at"] = datetime.utcnow().isoformat()
        save_state(state)

        # Print result
        base_url = "sandbox.zenodo.org" if args.sandbox else "zenodo.org"
        print("\n" + "=" * 70)
        print("Draft Created")
        print("=" * 70)
        print(f"  Deposit ID: {deposit_id}")
        print(f"  Version: {args.version}")
        print(f"  Datasets: {len(datasets)}")
        print(f"  Review at: https://{base_url}/uploads/{deposit_id}")
        print(f"\n  To publish:")
        print(f"    python scripts/zenodo_upload.py {'--sandbox ' if args.sandbox else ''}--publish")
        print("=" * 70)


if __name__ == "__main__":
    main()
