# File: R/R/data_processing.R
# This script loads and processes the CSV data.
library(data.table)
library(dplyr)

# Validate that the CSV file exists and has all required columns.
validate_csv_file <- function(csv_file_path, required_columns) {
  if (!file.exists(csv_file_path)) {
    stop("CSV file does not exist: ", csv_file_path)
  }
  # Read only the header using data.table for speed.
  header <- names(fread(csv_file_path, nrows = 0))
  missing <- setdiff(required_columns, header)
  if (length(missing) > 0) {
    stop("Missing required columns: ", paste(missing, collapse = ", "))
  }
  return(TRUE)
}

# Load the CSV file, validate its columns, and process the data.
# The user is responsible for computing the "mean_normed" variable later.
load_and_process_data <- function(csv_file_path, required_columns, gdp_baseline_start, gdp_baseline_end, collapse_regional_data = FALSE) {
  # Validate the CSV file.
  validate_csv_file(csv_file_path, required_columns)
  
  # Load data.
  df <- fread(csv_file_path)
  
  if (collapse_regional_data) {
    # Aggregate data by grouping over region, year, gcm, model, rcp, and ssp.
    df <- df %>%
      select(region, year, batch, gcm, model, rcp, ssp,
             adjusted_mortality, anomaly, total_population, gdppc) %>%
      group_by(region, year, gcm, model, rcp, ssp) %>%
      summarize(
        delta_mortality = mean(adjusted_mortality, na.rm = TRUE),
        delta_temp = mean(anomaly, na.rm = TRUE),
        population = mean(total_population, na.rm = TRUE),
        gdppc = mean(gdppc, na.rm = TRUE),
        .groups = 'drop'
      )
  } else {
    # Otherwise, load raw data (without aggregating batches) and rename columns.
    df <- df %>%
      select(region, year, batch, gcm, model, rcp, ssp,
             adjusted_mortality, anomaly, total_population, gdppc) %>%
      rename(
        delta_mortality = adjusted_mortality,  # Using 2005 as reference.
        delta_temp = anomaly,                  # Using 1980-1999 as reference.
        population = total_population
      )
  }
  
  # Compute additional variables.
  df$loggdppc <- log(df$gdppc)
  
  # Compute GDP reference values (using years 2010-2020).
  if (collapse_regional_data) {
    gdp_reference <- df %>%
      filter(year >= gdp_baseline_start & year <= gdp_baseline_end) %>%
      group_by(region, ssp, rcp, model) %>%
      summarize(avg_gdp_2010_2020 = mean(loggdppc, na.rm = TRUE), .groups = 'drop')
    
    df <- df %>%
      left_join(gdp_reference, by = c("region", "ssp", "rcp", "model")) %>%
      mutate(lgdp_delta = loggdppc - avg_gdp_2010_2020)
    
  } else {
    gdp_reference <- df %>%
      filter(year >= gdp_baseline_start & year <= gdp_baseline_end) %>%
      group_by(batch, region, ssp, rcp, model) %>%
      summarize(avg_gdp_2010_2020 = mean(loggdppc, na.rm = TRUE), .groups = 'drop')
    
    df <- df %>%
      left_join(gdp_reference, by = c("batch", "region", "ssp", "rcp", "model")) %>%
      mutate(lgdp_delta = loggdppc - avg_gdp_2010_2020)
  }
  
  # Compute the logarithm of delta_mortality and filter out extreme low values.
  df$log_delta_mortality <- log(df$delta_mortality)
  lower_bound <- quantile(df$log_delta_mortality, 0.05, na.rm = TRUE)
  df$log_delta_mortality[df$log_delta_mortality < lower_bound] <- NA
  
  # Create additional grouping variables.
  df$log_region <- paste0(sign(df$delta_mortality), '-', df$region)
  df$temp_preind_bin <- cut(df$delta_temp, seq(0, 10, by = 0.5))
  df$group <- paste(df$log_region, df$temp_preind_bin)
  
  # NOTE: The user must compute and add the "mean_normed" column to the dataframe before regional analysis.
  return(df)
}
