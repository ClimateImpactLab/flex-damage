# Methodology

## The damage function

The damage function relates sector-specific impacts to temperature
and income:

$$D_{it} = (\alpha_i T_t + \beta_i T_t^2) \cdot Y_{it}^{\gamma}$$

Each region has its own polynomial ($\alpha_i$, $\beta_i$) capturing
how sensitive it is to temperature. The global parameter $\gamma$
captures how income moderates impacts: if $\gamma < 0$, richer
regions experience less damage.

This differs from approaches like Carleton et al. (2022), which use
time-varying global coefficients. Here, spatial heterogeneity is
explicit through region-specific coefficients, and income effects
are captured by a single elasticity rather than explicit adaptation
pathways.

## Projection equation

The full projection equation with uncertainty, used for Monte Carlo
sampling, is:

$$D_{it}^k = (\hat{\alpha}_{ik} T_t + \hat{\beta}_{ik} T_t^2) Y_{it}^{\hat{\gamma}_k} + \hat{\theta}_{ik} T_t Y_{it}^{\hat{\gamma}_k} + \hat{\phi}_{it}^k$$

where $k$ indexes the Monte Carlo draw, $\hat{\gamma}_k$ is one of
19 quantile values, $\hat{\alpha}_{ik}$ and $\hat{\beta}_{ik}$ are
drawn from the joint normal with the provided VCV (sigma11, sigma12,
sigma22), $\hat{\theta}_{ik}$ is drawn from $N(0, \zeta_{ik})$ (the
run-specific temperature-dependent error), and $\hat{\phi}_{it}^k$ is
drawn from $N(0, \eta_{ik})$ (the annual noise). $\rho_i$ controls
the correlation between regional and global $\theta$ draws.

## Estimation steps

### 1. Data standardization

Raw simulation data (from Monte Carlo runs across GCMs, RCPs, and
SSPs) is standardized into a fixed 9-column parquet: region, year,
y, T, log_income, w, sdev, scenario, y_sign.

**Code**: [`standardize()`](https://climateimpactlab.github.io/flex-damage/api/#standardize)

### 2. Income elasticity (gamma)

Taking logs of the damage function isolates $\gamma$:

$$\log N_{it} = \sum_k \theta_{i,k}(T_t) + \gamma \log Y_{it} + \delta_t$$

The non-parametric temperature terms are absorbed by fixed effects
(sign $\times$ region $\times$ temperature bin), and year fixed
effects control for time trends.

Standard errors are clustered two-way by entity group and year.
We extract 19 quantiles (5% through 95%) from
$N(\hat{\gamma}, SE(\hat{\gamma}))$.

Observations where the outcome is negative are assigned to separate
fixed-effect groups. Values below the 5th percentile of $|N|$ are
dropped.

**Code**: [`estimate_gamma()`](https://climateimpactlab.github.io/flex-damage/api/#estimate_gamma)

### 3. Global polynomial

Population-weighted global averages by year and scenario are fit
with a quadratic:

$$\bar{N}_t / \bar{Y}_t^{\gamma} = \bar{\delta} + \bar{\alpha} T_t + \bar{\beta} T_t^2 + \bar{\epsilon}_t$$

The residuals $\bar{\epsilon}_t$ are saved for computing the spatial
correlation parameter $\rho$.

### 4. Regional polynomials

For each gamma quantile, the outcome is normalized by the income
effect and fit per region:

$$N_{it} / Y_{it}^{\gamma} = \delta_i + \alpha_i T_t + \beta_i T_t^2 + \epsilon_{it}$$

Sufficient statistics are computed via a single SQL GROUP BY query,
then solved as a batch of 3x3 linear systems in numpy. Constraints
are config-driven: $\beta \leq 0$ for agriculture (concavity),
$\beta \geq 0$ for mortality (convexity).

The intercept $\delta_i$ is dropped from the output: at
pre-industrial temperatures ($T = 0$), damage is zero.

**Code**: [`fit_regional_polynomials()`](https://climateimpactlab.github.io/flex-damage/api/#fit_regional_polynomials)

### 5. Error terms

Three additional uncertainty components:

**$\rho_i$**: Pearson correlation between regional and global polynomial
residuals. Maintains spatial covariance in Monte Carlo draws.

**$\zeta_{ik}$**: Temperature-dependent error scale, fit without
intercept: $E_{it} = \zeta_{ik} T_t + \phi_{it}$. Zero at
pre-industrial by construction.

**$\eta_{ik}$**: Standard deviation of $\phi_{it}$.

**Code**: [`compute_all_error_terms()`](https://climateimpactlab.github.io/flex-damage/api/#compute_all_error_terms)

### 6. Output

Each row contains 12 fields. `region` identifies the location. `gamma` is the income elasticity quantile value for this row (there are 19 rows per region, one per quantile). `alpha` and `beta` are the linear and quadratic temperature coefficients in the polynomial $D(T) = \alpha T + \beta T^2$. The variance-covariance matrix of $(\alpha, \beta)$ is given by `sigma11` (variance of alpha), `sigma12` (covariance), and `sigma22` (variance of beta), enabling joint uncertainty sampling. `rho` is the correlation between regional and global polynomial residuals, used to maintain spatial covariance in Monte Carlo draws. `zeta` is the temperature-dependent error scale and `eta` is the residual noise standard deviation; together they describe the prediction uncertainty that grows with temperature. `rsqr1` measures the polynomial fit quality and `rsqr2` measures the error model fit.

## Comparison methodology (flex vs raw)

For validation, the fitted damage function is compared to the raw
simulation data under specific scenarios (RCP $\times$ SSP $\times$
period). For a given scenario:

$$\hat{D}_i = (\alpha_i \bar{T} + \beta_i \bar{T}^2) \cdot \bar{Y}_i^{\gamma}$$

where $\bar{T}$ and $\bar{Y}_i$ are scenario-specific averages. This
is compared to the raw simulation mean per region. The comparison
reports correlation, RMSE, sign agreement, and identifies regions
where the polynomial fit diverges most from the simulation data.

## References

- Carleton, T. et al. (2022). Valuing the Global Mortality Consequences
  of Climate Change. *Quarterly Journal of Economics*.
- Hsiang, S. et al. (2017). Estimating economic damage from climate
  change in the United States. *Science*.
