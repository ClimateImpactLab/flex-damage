"""
Tests for gamma estimation.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import duckdb
import numpy as np
import pytest

from flexdamage.build.standardize import standardize, load_standardized
from flexdamage.config import load_config
from flexdamage.estimation.gamma import estimate_gamma

from conftest import TRUE_GAMMA


class TestGammaEstimation:
    """Tests for gamma estimation."""

    def test_gamma_point_estimate(self, test_config_path, temp_dir):
        """Test that gamma estimate is close to true value."""
        config = load_config(test_config_path)

        # Standardize data
        std_path = standardize(config, temp_dir / "std.parquet")

        # Create DuckDB connection and load data
        con = duckdb.connect()
        try:
            load_standardized(con, std_path)

            # Estimate gamma
            result = estimate_gamma(con, config)

            # Check gamma is close to true value (within 3 SE)
            gamma = result["gamma"]
            gamma_se = result["gamma_se"]

            error = abs(gamma - TRUE_GAMMA)
            tolerance = 3 * gamma_se + 0.1  # 3 SE + small buffer

            assert error < tolerance, (
                f"Gamma estimate {gamma:.4f} too far from true {TRUE_GAMMA:.4f} "
                f"(error={error:.4f}, tolerance={tolerance:.4f})"
            )

        finally:
            con.close()

    def test_gamma_quantiles(self, test_config_path, temp_dir):
        """Test that gamma quantiles are generated correctly."""
        config = load_config(test_config_path)
        std_path = standardize(config, temp_dir / "std.parquet")

        con = duckdb.connect()
        try:
            load_standardized(con, std_path)
            result = estimate_gamma(con, config)

            quantiles = result["gamma_quantiles"]

            # Check number of quantiles
            assert len(quantiles) == config.estimation.gamma.n_quantiles

            # Check quantiles are sorted
            assert quantiles == sorted(quantiles)

            # Check quantiles span around gamma
            gamma = result["gamma"]
            assert quantiles[0] < gamma < quantiles[-1]

        finally:
            con.close()

    def test_gamma_r_squared(self, test_config_path, temp_dir):
        """Test that R² is in valid range."""
        config = load_config(test_config_path)
        std_path = standardize(config, temp_dir / "std.parquet")

        con = duckdb.connect()
        try:
            load_standardized(con, std_path)
            result = estimate_gamma(con, config)

            r_squared = result["r_squared"]
            assert 0 <= r_squared <= 1

        finally:
            con.close()

    def test_gamma_standard_errors(self, test_config_path, temp_dir):
        """Test that standard errors are computed."""
        config = load_config(test_config_path)
        std_path = standardize(config, temp_dir / "std.parquet")

        con = duckdb.connect()
        try:
            load_standardized(con, std_path)
            result = estimate_gamma(con, config)

            # HC0 SE should always be present
            assert result["gamma_se_hc0"] > 0

            # Clustered SE should be present when enabled
            if config.estimation.gamma.cluster_se:
                assert result["gamma_se_clustered"] is not None
                assert result["gamma_se_clustered"] > 0

        finally:
            con.close()
