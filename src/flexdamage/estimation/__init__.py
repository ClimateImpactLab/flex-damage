"""
Estimation module: Standardized parquet → Parameters.

All estimation functions assume the DuckDB connection has a
'standardized' VIEW with exactly these columns:
region, year, y, T, log_income, w, sdev, scenario, y_sign

No conditional column handling needed — standardize.py guarantees the schema.
"""

from .errors import compute_all_error_terms
from .gamma import estimate_gamma
from .regional import fit_regional_polynomials

__all__ = [
    "estimate_gamma",
    "fit_regional_polynomials",
    "compute_all_error_terms",
]
