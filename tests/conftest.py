"""
Test fixtures for FlexDamage v3.

Creates synthetic data with KNOWN true parameters for validation.
Tests should verify recovered parameters are within 2 SE of truth.
"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

# True parameters for synthetic data
TRUE_GAMMA = 0.3
TRUE_PARAMS = {
    "REG_A": {"intercept": 10.0, "alpha": -50.0, "beta": 5.0},
    "REG_B": {"intercept": -5.0, "alpha": 100.0, "beta": -10.0},
    "REG_C": {"intercept": 0.0, "alpha": 0.0, "beta": 0.0},
}


@pytest.fixture
def synthetic_data() -> pd.DataFrame:
    """
    Create synthetic dataset with known parameters.

    Model: y = (intercept + alpha*T + beta*T²) * exp(gamma * log_income) + noise

    Includes:
    - Both positive and negative y values
    - scenario column (rcp + ssp)
    - sdev column (some NULL)
    """
    np.random.seed(42)

    rows = []

    for region, params in TRUE_PARAMS.items():
        intercept = params["intercept"]
        alpha = params["alpha"]
        beta = params["beta"]

        for year in range(2020, 2060):
            for rcp in ["rcp45", "rcp85"]:
                for ssp in ["SSP2", "SSP3"]:
                    # Generate covariates
                    T = np.random.uniform(-2, 6)
                    log_income = np.random.uniform(8, 12)
                    population = np.random.uniform(1e5, 1e7)

                    # Generate outcome
                    y_norm = intercept + alpha * T + beta * T**2
                    y = y_norm * np.exp(TRUE_GAMMA * log_income)
                    y += np.random.normal(0, 50)

                    rows.append({
                        "region": region,
                        "year": year,
                        "log_yield_impact": y,
                        "temperature_anomaly": T,
                        "gdppc": np.exp(log_income),
                        "pop": population,
                        "rcp": rcp,
                        "ssp": ssp,
                        "sdev": np.random.uniform(0.1, 1.0) if np.random.random() < 0.5 else None,
                    })

    return pd.DataFrame(rows)


@pytest.fixture
def temp_dir():
    """Provide a temporary directory that's cleaned up after tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def synthetic_csv(synthetic_data, temp_dir) -> Path:
    """Write synthetic data to CSV and return path."""
    path = temp_dir / "synthetic.csv"
    synthetic_data.to_csv(path, index=False)
    return path


@pytest.fixture
def test_config(synthetic_csv, temp_dir) -> dict:
    """Create test configuration dict."""
    return {
        "run": {
            "name": "test_run",
            "description": "Test with synthetic data",
        },
        "sector": {
            "name": "test",
            "subsector": "synthetic",
            "units": "physical",
            "adaptation": "na",
        },
        "data": {
            "source": str(synthetic_csv),
            "format": "csv",
            "columns": {
                "y": "log_yield_impact",
                "temperature": "temperature_anomaly",
                "income": "gdppc",
                "weight": "pop",
                "region": "region",
                "year": "year",
                "sdev": "sdev",
                "scenario_columns": ["rcp", "ssp"],
            },
            "income_is_log": False,
        },
        "estimation": {
            "formula": "alpha * T + beta * T**2",
            "gamma": {
                "method": "fixed_effects",
                "temperature_bins": 0.5,
                "cluster_se": True,
                "include_sign_in_fe": True,
                "n_quantiles": 5,
                "trim_percentile": 0.0,
            },
            "regional": {
                "min_observations": 10,
                "ridge_lambda": 1e-8,
            },
            "constraints": [],
        },
        "output": {
            "results_dir": str(temp_dir),
            "parameters_dir": str(temp_dir),
        },
        "execution": {
            "workers": 1,
            "memory_limit_gb": 8.0,
        },
    }


@pytest.fixture
def test_config_path(test_config, temp_dir) -> Path:
    """Write test config to YAML and return path."""
    path = temp_dir / "config.yaml"
    with open(path, "w") as f:
        yaml.dump(test_config, f)
    return path


@pytest.fixture
def duckdb_connection():
    """Create a DuckDB connection for testing."""
    import duckdb
    con = duckdb.connect()
    yield con
    con.close()
