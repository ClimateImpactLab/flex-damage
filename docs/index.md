# FlexDamage

Flexible Damage Functions are statistical emulators of the
high-resolution CIL projections, which can be incorporated into
other models to project climate impacts and damages. These damage
functions map global or national temperature and national income
levels to impact levels. This is useful to estimate impacts along
new socioeconomic and climate scenarios and for models for which
income and/or temperature are endogenous.

The estimated damage function is:

$$D_{it} = (\alpha_i T_t + \beta_i T_t^2) \cdot Y_{it}^{\gamma}$$

where $D_{it}$ is the impact for region $i$ at time $t$, $T_t$ is
the global mean temperature anomaly from pre-industrial, $Y_{it}$ is
GDP per capita, and $\gamma$ is the income elasticity.

The full projection equation with uncertainty is:

$$D_{it}^k = (\hat{\alpha}_{ik} T_t + \hat{\beta}_{ik} T_t^2) Y_{it}^{\hat{\gamma}_k} + \hat{\theta}_{ik} T_t Y_{it}^{\hat{\gamma}_k} + \hat{\phi}_{it}^k$$

where $k$ indexes the Monte Carlo draw, $\hat{\gamma}_k$ is one of
19 quantile values, $\hat{\alpha}_{ik}$ and $\hat{\beta}_{ik}$ are
drawn from the joint normal with the provided VCV (sigma11, sigma12,
sigma22), $\hat{\theta}_{ik}$ is drawn from $N(0, \zeta_{ik})$ (the
run-specific temperature-dependent error), and $\hat{\phi}_{it}^k$ is
drawn from $N(0, \eta_{ik})$ (the annual noise). $\rho_i$ controls
the correlation between regional and global $\theta$ draws.

## For users

The links below describe how to use and interpret the Flexible
Damage Function parameter files.

- [Parameters](parameters.md) -- format, download, and usage
- [Methodology](methodology.md) -- how the parameters were estimated
- [Reports](reports.md) -- diagnostic reports for each sector

## For developers

The links below describe FlexDamage, CIL's tool for creating
Flexible Damage Functions.

- [Pipeline](pipeline.md) -- running the estimation pipeline
- [API Reference](api.md) -- code documentation
