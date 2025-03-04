# File: R/R/logging_setup.R
library(logger)

# Create directories for storing results and logs.
# 'group_dimension' is provided by main.R.
setup_environment <- function(collapse_batch = FALSE) {
  # Define the grouping dimension based on collapse_batch
  group_dimension <- if (collapse_batch) "year_rcp_ssp_model_gcm" else "year_rcp_ssp_model_gcm_batch"
  
  # Format the folder name
  folder_name <- sprintf("collapseBatch_%s_groupBy_%s", 
                         ifelse(collapse_batch, "TRUE", "FALSE"), group_dimension)
  
  base_path <- file.path("results", folder_name)
  
  # Only create directories if needed
  dir.create(base_path, recursive = TRUE, showWarnings = FALSE)
  dir.create(file.path(base_path, "base_model"), showWarnings = FALSE)
  dir.create(file.path(base_path, "analysis_scenarios"), showWarnings = FALSE)
  dir.create(file.path(base_path, "logs"), recursive = TRUE, showWarnings = FALSE)
  
  return(base_path)
}

# Initialize logging.
init_logging <- function(base_path) {
  log_file <- file.path(base_path, "logs", "analysis_log.txt")
  
  #Create logs folder if does not exist
  dir.create(dirname(log_file), recursive = TRUE, showWarnings = FALSE)
  
  log_appender(appender_file(log_file))
  log_info(sprintf("Logging to file: %s", log_file))
}
