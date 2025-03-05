# File: R/R/utils.R
# Utility functions used across modules.

# Automatically detect and set working directory
get_script_path <- function() {
  # Check if running inside RStudio
  if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
    path <- rstudioapi::getActiveDocumentContext()$path
  } else {
    # Use commandArgs() as fallback
    args <- commandArgs(trailingOnly = FALSE)
    match <- grep("--file=", args)
    if (length(match) > 0) {
      path <- sub("--file=", "", args[match])
    } else {
      # Default to current working directory
      path <- getwd()
    }
  }
  
  # Normalize and return the script directory
  return(normalizePath(dirname(path), winslash = "/"))
}

# A safe logarithm function that warns on non-positive values.
safe_log <- function(x) {
  if (any(x <= 0)) {
    warning("Non-positive value encountered; returning NA for those entries.")
    x[x <= 0] <- NA
  }
  return(log(x))
}
