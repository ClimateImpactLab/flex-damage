# File: R/R/logging_setup.R
library(logger)

# Create directories for storing results and logs.
# 'group_dimension' is provided by main.R.
# Crear directorios para guardar resultados y logs.
setup_environment <- function(collapse_batch = FALSE, test = FALSE) {
  group_dimension <- if (collapse_batch) "year_rcp_ssp_model_gcm" else "year_rcp_ssp_model_gcm_batch"
  folder_name <- sprintf("collapseBatch_%s_groupBy_%s", ifelse(collapse_batch, "TRUE", "FALSE"), group_dimension)
  
  # ✅ Definir base_path, dependiendo de si estamos en modo test o no
  base_path <- file.path(if (test) "results_test" else "results", folder_name)
  
  # ✅ Crear los directorios necesarios, asegurándose de que todo esté creado
  dir.create(base_path, recursive = TRUE, showWarnings = FALSE)
  dir.create(file.path(base_path, "base_model"), showWarnings = FALSE)
  dir.create(file.path(base_path, "analysis_scenarios"), showWarnings = FALSE)
  
  # Crear los directorios de logs
  log_dir <- file.path(base_path, "analysis_scenarios", "all_gamma_values", "population_weighted", "logs")
  dir.create(log_dir, recursive = TRUE, showWarnings = FALSE)
  
  return(base_path)
}



# Initialize logging.
init_logging <- function(output_dir) {
  log_file <- file.path(output_dir, "logs", "analysis_log.txt")
  
  # Ensure logs directory is created inside the scenario
  dir.create(dirname(log_file), recursive = TRUE, showWarnings = FALSE)
  
  log_appender(appender_file(log_file))
  log_info(sprintf("Logging initialized for scenario at: %s", log_file))
}

