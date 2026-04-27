# Parameters

## File structure

Each estimation produces three files:

**regional_parameters.csv**: 12 columns, 19 rows per region.

Each row contains 12 fields. `region` identifies the location. `gamma` is the income elasticity quantile value for this row (there are 19 rows per region, one per quantile). `alpha` and `beta` are the linear and quadratic temperature coefficients in the polynomial $D(T) = \alpha T + \beta T^2$. The variance-covariance matrix of $(\alpha, \beta)$ is given by `sigma11` (variance of alpha), `sigma12` (covariance), and `sigma22` (variance of beta), enabling joint uncertainty sampling. `rho` is the correlation between regional and global polynomial residuals, used to maintain spatial covariance in Monte Carlo draws. `zeta` is the temperature-dependent error scale and `eta` is the residual noise standard deviation; together they describe the prediction uncertainty that grows with temperature. `rsqr1` measures the polynomial fit quality and `rsqr2` measures the error model fit.

**global_results.json**: Gamma estimate, SE, R-squared, quantiles.

**metadata.json**: Run configuration and summary statistics.

## Using the parameters

[Section to be expanded with user interface documentation]

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
| 1.1.0 | 2026-04-23 | [10.5281/zenodo.19712742](https://zenodo.org/records/19712742) | All sectors: agriculture (8 crops), mortality (allcause), labor (3), energy (3) |
| 1.0.0-alpha | 2026-03-22 | [10.5281/zenodo.19199919](https://zenodo.org/records/19199919) | Agriculture (8 crops) |

### Download

#### Latest version (auto-resolves via concept DOI)

The concept DOI always redirects to the most recent published version.
This is the recommended way for users who want the latest parameters.

**Shell (curl with follow-redirects):**
```bash
# Resolve the concept DOI to the latest record, then list files
curl -sL "https://zenodo.org/api/records/19199918/versions/latest" \
    | python -c "import json,sys; r=json.load(sys.stdin); print(r['id']); \
                 print('\n'.join(f['links']['self'] for f in r['files']))"

# Or just grab the zip directly from the DOI-resolved URL
curl -sLO "$(curl -sL https://zenodo.org/api/records/19199918/versions/latest \
    | python -c "import json,sys; r=json.load(sys.stdin); \
                 print(next(f['links']['self'] for f in r['files'] if f['key'].endswith('.zip')))")"
unzip flexdamage-parameters-v*.zip
```

Replace `19199918` with the actual concept DOI number for this dataset
(find it on any Zenodo record page under "Cite all versions").

**Python (requests):**
```python
import requests

CONCEPT_ID = 19199918  # concept DOI numeric part

# Resolve to latest version
r = requests.get(f"https://zenodo.org/api/records/{CONCEPT_ID}/versions/latest")
record = r.json()

print(f"Latest version: {record['metadata']['version']}")
print(f"Record ID: {record['id']}")

# Download the zip
for f in record["files"]:
    if f["key"].endswith(".zip"):
        url = f["links"]["self"]
        zip_bytes = requests.get(url).content
        with open(f["key"], "wb") as out:
            out.write(zip_bytes)
        print(f"Downloaded {f['key']} ({f['size'] / 1e6:.1f} MB)")
        break
```

#### Specific version (pin for reproducibility)

When publishing results, cite the version DOI so others can retrieve the
exact parameters you used.

**Shell:**
```bash
# Replace with your desired version record ID
VERSION_ID=19199919
curl -sL -O "https://zenodo.org/api/records/${VERSION_ID}/files/flexdamage-parameters-v1.0.0-alpha.zip/content"
```

**Python:**
```python
import requests

VERSION_ID = 19199919  # specific version DOI
FILENAME = "flexdamage-parameters-v1.0.0-alpha.zip"

r = requests.get(f"https://zenodo.org/records/{VERSION_ID}/files/{FILENAME}")
with open(FILENAME, "wb") as f:
    f.write(r.content)
```

#### Browse all versions

```python
import requests

CONCEPT_ID = 19199918
r = requests.get(f"https://zenodo.org/api/records/{CONCEPT_ID}/versions")
for hit in r.json()["hits"]["hits"]:
    v = hit["metadata"]["version"]
    rid = hit["id"]
    date = hit["metadata"]["publication_date"]
    print(f"  v{v:<12} id={rid:<10} published={date}")
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

Rising, J. and Cadavid Sanchez, S. (2026). Flexible Damage Function Parameters for Climate Impact Assessment (Version 1.1.0) [Data set]. Zenodo. https://zenodo.org/records/19712742
