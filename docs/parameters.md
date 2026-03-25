# Parameters

## File structure

Each estimation produces three files:

**regional_parameters.csv**: 12 columns, 19 rows per region.

Each row contains 12 fields. `region` identifies the location. `gamma` is the income elasticity quantile value for this row (there are 19 rows per region, one per quantile). `alpha` and `beta` are the linear and quadratic temperature coefficients in the polynomial $M(T) = \alpha T + \beta T^2$. The variance-covariance matrix of $(\alpha, \beta)$ is given by `sigma11` (variance of alpha), `sigma12` (covariance), and `sigma22` (variance of beta), enabling joint uncertainty sampling. `rho` is the correlation between regional and global polynomial residuals, used to maintain spatial covariance in Monte Carlo draws. `zeta` is the temperature-dependent error scale and `eta` is the residual noise standard deviation; together they describe the prediction uncertainty that grows with temperature. `rsqr1` measures the polynomial fit quality and `rsqr2` measures the error model fit.

**global_results.json**: Gamma estimate, SE, R-squared, quantiles.

**metadata.json**: Run configuration and summary statistics.

## Zenodo

Zenodo is a research data repository that assigns DOIs to datasets,
ensuring long-term availability and citability.

### DOI structure

Each Zenodo upload has two DOIs:

- **Version DOI**: Points to a specific version (e.g., `10.5281/zenodo.19199919`).
  Always returns the same data.
- **Concept DOI**: Points to the latest version. When parameters are
  re-estimated, a new version is uploaded under the same concept DOI.

For reproducibility, cite the version DOI. For always-current data,
use the concept DOI.

### Current release

| Version | Date | DOI | Sectors |
|---------|------|-----|---------|
| 1.0.0-alpha | 2026-03-22 | [10.5281/zenodo.19199919](https://zenodo.org/records/19199919) | Agriculture (8 crops) |

### Download

Direct download:

```bash
wget https://zenodo.org/records/19199919/files/flexdamage-parameters-v1.0.0-alpha.zip
unzip flexdamage-parameters-v1.0.0-alpha.zip
```

Via API (useful for automation):

```python
import requests

r = requests.get("https://zenodo.org/api/records/19199919")
files = r.json()["files"]
for f in files:
    if f["key"].endswith(".zip"):
        print(f["links"]["self"])
```

### ZIP contents

```
flexdamage-parameters-v1.0.0-alpha/
├── agriculture/
│   ├── corn/
│   │   ├── agriculture__corn__regional_parameters.csv
│   │   ├── agriculture__corn__global_results.json
│   │   └── agriculture__corn__metadata.json
│   ├── rice/
│   │   └── ...
│   └── ...
└── README.md
```

Each sector/subsector directory contains the three output files. The
CSV is the primary file for downstream use; the JSON files contain
metadata and global estimation results.

### Versioning

When parameters are re-estimated (e.g., with updated input data or
methodology changes), a new version is uploaded under the same concept
DOI. Users who pin a specific version DOI will always get the same
data. The concept DOI automatically resolves to the latest version.

### Citation

Rising, J. and Cadavid Sanchez, S. (2026). Flexible Damage Function Parameters for Climate Impact Assessment (Version 1.0.0-alpha) [Data set]. Zenodo. https://zenodo.org/records/19199919
