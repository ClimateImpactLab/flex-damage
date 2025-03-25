# This script analyzes regional polynomial results and generates reports
# with visualizations and statistics.

# ======================================================================
# Configuration Section - Modify these parameters as needed
# ======================================================================

# Enable or disable specific report types
do_generate_basic_report <- TRUE      # Basic coefficient analysis and plots
do_generate_prediction_report <- TRUE # Prediction vs actual analysis
do_generate_pdf_report <- TRUE        # Combined PDF report of all results

# Input/output configuration
scale_factor <- 1e5                # Scaling factor for coefficients
results_path <- "results/collapseBatch_FALSE_groupBy_year_rcp_ssp_model_gcm_batch/analysis_scenarios/all_gamma_values/population_weighted"
input_file <- file.path(results_path, "regional_polynomials.csv")
input_data_csv <- "data/mortality_regression_full_mc.csv"  # Original data for prediction analysis

# Define required columns for data loading
required_columns <- c("region", "year", "batch", "gcm", "model", "rcp", "ssp", 
                      "adjusted_mortality", "anomaly", "total_population", "gdppc")

# Set GDP baseline years
gdp_baseline_start <- 2010
gdp_baseline_end <- 2020
# Set batch collapse option
collapse_batch <- FALSE

# Monte Carlo simulation parameters for prediction analysis
n_draws <- 100                     # Number of Monte Carlo draws

# Test mode
test_mode <- TRUE
test_iso3_list <- c("USA", "IND", "PAK", "BGD", "CHN")

# ======================================================================
# Setup Section - Libraries and Environment
# ======================================================================

# Load required libraries
required_packages <- c(
  "data.table", "dplyr", "ggplot2", "scales", "knitr", "mvtnorm", 
  "scattermore", "kableExtra", "tinytex", "gridExtra"
)

# Function to check and install missing packages
install_if_missing <- function(packages) {
  missing_packages <- packages[!(packages %in% installed.packages()[, "Package"])]
  if (length(missing_packages) > 0) {
    install.packages(missing_packages, dependencies = TRUE)
  }
}

# Install missing packages
install_if_missing(required_packages)

# Load all packages
invisible(lapply(required_packages, library, character.only = TRUE))

# Function to set working directory based on script location
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

# Set working directory
script_path <- get_script_path()
setwd(script_path)
cat(sprintf("Working directory set to: %s\n", script_path))

# Source required external scripts
if (file.exists("R/R/data_processing.R")) {
  source("R/R/data_processing.R")
} else {
  stop("Required script 'R/R/data_processing.R' not found.")
}

# ======================================================================
# Helper Functions
# ======================================================================

# Ensure directories exist
create_directories <- function(base_dir) {
  report_dir <- file.path(base_dir, "alphaFitReport")
  figures_dir <- file.path(report_dir, "figures")
  tables_dir <- file.path(report_dir, "tables")
  
  # Create necessary directories
  dir.create(report_dir, showWarnings = FALSE, recursive = TRUE)
  dir.create(figures_dir, showWarnings = FALSE)
  dir.create(tables_dir, showWarnings = FALSE)
  
  cat(sprintf("Report directory created at: %s\n", report_dir))
  
  return(list(
    report_dir = report_dir,
    figures_dir = figures_dir,
    tables_dir = tables_dir
  ))
}

# Load and scale results data
load_results <- function(file_path, scale_factor) {
  # Ensure the file exists
  if (!file.exists(file_path)) {
    stop("Error: The specified CSV file does not exist: ", file_path)
  }
  
  # Load and scale results
  results <- fread(file_path) %>%
    mutate(
      alpha = alpha * scale_factor,
      beta = beta * scale_factor,
      sigma11 = sigma11 * scale_factor^2,
      sigma12 = sigma12 * scale_factor^2,
      sigma22 = sigma22 * scale_factor^2,
      zeta = zeta * scale_factor,
      eta = eta * scale_factor
    )
  
  return(results)
}

