# flexdamage: Flexible Damage Functions

`flex-damage` is an `R` package designed for calculating and analyzing flexible damage functions in integrated assessment models (IAMs).

## Mortality Damages Framework

This framework fits statistical emulators to represent projected climate impacts. A distinct emulation function is calibrated for each region of the globe. Globally common income elasticities capture the benefits of income-driven adaptation. The approach uses OLS to estimate the common income elasticity, and then uses OLS again to fit emulation functions for each region given values of the income elasticity.

The approach is currently setup for all-cause all-age mortality impacts.

## Installation

**From GitHub (Recommended):**
```r
# Install directly from GitHub
install.packages("devtools")
devtools::install_github("ClimateImpactLab/flex-damage", subdir = "flex-damage")
```

**From CRAN (Coming Soon):**
```r
# Will be available once published to CRAN
install.packages("flexdamage")
```

**Local Development:**
```r
# If working with the source code locally
source("install.R")  # From inside the flex-damage directory
```

## Quick Start

### Basic Analysis

```r
library(flexdamage)

# Step 1: Edit the default config file to set your paths and variables
# (or create a new one - see next section)

# Step 2: Run analysis (everything comes from config file)
results <- run_damage_analysis()
```

### Custom Configuration

```r
# Create configuration template
create_analysis_config("config.yaml")

# Edit config.yaml to set:
# - data_path: "/path/to/your/data.csv" 
# - impact_variable: "adjusted_mortality" (or your column name)
# - output_dir: "./results" (where to save)
# - analysis parameters

# Then run:
results <- run_damage_analysis(config_path = "config.yaml")
```

## Configuration File Setup

Your YAML config file needs these key settings:

```yaml
# Data settings  
data:
  data_path: "/project/cil/.../data.csv"
  impact_variable: "adjusted_mortality"  # or "labor_impact", etc.
  sector: "mortality"  # Used for output directory naming

# Output settings
output:
  output_dir: "./results"
  analysis_name: "damage_analysis"

# Analysis scenarios
scenarios:
  gamma_filter: 
    - "all_gamma_values"
  weighting:
    - "population_weighted"

# Output file settings
output_files:
  generate_tables: true
  scale_factor: 1e5  # For mortality per 100k
  regional_comparisons:  # Optional - for validation against reference values
    CHN:
      reference_values: [-6.4, 3.4]  # Reference values for 1°C, 2°C impacts
    USA:
      reference_values: [-12.7, -0.1]
    IND:
      reference_values: [12.0, 11.1]

# Other settings...
```

## Input Data Requirements

Your CSV data must contain these columns:
- `region`: Region identifier (e.g., ISO country codes)
- `year`: Year of observation
- `batch`: Batch identifier for Monte Carlo simulations  
- `gcm`: Global Climate Model identifier
- `model`: Model identifier
- `rcp`: Representative Concentration Pathway scenario
- `ssp`: Shared Socioeconomic Pathway scenario
- `anomaly`: Temperature anomaly
- `total_population`: Population data
- `gdppc`: GDP per capita
- `[your_impact_variable]`: Your impact variable (name specified in config)

## Output Structure and Results

When you run the analysis, it creates a **single compact directory** with config info in the name:

```
results/
└── damage_adjustedmortality_all_population_20241201_143022/  # Config info embedded in name
    ├── regional_polynomials.csv           # MAIN RESULTS: Regional damage functions
    ├── gamma_statistics.csv               # Adaptation parameter (gamma) stats  
    ├── gamma_values.csv                   # Gamma value distribution
    ├── global_analysis.csv                # Global aggregated results
    ├── global_model_coefficients.csv      # Global model fits
    ├── main_model_coefficients.csv        # Base model coefficients
    ├── parameter_distributions.pdf        # Diagnostic plots
    ├── adjusted_mortality_temp_relationship.pdf  # Impact-temperature plots
    ├── residuals_time.pdf                 # Residuals analysis
    ├── data_summary.txt                   # Data summary statistics
    ├── tables/                            # Comparison tables
    │   ├── scaled_coefficients.csv        # Coefficients scaled by factor
    │   ├── median_gamma_coefficients.csv  # Median gamma results
    │   ├── coefficient_summary.csv        # Summary statistics
    │   ├── regional_comparison.csv        # Regional comparisons with reference values
    │   └── formatted_regional_table.csv   # Publication-ready validation table
    └── estimated_scenarios/               # F2-style damage projection tables
        ├── SSP3_rcp85_low.csv             # F2 projections by scenario (if split_by_ssp: true)
        └── all_scenarios_low.csv          # Combined F2 projections (if split_by_ssp: false)
```

**Directory name format:** `analysis_[impact_var]_[gamma_filter]_[weighting]_[timestamp]`

### Key Output Files

**`regional_polynomials.csv`** - This is your main result file containing:
- `region`: Region identifier  
- `gamma`: Adaptation parameter value used
- `alpha`: Linear temperature coefficient
- `beta`: Quadratic temperature coefficient  
- `sigma11, sigma12, sigma22`: Coefficient variance-covariance matrix
- `rho`: Correlation with global residuals
- `zeta, eta`: Heteroskedasticity parameters
- `rsqr1, rsqr2`: R-squared values for models

