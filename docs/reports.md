# Diagnostic Reports

A diagnostic report is generated for each sector/subsector. It
evaluates how well the fitted polynomials represent the underlying
simulation data, following the evaluation framework described in the
methodology.

## Parameter distributions

Eight-panel histogram showing the distribution of each estimated
parameter across all regions. For gamma, the histogram is generated
by sampling from the estimated $N(\hat{\gamma}, SE)$ distribution
(matching the R reference approach). For all other parameters, the
histogram shows the values across regions at the median gamma quantile.

What to look for: the shape of the distributions indicates how much
heterogeneity exists across regions. A wide alpha distribution means
regions differ substantially in their linear temperature response.
Beta concentrated near zero suggests the constraint binds frequently.

## Polynomial summary

Evaluates the fitted quadratic $D(T) = \alpha T + \beta T^2$ across
all regions:

- **Zero crossings**: At what temperature does the polynomial change
  sign? Computed as $T^* = -\alpha / \beta$. Regions where $\beta = 0$
  (constraint binds) have no crossing. Regions with $T^* > 20$ or
  $T^* < 0$ are outside the relevant temperature range.

- **Slope distribution**: The maximum slope of the polynomial between
  0 and 10 C, computed as $\max(|\alpha|, |\alpha + 20\beta|)$.
  Extreme slopes suggest regions where small temperature changes
  produce large impact changes.

- **Convexity**: Fraction of regions where the unconstrained estimate
  would have had $\beta > 0$ (and was therefore clipped). For
  agriculture with the $\beta \leq 0$ constraint, this indicates how
  often the constraint binds.

## Damage curves

Spaghetti plot of sampled regional polynomials, with the cross-region
mean and interquartile range overlaid. Plotted from 0 to 8 C
temperature anomaly.

The spread of curves indicates the range of regional responses. The
mean curve shows the "typical" damage function shape. Wide IQR bands
suggest substantial regional heterogeneity.

## Flex vs raw comparison

The core validation: does the fitted polynomial, evaluated with
scenario-specific temperature and income, reproduce the raw
simulation data?

For each scenario (RCP $\times$ SSP $\times$ period):

$$\hat{D}_i = (\alpha_i \bar{T} + \beta_i \bar{T}^2) \cdot \bar{Y}_i^{\gamma}$$

is compared to the raw simulation mean $\bar{N}_i$ for that region
and scenario.

Diagnostics reported per scenario:

- **Correlation**: Pearson correlation between flex and raw across
  regions. Values above 0.95 indicate the polynomial captures the
  spatial pattern well.

- **RMSE**: Root mean squared error. Scale depends on the outcome
  variable units.

- **Sign agreement**: Fraction of regions where flex and raw have
  the same sign. Sign disagreement means the polynomial predicts
  benefit where the simulation shows damage (or vice versa).

- **Maps**: Four maps per scenario showing the spatial distribution
  of flex predictions, raw means, their difference, and sign
  agreement. Red indicates damage or overprediction; blue indicates
  benefit or underprediction.

- **Worst predictions**: The 10 regions with the largest absolute
  residual between flex and raw.

Results are organized by period (2080-2099, 2060-2079) with tabs
for each RCP/SSP combination.

## Generating reports

```bash
python scripts/generate_report.py --sector agriculture --subsector corn \
    --results-dir /path/to/parameters \
    --format html
```

Reports are self-contained HTML files. Each report covers one
sector/subsector combination.

## Available reports

Reports are hosted separately at [c1587s.github.io/flex-damage-reports](https://c1587s.github.io/flex-damage-reports/).

### Agriculture (Impact Regions)

- [Cassava](https://c1587s.github.io/flex-damage-reports/agriculture_cassava_ir.html){target="_blank"}
- [Corn](https://c1587s.github.io/flex-damage-reports/agriculture_corn_ir.html){target="_blank"}
- [Rice](https://c1587s.github.io/flex-damage-reports/agriculture_rice_ir.html){target="_blank"}
- [Sorghum](https://c1587s.github.io/flex-damage-reports/agriculture_sorghum_ir.html){target="_blank"}
- [Soy](https://c1587s.github.io/flex-damage-reports/agriculture_soy_ir.html){target="_blank"}
- [Wheat Combined](https://c1587s.github.io/flex-damage-reports/agriculture_wheat_combined_ir.html){target="_blank"}
- [Wheat Spring](https://c1587s.github.io/flex-damage-reports/agriculture_wheat_spring_ir.html){target="_blank"}
- [Wheat Winter](https://c1587s.github.io/flex-damage-reports/agriculture_wheat_winter_ir.html){target="_blank"}

### Agriculture Value (Impact Regions)

- [Combined (main spec)](https://c1587s.github.io/flex-damage-reports/agriculture_value_combined_main_spec_ir.html){target="_blank"}

### Mortality (Impact Regions)

- [All-cause all-age](https://c1587s.github.io/flex-damage-reports/mortality_allcause_ir.html){target="_blank"}

### Labor (Impact Regions)

- [Combined](https://c1587s.github.io/flex-damage-reports/labor_combined_ir.html){target="_blank"}
- [High-risk](https://c1587s.github.io/flex-damage-reports/labor_high_risk_ir.html){target="_blank"}
- [Low-risk](https://c1587s.github.io/flex-damage-reports/labor_low_risk_ir.html){target="_blank"}

### Energy (Impact Regions)

- [Total](https://c1587s.github.io/flex-damage-reports/energy_total_ir.html){target="_blank"}
- [Electricity](https://c1587s.github.io/flex-damage-reports/energy_electricity_ir.html){target="_blank"}
- [Non-electricity](https://c1587s.github.io/flex-damage-reports/energy_non_electricity_ir.html){target="_blank"}

These open in a new tab as self-contained HTML files with interactive
plots, maps, and scenario comparisons.
