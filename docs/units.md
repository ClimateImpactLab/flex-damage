# Units & Methodology

This page documents the units of every variable in the FlexDamage parameter
bundles and the upstream sources they come from.

## Damage function

The flexible damage function is

$$D(T, Y) = (\alpha\,T + \beta\,T^2) \cdot Y^{\gamma}$$

where:

| Symbol | Meaning | Units |
|--------|---------|-------|
| $D$ | Outcome (damage). Sector-specific (see below) | sector-specific |
| $T$ | Local temperature anomaly | °C above 1986 to 2005 climatology |
| $Y$ | GDP per capita | 2005 USD PPP per capita |
| $\alpha$, $\beta$ | Region-specific linear and quadratic coefficients | $D$-units / °C and $D$-units / °C² |
| $\gamma$ | Globally-fitted income elasticity | dimensionless |

## Outcome units per sector

| Sector | Subsector | Outcome units | Description |
|--------|-----------|---------------|-------------|
| mortality | allcause | `deaths_per_100k` | Excess all-cause all-age deaths per 100,000 person-years attributable to climate change (full adaptation including adaptation costs); rebased to 2005 baseline + costs/100k. |
| labor | combined | `mins/worker/day` | Change in productive minutes per worker per day for all workers. Negative values indicate productivity loss; positive values indicate gain. |
| labor | high_risk | `mins/worker/day` | Same as combined, for the high-heat-exposure worker subpopulation. |
| labor | low_risk | `mins/worker/day` | Same as combined, for the low-heat-exposure worker subpopulation. |
| energy | total | `kWh_per_capita` | Climate-attributable change in total electricity + non-electricity energy consumption per capita, rebased to 2005 baseline. |
| energy | electricity | `kWh_per_capita` | As above, electricity only. |
| energy | non_electricity | `kWh_per_capita` | As above, non-electricity (e.g., natural gas, oil) only. |
| agriculture | corn / rice / soy / sorghum / cassava / wheat_combined / wheat_spring / wheat_winter | `log_yield_change` | Log change in crop yield (kg/Ha, log scale): $\log(\text{yield}_{\text{climate}}) - \log(\text{yield}_{\text{histclim}})$. |

Sign conventions:

- Mortality: positive $D$ means excess deaths.
- Labor: negative $D$ means productivity loss (typical sign under warming for hot countries); positive $D$ means small gain (occasional in temperate countries).
- Energy (total / electricity): positive $D$ means more energy consumed.
- Energy (non-electricity): typically negative under warming.
- Agriculture: negative $D$ means yield decline.

## Temperature units

- Variable: local-area-weighted temperature anomaly.
- Units: °C.
- Baseline: 1986 to 2005, computed per impact region from the GMFD reanalysis.

## Income units

- Variable: GDP per capita.
- Units: 2005 USD PPP per capita (real, purchasing-power-parity adjusted to 2005 base year).
- Source: SSP scenario projections from IIASA GDP and OECD Env-Growth IAMs.

## Resolution

Parameters are estimated and published at two resolutions:

- Impact Region (IR): ~24,000 sub-national regions defined by the CIL
  region hierarchy. The default scientific resolution.
- Country: 245 to 253 country codes (ISO3-equivalent), obtained by
  population-weighted aggregation from the underlying impact-region data.

## Files in each parameter bundle

For every `(sector, subsector, resolution)` combination on Zenodo:

| File | Contents |
|------|----------|
| `<sector>__<sub>__regional_parameters.csv` | Per-region parameters (one row per region × gamma quantile) |
| `<sector>__<sub>__global_results.json` | Globally-fitted gamma + 19 quantile values + R² |
| `<sector>__<sub>__metadata.json` | Full run config + summary statistics |
| `<sector>__<sub>__README.md` | Per-sector unit summary and provenance |

## Reproducing

Code: <https://github.com/ClimateImpactLab/flex-damage>.

The estimation and report pipeline is developed at the Climate Impact Lab
and runs on the University of Chicago Research Computing Center (RCC).
End-to-end reproduction (from raw projection-system Monte Carlo outputs
through to parameters and reports) requires access to the RCC and to the
shared Climate Impact Lab data directories on Midway. Without that
access, the codebase can still be inspected, and the published parameters
and reports can be downloaded directly from Zenodo and the reports site.
