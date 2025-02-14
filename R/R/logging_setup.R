# File: R/R/logging_setup.R
library(logger)

# Create directories for storing results and logs.
# 'group_dimension' is provided by main.R.
setup_environment <- function(collapse_flag = FALSE, group_dimension = "default") {
  if (collapse_flag) {
    group_dir <- paste0("collapse_TRUE_", group_dimension)
  } else {
    group_dir <- paste0("collapse_FALSE_", group_dimension)
  }
  base_path <- file.path("results", group_dir)
  dir.create(base_path, recursive = TRUE, showWarnings = FALSE)
  dir.create(file.path(base_path, "base_model"), showWarnings = FALSE)
  dir.create(file.path(base_path, "analysis_scenarios"), showWarnings = FALSE)
  dir.create(file.path(base_path, "logs"), recursive = TRUE, showWarnings = FALSE)
  return(base_path)
}

# Initialize logging.
init_logging <- function(base_path) {
  log_file <- file.path(base_path, "logs", "analysis_log.txt")
  log_appender(appender_file(log_file))
  log_info("Logging to file: {log_file}")
}
