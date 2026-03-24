# Pipeline

## Running

```bash
python scripts/run.py configs/agriculture/corn.yaml
```

## What happens step by step

### 1. Standardize

Reads the source data (zarr, parquet, CSV) and produces a 9-column
parquet with fixed schema. Column mappings are defined in the YAML:

```yaml
data:
  source: "/path/to/data.zarr"
  columns:
    y: "log_yield_impact"
    temperature: "temperature_anomaly"
    income: "gdppc"
    income_is_log: false
    weight: "population"
    region: "region"
    year: "year"
```

### 2. Gamma estimation

Fixed-effects regression using pyfixest:

$$\log N_{it} = \sum_k \theta_{i,k}(T_t) + \gamma \log Y_{it} + \delta_t$$

FE groups: sign(y) $\times$ region $\times$ floor(T / 0.5).
Clustered SE: two-way by group and year.
Output: 19 quantiles from $N(\hat{\gamma}, SE)$.

### 3. Regional polynomials (x19 parallel)

For each gamma quantile, DuckDB computes sufficient statistics via
GROUP BY, numpy solves the 2x2 system per region.

$$N_{it} / Y_{it}^{\gamma} = \delta_i + \alpha_i T_t + \beta_i T_t^2$$

Constraints:

```yaml
estimation:
  constraints:
    - parameter: "beta"
      type: "max"
      value: 0        # beta <= 0 for agriculture
```

### 4. Error terms

$\rho$, $\zeta$, $\eta$ computed in a single SQL pass.

### 5. Export

12-column CSV + metadata JSON.

## Configuration

```yaml
run:
  name: "agriculture_corn_ir"

sector:
  name: "agriculture"
  subsector: "corn"
  units: "log yield impact"

data:
  source: "/path/to/data.zarr"
  columns:
    y: "log_yield_impact"
    temperature: "temperature_anomaly"
    income: "gdppc"
    income_is_log: false
    weight: "population"
    region: "region"
    year: "year"
    scenario_columns: ["rcp", "ssp"]

estimation:
  gamma:
    temperature_bins: 0.5
    cluster_se: true
    include_sign_in_fe: true
    n_quantiles: 19
    trim_percentile: 0.05
  regional:
    min_observations: 10
  constraints:
    - parameter: "beta"
      type: "max"
      value: 0

output:
  results_dir: "/path/to/results"
  parameters_dir: "/path/to/parameters"

execution:
  workers: 0
  memory_limit_gb: 200
```
