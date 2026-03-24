"""
Tests for build module (readers and standardize).
"""

import pandas as pd
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flexdamage.build.readers import detect_format, read_csv, read_source
from flexdamage.build.standardize import standardize
from flexdamage.config import load_config


class TestReaders:
    """Tests for data readers."""

    def test_detect_format_csv(self, temp_dir):
        """Test CSV format detection."""
        csv_path = temp_dir / "test.csv"
        csv_path.write_text("a,b\n1,2\n")
        assert detect_format(csv_path) == "csv"

    def test_detect_format_parquet(self, temp_dir):
        """Test parquet format detection."""
        parquet_path = temp_dir / "test.parquet"
        pd.DataFrame({"a": [1, 2]}).to_parquet(parquet_path)
        assert detect_format(parquet_path) == "parquet"

    def test_read_csv(self, synthetic_csv):
        """Test reading CSV file."""
        df = read_csv(synthetic_csv)
        assert len(df) > 0
        assert "region" in df.columns
        assert "log_yield_impact" in df.columns

    def test_read_source_auto_detect(self, synthetic_csv):
        """Test read_source with auto-detection."""
        df = read_source(synthetic_csv)
        assert len(df) > 0


class TestStandardize:
    """Tests for data standardization."""

    def test_standardize_output_columns(self, test_config_path, temp_dir):
        """Test that standardize produces correct columns."""
        config = load_config(test_config_path)
        output_path = temp_dir / "standardized.parquet"

        result_path = standardize(config, output_path)

        df = pd.read_parquet(result_path)

        # Check all required columns exist
        required = ["region", "year", "y", "T", "log_income", "w", "sdev", "scenario", "y_sign"]
        for col in required:
            assert col in df.columns, f"Missing column: {col}"

    def test_standardize_removes_nulls(self, test_config_path, temp_dir):
        """Test that standardize removes NULL values."""
        config = load_config(test_config_path)
        output_path = temp_dir / "standardized.parquet"

        result_path = standardize(config, output_path)
        df = pd.read_parquet(result_path)

        # Required columns should have no NULLs
        assert df["y"].isna().sum() == 0
        assert df["T"].isna().sum() == 0
        assert df["log_income"].isna().sum() == 0
        assert df["w"].isna().sum() == 0

    def test_standardize_log_income(self, test_config_path, temp_dir):
        """Test that income is log-transformed."""
        config = load_config(test_config_path)
        output_path = temp_dir / "standardized.parquet"

        result_path = standardize(config, output_path)
        df = pd.read_parquet(result_path)

        # log_income should be in reasonable range (log of GDP per capita)
        assert df["log_income"].min() > 0  # log(income) > 0 for income > 1
        assert df["log_income"].max() < 20  # log(income) < 20 for reasonable values

    def test_standardize_scenario(self, test_config_path, temp_dir):
        """Test that scenario is constructed correctly."""
        config = load_config(test_config_path)
        output_path = temp_dir / "standardized.parquet"

        result_path = standardize(config, output_path)
        df = pd.read_parquet(result_path)

        # Scenario should be rcp_ssp format
        scenarios = df["scenario"].unique()
        assert len(scenarios) > 1
        assert all("_" in s for s in scenarios)

    def test_standardize_y_sign(self, test_config_path, temp_dir):
        """Test that y_sign is computed correctly."""
        config = load_config(test_config_path)
        output_path = temp_dir / "standardized.parquet"

        result_path = standardize(config, output_path)
        df = pd.read_parquet(result_path)

        # y_sign should be +1 or -1
        assert set(df["y_sign"].unique()).issubset({-1, 1})

        # y_sign should match sign of y
        positive_y = df[df["y"] > 0]
        negative_y = df[df["y"] < 0]

        if len(positive_y) > 0:
            assert (positive_y["y_sign"] == 1).all()
        if len(negative_y) > 0:
            assert (negative_y["y_sign"] == -1).all()
