# flex-damage

`flex-damage` is an `R` package designed for calculating and analyzing flexible damage functions in integrated assessment models (IAMs).

## Mortality Damages Framework

This framework fits statistical emulators to represent projected climate impacts. A distinct emulation function is calibrated for each region of the globe. Globally common income elasticities capture the benefits of income-driven adaptation. The approach uses OLS to estimate the common income elasticity, and then uses OLS again to fit emulation functions for each region given values of the income elasticity.

The approach is currently setup for all-cause all-age mortality impacts.

## Project Structure


```{bash}
├── main.R                  # Main entry point for the analysis
├── R/
│   └── R/
│       ├── utils.R         # Utility functions
│       ├── data_processing.R # Data loading and preprocessing
│       ├── resources.R     # Hardware resource detection and allocation
│       ├── logging_setup.R # Logging configuration
│       ├── regional_analysis.R # # Calibration of each region-specific emulator
│       ├── scenario_analysis.R # Scenario analysis and calibration of income elasticity (gamma)
│       └── results.R       # Functions for saving and visualizing results
└── data/
    └── mortality_regression_full_mc.csv # Input data file

```

## Input Data Format
The expected input CSV should contain the following required columns:

- `region`: Region identifier (usually ISO country code)
- `year`: Year of the observation
- `batch`: Batch identifier for Monte Carlo simulations
- `gcm`: Global Climate Model identifier
- `model`: Model identifier
- `rcp`: Representative Concentration Pathway scenario
- `ssp`: Shared Socioeconomic Pathway scenario
- `adjusted_mortality`: Mortality data
- `anomaly`: Temperature anomaly
- `total_population`: Population data
- `gdppc`: GDP per capita

## Usage
1. Ensure your data file is in the expected format and location (`data/mortality_regression_full_mc.csv`).
2. Configure the parameters in `main.R` according to your analysis needs.
3. Run the main script:
   ```r
    ("main.R")
    ```

## Configuration Options
The main script includes several configurable parameters:

- **gamma_filter**: Filter method for gamma values  
  - `"all_gamma_values"`: Use all gamma values in the analysis  
  - `"positive_gamma_only"`: Restrict to positive gamma values only  

- **weighting**: Analysis weighting approach  
  - `"population_weighted"`: Weight by population  
  - `"unweighted"`: No weighting  

- **collapse_batch**: Whether to aggregate data during loading (`TRUE/FALSE`)  
  - If `TRUE`, aggregates data by region, year, gcm, model, rcp, and ssp  
  - If `FALSE`, maintains separate batch-level data  

- **parallel_processing**: Enable parallel computation (`TRUE/FALSE`)  

- **n_cores**: Number of CPU cores to use for parallel processing  

- **test_mode**: Run in test mode with limited regions (`TRUE/FALSE`)  
  - When `TRUE`, only processes 10 regions (prioritizing USA and CHN)  

- **save_regional_results**: Save regional analysis results to files (`TRUE/FALSE`)  

- **create_regional_plots**: Generate plots from regional analysis (`TRUE/FALSE`)  



## Output Structure
The analysis generates outputs in a timestamped directory structure:

```{bash}
results/
└── collapseBatch_[TRUE/FALSE]_groupBy_[grouping_dimension]/
    ├── base_model/
    │   ├── main_model_coefficients.csv
    │   └── data_summary.txt
    ├── analysis_scenarios/
    │   └── [gamma_filter]/
    │       └── [weighted/unweighted]/
    │           ├── gamma_statistics.csv
    │           ├── global_analysis.csv
    │           ├── global_model_coefficients.csv
    │           ├── regional_polynomials.csv
    │           └── regional_alpha_distribution.pdf
    └── logs/
        └── analysis_log.txt
```

## Analysis Process
The framework follows these steps:

### Environment Setup
- Detects available hardware resources and sets up the working environment.

### Data Loading & Processing
- Validates and loads the CSV data.
- Creates derived variables (log transformations, GDP deltas).
- Performs grouping and normalization.