# ======================================================================
# Report Generation Functions
# ======================================================================

# Basic Coefficient Analysis
generate_basic_coefficient_report <- function(results, dirs) {
  cat("Generating basic coefficient analysis...\n")
  
  # Filter results based on the median gamma value
  results.mu <- results[results$gamma == median(results$gamma),]
  
  if (test_mode) {
    results.mu$iso3 <- substring(results.mu$region, 1, 3)
    results.mu <- results.mu[results.mu$iso3 %in% test_iso3_list, ]
  }
  
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
    warning("No data available for median gamma value.")
  }
  
  # Save the summary statistics table
  summary_file <- file.path(dirs$tables_dir, "summary_statistics.csv")
  write.csv(summary(results.mu), summary_file, row.names = FALSE)
  cat(sprintf("Summary statistics saved to: %s\n", summary_file))
  
  # Generate and save the damage function plot
  if (nrow(pdf_data) > 0) {
    p <- ggplot(pdf_data, aes(TT, yy)) +
      geom_line() +
      geom_ribbon(aes(ymin = q25, ymax = q75), alpha = 0.5) +
      xlab("Climatic temperature change") + 
      ylab("Regional damage function") +
      theme_bw()
    
    plot_file <- file.path(dirs$figures_dir, "regional_damage_function.pdf")
    ggsave(plot_file, p, width = 7, height = 5)
    cat(sprintf("Plot saved to: %s\n", plot_file))
  }
  
  # Extract ISO3 codes (first 3 characters of region names)
  results.mu$iso3 <- substring(results.mu$region, 1, 3)
  
  # Compute zero crossing temperature: T = -alpha/beta
  results.mu$cross0 <- -results.mu$alpha / results.mu$beta
  
  # Compute proportions of different crossing scenarios
  prop_beta_zero <- mean(results.mu$beta == 0)  # Proportion where beta == 0
  prop_cross0_above_20 <- mean(results.mu$alpha < 0 & results.mu$beta != 0 & results.mu$cross0 > 20, na.rm = TRUE)
  prop_cross0_below_0 <- mean(results.mu$alpha > 0 & results.mu$beta != 0 & results.mu$cross0 < 0, na.rm = TRUE)
  
  # Create summary table
  zero_crossings_summary <- data.frame(
    Category = c("No crossing (β = 0)", "Beyond graph (T > 20)", "Never crossing (T < 0)"),
    Percentage = round(100 * c(prop_beta_zero, prop_cross0_above_20, prop_cross0_below_0), 2)
  )
  
  # Save results as CSV
  zero_crossings_file <- file.path(dirs$tables_dir, "zero_crossings_distribution.csv")
  write.csv(zero_crossings_summary, zero_crossings_file, row.names = FALSE)
  cat(sprintf("Zero crossings distribution saved to: %s\n", zero_crossings_file))
  
  # Classify regions as concave or convex based on alpha sign
  results.mu$poscross0 <- ifelse(results.mu$alpha > 0, "Concave", "Convex")
  
  # Generate histogram plot
  zero_crossings_plot <- file.path(dirs$figures_dir, "zero_crossings_histogram.pdf")
  p <- ggplot(subset(results.mu, cross0 > 0 & cross0 < 20), aes(cross0)) +
    facet_wrap(~ poscross0, ncol=1, scale="free_y") +
    geom_histogram() + 
    xlab("Temperature for crossing 0") + 
    ylab("Region count") +
    theme_bw() + 
    scale_x_continuous(expand=c(0, 0)) + 
    scale_y_continuous(expand=c(0, 0))
  
  # Save the plot
  ggsave(zero_crossings_plot, p, width = 8, height = 6)
  cat(sprintf("Zero crossings histogram saved to: %s\n", zero_crossings_plot))
  
  # Compute the maximum slope within the range 0 to 10°C
  results.mu$maxslope <- pmax(results.mu$alpha + 2 * results.mu$beta * 10, results.mu$alpha)
  
  # Save the computed slope values in a CSV file
  slope_summary_file <- file.path(dirs$tables_dir, "slope_distribution.csv")
  slope_summary <- data.frame(
    Region = results.mu$region,
    ISO3 = results.mu$iso3,
    Max_Slope = results.mu$maxslope
  )
  write.csv(slope_summary, slope_summary_file, row.names = FALSE)
  cat(sprintf("Slope distribution saved to: %s\n", slope_summary_file))
  
  # Generate histogram of the maximum slope
  slope_plot_file <- file.path(dirs$figures_dir, "slope_histogram.pdf")
  p_slope <- ggplot(results.mu, aes(maxslope)) +
    geom_histogram(bins = 30) + 
    xlab("Maximum slope from 0 to 10°C") + 
    ylab("Region count") +
    theme_bw() + 
    scale_x_continuous(expand=c(0, 0)) + 
    scale_y_continuous(expand=c(0, 0))
  
  # Save the plot
  ggsave(slope_plot_file, p_slope, width = 8, height = 6)
  cat(sprintf("Slope histogram saved to: %s\n", slope_plot_file))
  
  # Calculate convexity distribution by region
  results$iso3 <- substring(results$region, 1, 3)
  
  # Count how many times β > 0 for each region
  convex_df <- results %>%
    group_by(iso3) %>%
    summarise(
      convex_count = sum(beta > 0, na.rm = TRUE),  # Number of times β > 0
      total_count = n(),  # Total observations per region
      Proportion = convex_count / total_count  # Proportion of convexity
    ) %>%
    arrange(desc(Proportion))  # Sort by decreasing convexity
  
  # Save results
  convex_summary_file <- file.path(dirs$tables_dir, "convex_polynomial_distribution.csv")
  write.csv(convex_df, convex_summary_file, row.names = FALSE)
  
  # Print a summary
  prop_convex <- mean(results.mu$beta > 0, na.rm = TRUE)
  cat(sprintf("Proportion of convex responses (β > 0): %.2f%%\n", 100 * prop_convex))
  cat(sprintf("Convex polynomial distribution saved to: %s\n", convex_summary_file))
  
  # Return results for potential further analysis
  return(list(
    results = results,
    results_mu = results.mu
  ))
}

