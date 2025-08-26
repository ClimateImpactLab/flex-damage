# Table Generation Functions
# Reproduces f2_tables.R functionality within the flexdamage framework

#' Generate comparison tables with scaled coefficients
#' 
#' Creates comparison tables similar to f2_tables.R functionality
#' 
#' @param output_dir Base output directory where results are saved
#' @param config Configuration list containing scale_factor and other settings
#' @param raw_data_path Path to raw data file for comparisons
#' @param temperature_data_path Path to temperature data file (optional)
#' @export
generate_comparison_tables <- function(output_dir, config, raw_data_path = NULL, temperature_data_path = NULL) {
  
  if (!config$output_files$generate_tables) {
    return(invisible(NULL))
  }
  
  # Check if F2-only mode is enabled
  f2_only_mode <- !is.null(config$output_files$f2_table_settings$generate_f2_table) &&
                  config$output_files$f2_table_settings$generate_f2_table
  
  if (f2_only_mode) {
    cat("\n=== Generating F2 Tables ===\n")
    generate_f2_tables_direct(output_dir, config, raw_data_path)
    return(invisible(NULL))
  }
  
  cat("\n=== Generating Comparison Tables ===\n")
  
  # Create tables subdirectory
  tables_dir <- file.path(output_dir, "tables")
  dir.create(tables_dir, recursive = TRUE, showWarnings = FALSE)
  
  # Load and scale polynomial coefficients
  cat("Loading and scaling polynomial coefficients...\n")
  poly_file <- file.path(output_dir, "regional_polynomials.csv")
  
  if (!file.exists(poly_file)) {
    cat("Warning: regional_polynomials.csv not found. Skipping table generation.\n")
    return(invisible(NULL))
  }
  
  results_poly <- read.csv(poly_file)
  scale_factor <- as.numeric(config$output_files$scale_factor)
  
  cat("Data loaded. Rows:", nrow(results_poly), "Columns:", ncol(results_poly), "\n")
  cat("Scale factor:", scale_factor, "(class:", class(scale_factor), ")\n")
  
  # Ensure numeric columns
  numeric_cols <- c("alpha", "beta", "sigma11", "sigma12", "sigma22", "zeta", "eta")
  for (col in numeric_cols) {
    if (col %in% names(results_poly)) {
      results_poly[[col]] <- as.numeric(results_poly[[col]])
    }
  }
  
  # Scale coefficients
  results_scaled <- results_poly %>%
    mutate(
      alpha_scaled = alpha * scale_factor,
      beta_scaled = beta * scale_factor,
      sigma11_scaled = sigma11 * (scale_factor^2),
      sigma12_scaled = sigma12 * (scale_factor^2), 
      sigma22_scaled = sigma22 * (scale_factor^2),
      zeta_scaled = zeta * scale_factor,
      eta_scaled = eta * scale_factor
    )
  
  # Use median gamma coefficients
  results_median <- results_scaled[results_scaled$gamma == median(results_scaled$gamma),]
  
  cat("Coefficients loaded and scaled with factor:", scale_factor, "\n")
  
  # Save scaled coefficients table
  scaled_file <- file.path(tables_dir, "scaled_coefficients.csv")
  write.csv(results_scaled, scaled_file, row.names = FALSE)
  cat("Scaled coefficients saved to:", scaled_file, "\n")
  
  # Save median coefficients table
  median_file <- file.path(tables_dir, "median_gamma_coefficients.csv")
  write.csv(results_median, median_file, row.names = FALSE)
  cat("Median gamma coefficients saved to:", median_file, "\n")
  
  # Generate summary statistics table
  create_coefficient_summary_table(results_scaled, tables_dir, scale_factor)
  
  # Generate regional comparison table if raw data is available and comparisons are specified
  if (!is.null(raw_data_path) && file.exists(raw_data_path) && 
      !is.null(config$output_files$regional_comparisons) && 
      length(config$output_files$regional_comparisons) > 0) {
    create_regional_comparison_table(results_median, raw_data_path, tables_dir, config)
  }
  
  # Generate F2-style damage table if enabled
  if (!is.null(config$output_files$f2_table_settings$generate_f2_table) &&
      config$output_files$f2_table_settings$generate_f2_table &&
      !is.null(raw_data_path) && file.exists(raw_data_path)) {
    cat("Generating F2-style damage projection table for sector:", config$data$sector, "...\n")
    create_f2_damage_table(results_median, raw_data_path, tables_dir, config)
  }
  
  cat("Table generation complete. Results saved in:", tables_dir, "\n")
}

