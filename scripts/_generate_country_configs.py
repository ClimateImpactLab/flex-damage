#!/usr/bin/env python3
"""One-shot helper: generate the 14 country configs from per-sector templates."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = "/scratch/midway3/cadavidsanchez/flex-damages"

# (sector, subsector_ir, y_col, units, units_desc, beta_constraint, source_pattern)
# beta_constraint: ("max", 0) for concave (ag, labor); ("min", 0) for convex (energy, mortality)
SECTORS = []

# Labor: 3 subsectors, beta <= 0
for sub, ycol in [("combined", "labor_combined"),
                  ("high_risk", "labor_high_risk"),
                  ("low_risk", "labor_low_risk")]:
    SECTORS.append(dict(
        sector="labor",
        subsector_ir=sub,
        subsector_country=f"{sub}_country",
        y=ycol,
        units="portion",
        units_desc=f"dimensionless fraction of labor productivity for {sub.replace('_', ' ')} workers, rebased to 2005 baseline; population-weighted aggregation to country",
        beta_type="max", beta_value=0,
        source=f"{SCRATCH}/labor/country_keepmc_full/labor_aggregated_country_keepmc_full.parquet",
        adaptation="fulladapt",
    ))

# Energy: 3 subsectors, beta >= 0
for sub, ycol in [("total", "energy_total"),
                  ("electricity", "energy_electricity"),
                  ("non_electricity", "energy_non_electricity")]:
    SECTORS.append(dict(
        sector="energy",
        subsector_ir=sub,
        subsector_country=f"{sub}_country",
        y=ycol,
        units="kWh_per_capita",
        units_desc=f"kWh per capita for {sub.replace('_', ' ')}, rebased to 2005 baseline; pre-aggregated to country in projection system",
        beta_type="min", beta_value=0,
        source=f"{SCRATCH}/energy/country_keepmc_full/energy_aggregated_country_keepmc_full.parquet",
        adaptation="fulladapt",
    ))

# Agriculture: 8 crops, beta <= 0
for crop in ["corn", "rice", "soy", "sorghum", "cassava",
             "wheat_combined", "wheat_spring", "wheat_winter"]:
    SECTORS.append(dict(
        sector="agriculture",
        subsector_ir=crop,
        subsector_country=f"{crop}_country",
        y="log_yield_impact",
        units="physical",
        units_desc=f"log change in {crop.replace('_', ' ')} yield (population-weighted to country)",
        beta_type="max", beta_value=0,
        source=f"{SCRATCH}/agriculture/country_keepmc_full/agriculture_{crop}_aggregated_country_keepmc_full.parquet",
        adaptation="fulladapt",
        crop=crop,
    ))


TEMPLATE = """\
# =============================================================================
# FlexDamage v3 - {sector} {subsector_country} Country-Level Configuration
# =============================================================================
# Country-resolution analog of {subsector_ir}.yaml. Same estimation logic,
# different input parquet (country-aggregated) and output naming.

run:
  name: {sector}_{subsector_country}_ir
  description: "{sector} {subsector_ir} response estimation - Country resolution"

sector:
  name: {sector}
  subsector: {subsector_country}
  units: "{units}"
  units_description: "{units_desc}"
  adaptation: {adaptation}
  resolution: country

data:
  source: {source}
  format: parquet
  collapse_mc: false   # default: keep all MC draws

  columns:
    y: {y}
    temperature: temperature_anomaly
    income: gdppc
    weight: pop
    region: region
    year: year
    sdev: null
    scenario_columns:
      - rcp
      - ssp

  income_is_log: false

estimation:
  formula: "alpha * T + beta * T**2"

  gamma:
    method: fixed_effects
    backend: fixest        # R fixest (50-200x faster on big keep-MC datasets)
    temperature_bins: 0.5
    cluster_se: true
    include_sign_in_fe: true
    n_quantiles: 19
    trim_percentile: 0.05

  regional:
    min_observations: 5
    ridge_lambda: 1.0e-8

  constraints:
    - parameter: beta
      type: {beta_type}
      value: {beta_value}

output:
  results_dir: /project/cil/gcp/flex_damage_funcs/results/{sector}/{subsector_country}
  parameters_dir: /project/cil/gcp/flex_damage_funcs/parameters

execution:
  workers: 0
  memory_limit_gb: 60
"""


def main():
    out_count = 0
    for s in SECTORS:
        out_dir = ROOT / "configs" / s["sector"]
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{s['subsector_country']}.yaml"
        out_path.write_text(TEMPLATE.format(**s))
        print(f"  wrote {out_path.relative_to(ROOT)}")
        out_count += 1
    print(f"\nWrote {out_count} country configs")


if __name__ == "__main__":
    main()
