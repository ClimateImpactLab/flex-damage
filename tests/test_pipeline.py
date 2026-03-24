"""
Tests for full pipeline integration.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import pytest

from flexdamage import FlexDamagePipeline
from flexdamage.export.parameters import PARAMETER_COLUMNS

from conftest import TRUE_GAMMA


class TestPipeline:
    """Integration tests for full pipeline."""

    def test_pipeline_runs_successfully(self, test_config_path, temp_dir):
        """Test that pipeline completes without error."""
        pipeline = FlexDamagePipeline(test_config_path)
        summary = pipeline.run()

        assert summary["status"] == "success"

    def test_pipeline_creates_output_files(self, test_config_path, temp_dir):
        """Test that pipeline creates expected output files."""
        pipeline = FlexDamagePipeline(test_config_path)
        summary = pipeline.run()

        # Check CSV exists
        csv_path = Path(summary["output_csv"])
        assert csv_path.exists()

        # Check JSON exists
        json_path = Path(summary["output_json"])
        assert json_path.exists()

    def test_pipeline_output_has_correct_columns(self, test_config_path, temp_dir):
        """Test that output CSV has correct columns."""
        pipeline = FlexDamagePipeline(test_config_path)
        summary = pipeline.run()

        df = pd.read_csv(summary["output_csv"])

        for col in PARAMETER_COLUMNS:
            assert col in df.columns, f"Missing column: {col}"

    def test_pipeline_output_has_all_quantiles(self, test_config_path, temp_dir):
        """Test that output has all gamma quantiles."""
        pipeline = FlexDamagePipeline(test_config_path)
        summary = pipeline.run()

        df = pd.read_csv(summary["output_csv"])

        n_quantiles = summary["n_quantiles"]
        n_regions = summary["n_regions"]

        # Should have rows for all quantiles × all regions
        # (some regions may be dropped for insufficient data)
        assert len(df) >= n_regions  # At least one quantile per region
        assert df["gamma"].nunique() == n_quantiles

    def test_pipeline_gamma_estimate(self, test_config_path, temp_dir):
        """Test that pipeline gamma estimate is reasonable."""
        pipeline = FlexDamagePipeline(test_config_path)
        summary = pipeline.run()

        gamma = summary["gamma"]
        gamma_se = summary["gamma_se"]

        # Should be within 3 SE of true value
        error = abs(gamma - TRUE_GAMMA)
        tolerance = 3 * gamma_se + 0.15

        assert error < tolerance, (
            f"Gamma {gamma:.4f} too far from true {TRUE_GAMMA:.4f}"
        )

    def test_pipeline_timing_recorded(self, test_config_path, temp_dir):
        """Test that timing information is recorded."""
        pipeline = FlexDamagePipeline(test_config_path)
        summary = pipeline.run()

        assert "timings" in summary
        assert "standardize" in summary["timings"]
        assert "gamma" in summary["timings"]
        assert "regional" in summary["timings"]
        assert "total" in summary["timings"]

        # All timings should be positive
        for name, value in summary["timings"].items():
            assert value > 0, f"Timing {name} should be positive"

    def test_pipeline_cleans_up_temp_files(self, test_config_path, temp_dir):
        """Test that pipeline cleans up temporary files."""
        pipeline = FlexDamagePipeline(test_config_path)

        # Run pipeline
        summary = pipeline.run()

        # Temp parquet should be cleaned up
        assert pipeline.std_parquet is None or not Path(pipeline.std_parquet).exists()

    def test_pipeline_sequential_mode(self, test_config_path, temp_dir):
        """Test pipeline in sequential mode (workers=1)."""
        pipeline = FlexDamagePipeline(test_config_path)
        pipeline.config.execution.workers = 1

        summary = pipeline.run()

        assert summary["status"] == "success"