#' Generate F2 tables only (no other comparison tables)
#' 
#' Creates only F2-style damage projections, saves in results/estimated_scenarios/
#' 
#' @param output_dir Base output directory (results folder)
#' @param config Configuration list
#' @param raw_data_path Path to raw data file
#' @export
generate_f2_tables_only <- function(output_dir, config, raw_data_path = NULL) {
  
  if (!config$output_files$f2_table_settings$generate_f2_table) {
    return(invisible(NULL))
  }
  
  cat("\\n=== Generating F2 Tables Only ===\\n")
  
  # Load and scale polynomial coefficients
  cat("Loading polynomial coefficients...\\n")
  poly_file <- file.path(output_dir, "regional_polynomials.csv")
  
  if (!file.exists(poly_file)) {
    cat("Warning: regional_polynomials.csv not found. Skipping F2 table generation.\\n")
    return(invisible(NULL))
  }
  
  results_poly <- read.csv(poly_file)
  scale_factor <- as.numeric(config$output_files$scale_factor)
  
  # Ensure numeric columns
  numeric_cols <- c("alpha", "beta", "sigma11", "sigma12", "sigma22", "zeta", "eta")
  for (col in numeric_cols) {
    if (col %in% names(results_poly)) {
      results_poly[[col]] <- as.numeric(results_poly[[col]])
    }
  }
  
  # Scale coefficients
  results_scaled <- results_poly %>%
    dplyr::mutate(
      alpha_scaled = alpha * scale_factor,
      beta_scaled = beta * scale_factor,
      sigma11_scaled = sigma11 * (scale_factor^2),
      sigma12_scaled = sigma12 * (scale_factor^2), 
      sigma22_scaled = sigma22 * (scale_factor^2),
      zeta_scaled = zeta * scale_factor,
      eta_scaled = eta * scale_factor
    )
  
  # Use median gamma coefficients
  results_median <- results_scaled[results_scaled$gamma == median(results_scaled$gamma),]
  
  # Generate F2 damage table directly in results folder
  if (!is.null(raw_data_path) && file.exists(raw_data_path)) {
    cat("Generating F2-style damage projection table for sector:", config$data$sector, "...\\n")
    create_f2_damage_table_direct(results_median, raw_data_path, output_dir, config)
  }
  
  cat("F2 table generation complete.\\n")
}

#' Generate F2 tables directly (simplified version)
#' 
#' Just generates F2 tables in results/estimated_scenarios/, nothing else
#' 
#' @param output_dir Results directory
#' @param config Configuration list
#' @param raw_data_path Path to raw data
generate_f2_tables_direct <- function(output_dir, config, raw_data_path = NULL) {
  
  # Load and scale polynomial coefficients
  cat("Loading polynomial coefficients...\\n")
  poly_file <- file.path(output_dir, "regional_polynomials.csv")
  
  if (!file.exists(poly_file)) {
    cat("Error: regional_polynomials.csv not found in", output_dir, "\\n")
    return(invisible(NULL))
  }
  
  results_poly <- read.csv(poly_file)
  scale_factor <- as.numeric(config$output_files$scale_factor)
  
  # Ensure numeric columns
  numeric_cols <- c("alpha", "beta", "sigma11", "sigma12", "sigma22", "zeta", "eta")
  for (col in numeric_cols) {
    if (col %in% names(results_poly)) {
      results_poly[[col]] <- as.numeric(results_poly[[col]])
    }
  }
  
  # Scale coefficients
  results <- results_poly %>%
    dplyr::mutate(
      alpha = alpha * scale_factor,
      beta = beta * scale_factor,
      sigma11 = sigma11 * (scale_factor^2),
      sigma12 = sigma12 * (scale_factor^2),
      sigma22 = sigma22 * (scale_factor^2),
      zeta = zeta * scale_factor,
      eta = eta * scale_factor
    )
  
  # Use median gamma coefficients
  results.mu <- results[results$gamma == median(results$gamma),]
  
  # Generate F2 damage table
  if (!is.null(raw_data_path) && file.exists(raw_data_path)) {
    create_f2_damage_table_direct(results.mu, raw_data_path, output_dir, config)
  } else {
    cat("Skipping F2 table: raw data not found\\n")
  }
}

