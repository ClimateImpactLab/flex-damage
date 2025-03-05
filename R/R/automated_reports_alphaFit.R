library(ggplot2)
library(dplyr)
library(scales)
library(knitr)

# Load libraries.
required_packages <- c("data.table", "ggplot2", "dplyr", "scales", "knitr")
install_if_missing <- function(packages) {
  missing_packages <- packages[!(packages %in% installed.packages()[, "Package"])]
  if (length(missing_packages) > 0) {
    install.packages(missing_packages, dependencies = TRUE)
  }
}
install_if_missing(required_packages)
lapply(required_packages, library, character.only = TRUE)

# Set working directory
source("R/R/utils.R")
# Set working directory
script_path <- get_script_path()
setwd(script_path)
cat(sprintf("Working directory set to: %s\n", script_path))


results/collapseBatch_FALSE_groupBy_year_rcp_ssp_model_gcm_batch/analysis_scenarios/all_gamma_values/unweighted/regional_polynomials_test.csv

# Set working directory
opts_knit$set(root.dir = "D:/CIL/damage_functions")
setwd("D:/CIL/damage_functions")
setwd("C:/Users/scada/git/cil/dev/")

# Define input CSV file
outfile <- "results/collapse_FALSE_year_rcp_ssp_model_gcm/analysis_scenarios/all_gamma_values/unweighted/global_analysis.csv"


# Ensure the CSV file exists
if (!file.exists(outfile)) {
  stop("Error: The specified CSV file does not exist.")
}


# Load the data
results <- read.csv(outfile) %>%
  mutate(alpha = alpha * 1e5, beta = beta * 1e5, sigma11 = sigma11 * 1e10, 
         sigma12 = sigma12 * 1e10, sigma22 = sigma22 * 1e10, 
         zeta = zeta * 1e5, eta = eta * 1e5)

results.mu <- results[results$gamma == median(results$gamma),]


# Compute polynomial fits
TT <- seq(0, 20, length.out = 100)
if (nrow(results.mu) > 0) {
  allyy <- sapply(1:nrow(results.mu), function(ii) results.mu$alpha[ii] * TT + results.mu$beta[ii] * TT^2)
  pdf_data <- data.frame(
    TT, 
    yy = rowMeans(allyy, na.rm = TRUE), 
    q25 = apply(allyy, 1, function(yy) quantile(yy, .25, na.rm = TRUE)), 
    q75 = apply(allyy, 1, function(yy) quantile(yy, .75, na.rm = TRUE))
  )
} else {
  pdf_data <- data.frame(TT = numeric(), yy = numeric(), q25 = numeric(), q75 = numeric())
}