### Global Model Estimation
- Estimates overall relationship between mortality, temperature, and GDP.
- Calibrates the income elasticity parameter (gamma), which reflects adaptation capacity.
- Gamma is used to normalize mortality impacts by removing income-driven adaptation effects.

### Regional Analysis
- Processes data on a per-region basis.
- Normalizes mortality using gamma values.
- Fits regional regressions with temperature variables.
- Forces model convexity when necessary.
- Calculates residuals and correlations with global models.

### Results Output
- Saves model coefficients and statistics.
- Generates diagnostic plots.
- Provides comprehensive logging.

## Extending the Framework
The framework is designed to be modular and extensible:

- To modify the base model, update the `custom_base_model_fn` function in `main.R`.
- To add new analysis scenarios, extend the `run_scenario_analysis` function in `scenario_analysis.R`.
- To process additional data columns, update the `required_columns` list in `main.R`.

## Troubleshooting
Common issues and solutions:

- **Missing columns error**: Ensure your input CSV contains all required columns.
- **Memory limitations**: Reduce `n_cores` or use `collapse_batch = TRUE` for large datasets.
- **Platform-specific issues**: Resource detection may behave differently across operating systems.

## Technical Notes
- The framework uses GDP normalization to control for economic factors when analyzing climate impacts.
- Regional analysis applies quadratic models for temperature response.
- Convexity constraints are applied when necessary.
- Residual analysis is performed to evaluate model fit.
- Progress tracking uses Unicode spinners for visual feedback.

## Result Analysis and Visualization

After running the main analysis, you can use the `automated_reports_alphaFit.R` script to generate comprehensive reports and visualizations from the regional polynomial results:

```{bash}
├── automated_reports_alphaFit.R  # Script for generating reports from analysis results
```

## Report Generation Features

The report generator provides different types of analysis:

- **Basic Coefficient Analysis**: Examines the distribution of coefficients and creates visualizations of regional damage functions.
- **Zero Crossing Analysis**: Identifies temperature thresholds where damage functions cross zero.
- **Convexity Analysis**: Evaluates the proportion of regions with convex responses to temperature changes.
- **Prediction Evaluation**: Compares predicted values against reported data to assess model performance.

## Using the Report Generator

1. Configure the report options at the top of `automated_reports_alphaFit.R`:

    ```{r}
    # Enable or disable specific report types
    generate_basic_report <- TRUE      # Basic coefficient analysis and plots
    generate_prediction_report <- TRUE # Prediction vs actual analysis
    generate_pdf_report <- TRUE        # Combined PDF report of all results

    # Input/output configuration
    scale_factor <- 1e5                # Scaling factor for coefficients
    results_path <- "results/collapseBatch_FALSE_groupBy_year_rcp_ssp_model_gcm_batch/analysis_scenarios/all_gamma_values/unweighted"
    input_file <- file.path(results_path, "regional_polynomials.csv")
    input_data_csv <- "data/mortality_regression_full_mc.csv"  # Original data for prediction analysis

    # Set GDP baseline years
    gdp_baseline_start <- 2010
    gdp_baseline_end <- 2020
    # Set batch collapse option
    collapse_batch <- FALSE
    # Monte Carlo simulation parameters for prediction analysis
    n_draws <- 100              
    ```

2. Run the script after completing the main analysis:
    ```{r}
    source("automated_reports_alphaFit.R")
    ```
## Report Outputs

The script generates outputs in an organized directory structure:

```{bash}
results/.../alphaFitReport/
├── figures/
│   ├── regional_damage_function.pdf
│   ├── zero_crossings_histogram.pdf
│   ├── slope_histogram.pdf
│   ├── scatter_plot_predicted_vs_reported.pdf
│   ├── scatter_plot_predicted_mean_vs_reported.pdf
│   └── worst_offenders_top5.pdf
├── tables/
│   ├── summary_statistics.csv
│   ├── zero_crossings_distribution.csv
│   ├── slope_distribution.csv
│   ├── convex_polynomial_distribution.csv
│   ├── correlation_values.csv
│   └── r2_values.csv
└── damage_function_report.pdf
```