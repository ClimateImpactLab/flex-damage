"""
Tests for regional polynomial estimation.
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

from conftest import TRUE_GAMMA, TRUE_PARAMS


class TestRegionalEstimation:
    """Tests for regional polynomial estimation."""

    def test_regional_returns_all_regions(self, test_config_path, temp_dir):
        """Test that all regions with sufficient data are returned."""
        config = load_config(test_config_path)
        std_path = standardize(config, temp_dir / "std.parquet")

        con = duckdb.connect()
        try:
            load_standardized(con, std_path)

            result = fit_regional_polynomials(con, TRUE_GAMMA, config)

            # Should have all 3 test regions
            regions = set(result["region"])
            assert "REG_A" in regions
            assert "REG_B" in regions
            assert "REG_C" in regions

        finally:
            con.close()

    def test_regional_output_columns(self, test_config_path, temp_dir):
        """Test that output has all required columns."""
        config = load_config(test_config_path)
        std_path = standardize(config, temp_dir / "std.parquet")

        con = duckdb.connect()
        try:
            load_standardized(con, std_path)

            result = fit_regional_polynomials(con, TRUE_GAMMA, config)

            required = ["region", "gamma", "intercept", "alpha", "beta",
                       "sigma11", "sigma12", "sigma22", "rsqr1", "n"]
            for col in required:
                assert col in result.columns, f"Missing column: {col}"

        finally:
            con.close()

    def test_regional_parameter_estimates(self, test_config_path, temp_dir):
        """Test that regional parameters are close to true values."""
        config = load_config(test_config_path)
        std_path = standardize(config, temp_dir / "std.parquet")

        con = duckdb.connect()
        try:
            load_standardized(con, std_path)

            result = fit_regional_polynomials(con, TRUE_GAMMA, config)

            for region, true in TRUE_PARAMS.items():
                row = result[result["region"] == region].iloc[0]

                # Check alpha (with tolerance based on magnitude)
                alpha_err = abs(row["alpha"] - true["alpha"])
                alpha_tol = max(50, abs(true["alpha"]) * 0.5)  # 50% or 50 units
                assert alpha_err < alpha_tol, (
                    f"{region}: alpha={row['alpha']:.2f}, true={true['alpha']:.2f}, "
                    f"error={alpha_err:.2f}, tol={alpha_tol:.2f}"
                )

                # Check beta (with tolerance based on magnitude)
                beta_err = abs(row["beta"] - true["beta"])
                beta_tol = max(5, abs(true["beta"]) * 0.5)
                assert beta_err < beta_tol, (
                    f"{region}: beta={row['beta']:.2f}, true={true['beta']:.2f}, "
                    f"error={beta_err:.2f}, tol={beta_tol:.2f}"
                )

        finally:
            con.close()

    def test_regional_r_squared(self, test_config_path, temp_dir):
        """Test that R² is in valid range."""
        config = load_config(test_config_path)
        std_path = standardize(config, temp_dir / "std.parquet")

        con = duckdb.connect()
        try:
            load_standardized(con, std_path)

            result = fit_regional_polynomials(con, TRUE_GAMMA, config)

            # R² should be between 0 and 1
            assert (result["rsqr1"] >= 0).all()
            assert (result["rsqr1"] <= 1).all()

        finally:
            con.close()

    def test_regional_variance_positive(self, test_config_path, temp_dir):
        """Test that variance estimates are non-negative."""
        config = load_config(test_config_path)
        std_path = standardize(config, temp_dir / "std.parquet")

        con = duckdb.connect()
        try:
            load_standardized(con, std_path)

            result = fit_regional_polynomials(con, TRUE_GAMMA, config)

            assert (result["sigma11"] >= 0).all()
            assert (result["sigma22"] >= 0).all()

        finally:
            con.close()