# Prediction Analysis
generate_prediction_report <- function(results, dirs, input_data_csv, required_columns,
                                       gdp_baseline_start, gdp_baseline_end, collapse_batch, n_draws, scale_factor, test_mode, test_iso3_list) {
  cat("Generating prediction analysis...\n")
  
  # Get median gamma value
  gamma.mu <- median(results$gamma)
  if (!("df" %in% ls(envir = .GlobalEnv)) || tolower(readline("Reload 'df' from disk? (y/n): ")) == "y") {
    cat("Loading data from disk...\n")
    # Load the original data
    df <- load_and_process_data(
      input_data_csv, 
      required_columns, 
      gdp_baseline_start = gdp_baseline_start, 
      gdp_baseline_end = gdp_baseline_end,
      collapse_batch_data = collapse_batch
    )
  } else {
    cat("Using the existing 'df' in memory.\n")
  }
  
  
  # Get the list of unique regions from results
  region_list <- unique(results$region)
  
  # Filter data to include only regions in results
  if (test_mode) {
    df <- df[df$region %in% test_iso3_list, ]
  } else {
    df <- df[df$region %in% region_list, ]
  }
  
  # Calculate normed values
  df$mean.normed <- df$delta_mortality / (exp(df$lgdp_delta)^gamma.mu)
  df$mean.normed.pred <- NA
  df$mean.pred <- NA
  df$mean.pred.mu <- NA
  df$mean.pred.sd <- NA
  
  # Process each region
  for (reg in region_list) {
    # Basic region-specific calculations
    reg_idx <- df$region == reg
    subdf <- df[reg_idx, ]
    subres_mu <- results[results$region == reg & results$gamma == gamma.mu, ]
    
    # Skip if no data for this region
    if (nrow(subres_mu) == 0) {
      warning(paste("No results found for region:", reg))
      next
    }
    
    # Simple predictions with vectorization
    pred <- subres_mu$alpha * subdf$delta_temp + subres_mu$beta * subdf$delta_temp^2
    df$mean.normed.pred[reg_idx] <- pred
    df$mean.pred[reg_idx] <- pred * exp(subdf$lgdp_delta)^gamma.mu
    
    # More complex Monte Carlo part
    subres <- results[results$region == reg, ]
    n_subres <- nrow(subres)
    n_subdf <- nrow(subdf)
    
    # Skip Monte Carlo if no data
    if (n_subres == 0 || n_subdf == 0) {
      next
    }
    
    # Pre-allocate full matrix
    all_draws <- matrix(0, nrow = n_draws * n_subres, ncol = n_subdf)
    
    # Key optimization: Prepare all input data first as vectors/matrices
    delta_temps <- subdf$delta_temp
    delta_temps_squared <- delta_temps^2
    lgdp_deltas <- subdf$lgdp_delta
    
    # Track progress
    cat("Processing region:", reg, "with", n_subres, "parameter sets\n")
    
    # Loop through parameter sets (potentially parallelize this loop)
    for (ii in 1:n_subres) {
      # Current parameters
      alpha <- subres$alpha[ii]
      beta <- subres$beta[ii]
      gamma <- subres$gamma[ii]
      sigma11 <- subres$sigma11[ii]
      sigma12 <- subres$sigma12[ii]
      sigma22 <- subres$sigma22[ii]
      zeta <- subres$zeta[ii]
      eta <- subres$eta[ii]
      
      # Setup covariance matrix once
      cov_matrix <- matrix(c(sigma11, sigma12, sigma12, sigma22), 2, 2)
      
      # Generate all random draws at once
      alphabetas <- rmvnorm(n_draws, c(alpha, beta), cov_matrix)
      thetas <- rnorm(n_draws, 0, zeta)
      phis <- rnorm(n_draws, 0, eta)
      
      # Pre-calculate GDP effects for all observations (expensive operation)
      gdp_effects <- exp(lgdp_deltas)^gamma
      
      # Row indices for current batch
      row_start <- (ii-1)*n_draws + 1
      row_end <- ii*n_draws
      
      # Optimized inner loop using vectorization
      for (draw in 1:n_draws) {
        alpha_i <- alphabetas[draw, 1]
        beta_i <- alphabetas[draw, 2]
        theta_i <- thetas[draw]
        phi_i <- phis[draw]
        
        # Vectorized operation for all observations at once
        all_draws[row_start + draw - 1, ] <- 
          (alpha_i * delta_temps + beta_i * delta_temps_squared) * gdp_effects + 
          theta_i * delta_temps * gdp_effects + phi_i
      }
    }
    
    # Calculate summary statistics all at once
    df$mean.pred.mu[reg_idx] <- colMeans(all_draws)
    df$mean.pred.sd[reg_idx] <- apply(all_draws, 2, sd)
    
    # Clean up to free memory
    rm(all_draws, delta_temps, delta_temps_squared, lgdp_deltas, gdp_effects)
    gc()
  }
  
  # Define output file paths
  correlation_file <- file.path(dirs$tables_dir, "correlation_values.csv")
  r2_file <- file.path(dirs$tables_dir, "r2_values.csv")
  scatter_plot_1 <- file.path(dirs$figures_dir, "scatter_plot_predicted_vs_reported.pdf")
  scatter_plot_2 <- file.path(dirs$figures_dir, "scatter_plot_predicted_mean_vs_reported.pdf")
  
  # Create the scatter plots
  df <- df %>% filter(!is.na(delta_mortality), !is.na(mean.pred))
  df$delta_mortality <- df$delta_mortality * scale_factor
  
  # Reported vs. Predicted plot
  p1 <- ggplot(df, aes(x = delta_mortality, y = mean.pred)) +
    geom_scattermore(pointsize = 0.5, alpha = 0.2) +
    geom_abline(slope = 1, colour = scales::muted('red')) +
    theme_bw() +
    xlab("Reported value") +
    ylab("Predicted value")
  
  # Save the plot
  ggsave(scatter_plot_1, p1, width = 7, height = 5)
  cat(sprintf("Scatter plot saved to: %s\n", scatter_plot_1))
  
  # Reported vs. Predicted Mean plot
  p2 <- ggplot(df, aes(x = delta_mortality, y = mean.pred.mu)) +
    geom_scattermore(pointsize = 0.5, alpha = 0.2) +
    geom_abline(slope = 1, colour = scales::muted('red')) +
    theme_bw() +
    xlab("Reported value") +
    ylab("Predicted value")
  
  # Save the plot
  ggsave(scatter_plot_2, p2, width = 7, height = 5)
  cat(sprintf("Scatter plot saved to: %s\n", scatter_plot_2))
  
  # Compute correlations, handling missing values
  cor1 <- cor(df$delta_mortality, df$mean.pred, use = 'complete.obs')
  cor2 <- cor(df$mean.pred, df$mean.pred.mu, use = 'complete.obs')
  
  # Save correlation results to CSV
  cor_data <- data.frame(
    Metric = c("Correlation: Reported vs Predicted", "Correlation: Predicted vs Predicted Mean"),
    Value = c(cor1, cor2)
  )
  write.csv(cor_data, correlation_file, row.names = FALSE)
  cat(sprintf("Correlation values saved to: %s\n", correlation_file))
  
  # Compute R² for different comparisons, ensuring there are valid data points
  
  ## R²: Mean Normed vs Predicted
  valid1 <- !is.na(df$mean.normed) & !is.na(df$mean.normed.pred)
  
  if (sum(valid1) > 0) {
    y_true <- df$mean.normed[valid1]
    y_pred <- df$mean.normed.pred[valid1]
    
    ss_total <- sum((y_true - mean(y_true, na.rm = TRUE))^2, na.rm = TRUE)
    ss_residual <- sum((y_true - y_pred)^2, na.rm = TRUE)
    
    if (ss_total > 1e-10 && ss_residual >= 0) {  
      r2_1 <- max(1 - (ss_residual / ss_total), -1)
    } else {
      r2_1 <- NA
      cat("Warning: Variance of mean.normed is too small. Assigning NA to R².\n")
    }
  } else {
    r2_1 <- NA
    cat("Warning: No valid observations for R² (Mean Normed vs Predicted). Assigning NA.\n")
  }
  
  ## R²: Reported (delta_mortality) vs Predicted
  valid2 <- !is.na(df$delta_mortality) & !is.na(df$mean.pred)
  
  if (sum(valid2) > 0) {
    y_true <- df$delta_mortality[valid2]
    y_pred <- df$mean.pred[valid2]
    
    ss_total <- sum((y_true - mean(y_true, na.rm = TRUE))^2, na.rm = TRUE)
    ss_residual <- sum((y_true - y_pred)^2, na.rm = TRUE)
    
    if (ss_total > 1e-10) {
      r2_2 <- max(1 - (ss_residual / ss_total), -1)
    } else {
      r2_2 <- NA
      cat("Warning: Variance of delta_mortality is zero. Assigning NA to R².\n")
    }
  } else {
    r2_2 <- NA
    cat("Warning: No valid observations for R² (Mean vs Predicted). Assigning NA.\n")
  }
  
  # Save R² results to CSV
  r2_data <- data.frame(
    Metric = c("R²: Mean Normed vs Predicted", "R²: Mean vs Predicted"),
    Value = c(r2_1, r2_2)
  )
  write.csv(r2_data, r2_file, row.names = FALSE)
  cat(sprintf("R² values saved to: %s\n", r2_file))
  
  # Identify the top 5 worst offenders (unique regions)
  top_offenders <- df %>%
    filter(!is.na(delta_mortality), !is.na(mean.pred)) %>%
    group_by(region) %>%
    summarize(max_abs_error = max(abs(delta_mortality - mean.pred), na.rm = TRUE)) %>%
    arrange(desc(max_abs_error)) %>%
    slice(1:5)
  
  # Check if fewer than 5 regions exist in the dataset
  if (nrow(top_offenders) < 5) {
    cat(sprintf("Warning: Only %d unique regions found with valid data.\n", nrow(top_offenders)))
  }
  
  # Create the grid plot for worst offenders
  offenders_plot <- file.path(dirs$figures_dir, "worst_offenders_top5.pdf")
  
  # Only create the plot if we have offenders
  if (nrow(top_offenders) > 0) {
    gp <- ggplot(df %>% filter(region %in% top_offenders$region), 
                 aes(x = delta_temp, colour = as.factor(round(lgdp_delta, 2)))) +
      geom_point(aes(y = delta_mortality, shape = 'Reported')) +
      geom_point(aes(y = mean.pred, shape = 'Predicted')) +
      facet_wrap(~ region, scales = "free") +
      theme_bw() +
      labs(title = "Top 5 Worst Offenders: Reported vs Predicted",
           x = "Temperature Change",
           y = "Mortality Change",
           colour = "Log GDP Delta") +
      scale_shape_manual(name = "Value Type", values = c(16, 17))
    
    # Save the plot
    ggsave(offenders_plot, gp, width = 10, height = 8)
    cat(sprintf("Offenders plot saved to: %s\n", offenders_plot))
  }
  
  return(df)
}

