# Main Damage Function Analysis Engine
# Flexible damage function analysis with configurable parameters

#' Run complete damage function analysis
#' 
#' Executes the full flexible damage function analysis pipeline including data processing,
#' econometric estimation, regional calibration, and results generation. Works with any
#' impact sector (mortality, labor, agriculture, etc.) specified in the configuration.
#' 
#' @param config_path Character string. Path to YAML configuration file. If NULL, uses
#'   default configuration file from the package installation directory. The config file
#'   must specify data paths, impact variables, analysis scenarios, and output settings.
#'   
#' @return List containing analysis results and metadata:
#' \itemize{
#'   \item \code{config}: Configuration object used for the analysis
#'   \item \code{output_directory}: Path to results directory with timestamp  
#'   \item \code{regional_results}: Data frame of regional damage function coefficients
#'   \item \code{global_results}: Global adaptation parameter estimates and statistics
#'   \item \code{data_summary}: Summary statistics of processed input data
#' }
#' 
#' @details 
#' The analysis implements a two-stage econometric framework:
#' \enumerate{
#'   \item \strong{Global Stage}: Estimates income elasticity of adaptation (γ) using 
#'         fixed effects regression across all regions and time periods
#'   \item \strong{Regional Stage}: Calibrates quadratic temperature-damage functions 
#'         for each region using the global adaptation parameter
#' }
#' 
#' Output files are saved to a timestamped directory containing:
#' \itemize{
#'   \item Regional polynomial coefficients (main results)
#'   \item Global adaptation parameter statistics  
#'   \item Diagnostic plots and residual analysis
#'   \item Comparison tables and F2-style projections (if enabled)
#'   \item Data summary and model validation metrics
#' }
#' 
#' @examples
#' \dontrun{
#' # Run with default configuration
#' results <- run_damage_analysis()
#' 
#' # Run with custom configuration
#' results <- run_damage_analysis("mortality_config.yaml")
#' 
#' # Access results
#' print(results$output_directory)
#' head(results$regional_results)
#' print(paste("Adaptation elasticity:", round(results$global_results$gamma_mu, 3)))
#' 
#' # Load saved results later
#' coeffs <- read.csv(file.path(results$output_directory, "regional_polynomials.csv"))
#' }
#' 
#' @seealso 
#' \code{\link{load_config}} for configuration file format
#' \code{\link{generate_comparison_tables}} for generating additional output tables
#' @export
run_damage_analysis <- function(config_path = NULL) {
  
  # Load configuration
  config <- load_config(config_path)
  
  # Get all settings from config
  data_path <- config$data$data_path
  impact_var <- config$data$impact_variable
  sector <- config$data$sector
  output_dir <- config$output$output_dir
  analysis_name <- paste0(sector, "_", config$output$analysis_name)
  
  # Load and process data
  cat("\n=== Loading and Processing Data ===\n")
  raw_data <- load_damage_data(data_path, impact_var, config)
  processed_data <- process_damage_data(raw_data, config)
  
  # Set up output directory structure
  base_output_dir <- setup_output_directory(output_dir, analysis_name, config)
  
  # Run analysis for each scenario combination
  all_results <- list()
  scenarios <- expand.grid(
    gamma_filter = config$scenarios$gamma_filter,
    weighting = config$scenarios$weighting,
    stringsAsFactors = FALSE
  )
  
  cat("\n=== Running Analysis Scenarios ===\n")
  cat("Total scenarios:", nrow(scenarios), "\n\n")
  
  for (i in 1:nrow(scenarios)) {
    gamma_filter <- scenarios$gamma_filter[i]
    weighting <- scenarios$weighting[i]
    use_weights <- (weighting == "population_weighted")
    
    cat("Scenario", i, "of", nrow(scenarios), ":", gamma_filter, "-", weighting, "\n")
    
    # Run scenario analysis
    scenario_results <- run_scenario_analysis(
      data = processed_data,
      gamma_filter = gamma_filter,
      use_weights = use_weights,
      config = config,
      base_output_dir = base_output_dir,
      impact_var = impact_var
    )
    
    # Store results
    scenario_key <- paste(gamma_filter, weighting, sep = "_")
    all_results[[scenario_key]] <- scenario_results
  }
  
  # Generate F2 tables if requested (skip other tables for F2-only generation)
  if (config$output_files$generate_tables && 
      !is.null(config$output_files$f2_table_settings$generate_f2_table) &&
      config$output_files$f2_table_settings$generate_f2_table) {
    cat("\n=== Generating F2 Tables ===\n")
    generate_f2_tables_only(
      output_dir = base_output_dir,
      config = config,
      raw_data_path = data_path
    )
  } else if (config$output_files$generate_tables) {
    cat("\n=== Generating Comparison Tables ===\n")
    generate_comparison_tables(
      output_dir = base_output_dir,
      config = config,
      raw_data_path = data_path
    )
  }
  
  cat("\n=== Analysis Complete ===\n")
  cat("Results saved to:", base_output_dir, "\n")
  
  return(list(
    results = all_results,
    output_directory = base_output_dir,
    config = config,
    data_summary = list(
      total_rows = nrow(processed_data),
      regions = length(unique(processed_data$region)),
      years = range(processed_data$year),
      impact_variable = impact_var
    )
  ))
}

