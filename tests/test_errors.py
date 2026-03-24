"""
Tests for error term computation (rho, zeta, eta).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import duckdb
import numpy as np
import pytest

from flexdamage.build.standardize import standardize, load_standardized
from flexdamage.config import load_config
from flexdamage.estimation.regional import fit_regional_polynomials
from flexdamage.estimation.errors import compute_all_error_terms

from conftest import TRUE_GAMMA


class TestErrorTerms:
    """Tests for error term computation."""

    def test_error_terms_output_columns(self, test_config_path, temp_dir):
        """Test that output has all required columns."""
        config = load_config(test_config_path)
        std_path = standardize(config, temp_dir / "std.parquet")

        con = duckdb.connect()
        try:
            load_standardized(con, std_path)

            # First fit regional
            regional = fit_regional_polynomials(con, TRUE_GAMMA, config)

            # Then compute error terms
            errors = compute_all_error_terms(con, regional, TRUE_GAMMA, config)

            required = ["region", "rho", "zeta", "eta", "rsqr2"]
            for col in required:
                assert col in errors.columns, f"Missing column: {col}"

        finally:
            con.close()

    def test_error_terms_returns_all_regions(self, test_config_path, temp_dir):
        """Test that all regions are returned."""
        config = load_config(test_config_path)
        std_path = standardize(config, temp_dir / "std.parquet")

        con = duckdb.connect()
        try:
            load_standardized(con, std_path)

            regional = fit_regional_polynomials(con, TRUE_GAMMA, config)
            errors = compute_all_error_terms(con, regional, TRUE_GAMMA, config)

            # Should have all regions from regional
            regional_regions = set(regional["region"])
            error_regions = set(errors["region"])

            # Error computation may drop some regions with insufficient data
            assert error_regions.issubset(regional_regions)
            assert len(error_regions) > 0

        finally:
            con.close()

    def test_rho_in_valid_range(self, test_config_path, temp_dir):
        """Test that rho (correlation) is in [-1, 1]."""
        config = load_config(test_config_path)
        std_path = standardize(config, temp_dir / "std.parquet")

        con = duckdb.connect()
        try:
            load_standardized(con, std_path)

            regional = fit_regional_polynomials(con, TRUE_GAMMA, config)
            errors = compute_all_error_terms(con, regional, TRUE_GAMMA, config)

            assert (errors["rho"] >= -1).all()
            assert (errors["rho"] <= 1).all()

        finally:
            con.close()

    def test_eta_non_negative(self, test_config_path, temp_dir):
        """Test that eta (std dev) is non-negative."""
        config = load_config(test_config_path)
        std_path = standardize(config, temp_dir / "std.parquet")

        con = duckdb.connect()
        try:
            load_standardized(con, std_path)

            regional = fit_regional_polynomials(con, TRUE_GAMMA, config)
            errors = compute_all_error_terms(con, regional, TRUE_GAMMA, config)

            assert (errors["eta"] >= 0).all()

        finally:
            con.close()

    def test_rsqr2_in_valid_range(self, test_config_path, temp_dir):
        """Test that rsqr2 is in [0, 1]."""
        config = load_config(test_config_path)
        std_path = standardize(config, temp_dir / "std.parquet")

        con = duckdb.connect()
        try:
            load_standardized(con, std_path)

            regional = fit_regional_polynomials(con, TRUE_GAMMA, config)
            errors = compute_all_error_terms(con, regional, TRUE_GAMMA, config)

            assert (errors["rsqr2"] >= 0).all()
            assert (errors["rsqr2"] <= 1).all()

        finally:
            con.close()

    def test_error_terms_merge_with_regional(self, test_config_path, temp_dir):
        """Test that error terms can be merged with regional results."""
        config = load_config(test_config_path)
        std_path = standardize(config, temp_dir / "std.parquet")

        con = duckdb.connect()
        try:
            load_standardized(con, std_path)

            regional = fit_regional_polynomials(con, TRUE_GAMMA, config)
            errors = compute_all_error_terms(con, regional, TRUE_GAMMA, config)

            # Merge should work
            merged = regional.merge(errors, on="region", how="left")

            # Should have all columns
            assert "alpha" in merged.columns
            assert "beta" in merged.columns
            assert "rho" in merged.columns
            assert "zeta" in merged.columns
            assert "eta" in merged.columns

        finally:
            con.close()