**`gamma_statistics.csv`** - Adaptation parameter statistics:
- `mu`: Mean gamma (adaptation elasticity)
- `se`: Standard error
- `ci_lower, ci_upper`: Confidence intervals

**`global_analysis.csv`** - Population-weighted global results by year/scenario

### Using the Results

```r
# Load the main results (simple flat structure)
regional_results <- read.csv(file.path(results$output_directory, "regional_polynomials.csv"))

# Examine damage function coefficients
head(regional_results[, c("region", "alpha", "beta")])

# Load adaptation parameter
gamma_stats <- read.csv(file.path(results$output_directory, "gamma_statistics.csv"))
print(paste("Adaptation elasticity (gamma):", round(gamma_stats$mu, 3)))
```

## F2-Style Damage Projection Tables

The package can generate F2-style damage projection tables that reproduce the methodology from reference papers. These tables provide damage projections across time periods and scenarios.

### Generating F2 Tables

To enable F2 table generation, add the following to your config file:

```yaml
# Data settings
data:
  data_path: "/path/to/mortality_regression_full_mc.csv"
  temperature_data_path: "/path/to/meantas.csv"  # External temperature data
  impact_variable: "adjusted_mortality"
  sector: "mortality"

# F2 table generation settings
output_files:
  f2_table_settings:
    generate_f2_table: true
    split_by_ssp: true  # Creates separate files per SSP scenario
    include_ssps: ["SSP3"]  # Filter to specific scenarios
    include_rcps: ["rcp85"] 
    include_models: ["IIASA GDP"]  # "IIASA GDP" = low model, "OECD Env-Growth" = high model
    time_periods:
      "2020_2039": [2020, 2039]
      "2040_2059": [2040, 2059] 
      "2060_2079": [2060, 2079]
      "2080_2094": [2080, 2094]
      "2095_2100": [2095, 2100]
```

### Standalone F2 Table Generation

You can also generate F2 tables from existing results without re-running the full analysis:

```r
library(flexdamage)

# Configuration
config_path <- "path/to/mortality_config.yaml"
config <- load_config(config_path)

# Point to existing results directory
results_dir <- "path/to/existing/results/directory"
raw_data_path <- config$data$data_path

# Generate F2 tables
generate_comparison_tables(
  output_dir = results_dir,
  config = config,
  raw_data_path = raw_data_path
)
```

### F2 Table Output Format

F2 tables contain the following columns:
- `iso`: Region/country code
- `rcp`: RCP scenario (e.g., "rcp85")
- `ssp`: SSP scenario (e.g., "SSP3") 
- `model`: Economic model ("IIASA GDP" for low, "OECD Env-Growth" for high)
- `period`: Time period (e.g., "2020_2039")
- `year_center`: Center year of the period
- `TT`: Temperature anomaly (from external temperature data)
- `flextotal`: Flexible damage function projection
- `rawtotal`: Raw mortality average for the period
- `f2mort`, `f2total`: Reference values for validation (SSP3 2095-2100 only)

**Key Features:**
- Uses external temperature data (`meantas.csv`) for consistent temperature values
- Matches reference methodology for damage calculations
- Supports filtering by scenario, model, and time period
- Can split output by SSP or combine all scenarios

## Methodology

This package implements a two-stage econometric framework for estimating flexible damage functions:

### Stage 1: Global Adaptation Parameter Estimation
- Estimates income elasticity of climate adaptation (gamma) using fixed effects regression
- Accounts for regional and temporal heterogeneity in climate impacts
- Controls for economic development effects on damage vulnerability

### Stage 2: Regional Damage Function Calibration  
- Fits quadratic temperature-damage relationships for each region
- Normalizes impacts by estimated adaptation capacity (GDP^gamma)
- Enforces convexity constraints where economically justified
- Estimates uncertainty through variance-covariance matrices

### Weighting Options
The analysis supports both population-weighted and unweighted estimation:
- **Population-weighted**: Emphasizes regions with larger populations in global aggregation
- **Unweighted**: Treats all regions equally regardless of population size

### Damage Function Specification
The framework estimates regional damage functions of the form:
```
impact_it / (exp(lgdp_delta_it)^γ) = δ_i + α_i * T_t + β_i * T_t² + ε_it
```

Where:
- `impact_it`: Impact measure (e.g., adjusted_mortality) for region i at time t
- `exp(lgdp_delta_it)`: GDP per capita ratio relative to baseline period
- `T_t`: Temperature anomaly relative to baseline
- `γ`: Global adaptation elasticity (estimated via fixed effects regression)
- `δ_i`: Region-specific intercept (baseline impact level)
- `α_i, β_i`: Region-specific linear and quadratic temperature response coefficients
- `ε_it`: Regional error term correlated with global residuals

The left side normalizes impacts by economic adaptation capacity before fitting temperature-damage relationships. The intercept δ_i captures baseline impact levels independent of temperature.

## Examples

See the `examples/` directory:
- `mortality_example.R`: Complete working example
- `test_installation.R`: Installation test

## License

MIT License