#' Set up simplified output directory structure
#' 
#' Creates a compact directory with config info embedded in name
#' 
#' @param output_dir Base output directory
#' @param analysis_name Analysis name
#' @param config Configuration list
#' @return Base output directory path
setup_output_directory <- function(output_dir, analysis_name, config) {
  
  # Create compact directory name with key config info
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  
  # Extract key config elements for directory name
  gamma_filter <- paste(config$scenarios$gamma_filter, collapse = "_")
  weighting <- paste(config$scenarios$weighting, collapse = "_")
  impact_var <- gsub("[^A-Za-z0-9]", "", config$data$impact_variable)  # Clean variable name
  
  # Compact directory name: analysis_impact_gamma_weighting_timestamp
  dir_name <- paste0(analysis_name, "_", impact_var, "_", 
                     gsub("_gamma_values", "", gamma_filter), "_",
                     gsub("_weighted", "", weighting), "_", timestamp)
  
  base_dir <- file.path(output_dir, dir_name)
  
  # Simple flat structure - no deep nesting
  dir.create(base_dir, recursive = TRUE, showWarnings = FALSE)
  
  cat("Output directory created:", base_dir, "\n")
  
  return(base_dir)
}

#' Run analysis for a single scenario
#' 
#' Runs analysis for a single scenario configuration
#' 
#' @param data Processed data
#' @param gamma_filter Gamma filtering approach  
#' @param use_weights Whether to use population weights
#' @param config Configuration list
#' @param base_output_dir Base output directory
#' @param impact_var Impact variable name for labeling
#' @return Analysis results
run_scenario_analysis <- function(data, gamma_filter, use_weights, config, 
                                base_output_dir, impact_var) {
  
  # Set weights based on weighting scenario
  weights <- if(use_weights) ifelse(!is.na(data$population), data$population, 1) else rep(1, nrow(data))
  
  # Estimate gamma using fixed effects model
  if (config$modeling$augmented_fe) {
    # Augmented model (not commonly used)
    mod <- lfe::felm(log_delta_impact ~ delta_temp + I(delta_temp^2) + lgdp_delta | region + year | 0 | region,
                     data = data, weights = weights)
  } else {
    # Standard model
    mod <- lfe::felm(log_delta_impact ~ loggdppc | group + year | 0 | group + year,
                     data = data, weights = weights)
  }
  
  # Calculate gamma statistics
  gamma <- list(
    mu = mod$coefficients[1],
    se = mod$cse[1],
    values = qnorm(seq(0.05, 0.95, by=0.05), mod$coefficients[1], mod$cse[1])
  )
  
  # Filter gamma values based on scenario
  if (gamma_filter == "positive_gamma_only") {
    gamma$values <- gamma$values[gamma$values > 0]
    gamma$mu <- mean(gamma$values, na.rm = TRUE)
    gamma$se <- sd(gamma$values, na.rm = TRUE) / sqrt(length(gamma$values))
  }
  
  # Global analysis
  global_results <- run_global_analysis(data, gamma, use_weights)
  
  # Save all results in flat directory structure
  save_scenario_results(gamma, global_results, base_output_dir, impact_var, config)
  
  # Run regional analysis (saves directly to base directory)
  regional_results <- run_regional_analysis(data, gamma, global_results$globaldf, 
                                          base_output_dir, config, impact_var)
  
  return(list(
    gamma = gamma,
    global_results = global_results,
    regional_results = regional_results,
    main_model = mod
  ))
}