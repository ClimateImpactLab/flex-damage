# flex-damage

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19225233.svg)](https://doi.org/10.5281/zenodo.19225233)

[Documentation](https://climateimpactlab.github.io/flex-damage/) |
[Reports](https://c1587s.github.io/flex-damage-reports/)

> This is an internal tool for the Climate Impact Lab, designed to
> run on the University of Chicago RCC cluster (Midway) with access
> to CIL project data.

This library fits statistical emulators to represent projected climate
impacts. A distinct emulation function is calibrated for each region
of the globe. Globally common income elasticities capture the benefits
of income-driven adaptation. The approach uses OLS to estimate the
common income elasticity, and then uses OLS again to fit emulation
functions for each region given values of the income elasticity.

The estimated damage function for region i at time t is:

$$D_{it} = (\alpha_i T_t + \beta_i T_t^2) \cdot Y_{it}^{\gamma}$$

where D is the sector-specific impact, T is global mean temperature
anomaly from pre-industrial (degrees C), Y is GDP per capita, and
gamma is the income elasticity. Each region gets its own polynomial
coefficients (alpha, beta) capturing local climate sensitivity.

## Sectors

Parameters are estimated at impact region (~24,000 regions) and
country level. All current results use full adaptation.

**Agriculture (IR)**
- [x] Corn
- [x] Rice
- [x] Soy
- [x] Sorghum
- [x] Cassava
- [x] Wheat combined
- [x] Wheat spring
- [x] Wheat winter
- [ ] All calories (aggregate)

**Mortality (IR)**
- [ ] All-cause all-age
- [ ] Age-specific (0-4, 5-64, 65+)

**Energy (IR)**
- [ ] Total
- [ ] Electricity
- [ ] Non-electricity

**Labor (IR)**
- [ ] All
- [ ] High-risk
- [ ] Low-risk

Country-level aggregations are planned for all sectors.

## Installation
```bash
git clone https://github.com/ClimateImpactLab/flex-damage.git
cd flex-damage
pip install -e .
```

## Usage

Estimation is driven by YAML config files that specify the data
source, column mappings, and constraints for each sector. Example
configs are in `configs/`:
```bash
python scripts/run.py configs/agriculture/corn.yaml
```

This runs the full pipeline: data standardization, gamma estimation
via fixed effects, regional polynomial fitting, error term computation,
and parameter export. See the
[pipeline documentation](https://climateimpactlab.github.io/flex-damage/pipeline/)
for details on each step and the config format.

To generate a diagnostic report:
```bash
python scripts/render_report.py \
    --sector agriculture --subsector corn \
    --params-csv /path/to/regional_parameters.csv \
    --global-json /path/to/global_results.json \
    --source-data /path/to/source.zarr
```

## Estimated parameters

Pre-estimated parameters for all completed sectors are available
on Zenodo:

- **Latest version** (always current): https://doi.org/10.5281/zenodo.19199918
- **Version 1.1.0** (current release): https://zenodo.org/records/19712742
- **Version 1.0.0-alpha**: https://zenodo.org/records/19199919

Each parameter file contains 12 fields per region per gamma quantile:
alpha, beta, their variance-covariance matrix, spatial correlation,
error terms, and fit diagnostics. The format is described in the
[parameters documentation](https://climateimpactlab.github.io/flex-damage/parameters/).

## Documentation

Full methodology, pipeline reference, and API docs (work in progress):

> https://climateimpactlab.github.io/flex-damage/

Diagnostic reports for each estimated sector:

> https://c1587s.github.io/flex-damage-reports/

## License

CC-BY-4.0

Climate Impact Lab
