"""
Manifest builder for Zenodo packaging.

Creates manifest.json with checksums and metadata for all parameter files.
"""

import hashlib
import json
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)


class ManifestBuilder:
    """
    Build manifest.json for Zenodo upload.

    Manifest includes per file:
    - sha256, size_bytes
    - sector, subsector, resolution, units, adaptation
    - n_regions, n_gamma_quantiles, n_rows
    - format_version
    """

    def __init__(
        self,
        output_dir: Union[str, Path],
        version: str,
        title: str = "FlexDamage Parameters",
        description: str = "",
    ):
        """
        Initialize manifest builder.

        Args:
            output_dir: Directory containing parameter files
            version: Version string (e.g., "1.0.0")
            title: Dataset title
            description: Dataset description
        """
        self.output_dir = Path(output_dir)
        self.version = version
        self.title = title
        self.description = description
        self.files: List[Dict] = []
        self.errors: List[str] = []

    def add_file(
        self,
        path: Union[str, Path],
        metadata: Optional[Dict] = None,
    ) -> None:
        """
        Add a file to the manifest.

        Args:
            path: Path to parameter CSV or JSON file
            metadata: Optional metadata dict (auto-extracted if not provided)
        """
        path = Path(path)

        if not path.exists():
            self.errors.append(f"File not found: {path}")
            return

        # Compute checksum and size
        sha256 = self._compute_sha256(path)
        size_bytes = path.stat().st_size

        # Extract metadata from file if not provided
        if metadata is None:
            metadata = self._extract_metadata(path)

        file_entry = {
            "filename": path.name,
            "path": str(path.relative_to(self.output_dir)) if path.is_relative_to(self.output_dir) else str(path),
            "sha256": sha256,
            "size_bytes": size_bytes,
            "format_version": "3.0",
            **metadata,
        }

        self.files.append(file_entry)
        logger.debug(f"Added to manifest: {path.name}")

    def add_directory(
        self,
        path: Union[str, Path],
        pattern: str = "*.csv",
    ) -> None:
        """
        Add all matching files from a directory.

        Args:
            path: Directory path
            pattern: Glob pattern (default: "*.csv")
        """
        path = Path(path)

        if not path.is_dir():
            self.errors.append(f"Not a directory: {path}")
            return

        for file_path in sorted(path.glob(pattern)):
            self.add_file(file_path)

    def validate(self) -> List[str]:
        """
        Validate all files in the manifest.

        Checks:
        - Files exist
        - Checksums match
        - Required columns present in CSVs

        Returns:
            List of error messages (empty if valid)
        """
        errors = list(self.errors)

        for entry in self.files:
            file_path = self.output_dir / entry["path"]

            # Check existence
            if not file_path.exists():
                errors.append(f"File missing: {entry['path']}")
                continue

            # Verify checksum
            actual_sha256 = self._compute_sha256(file_path)
            if actual_sha256 != entry["sha256"]:
                errors.append(f"Checksum mismatch for {entry['path']}")

            # Validate CSV columns
            if file_path.suffix == ".csv":
                try:
                    df = pd.read_csv(file_path, nrows=0)
                    required = {"region", "gamma", "alpha", "beta"}
                    missing = required - set(df.columns)
                    if missing:
                        errors.append(f"Missing columns in {entry['path']}: {missing}")
                except Exception as e:
                    errors.append(f"Cannot read {entry['path']}: {e}")

        return errors

    def save(self, path: Optional[Union[str, Path]] = None) -> Path:
        """
        Write manifest.json.

        Args:
            path: Output path (default: output_dir/manifest.json)

        Returns:
            Path to manifest file
        """
        if path is None:
            path = self.output_dir / "manifest.json"
        else:
            path = Path(path)

        manifest = {
            "flexdamage_version": "3.0.0",
            "manifest_version": "1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "dataset": {
                "title": self.title,
                "version": self.version,
                "description": self.description,
            },
            "statistics": {
                "n_files": len(self.files),
                "total_size_bytes": sum(f["size_bytes"] for f in self.files),
                "sectors": list(set(f.get("sector", "unknown") for f in self.files)),
            },
            "files": self.files,
        }

        with open(path, "w") as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"Wrote manifest with {len(self.files)} files to {path}")
        return path

    def package_zip(
        self,
        path: Optional[Union[str, Path]] = None,
        include_manifest: bool = True,
    ) -> Path:
        """
        Create distributable zip archive.

        Args:
            path: Output path (default: output_dir/flexdamage_parameters_{version}.zip)
            include_manifest: Include manifest.json in zip

        Returns:
            Path to zip file
        """
        if path is None:
            path = self.output_dir / f"flexdamage_parameters_{self.version}.zip"
        else:
            path = Path(path)

        # Save manifest first
        manifest_path = self.save()

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add manifest
            if include_manifest:
                zf.write(manifest_path, "manifest.json")

            # Add all files
            for entry in self.files:
                file_path = self.output_dir / entry["path"]
                if file_path.exists():
                    zf.write(file_path, entry["path"])

        total_size = path.stat().st_size / (1024 * 1024)
        logger.info(f"Created zip archive: {path} ({total_size:.1f} MB)")

        return path

    def _compute_sha256(self, path: Path) -> str:
        """Compute SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _extract_metadata(self, path: Path) -> Dict:
        """Extract metadata from a parameter file."""
        metadata = {}

        if path.suffix == ".csv":
            try:
                df = pd.read_csv(path)
                metadata["n_rows"] = len(df)
                metadata["n_regions"] = df["region"].nunique() if "region" in df.columns else 0
                metadata["n_gamma_quantiles"] = df["gamma"].nunique() if "gamma" in df.columns else 0

                # Parse sector info from filename
                # Expected format: {sector}_{subsector}_{units}_{adaptation}.csv
                parts = path.stem.split("_")
                if len(parts) >= 2:
                    metadata["sector"] = parts[0]
                    metadata["subsector"] = parts[1]
                if len(parts) >= 3:
                    metadata["units"] = parts[2]
                if len(parts) >= 4:
                    metadata["adaptation"] = parts[3]

            except Exception as e:
                logger.warning(f"Could not extract metadata from {path}: {e}")

        elif path.suffix == ".json":
            try:
                with open(path) as f:
                    data = json.load(f)
                metadata["type"] = "metadata"
                if "sector" in data:
                    metadata.update(data["sector"])
            except Exception as e:
                logger.warning(f"Could not read JSON {path}: {e}")

        return metadata


def load_manifest(path: Union[str, Path]) -> Dict:
    """
    Load a manifest.json file.

    Args:
        path: Path to manifest.json

    Returns:
        Manifest dict
    """
    with open(path, "r") as f:
        return json.load(f)
