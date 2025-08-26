# Flexible Data Processing Functions
# Generic functions that work with any impact variable

#' Load and validate damage function data
#' 
#' Loads data and validates required structure
#' 
#' @param data_path Path to data file (CSV, NC4, etc.)
#' @param impact_var Name of the impact variable column (e.g., "adjusted_mortality", "labor_impact")
#' @param config Configuration list
#' @return Loaded and validated data
#' @export
load_damage_data <- function(data_path, impact_var, config = NULL) {
  
  # For now, support CSV - can extend to NC4/zarr later
  if (!file.exists(data_path)) {
    stop("Data file not found: ", data_path)
  }
  
  # Load data based on file extension
  file_ext <- tools::file_ext(data_path)
  
  if (file_ext == "csv") {
    data <- data.table::fread(data_path)
  } else {
    stop("File format not yet supported: ", file_ext, ". Currently supports: csv")
  }
  
  # Define core required columns (without specifying impact variable)
  core_required_cols <- c(
    "region", "year", "batch", "gcm", "model", "rcp", "ssp",
    "anomaly", "total_population", "gdppc"
  )
  
  # Add the user-specified impact variable to required columns
  required_cols <- c(core_required_cols, impact_var)
  
  # Validate columns exist
  missing_cols <- setdiff(required_cols, names(data))
  if (length(missing_cols) > 0) {
    stop("Missing required columns: ", paste(missing_cols, collapse = ", "))
  }
  
  # Rename impact variable to standard name for internal processing
  data$impact_value <- data[[impact_var]]
  
  # Rename other columns to standard names
  data$delta_temp <- data$anomaly
  data$population <- data$total_population
  
  cat("Data loaded successfully:\n")
  cat("  - Rows:", nrow(data), "\n")
  cat("  - Impact variable:", impact_var, "\n")
  cat("  - Regions:", length(unique(data$region)), "\n")
  cat("  - Years:", min(data$year), "-", max(data$year), "\n")
  
  return(data)
}

#' Process damage function data
#' 
#' Processes data following the reference code methodology but with flexible impact variable
#' 
#' @param data Raw data from load_damage_data()
#' @param config Configuration list
#' @return Processed data ready for analysis
#' @export
process_damage_data <- function(data, config) {
  
  # Aggregate by batch if specified
  if (config$data_processing$collapse_batch) {
    processed_data <- data %>%
      group_by(region, year, gcm, model, rcp, ssp) %>%
      summarize(
        delta_impact = mean(impact_value, na.rm = TRUE),
        delta_temp = mean(delta_temp, na.rm = TRUE),
        population = mean(population, na.rm = TRUE),
        gdppc = mean(gdppc, na.rm = TRUE),
        .groups = 'drop'
      )
  } else {
    processed_data <- data %>%
      mutate(delta_impact = impact_value)
  }
  
  # GDP processing
  processed_data$loggdppc <- log(processed_data$gdppc)
  
  gdp_reference <- processed_data %>%
    filter(
      year >= config$data_processing$gdp_baseline_years$start & 
      year <= config$data_processing$gdp_baseline_years$end
    ) %>%
    group_by(region, ssp, rcp, model) %>%
    summarize(avg_gdp_baseline = mean(loggdppc, na.rm = TRUE), .groups = 'drop')
  
  processed_data <- processed_data %>%
    left_join(gdp_reference, by = c("region", "ssp", "rcp", "model")) %>%
    mutate(lgdp_delta = loggdppc - avg_gdp_baseline)
  
  # Log impact processing
  processed_data$log_delta_impact <- log(processed_data$delta_impact)
  
  # Filter extreme values
  quantile_threshold <- quantile(
    processed_data$log_delta_impact, 
    config$data_processing$log_impact_quantile_filter, 
    na.rm = TRUE
  )
  processed_data$log_delta_impact[
    processed_data$log_delta_impact < quantile_threshold
  ] <- NA
  
  # Additional processing for grouping
  processed_data$log_region <- paste0(sign(processed_data$delta_impact), '-', processed_data$region)
  processed_data$temp_preind_bin <- cut(processed_data$delta_temp, seq(0, 10, by = 0.5))
  processed_data$group <- paste(processed_data$log_region, processed_data$temp_preind_bin)
  
  return(processed_data)
}