#' Create F2-style damage projection table
#' 
#' Creates damage projection tables compatible with F2-style analysis methodology.
#' Works with any impact sector (mortality, labor, etc.) as specified in the configuration.
#' Generates time-series damage projections across scenarios, time periods, and regions.
#' 
#' @param results_median Data frame containing median gamma coefficients with scaled 
#'   damage function parameters (alpha, beta, gamma) for each region
#' @param raw_data_path Character string. Path to the raw impact data CSV file containing
#'   historical and projected impacts, temperature, and socioeconomic variables
#' @param tables_dir Character string. Directory path where F2 tables will be saved
#' @param config List. Configuration object containing analysis settings including
#'   sector specification, time periods, scenario filters, and reference values
#'   
#' @return Invisibly returns NULL. Creates CSV files in the specified tables directory
#'   containing F2-style damage projections split by scenario (if configured) or combined.
#'   
#' @details 
#' The function implements the F2 methodology for damage projections:
#' \itemize{
#'   \item Uses external temperature data for consistent temperature values
#'   \item Calculates income adaptation effects using GDP baseline normalization  
#'   \item Applies quadratic damage functions: (α*T + β*T²) * (GDP_ratio^γ)
#'   \item Supports filtering by SSP scenario, RCP pathway, and economic model
#'   \item Includes reference validation values for specified regions and periods
#' }
#' 
#' @examples
#' \dontrun{
#' # Load configuration and results
#' config <- load_config("mortality_config.yaml")
#' results <- read.csv("regional_polynomials.csv")
#' 
#' # Create F2 tables
#' create_f2_damage_table(
#'   results_median = results,
#'   raw_data_path = config$data$data_path,
#'   tables_dir = "output/tables",
#'   config = config
#' )
#' 
#' # Results saved to tables_dir/estimated_scenarios/
#' }
#' 
#' @seealso \code{\link{create_f2_damage_table_direct}} for direct output to results folder
#' @export
create_f2_damage_table <- function(results_median, raw_data_path, tables_dir, config) {
  
  # Load raw data
  raw_data <- data.table::fread(raw_data_path)
  
  # Get settings from config
  f2_settings <- config$output_files$f2_table_settings
  
  # Use time periods from config or defaults
  if (!is.null(f2_settings$time_periods)) {
    year_windows <- f2_settings$time_periods
  } else {
    year_windows <- list(
      "2020_2039" = c(2020, 2039),
      "2040_2059" = c(2040, 2059), 
      "2060_2079" = c(2060, 2079),
      "2080_2094" = c(2080, 2094),
      "2095_2100" = c(2095, 2100)
    )
  }
  
  # Create F2 subfolder
  f2_subfolder <- if (!is.null(f2_settings$f2_subfolder)) {
    f2_settings$f2_subfolder
  } else {
    "estimated_scenarios"  
  }
  f2_dir <- file.path(tables_dir, f2_subfolder)
  dir.create(f2_dir, recursive = TRUE, showWarnings = FALSE)
  
  # Function to compute mortality average (matching reference)
  get_mortality_mean <- function(df, iso, start, end) {
    df %>%
      filter(region == iso, year >= start, year <= end) %>%
      summarize(mean_mort = mean(adjusted_mortality, na.rm = TRUE)) %>%
      pull(mean_mort) * 1e5
  }
  
  # Initialize output dataframe
  f2_table <- data.frame()
  
  # Get temperature data from anomaly column (simplified - would need actual temp data file)
  # For now, using anomaly as proxy for temperature
  cat("Warning: Using anomaly as temperature proxy. For full F2 table, provide temperature data file.\n")
  
  # Get unique scenario combinations and filter by config
  combinations <- raw_data %>%
    distinct(rcp, ssp, model) %>%
    na.omit()
  
  # Filter SSPs if specified in config
  if (!is.null(f2_settings$include_ssps) && length(f2_settings$include_ssps) > 0) {
    combinations <- combinations %>%
      filter(ssp %in% f2_settings$include_ssps)
    cat("Filtering to SSPs:", paste(f2_settings$include_ssps, collapse = ", "), "\n")
  }
  
  cat("Processing", nrow(combinations), "scenario combinations...\n")
  
  # Process each combination
  for (i in 1:nrow(combinations)) {
    current_rcp <- combinations$rcp[i]
    current_ssp <- combinations$ssp[i] 
    current_model <- combinations$model[i]
    
    rawdf_sub <- raw_data %>%
      filter(rcp == current_rcp, ssp == current_ssp, model == current_model) %>%
      mutate(loggdppc = log(gdppc))
    
    if (nrow(rawdf_sub) == 0) next
    
    # GDP baseline (2010-2015)
    baseline_lgdp <- rawdf_sub %>%
      filter(year >= 2010, year <= 2015) %>%
      group_by(region, batch, gcm, model, rcp, ssp) %>%
      summarize(loggdp_base = mean(loggdppc, na.rm = TRUE), .groups = "drop")
    
    rawdf_sub <- rawdf_sub %>%
      left_join(baseline_lgdp, by = c("region", "batch", "gcm", "model", "rcp", "ssp")) %>%
      mutate(lgdp_diff = loggdppc - loggdp_base)
    
    # Process each region
    iso_list <- sort(unique(rawdf_sub$region))
    
    for (iso in iso_list) {
      coeffs <- results.mu[results.mu$region == iso,]
      if (nrow(coeffs) == 0) next
      
      for (wname in names(year_windows)) {
        years <- year_windows[[wname]]
        year_center <- max(years)
        
        # Income effect
        income_window <- rawdf_sub %>%
          filter(region == iso, year >= years[1], year <= years[2]) %>%
          summarize(lgdp_diff = mean(lgdp_diff, na.rm = TRUE)) %>%
          pull(lgdp_diff)
        
        if (length(income_window) == 0 || is.na(income_window)) next
        
        # Temperature (using mean anomaly for the period)
        temp_window <- rawdf_sub %>%
          filter(region == iso, year >= years[1], year <= years[2]) %>%
          summarize(tt = mean(anomaly, na.rm = TRUE)) %>%
          pull(tt)
        
        if (length(temp_window) == 0 || is.na(temp_window)) next
        
        # Calculate projections
        ratioy <- exp(income_window * coeffs$gamma)
        flex_total <- (coeffs$alpha_scaled * temp_window + coeffs$beta_scaled * temp_window^2) * ratioy
        flex_raw <- get_mortality_mean(rawdf_sub, iso, years[1], years[2])
        
        # Add reference values for SSP3 2095-2100 if available
        if (current_ssp == "SSP3" && wname == "2095_2100" && 
            !is.null(config$output_files$regional_comparisons[[iso]])) {
          ref_vals <- config$output_files$regional_comparisons[[iso]]$reference_values
          f2_mort <- ref_vals[1]
          f2_total <- ref_vals[2]
        } else {
          f2_mort <- NA
          f2_total <- NA
        }
        
        # Create row
        row <- data.frame(
          iso,
          rcp = current_rcp,
          ssp = current_ssp, 
          model = current_model,
          period = wname,
          year_center = year_center,
          TT,
          flextotal,
          rawtotal,
          f2mort,
          f2total
        )
        
        compdf_all <- rbind(compdf_all, row)
      }
    }
  }
  
  # Save F2 table(s) - split by SSP or combined
  if (!is.null(f2_settings$split_by_ssp) && f2_settings$split_by_ssp) {
    # Split by SSP scenario
    unique_ssps <- unique(f2_table$ssp)
    cat("Saving F2 tables split by SSP scenarios...\n")
    
    for (ssp in unique_ssps) {
      ssp_data <- f2_table[f2_table$ssp == ssp, ]
      if (nrow(ssp_data) > 0) {
        ssp_file <- file.path(f2_dir, paste0(ssp, ".csv"))
        write.csv(ssp_data, ssp_file, row.names = FALSE)
        cat("  -", ssp, ":", nrow(ssp_data), "rows saved to", basename(ssp_file), "\n")
      }
    }
  } else {
    # Combined file
    f2_file <- file.path(f2_dir, "all_SSPs.csv")
    write.csv(f2_table, f2_file, row.names = FALSE)
    cat("Combined F2 table saved to:", basename(f2_file), "\n")
  }
  
  cat("F2 tables saved in subfolder:", f2_subfolder, "\n")
  cat("Total projection rows generated:", nrow(f2_table), "\n")
}

