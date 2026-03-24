# FlexDamage

FlexDamage fits region-specific damage functions from projected climate
impact data, for use in integrated assessment models. It estimates the
relationship between temperature, income, and sector-specific impacts
at multiple spatial resolutions.

The estimated damage function is:

$$M_{it} = (\alpha_i T_t + \beta_i T_t^2) \cdot Y_{it}^{\gamma}$$

where $M_{it}$ is the impact for region $i$ at time $t$, $T_t$ is
the global mean temperature anomaly from pre-industrial, $Y_{it}$ is
GDP per capita, and $\gamma$ is the income elasticity.

## Documentation

- [Methodology](methodology.md) — estimation procedure and model specification
- [Parameters](parameters.md) — output file format and Zenodo downloads
- [Pipeline](pipeline.md) — running the estimation pipeline
- [Reports](reports.md) — diagnostic report contents
- [API Reference](api.md) — function documentation
