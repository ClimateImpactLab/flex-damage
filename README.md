# flex-damage

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19199919.svg)](https://doi.org/10.5281/zenodo.19199919)

[Documentation](https://climateimpactlab.github.io/flex-damage/) | [Reports](https://c1587s.github.io/flex-damage-reports/)

## Abstract

This dataset provides estimated parameters for climate damage functions covering
multiple economic sectors. The parameters relate temperature anomalies to economic
impacts while accounting for income-dependent adaptation, enabling their use in
integrated assessment models and social cost of carbon calculations.

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

## Usage Notes

For deterministic applications, select the median gamma quantile (row 10 of 19
for each region). For Monte Carlo simulations, sample across all 19 quantiles
to propagate income elasticity uncertainty.

The variance-covariance parameters (sigma11, sigma12, sigma22) enable joint
sampling of alpha and beta for uncertainty quantification.

## License

CC-BY-4.0

## Contact

Climate Impact Lab -- https://github.com/ClimateImpactLab/flex-damage
