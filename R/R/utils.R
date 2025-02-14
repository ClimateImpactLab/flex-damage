# File: R/R/utils.R
# Utility functions used across modules.

# A safe logarithm function that warns on non-positive values.
safe_log <- function(x) {
  if (any(x <= 0)) {
    warning("Non-positive value encountered; returning NA for those entries.")
    x[x <= 0] <- NA
  }
  return(log(x))
}
