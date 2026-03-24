"""
Database module: Discovery, standardization, and Zenodo packaging.

Handles:
- Discovering results across multiple directories
- Converting legacy formats (v1 R, v2 Python) to v3 schema
- Building manifests with checksums for Zenodo upload
"""

from .discovery import discover_results
from .registry import ManifestBuilder
from .standardize_legacy import standardize_to_v3

__all__ = ["discover_results", "standardize_to_v3", "ManifestBuilder"]
