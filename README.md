# Flexible Damage Function Parameters for Climate Impact Assessment

Version 1.0.0-alpha

## Authors

James Rising (jarising@gmail.com)
Sebastian Cadavid Sanchez (scadavidsanchez@uchicago.edu)
Climate Impact Lab

## Abstract

This dataset provides econometrically estimated parameters for climate damage
functions covering multiple economic sectors. The parameters relate temperature
anomalies to economic impacts while accounting for income-dependent adaptation,
enabling their use in integrated assessment models and social cost of carbon
calculations.

The estimation follows a two-stage procedure. First, a global income elasticity
parameter (gamma) is estimated via fixed-effects regression on binned
temperature-impact data. Second, region-specific polynomial coefficients are
estimated conditional on draws from the income elasticity distribution. This
approach propagates uncertainty from the global estimation through to regional
parameters.

## Damage Function Specification

The damage function takes the form:

    M_it = (alpha_i * T_t + beta_i * T_t^2) * Y_it^gamma

where:

- M_it is the impact for region i at time t
- T_t is global mean temperature anomaly from pre-industrial (degrees C)
- Y_it is GDP per capita (2020 USD PPP)
- gamma is the income elasticity of damages
- alpha_i, beta_i are region-specific polynomial coefficients

The income elasticity gamma is estimated globally using a fixed-effects
specification that controls for region-by-temperature-bin and year effects.
Standard errors are clustered two-way by region-temperature-bin and year
following Cameron, Gelbach, and Miller (2011).

## Data Description

| Sector | Subsector | Resolution | gamma | SE(gamma) | Regions | R^2 |
|--------|-----------|------------|-------|-----------|---------|-----|
| Agriculture | Cassava | IR | 0.0060 | 0.0015 | -- | 0.911 |
| Agriculture | Corn | IR | 0.0323 | 0.0008 | -- | 0.967 |
| Agriculture | Rice | IR | 0.0694 | 0.0020 | -- | 0.964 |
| Agriculture | Sorghum | IR | 0.0756 | 0.0024 | -- | 0.958 |
| Agriculture | Soy | IR | -0.0086 | 0.0010 | -- | 0.981 |
| Agriculture | Wheat Combined | IR | -0.0392 | 0.0016 | -- | 0.778 |
| Agriculture | Wheat Spring | IR | -0.0326 | 0.0017 | -- | 0.740 |
| Agriculture | Wheat Winter | IR | -0.0182 | 0.0010 | -- | 0.961 |

Resolution codes:

- IR = Impact Regions (24,326 globally)
- Country = national-level aggregation

## File Organization

The archive contains sector-specific subdirectories organized by spatial
resolution:

    flexdamage-parameters-v1.0.0-alpha/
    |-- README.md
    |-- manifest.json
    |-- shapefiles/
    |   |-- impact_regions.shp
    |   |-- impact_regions.shx
    |   |-- impact_regions.dbf
    |   |-- impact_regions.prj
    |-- agriculture/
    |   |-- README.md
    |   |-- ir/
    |       |-- corn/
    |       |   |-- regional_parameters.csv
    |       |   |-- global_results.json
    |       |   |-- metadata.json
    |       |-- rice/
    |           |-- ...

## Shapefile

The shapefiles/ directory contains the Impact Regions shapefile for mapping
parameters to geographic locations. The 'hierid' field matches the 'region'
column in the parameter CSV files. Load with geopandas:

    import geopandas as gpd
    gdf = gpd.read_file("shapefiles/impact_regions.shp")

Each subsector directory contains three files:

1. regional_parameters.csv -- Regional polynomial coefficients with 12 columns
   and 19 rows per region (one per gamma quantile).

2. global_results.json -- Results from income elasticity estimation including
   point estimate, standard error, R^2, sample size, and 19 quantile values.

3. metadata.json -- Run configuration including estimation settings, constraint
   specifications, and summary statistics.

## Variable Definitions

The regional parameters file contains the following columns:

| Variable | Description |
|----------|-------------|
| region   | Region identifier (Impact Region ID or ISO3 code) |
| gamma    | Income elasticity quantile value |
| alpha    | Linear temperature coefficient |
| beta     | Quadratic temperature coefficient |
| sigma11  | Var(alpha) |
| sigma12  | Cov(alpha, beta) |
| sigma22  | Var(beta) |
| rho      | Correlation with global residual process |
| zeta     | Temperature-dependent heteroskedasticity parameter |
| eta      | Residual standard deviation |
| rsqr1    | R^2 of polynomial fit |
| rsqr2    | R^2 of heteroskedasticity model |

## Usage Notes

For deterministic applications, select the median gamma quantile (row 10 of 19
for each region). For Monte Carlo simulations, sample across all 19 quantiles
to propagate income elasticity uncertainty.

The variance-covariance parameters (sigma11, sigma12, sigma22) enable joint
sampling of alpha and beta for uncertainty quantification.

## License

CC-BY-4.0

## Contact

Climate Impact Lab
Institution: University of Chicago
Repository: https://github.com/ClimateImpactLab/flexdamage
