# File: main.R

# Set working directory (adjust as needed).
# setwd("D:/CIL/damage_functions")
# setwd("/mnt/d/CIL/damage_functions")
# setwd("C:/Users/scada/git/cil/flex-damage")
setwd("C:/Users/scada/git/cil/dev")

# Define required packages.
required_packages <- c("data.table", "dplyr", "tidyr", "lfe", "mvtnorm", 
                       "ggplot2", "progressr", "crayon", "future.apply", "logger")

# Function to check and install missing packages.
install_if_missing <- function(packages) {
  missing_packages <- packages[!(packages %in% installed.packages()[, "Package"])]
  if (length(missing_packages) > 0) {
    install.packages(missing_packages, dependencies = TRUE)
  }
}

# Install any missing packages.
install_if_missing(required_packages)

# Load libraries.
lapply(required_packages, library, character.only = TRUE)

# Source modular scripts.
source("R/R/utils.R")
source("R/R/data_processing.R")
source("R/R/resources.R")
source("R/R/logging_setup.R")
source("R/R/regional_analysis.R")
source("R/R/scenario_analysis.R")
source("R/R/results.R")

# --- Flexible Resource Allocation ---
total_cores <- parallel::detectCores()

# Attempt to detect available RAM.
if (.Platform$OS.type == "windows") {
  ram_info <- try(system("wmic computersystem get TotalPhysicalMemory", intern = TRUE), silent = TRUE)
  if (inherits(ram_info, "try-error") || length(ram_info) < 2) {
    max_ram_mb <- 16384  # Default to 16 GB
  } else {
    ram_num <- as.numeric(gsub("[^0-9]", "", ram_info[2]))
    if (is.na(ram_num) || ram_num <= 0) {
      max_ram_mb <- 16384
    } else {
      max_ram_mb <- ram_num / (1024^2)
    }
  }
} else if (file.exists("/proc/meminfo")) {
  meminfo <- readLines("/proc/meminfo")
  mem_total_line <- meminfo[grep("^MemTotal:", meminfo)]
  max_ram_mb <- as.numeric(gsub("[^0-9]", "", mem_total_line)) / 1024
} else {
  max_ram_mb <- 16384
}
max_ram_bytes <- max_ram_mb * 1024^2

cat(sprintf("Total cores available: %d\n", total_cores))
cat(sprintf("Total RAM available: %.1f MB (%.1f GB)\n", max_ram_mb, max_ram_mb / 1024))

# Set number of cores to use.
n_cores_flexible <- total_cores - 2
cat(sprintf("Using %d cores for parallel processing.\n", n_cores_flexible))

# Set future globals maximum size to 95% of available RAM.
options(future.globals.maxSize = 0.95 * max_ram_bytes)

# --- Experiment Configuration (provided by the user) ---
required_columns <- c("region", "year", "batch", "gcm", "model", "rcp", "ssp",
                      "adjusted_mortality", "anomaly", "total_population", "gdppc")
csv_file_path <- "data/mortality_regression_full_mc.csv"

# Set parameters (these replace the former config.R).
gamma_filter <- "all_gamma_values"      # Options: "all_gamma_values", "positive_gamma_only"
weighting <- "weighted"                 # Options: "population_weighted", "unweighted"
collapse_batch <- FALSE         # If TRUE, aggregate data during loading. (collapse batches)
parallel_processing <- FALSE            # Execute regional computations in parallel.
n_cores <- n_cores_flexible
gdp_baseline_START <- 2010
gdp_baseline_END <- 2020
test_mode <- TRUE
# Print configuration.
log_info("User configuration set:")
cat(blue("Parameters Selected:\n"))
cat(green(sprintf("  gamma_filter: %s\n", gamma_filter)))
cat(green(sprintf("  weighting: %s\n", weighting)))
cat(green(sprintf("  collapse_regional_data: %s\n", collapse_batch)))
cat(green(sprintf("  parallel_processing: %s\n", parallel_processing)))
cat(green(sprintf("  n_cores: %s\n", n_cores)))

# --- Data Loading & Processing ---
log_info("Loading and processing data...")
df <- load_and_process_data(csv_file_path, required_columns, gdp_baseline_start = gdp_baseline_START, gdp_baseline_end = gdp_baseline_END,
                            collapse_batch_data = collapse_batch)

log_info("Data loaded and processed successfully.")

# --- Environment Setup & Logging ---
base_path <- setup_environment(collapse_batch = collapse_batch)

init_logging(base_path)

# --- Define User-Specified Overall Model Function (Optional) ---

# Custom overall (base) model function.
custom_base_model_fn <- function(data, weights) {
  felm(log_delta_mortality ~ loggdppc | group + year | 0 | group + year,
       data = data, weights = weights)
}

# --- Run Scenario Analysis ---
results <- run_scenario_analysis(
  data = df,
  gamma_filter = gamma_filter,
  use_weights = (weighting == "population_weighted"),
  collapse_batch = collapse_batch,
  parallel = parallel_processing,
  ncores = n_cores,
  base_model_fn = custom_base_model_fn,  # Overall model function
  test = test_mode
  # Note: regional analysis now uses gamma values internally.
)

# --- Save Base Results ---
save_base_results(df, results$main_model, results$base_path)
log_info("Analysis complete.")
