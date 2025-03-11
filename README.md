# flex-damage

`flex-damage` is an `R` package designed for calculating and analyzing flexible damage functions in integrated assessment models (IAMs).

## Mortality Damages Framework

This framework provides tools for analyzing climate data, focusing on mortality regression analysis and regional impact assessment. The framework processes climate-related datasets to evaluate temperature anomalies, mortality rates, and economic factors across different regions, climate models, and scenarios. 

## Project Structure


```{bash}
├── main.R                  # Main entry point for the analysis
├── R/
│   └── R/
│       ├── utils.R         # Utility functions
│       ├── data_processing.R # Data loading and preprocessing
│       ├── resources.R     # Hardware resource detection and allocation
│       ├── logging_setup.R # Logging configuration
│       ├── regional_analysis.R # Regional-level analysis functions
│       ├── scenario_analysis.R # Scenario analysis implementation
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

- **gdp_baseline_START/END**: Year range for GDP baseline calculation  
  - Used to normalize GDP across regions and time periods  

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
- Calculates gamma values for GDP normalization.

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
