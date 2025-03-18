# File: R/R/logging_setup.R
library(logger)

# Create directories for storing results and logs.
# 'group_dimension' is provided by main.R.
setup_environment <- function(collapse_batch = FALSE, test = FALSE) {
  group_dimension <- if (collapse_batch) "year_rcp_ssp_model_gcm" else "year_rcp_ssp_model_gcm_batch"
  folder_name <- sprintf("collapseBatch_%s_groupBy_%s", ifelse(collapse_batch, "TRUE", "FALSE"), group_dimension)
  
  # Define base path based on test mode
  base_path <- file.path(if (test) "results_test" else "results", folder_name)
  
  # Ensure necessary directories exist
  dir.create(base_path, recursive = TRUE, showWarnings = FALSE)
  dir.create(file.path(base_path, "base_model"), showWarnings = FALSE)
  dir.create(file.path(base_path, "analysis_scenarios"), showWarnings = FALSE)
  dir.create(file.path(base_path, "logs"), recursive = TRUE, showWarnings = FALSE)  # ✅ Create logs/
  
  return(base_path)
}



# Initialize logging.
init_logging <- function(base_path) {
  log_file <- file.path(base_path, "logs", "analysis_log.txt")
  
  # Ensure logs folder exists
  dir.create(dirname(log_file), recursive = TRUE, showWarnings = FALSE)
  
  # Set up logging to write to file
  log_appender(appender_file(log_file))
  
  # Log a message to confirm logging is active
  log_info(paste("Logging initialized. Writing to:", log_file))
}