#' Create F2-style damage table directly in results folder
#' 
#' Creates F2-style damage projection tables directly in the results/estimated_scenarios/ 
#' directory without creating a tables subdirectory. Works with any impact sector and 
#' uses external temperature data for consistency with reference methodology.
#' 
#' @param results.mu Data frame containing median gamma coefficients with scaled 
#'   damage function parameters. Must include columns: region, alpha, beta, gamma
#' @param raw_data_path Character string. Path to raw impact data CSV file containing
#'   regional time-series data with temperature, GDP, and impact variables
#' @param output_dir Character string. Results directory path where estimated_scenarios/ 
#'   subfolder will be created
#' @param config List. Configuration object specifying sector, time periods, scenario 
#'   filters, temperature data path, and F2 table settings
#'   
#' @return Invisibly returns NULL. Creates CSV files in output_dir/estimated_scenarios/
#'   containing damage projections. Files are named by scenario combination (e.g., 
#'   "SSP3_rcp85_low.csv") or combined (e.g., "all_scenarios_low.csv").
#'   
#' @details
#' This function generates F2-compatible damage projections by:
#' \itemize{
#'   \item Loading external temperature data (meantas.csv) for accurate temperature values
#'   \item Computing GDP baseline effects (2010-2015 average) for income adaptation
#'   \item Calculating damage using quadratic functions: (α*T + β*T²) * exp(income_effect * γ)
#'   \item Supporting multiple time periods, scenarios, and economic models
#'   \item Including validation against reference values for specified regions/periods
#'   \item Generating progress indicators for large country sets
#' }
#' 
#' The output CSV contains columns: iso, rcp, ssp, model, period, year_center, TT, 
#' flextotal, rawtotal, f2mort, f2total (where applicable).
#' 
#' @examples
#' \dontrun{
#' # Load configuration and coefficients  
#' config <- load_config("damage_config.yaml")
#' coeffs <- read.csv("results/regional_polynomials.csv")
#' median_coeffs <- coeffs[coeffs$gamma == median(coeffs$gamma), ]
#' 
#' # Generate F2 tables
#' create_f2_damage_table_direct(
#'   results.mu = median_coeffs,
#'   raw_data_path = config$data$data_path, 
#'   output_dir = "results/analysis_output",
#'   config = config
#' )
#' 
#' # Check results in: results/analysis_output/estimated_scenarios/
#' }
#' 
#' @seealso \code{\link{create_f2_damage_table}} for output to tables subdirectory
#' @export  
create_f2_damage_table_direct <- function(results.mu, raw_data_path, output_dir, config) {
  
  # Load raw data
  rawdf <- data.table::fread(raw_data_path)
  
  # Load temperature data from config or default location
  temp_data_path <- if (!is.null(config$data$temperature_data_path)) {
    config$data$temperature_data_path
  } else {
    "/Volumes/cil/home_dirs/scadavidsanchez/repos/flex-damage-dev/flex-damage/data/meantas.csv"
  }
  
  if (!file.exists(temp_data_path)) {
    cat("Warning: Temperature data file not found at:", temp_data_path, "\n")
    cat("Falling back to anomaly column from raw data.\n")
    tasdf <- NULL
  } else {
    tasdf <- read.csv(temp_data_path)
    cat("Temperature data loaded from:", temp_data_path, "\n")
  }
  
  # Get settings from config
  f2_settings <- config$output_files$f2_table_settings
  
  # Use time periods from config or defaults
  if (!is.null(f2_settings$time_periods)) {
    year_windows <- f2_settings$time_periods
  } else {
    year_windows <- list(
      "2020_2039" = c(2020, 2039),
      "2040_2059" = c(2040, 2059), 
      "2060_2079" = c(2060, 2079),
      "2080_2094" = c(2080, 2094),
      "2095_2100" = c(2095, 2100)
    )
  }
  
  # Create F2 subfolder directly in results (not in tables/)
  f2_subfolder <- if (!is.null(f2_settings$f2_subfolder)) {
    f2_settings$f2_subfolder
  } else {
    "estimated_scenarios"  
  }
  f2_dir <- file.path(output_dir, f2_subfolder)  # results/estimated_scenarios/
  dir.create(f2_dir, recursive = TRUE, showWarnings = FALSE)
  
  # Function to compute mortality average (matching reference)
  get_mortality_mean <- function(df, iso, start, end) {
    df %>%
      dplyr::filter(region == iso, year >= start, year <= end) %>%
      dplyr::summarize(mean_mort = mean(adjusted_mortality, na.rm = TRUE)) %>%
      dplyr::pull(mean_mort) * 1e5
  }
  
  # Initialize output dataframe
  compdf_all <- data.frame()
  
  # Get unique scenario combinations and filter by config
  combinations <- rawdf %>%
    dplyr::distinct(rcp, ssp, model) %>%
    na.omit()
  
  # Filter SSPs and RCPs if specified in config
  if (!is.null(f2_settings$include_ssps) && length(f2_settings$include_ssps) > 0) {
    combinations <- combinations %>%
      dplyr::filter(ssp %in% f2_settings$include_ssps)
    cat("Filtering to SSPs:", paste(f2_settings$include_ssps, collapse = ", "), "\n")
  }
  
  if (!is.null(f2_settings$include_rcps) && length(f2_settings$include_rcps) > 0) {
    combinations <- combinations %>%
      dplyr::filter(rcp %in% f2_settings$include_rcps)
    cat("Filtering to RCPs:", paste(f2_settings$include_rcps, collapse = ", "), "\n")
  }
  
  if (!is.null(f2_settings$include_models) && length(f2_settings$include_models) > 0) {
    combinations <- combinations %>%
      dplyr::filter(model %in% f2_settings$include_models)
    cat("Filtering to models:", paste(f2_settings$include_models, collapse = ", "), "\n")
  }
  
  cat("Processing", nrow(combinations), "scenario combinations...\n")
  
  # Process each combination
  for (i in 1:nrow(combinations)) {
    current_rcp <- combinations$rcp[i]
    current_ssp <- combinations$ssp[i] 
    current_model <- combinations$model[i]
    
    cat("  Processing", i, "of", nrow(combinations), ":", current_rcp, current_ssp, current_model, "\n")
    
    rawdf_sub <- rawdf %>%
      dplyr::filter(rcp == current_rcp, ssp == current_ssp, model == current_model) %>%
      dplyr::mutate(loggdppc = log(gdppc))
    
    if (nrow(rawdf_sub) == 0) next
    
    # GDP baseline (2010-2015) - matching reference code exactly
    baseline_lgdp <- rawdf_sub %>%
      dplyr::filter(year >= 2010, year <= 2015) %>%
      dplyr::group_by(region, batch, gcm, model, rcp, ssp) %>%
      dplyr::summarize(loggdp_base = mean(loggdppc, na.rm = TRUE), .groups = "drop")
    
    rawdf_sub <- rawdf_sub %>%
      dplyr::left_join(baseline_lgdp, by = c("region", "batch", "gcm", "model", "rcp", "ssp")) %>%
      dplyr::mutate(lgdp.diff = loggdppc - loggdp_base)
    
    # Process each region with progress bar
    iso_list <- sort(unique(rawdf_sub$region))
    n_iso <- length(iso_list)
    
    # Create progress bar
    if (n_iso > 10) {
      pb <- txtProgressBar(min = 0, max = n_iso, style = 3, width = 50)
      cat(sprintf("    Processing %d countries for %s %s %s\\n", n_iso, current_rcp, current_ssp, current_model))
    }
    
    for (j in seq_along(iso_list)) {
      iso <- iso_list[j]
      
      # Update progress bar
      if (n_iso > 10) {
        setTxtProgressBar(pb, j)
      } else if (n_iso > 1) {
        cat(sprintf("    Processing country %d of %d - %s\\n", j, n_iso, iso))
      }
      coeffs <- results.mu[results.mu$region == iso,]
      if (nrow(coeffs) == 0) next
      
      for (wname in names(year_windows)) {
        years <- year_windows[[wname]]
        year_center <- max(years)
        
        # Income effect
        income_window <- rawdf_sub %>%
          dplyr::filter(region == iso, year >= years[1], year <= years[2]) %>%
          dplyr::summarize(lgdp.diff = mean(lgdp.diff, na.rm = TRUE)) %>%
          dplyr::pull(lgdp.diff)
        
        if (length(income_window) == 0 || is.na(income_window)) next
        
        # Temperature calculation - use external data if available, otherwise anomaly
        if (!is.null(tasdf)) {
          # Use external temperature data (matching reference code logic)
          TT <- tasdf[[current_rcp]][tasdf$year == year_center]
          if (length(TT) == 0 || is.na(TT)) next
        } else {
          # Fallback to anomaly column
          TT <- rawdf_sub %>%
            dplyr::filter(region == iso, year >= years[1], year <= years[2]) %>%
            dplyr::summarize(tt = mean(anomaly, na.rm = TRUE)) %>%
            dplyr::pull(tt)
          if (length(TT) == 0 || is.na(TT)) next
        }
        
        # Calculate projections
        ratioy <- exp(income_window * 110 / 80)
        flextotal <- (coeffs$alpha * TT + coeffs$beta * TT^2) * (ratioy ^ coeffs$gamma)
        rawtotal <- get_mortality_mean(rawdf_sub, iso, years[1], years[2])
        
        # Add reference values for comparison
        ref_scenario <- config$output_files$regional_comparisons$reference_scenario
        if (current_ssp == ref_scenario$ssp && wname == "2095_2100" && 
            !is.null(config$output_files$regional_comparisons$reference_values[[iso]])) {
          ref_vals <- config$output_files$regional_comparisons$reference_values[[iso]]$values
          f2mort <- ref_vals[1]
          f2total <- ref_vals[2]
        } else {
          f2mort <- NA
          f2total <- NA
        }
        
        # Create row
        row <- data.frame(
          iso,
          rcp = current_rcp,
          ssp = current_ssp, 
          model = current_model,
          period = wname,
          year_center = year_center,
          TT,
          flextotal,
          rawtotal,
          f2mort,
          f2total
        )
        
        compdf_all <- rbind(compdf_all, row)
      }
    }
    # Close progress bar
    if (n_iso > 10) {
      close(pb)
      cat("\n")
    }
  }
  
  # Save F2 table(s) - split by SSP+RCP combinations or combined
  if (!is.null(f2_settings$split_by_ssp) && f2_settings$split_by_ssp) {
    # Split by SSP+RCP combinations
    unique_combinations <- compdf_all %>%
      dplyr::distinct(ssp, rcp) %>%
      dplyr::arrange(ssp, rcp)
    
    cat("Saving F2 tables split by SSP+RCP combinations to", f2_dir, "...\n")
    
    # Determine model suffix for filename
    unique_models <- unique(compdf_all$model)
    model_suffix <- ""
    if (length(unique_models) == 1) {
      if ("IIASA GDP" %in% unique_models) {
        model_suffix <- "_low"
      } else if ("OECD Env-Growth" %in% unique_models) {
        model_suffix <- "_high"
      }
    }
    # If both models or other models, no suffix
    
    for (i in 1:nrow(unique_combinations)) {
      current_ssp <- unique_combinations$ssp[i]
      current_rcp <- unique_combinations$rcp[i]
      
      combo_data <- compdf_all[compdf_all$ssp == current_ssp & compdf_all$rcp == current_rcp, ]
      if (nrow(combo_data) > 0) {
        # Create filename like SSP3_rcp85_low.csv or SSP3_rcp85.csv
        filename <- paste0(current_ssp, "_", current_rcp, model_suffix, ".csv")
        combo_file <- file.path(f2_dir, filename)
        write.csv(combo_data, combo_file, row.names = FALSE)
        cat("  -", current_ssp, current_rcp, model_suffix, ":", nrow(combo_data), "rows saved to", basename(combo_file), "\n")
      }
    }
  } else {
    # Combined file - determine model suffix
    unique_models <- unique(compdf_all$model)
    model_suffix <- ""
    if (length(unique_models) == 1) {
      if ("IIASA GDP" %in% unique_models) {
        model_suffix <- "_low"
      } else if ("OECD Env-Growth" %in% unique_models) {
        model_suffix <- "_high"
      }
    }
    
    filename <- paste0("all_scenarios", model_suffix, ".csv")
    f2_file <- file.path(f2_dir, filename)
    write.csv(compdf_all, f2_file, row.names = FALSE)
    cat("Combined F2 table saved to:", basename(f2_file), "\n")
  }
  
  cat("F2 tables saved in:", f2_dir, "\n")
  cat("Total projection rows generated:", nrow(compdf_all), "\n")
}

