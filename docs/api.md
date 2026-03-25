# API Reference

Documentation for the FlexDamage estimation pipeline.

---

## Pipeline

### `FlexDamagePipeline`

```python
from flexdamage.pipeline import FlexDamagePipeline

pipeline = FlexDamagePipeline("configs/agriculture_corn.yaml")
result = pipeline.run()
```

Main pipeline orchestrator for flexible damage function estimation.

Coordinates the full estimation pipeline:

1. Standardize source data to fixed parquet format
2. Estimate global income elasticity (gamma)
3. Fit regional polynomials for each gamma quantile
4. Compute error structure parameters
5. Export results to CSV and JSON

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `config_path` | `str` or `Path` | Path to YAML configuration file |

**Attributes:**

| Name | Type | Description |
|------|------|-------------|
| `config` | `RunConfig` | Validated configuration object |
| `config_path` | `Path` | Path to the configuration file |

#### `run() -> dict`

Execute full estimation pipeline.

Runs the complete estimation workflow:

1. Standardize input data
2. Estimate gamma via fixed-effects regression
3. Fit regional polynomials for each gamma quantile
4. Compute error terms (rho, zeta, eta)
5. Export parameters to CSV and JSON

**Returns:**

| Key | Type | Description |
|-----|------|-------------|
| `gamma` | `float` | Point estimate of income elasticity |
| `gamma_se` | `float` | Standard error of gamma |
| `n_regions` | `int` | Number of regions processed |
| `n_observations` | `int` | Total observations |
| `output_csv` | `str` | Path to output CSV file |
| `output_json` | `str` | Path to global results JSON |
| `timings` | `dict` | Timing for each pipeline stage |

---

## Data Preparation

### `standardize(config, output_path=None) -> str`

```python
from flexdamage.build.standardize import standardize

parquet_path = standardize(config)
```

Transform source data into standardized parquet format.

Reads input data from any supported format (zarr, parquet, CSV) and produces
a standardized parquet file with fixed column names for downstream estimation.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `config` | `RunConfig` | Pipeline configuration with column mappings and data source path |
| `output_path` | `str` or `Path`, optional | Output path for standardized parquet. If None, creates a temp file |

**Returns:**

`str` - Path to the standardized parquet file.

**Output columns (always present):**

| Column | Type | Description |
|--------|------|-------------|
| `region` | `str` | Region identifier |
| `year` | `int` | Year |
| `y` | `float` | Outcome variable |
| `T` | `float` | Temperature anomaly (°C) |
| `log_income` | `float` | Natural log of GDP per capita |
| `w` | `float` | Population weight |
| `sdev` | `float` or `None` | MC standard deviation |
| `scenario` | `str` or `None` | Scenario identifier |
| `y_sign` | `int` | Sign of y (+1 or -1) |

---

## Estimation

### `estimate_gamma(con, config) -> dict`

```python
from flexdamage.estimation.gamma import estimate_gamma

global_results = estimate_gamma(con, config)
gamma = global_results["gamma"]
```

Estimate global income elasticity (gamma) via fixed-effects regression.

Uses pyfixest for fast high-dimensional fixed effects regression with two-way
clustered standard errors (Cameron, Gelbach & Miller 2011).

The regression model is:

```
y = gamma * log_income + FE(region x temp_bin x sign) + FE(year) + epsilon
```

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `con` | `duckdb.DuckDBPyConnection` | Active DuckDB connection with 'standardized' view |
| `config` | `RunConfig` | Pipeline configuration with gamma estimation settings |

**Returns:**

| Key | Type | Description |
|-----|------|-------------|
| `gamma` | `float` | Point estimate of income elasticity |
| `gamma_se` | `float` | Clustered standard error |
| `gamma_quantiles` | `list` | 19 quantiles from N(gamma, SE) |
| `r_squared` | `float` | R-squared of the FE regression |
| `n_obs` | `int` | Number of observations |
| `n_fe_groups` | `int` | Number of fixed effect groups |

**Notes:**

Positive gamma indicates adaptation: richer regions experience smaller damages
from the same temperature change.

---

### `fit_regional_polynomials(con, gamma, config) -> DataFrame`

```python
from flexdamage.estimation.regional import fit_regional_polynomials

regional_df = fit_regional_polynomials(con, gamma, config)
```

Fit regional polynomial coefficients (alpha, beta) for all regions.

Fits the model for each region i:

```
y_norm = intercept + alpha_i * T + beta_i * T^2 + epsilon
```

