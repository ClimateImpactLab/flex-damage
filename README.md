# flex-damage

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19199918.svg)](https://doi.org/10.5281/zenodo.19199918)

[Documentation](https://climateimpactlab.github.io/flex-damage/paper.html) |
[Developer docs](https://climateimpactlab.github.io/flex-damage/) |
[Reports](https://c1587s.github.io/flex-damage-reports/) |
[Parameters on Zenodo](https://zenodo.org/records/19916065)

> Internal tool for the Climate Impact Lab. Runs on the University of
> Chicago RCC cluster (Midway) with access to CIL project data.
>
> This implementation is based on the original CIL FlexDamage code at
> [ClimateImpactLab/flexdamage](https://github.com/ClimateImpactLab/flexdamage/tree/main/src).

`flex-damage` fits statistical emulators of CIL climate impact projections.
Each region gets its own quadratic in temperature; a globally fitted income
elasticity captures adaptation. The damage function is

$$D_{it} = (\alpha_i T_t + \beta_i T_t^2) \cdot Y_{it}^{\gamma}$$

with $T$ in °C anomaly, $Y$ in 2005 USD PPP per capita, and outcome units
that depend on the sector. See the
[documentation](https://climateimpactlab.github.io/flex-damage/paper.html)
for methodology, per-sector units, and parameter format.

## Sectors

Released at impact-region (~24k regions) and country resolution:

- **Agriculture**: corn, rice, soy, sorghum, cassava, wheat (combined, spring, winter)
- **Mortality**: all-cause all-age
- **Labor**: combined, high-risk, low-risk
- **Energy**: total, electricity, non-electricity

## Quick start

```bash
git clone https://github.com/ClimateImpactLab/flex-damage.git
cd flex-damage
pip install -e .

# Run one sector end-to-end (estimation + parameter export)
python scripts/run.py configs/agriculture/corn.yaml
```

To regenerate the documentation site after editing docs:

```bash
bash scripts/deploy_docs.sh
```

## License

CC-BY-4.0. Climate Impact Lab.