#' Create coefficient summary table
#' 
#' Creates summary statistics for scaled coefficients
#' 
#' @param results_scaled Scaled coefficient results
#' @param tables_dir Output directory for tables
#' @param scale_factor Scale factor used
#' @keywords internal
create_coefficient_summary_table <- function(results_scaled, tables_dir, scale_factor) {
  
  # Summary statistics for key coefficients
  summary_stats <- results_scaled %>%
    summarize(
      n_regions = n(),
      alpha_mean = mean(alpha_scaled, na.rm = TRUE),
      alpha_median = median(alpha_scaled, na.rm = TRUE),
      alpha_sd = sd(alpha_scaled, na.rm = TRUE),
      beta_mean = mean(beta_scaled, na.rm = TRUE),
      beta_median = median(beta_scaled, na.rm = TRUE), 
      beta_sd = sd(beta_scaled, na.rm = TRUE),
      gamma_mean = mean(gamma, na.rm = TRUE),
      gamma_median = median(gamma, na.rm = TRUE),
      gamma_sd = sd(gamma, na.rm = TRUE),
      rsqr1_mean = mean(rsqr1, na.rm = TRUE),
      rsqr1_median = median(rsqr1, na.rm = TRUE)
    )
  
  # Add metadata
  summary_stats$scale_factor <- scale_factor
  summary_stats$timestamp <- Sys.time()
  
  summary_file <- file.path(tables_dir, "coefficient_summary.csv")
  write.csv(summary_stats, summary_file, row.names = FALSE)
  cat("Coefficient summary saved to:", summary_file, "\n")
}