where `y_norm = y * Y^(-gamma)` is the income-normalized outcome.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `con` | `duckdb.DuckDBPyConnection` | Active DuckDB connection with 'standardized' view |
| `gamma` | `float` | Income elasticity value (called once per quantile) |
| `config` | `RunConfig` | Pipeline configuration with constraints and settings |

**Returns:**

`pandas.DataFrame` with columns:

| Column | Type | Description |
|--------|------|-------------|
| `region` | `str` | Region identifier |
| `gamma` | `float` | Gamma value used |
| `alpha` | `float` | Linear temperature coefficient |
| `beta` | `float` | Quadratic temperature coefficient |
| `sigma11` | `float` | Variance of alpha |
| `sigma12` | `float` | Covariance of alpha, beta |
| `sigma22` | `float` | Variance of beta |
| `rsqr1` | `float` | R-squared of polynomial fit |
| `n` | `int` | Number of observations |

**Notes:**

Uses vectorized OLS via sufficient statistics (no Python loops over regions).
Constraints (e.g., `beta <= 0` for agriculture) are applied post-estimation.

---

### `compute_all_error_terms(con, regional_params, gamma, config) -> DataFrame`

```python
from flexdamage.estimation.errors import compute_all_error_terms

error_df = compute_all_error_terms(con, regional_params, gamma, config)
```

Compute error structure parameters (rho, zeta, eta) for all regions.

Computes the error decomposition for Monte Carlo sampling:

```
epsilon = rho * u_global + zeta * T * v_scenario + eta * noise
```

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `con` | `duckdb.DuckDBPyConnection` | Active DuckDB connection with 'standardized' view |
| `regional_params` | `pandas.DataFrame` | Regional parameters with columns [region, intercept, alpha, beta] |
| `gamma` | `float` | Gamma value used for income normalization |
| `config` | `RunConfig` | Pipeline configuration |

**Returns:**

`pandas.DataFrame` with columns:

| Column | Type | Description |
|--------|------|-------------|
| `region` | `str` | Region identifier |
| `rho` | `float` | Correlation with global residual process |
| `zeta` | `float` | Temperature-dependent error scale |
| `eta` | `float` | Residual noise standard deviation |
| `rsqr2` | `float` | R-squared of error model fit |

---

## Export

### `export_parameters(regional_results, global_results, config, output_dir=None) -> dict`

```python
from flexdamage.export.parameters import export_parameters

paths = export_parameters(regional_results, global_results, config)
print(f"CSV: {paths['csv']}")
```

Export estimation results to standardized CSV and JSON files.

Creates three output files:

- `{sector}__{subsector}__regional_parameters.csv` - 12-column parameter file
- `{sector}__{subsector}__global_results.json` - Gamma estimation results
- `{sector}__{subsector}__metadata.json` - Run configuration and statistics

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `regional_results` | `pandas.DataFrame` | Regional parameters for all gamma quantiles |
| `global_results` | `dict` | Global estimation results from estimate_gamma() |
| `config` | `RunConfig` | Pipeline configuration |
| `output_dir` | `str` or `Path`, optional | Output directory. Defaults to config.output.parameters_dir |

**Returns:**

`dict` with keys `csv`, `json`, `metadata` containing paths to output files.

**CSV columns (12 total):**

| Column | Type | Description |
|--------|------|-------------|
| `region` | `str` | Region identifier |
| `gamma` | `float` | Gamma quantile value used |
| `alpha` | `float` | Linear temperature coefficient |
| `beta` | `float` | Quadratic temperature coefficient |
| `sigma11` | `float` | Variance of alpha |
| `sigma12` | `float` | Covariance of alpha, beta |
| `sigma22` | `float` | Variance of beta |
| `rho` | `float` | Correlation with global residuals |
| `zeta` | `float` | Slope of \|residuals\| vs T |
| `eta` | `float` | Std dev of residual noise |
| `rsqr1` | `float` | R² of regional polynomial fit |
| `rsqr2` | `float` | R² of error term fit |

---

## Configuration

### `load_config(path) -> RunConfig`

```python
from flexdamage.config import load_config

config = load_config("configs/agriculture_corn.yaml")
print(config.run.name)
```

Load and validate a YAML configuration file.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `path` | `str` or `Path` | Path to YAML configuration file |

**Returns:**

`RunConfig` - Validated configuration object with nested attributes for
`run`, `data`, `estimation`, `output`, and `execution` settings.