# Generate PDF Report
generate_pdf_report <- function(dirs) {
  cat("Generating PDF report...\n")
  
  # Define paths
  output_pdf <- file.path(dirs$report_dir, "damage_function_report.pdf")
  output_tex <- file.path(dirs$report_dir, "damage_function_report.tex")
  
  # Function to read CSV and format it as LaTeX
  read_table_latex <- function(file_path, caption) {
    if (file.exists(file_path)) {
      data <- read.csv(file_path)
      return(kable(data, format = "latex", booktabs = TRUE, caption = caption) %>% 
               kable_styling(latex_options = "hold_position"))
    } else {
      return(paste("\\textbf{Error:}", file_path, "not found.\\newline"))
    }
  }
  
  # Read tables
  summary_table <- read_table_latex(file.path(dirs$tables_dir, "summary_statistics.csv"), 
                                    "Summary Statistics")
  zero_crossings_table <- read_table_latex(file.path(dirs$tables_dir, "zero_crossings_distribution.csv"), 
                                           "Zero Crossings Distribution")
  
  # Check if prediction analysis tables exist
  correlation_table <- ""
  r2_table <- ""
  if (file.exists(file.path(dirs$tables_dir, "correlation_values.csv"))) {
    correlation_table <- read_table_latex(file.path(dirs$tables_dir, "correlation_values.csv"), 
                                          "Correlation Values")
    r2_table <- read_table_latex(file.path(dirs$tables_dir, "r2_values.csv"), 
                                 "R-squared Values")
  }
  
  # Function to embed a figure in LaTeX
  embed_figure <- function(fig_path, caption, width = "0.8\\textwidth") {
    if (file.exists(fig_path)) {
      return(paste("\\begin{figure}[h]",
                   "\\centering",
                   paste0("\\includegraphics[width=", width, "]{", fig_path, "}"),
                   paste0("\\caption{", caption, "}"),
                   "\\end{figure}", sep = "\n"))
    } else {
      return("")  # Skip if file doesn't exist
    }
  }
  
  # Identify which figures exist
  figures <- c()
  
  # Basic figures
  basic_figs <- list(
    list(path = file.path(dirs$figures_dir, "regional_damage_function.pdf"), 
         caption = "Regional Damage Function"),
    list(path = file.path(dirs$figures_dir, "zero_crossings_histogram.pdf"), 
         caption = "Zero Crossings Histogram"),
    list(path = file.path(dirs$figures_dir, "slope_histogram.pdf"), 
         caption = "Slope Distribution")
  )
  
  # Prediction figures
  pred_figs <- list(
    list(path = file.path(dirs$figures_dir, "scatter_plot_predicted_vs_reported.pdf"), 
         caption = "Scatter Plot: Reported vs Predicted"),
    list(path = file.path(dirs$figures_dir, "scatter_plot_predicted_mean_vs_reported.pdf"), 
         caption = "Scatter Plot: Reported vs Predicted Mean"),
    list(path = file.path(dirs$figures_dir, "worst_offenders_top5.pdf"), 
         caption = "Top 5 Worst Offenders")
  )
  
  # Add figures that exist
  for (fig in c(basic_figs, pred_figs)) {
    if (file.exists(fig$path)) {
      figures <- c(figures, embed_figure(fig$path, fig$caption))
    }
  }
  
  # Create the LaTeX document with sections based on what's available
  latex_content <- paste0("
\\documentclass{article}
\\usepackage{graphicx}
\\usepackage{booktabs}
\\usepackage{float}
\\usepackage{caption}
\\usepackage{geometry}
\\geometry{margin=1in}

\\title{Damage Function Report}
\\author{Generated Automatically}
\\date{\\today}

\\begin{document}

\\maketitle

\\section{Summary Statistics}
", summary_table, "

\\section{Zero Crossings Distribution}
", zero_crossings_table, "

")
  
  # Add prediction sections if they exist
  if (correlation_table != "") {
    latex_content <- paste0(latex_content, "
\\section{Prediction Performance}
\\subsection{Correlation Values}
", correlation_table, "

\\subsection{R-squared Values}
", r2_table, "

")
  }
  
  # Add figures section
  if (length(figures) > 0) {
    latex_content <- paste0(latex_content, "
\\section{Figures}
", paste(figures, collapse = "\n"), "
")
  }
  
  # Close the document
  latex_content <- paste0(latex_content, "
\\end{document}
")
  
  # Save the LaTeX file
  writeLines(latex_content, output_tex)
  
  # Compile LaTeX to PDF if tinytex is available
  if (requireNamespace("tinytex", quietly = TRUE)) {
    tinytex::pdflatex(output_tex)
    cat(sprintf("Report saved to: %s\n", output_pdf))
  } else {
    cat("TinyTeX not available. LaTeX file saved to: ", output_tex, 
        ". Please compile manually.\n")
  }
}


# ======================================================================
# Main Execution
# ======================================================================

main <- function() {
  # Validate input file
  if (!file.exists(input_file)) {
    stop("Input file does not exist: ", input_file)
  }
  
  # Create output directories
  dirs <- create_directories(dirname(input_file))
  
  # Load results data
  results <- load_results(input_file, scale_factor)
  
  # Filter by test countries if test_mode is enabled
  if (test_mode) {
    cat("Test mode active. Filtering results to test countries only.\n")
    results$iso3 <- substring(results$region, 1, 3)
    results <- results %>% filter(iso3 %in% test_iso3_list)
  }
  
  # Generate basic report if requested
  if (do_generate_basic_report) {
    cat("=== Generating Basic Report ===\n")
    basic_results <- generate_basic_coefficient_report(results, dirs)
  }
  
  # Generate prediction report if requested
  if (do_generate_prediction_report) {
    cat("=== Generating Prediction Report ===\n")

    # Generate the prediction report
    prediction_data <- generate_prediction_report(
      results, 
      dirs, 
      input_data_csv, 
      required_columns,
      gdp_baseline_start, 
      gdp_baseline_end, 
      collapse_batch, 
      n_draws,
      scale_factor,
      test_mode = test_mode, 
      test_iso3_list = test_iso3_list
    )
  }
  
  # Generate combined PDF report if requested
  if (do_generate_pdf_report) {
    cat("=== Generating PDF Report ===\n")
    generate_pdf_report(dirs)
  }
  
  cat("Analysis complete!\n")
}

# Run the main function
main()

