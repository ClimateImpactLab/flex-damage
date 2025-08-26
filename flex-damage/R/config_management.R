# Configuration Management Functions

#' Load configuration file
#' 
#' Loads and validates configuration from YAML file
#' 
#' @param config_path Path to YAML configuration file
#' @return Configuration list
#' @export
load_config <- function(config_path = NULL) {
  
  # Use default config if none specified
  if (is.null(config_path)) {
    config_path <- system.file("configs", "mortality_config.yaml", package = "flexdamage")
    if (config_path == "") {
      # Fallback for development
      config_path <- "inst/configs/mortality_config.yaml"
    }
  }
  
  if (!file.exists(config_path)) {
    stop("Configuration file not found: ", config_path)
  }
  
  config <- yaml::read_yaml(config_path)
  
  # Validate required configuration sections
  required_sections <- c("data_processing", "scenarios", "modeling", "output")
  missing_sections <- setdiff(required_sections, names(config))
  if (length(missing_sections) > 0) {
    stop("Missing required configuration sections: ", paste(missing_sections, collapse = ", "))
  }
  
  cat("Configuration loaded from:", config_path, "\n")
  
  return(config)
}

#' Create a new configuration file template
#' 
#' Creates a template configuration file that users can customize
#' 
#' @param output_path Where to save the configuration file
#' @param template_type Type of template ("generic", "mortality", "labor")
#' @export
create_analysis_config <- function(output_path, template_type = "generic") {
  
  # Get template path
  template_file <- switch(template_type,
    "generic" = "mortality_config.yaml",  # Use mortality as generic template
    "mortality" = "mortality_config.yaml",
    "labor" = "labor_config.yaml"
  )
  
  template_path <- system.file("configs", template_file, package = "flexdamage")
  if (template_path == "") {
    # Fallback for development
    template_path <- file.path("inst/configs", template_file)
  }
  
  if (!file.exists(template_path)) {
    stop("Template configuration not found: ", template_path)
  }
  
  # Copy template to output location
  file.copy(template_path, output_path, overwrite = TRUE)
  
  cat("Configuration template created at:", output_path, "\n")
  cat("Please edit this file to customize your analysis parameters.\n")
  
  return(invisible(output_path))
}

#' Merge user config with defaults
#' 
#' Merges user configuration with default settings
#' 
#' @param user_config User configuration list
#' @return Merged configuration
merge_with_defaults <- function(user_config) {
  
  # Load default settings
  default_path <- system.file("configs", "default_settings.yaml", package = "flexdamage")
  if (default_path == "") {
    default_path <- "inst/configs/default_settings.yaml"
  }
  
  if (file.exists(default_path)) {
    defaults <- yaml::read_yaml(default_path)
    
    # Simple merge (user config takes precedence)
    merged_config <- modifyList(defaults, user_config)
    return(merged_config)
  }
  
  return(user_config)
}