#' Create regional comparison table
#' 
#' Creates regional comparisons for user-specified regions from config
#' 
#' @param results_median Median gamma coefficients
#' @param raw_data_path Path to raw data
#' @param tables_dir Output directory
#' @param config Configuration list (uses comparison_regions from config)
#' @keywords internal
create_regional_comparison_table <- function(results_median, raw_data_path, tables_dir, config) {
  
  cat("Creating regional comparison table...\n")
  
  # Load raw data
  raw_data <- data.table::fread(raw_data_path)
  
  # Get comparison regions from config
  regional_comparisons <- config$output_files$regional_comparisons
  comparison_regions <- names(regional_comparisons)
  
  # Filter to comparison regions that exist in our results
  available_regions <- intersect(comparison_regions, unique(results_median$region))
  
  if (length(available_regions) == 0) {
    cat("Warning: No comparison regions found in results.\n")
    return(invisible(NULL))
  }
  
  # Create regional comparison
  regional_comparison <- results_median %>%
    filter(region %in% available_regions) %>%
    select(region, alpha_scaled, beta_scaled, gamma, rsqr1, rsqr2) %>%
    arrange(region)
  
  # Add descriptive statistics
  regional_comparison <- regional_comparison %>%
    mutate(
      temp_sensitivity_1C = alpha_scaled + beta_scaled * 1, # Impact at 1°C
      temp_sensitivity_2C = alpha_scaled + beta_scaled * 4, # Impact at 2°C  
      temp_sensitivity_3C = alpha_scaled + beta_scaled * 9  # Impact at 3°C
    )
  
  # Add reference values for comparison
  regional_comparison$reference_1C <- NA
  regional_comparison$reference_2C <- NA
  regional_comparison$diff_1C <- NA
  regional_comparison$diff_2C <- NA
  
  for (region in available_regions) {
    if (region %in% names(regional_comparisons)) {
      ref_values <- regional_comparisons[[region]]$reference_values
      if (length(ref_values) >= 2) {
        idx <- which(regional_comparison$region == region)
        regional_comparison$reference_1C[idx] <- ref_values[1]
        regional_comparison$reference_2C[idx] <- ref_values[2] 
        regional_comparison$diff_1C[idx] <- regional_comparison$temp_sensitivity_1C[idx] - ref_values[1]
        regional_comparison$diff_2C[idx] <- regional_comparison$temp_sensitivity_2C[idx] - ref_values[2]
      }
    }
  }
  
  comparison_file <- file.path(tables_dir, "regional_comparison.csv")
  write.csv(regional_comparison, comparison_file, row.names = FALSE)
  cat("Regional comparison saved to:", comparison_file, "\n")
  
  # Create a formatted summary table with comparisons
  formatted_table <- regional_comparison %>%
    mutate(
      alpha_formatted = sprintf("%.2f", alpha_scaled),
      beta_formatted = sprintf("%.3f", beta_scaled),
      gamma_formatted = sprintf("%.3f", gamma),
      rsqr1_formatted = sprintf("%.3f", rsqr1),
      impact_1C_formatted = sprintf("%.1f", temp_sensitivity_1C),
      impact_2C_formatted = sprintf("%.1f", temp_sensitivity_2C),
      reference_1C_formatted = ifelse(is.na(reference_1C), "N/A", 
                                       sprintf("%.1f", reference_1C)),
      reference_2C_formatted = ifelse(is.na(reference_2C), "N/A", 
                                       sprintf("%.1f", reference_2C)),
      diff_1C_formatted = ifelse(is.na(diff_1C), "N/A", 
                                 sprintf("%.1f", diff_1C)),
      diff_2C_formatted = ifelse(is.na(diff_2C), "N/A", 
                                 sprintf("%.1f", diff_2C))
    ) %>%
    dplyr::select(
      Region = region,
      `Linear Coeff (α)` = alpha_formatted,
      `Quadratic Coeff (β)` = beta_formatted,
      `Adaptation (γ)` = gamma_formatted,
      `R-squared` = rsqr1_formatted,
      `Estimated 1°C` = impact_1C_formatted,
      `Reference 1°C` = reference_1C_formatted,
      `Diff 1°C` = diff_1C_formatted,
      `Estimated 2°C` = impact_2C_formatted,
      `Reference 2°C` = reference_2C_formatted,
      `Diff 2°C` = diff_2C_formatted
    )
  
  formatted_file <- file.path(tables_dir, "formatted_regional_table.csv")
  write.csv(formatted_table, formatted_file, row.names = FALSE)
  cat("Formatted table saved to:", formatted_file, "\n")
}