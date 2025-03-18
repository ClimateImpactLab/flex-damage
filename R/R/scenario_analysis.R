# File: R/R/scenario_analysis.R
library(dplyr)
library(lfe)
library(ggplot2)
library(logger)
source("R/R/utils.R")

# Run the overall scenario analysis.
run_scenario_analysis <- function(data, gamma_filter, 
                                  use_weights = TRUE, 
                                  collapse_batch = FALSE, 
                                  parallel = FALSE,
                                  ncores = 1,
                                  test = FALSE,  # Test flag
                                  base_model_fn = NULL, 
                                  regional_model_fn = NULL,
                                  save_regional_results = TRUE, 
                                  create_regional_plots = TRUE,
                                  regional_formula = mean_normed ~ delta_temp + I(delta_temp^2)) {
  
  log_info("Running scenario analysis with gamma_filter: {gamma_filter}, use_weights: {use_weights}, collapse_batch: {collapse_batch}, parallel: {parallel}, ncores: {ncores}, test: {test}")
  
  if ("delta_mortality" %in% names(data)) {
    data$log_delta_mortality <- safe_log(data$delta_mortality)
  } else {
    stop("Error: Column 'delta_mortality' not found in the dataframe.")
  }
  
  if (is.null(base_model_fn)) {
    base_model_fn <- function(data, weights) {
      felm(log_delta_mortality ~ loggdppc | group + year | 0 | group + year,
           data = data, weights = weights)
    }
  }
  
  # Determine weights.
  weights <- if (use_weights) ifelse(!is.na(data$population), data$population, 1) else rep(1, nrow(data))
  
  base_path <- if (test) {
    file.path("results_test", setup_environment(collapse_batch = collapse_batch))
  } else {
    file.path("results", setup_environment(collapse_batch = collapse_batch))
  }
  
  output_dir <- file.path(base_path, "analysis_scenarios", gamma_filter,
                          if (use_weights) "population_weighted" else "unweighted")
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  
  log_info("Base path for results: {base_path}")
  
  # Check if the global model already exists
  
  base_model_dir <- file.path(base_path, "base_model")
  dir.create(base_model_dir, recursive = TRUE, showWarnings = FALSE)
  
  global_model_path <- file.path(base_model_dir, "global_model_coefficients.csv")
  gamma_statistics_path <- file.path(base_model_dir, "gamma_statistics.csv")
  gamma_distribution_path <- file.path(base_model_dir, "gamma_distribution.pdf")
  gamma_file <- file.path(base_model_dir, "gamma_statistics.csv")
  
  log_info("Global model path: {global_model_path}")

  
  if (file.exists(global_model_path)) {
    log_info("Global model already exists. Skipping computation.")
    
    # Load gamma values from saved results
    gamma_df <- read.csv(gamma_file)
    gamma <- list(
      mu = gamma_df$mu[1],
      se = gamma_df$se[1],
      values = seq(gamma_df$ci_lower[1], gamma_df$ci_upper[1], length.out = 19)
    )
    
    # Load previously saved global analysis
    globaldf <- read.csv(file.path(output_dir, "global_analysis.csv"))
    
    # Load mod_global from previously saved coefficients
    mod_global <- read.csv(global_model_path)
    
    # Assign mod as NULL (it's not used when skipping)
    mod <- NULL
  } else {
    log_info("Running global model estimation...")
    
    mod <- base_model_fn(data, weights)
    
    gamma <- list(
      mu = mod$coefficients[1],
      se = mod$cse[1],
      values = qnorm(seq(0.05, 0.95, by = 0.05), mod$coefficients[1], mod$cse[1])
    )
    
    gamma_unfiltered <- gamma$mu
    
    # Save gamma distribution plot
    pdf(gamma_distribution_path)
    plot(density(gamma$values), 
         main = "Distribution of gamma values",
         xlab = "Gamma",
         ylab = "Density")
    abline(v = gamma$mu, col = "red")
    abline(v = gamma$mu + 2 * gamma$se, col = "blue", lty = 2)
    abline(v = gamma$mu - 2 * gamma$se, col = "blue", lty = 2)
    dev.off()
    log_info("Gamma distribution plot saved to: {gamma_distribution_path}")
  
    
    if (gamma_filter == "positive_gamma_only") {
      gamma$values <- gamma$values[gamma$values > 0]
      
      if (length(gamma$values) == 0) {
        stop("Error: No positive values in gamma$values after filtering. Unable to compute gamma$mu.")
      }
      
      gamma$mu <- mean(gamma$values, na.rm = TRUE)
      gamma$se <- sd(gamma$values, na.rm = TRUE) / sqrt(length(gamma$values))
      
      if (is.na(gamma$mu) || is.infinite(gamma$mu)) {
        stop("Error: gamma$mu is invalid after filtering positive values.")
      }
    }
    
    if (collapse_batch) {
      globaldf <- data %>%
        group_by(year, rcp, ssp, model, gcm) %>%
        summarize(
          mean = sum(delta_mortality * population, na.rm = TRUE) / sum(population, na.rm = TRUE),
          tas_preind = sum(delta_temp * population, na.rm = TRUE) / sum(population, na.rm = TRUE),
          gdp_diff = sum(exp(lgdp_delta) * population, na.rm = TRUE) / sum(population, na.rm = TRUE),
          population = sum(population, na.rm = TRUE),
          .groups = 'drop'
        ) %>%
        mutate(
          mean_normed = mean / (gdp_diff^gamma_unfiltered),
          tas_preind2 = tas_preind^2
        )
    } else {
      globaldf <- data %>%
        group_by(batch, year, rcp, ssp, model, gcm) %>%
        summarize(
          mean = sum(delta_mortality * population, na.rm = TRUE) / sum(population, na.rm = TRUE),
          tas_preind = sum(delta_temp * population, na.rm = TRUE) / sum(population, na.rm = TRUE),
          gdp_diff = sum(exp(lgdp_delta) * population, na.rm = TRUE) / sum(population, na.rm = TRUE),
          population = sum(population, na.rm = TRUE),
          .groups = 'drop'
        ) %>%
        mutate(
          mean_normed = mean / (gdp_diff^gamma_unfiltered),
          tas_preind2 = tas_preind^2
        )
    }
    
    mod_global <- lm(mean_normed ~ tas_preind + tas_preind2,
                     data = globaldf,
                     weights = if (use_weights) globaldf$population else NULL)
    
    globaldf$resids <- if (!is.null(mod_global$na.action)) {
      x <- rep(NA, nrow(globaldf))
      x[-mod_global$na.action] <- residuals(mod_global)
      x
    } else {
      residuals(mod_global)
    }
    
    gamma_df <- data.frame(
      mu = gamma$mu,
      se = gamma$se,
      ci_lower = gamma$mu - 2 * gamma$se,
      ci_upper = gamma$mu + 2 * gamma$se
    )
    write.csv(gamma_df, gamma_statistics_path, row.names = FALSE)
    log_info("Gamma statistics saved to: {gamma_statistics_path}")
    
    global_model_coef <- data.frame(
      term = names(coef(mod_global)),
      estimate = coef(mod_global),
      std_error = summary(mod_global)$coefficients[, "Std. Error"],
      t_value = summary(mod_global)$coefficients[, "t value"],
      p_value = summary(mod_global)$coefficients[, "Pr(>|t|)"]
    )
    write.csv(global_model_coef, global_model_path, row.names = FALSE)
    log_info("Global model coefficients saved to: {global_model_path}")
  }
  
  # **1. Graph for Mortality and Temperature relationship
  p1 <- ggplot(globaldf, aes(x = tas_preind, y = mean_normed)) +
    geom_point(alpha = 0.5) +
    geom_smooth(method = "lm", formula = y ~ poly(x, 2), se = TRUE) +
    labs(x = "Temperature anomaly (°C)",
         y = "Normalized mortality",
         title = paste("Global mortality response to temperature -",
                       gamma_filter,
                       if(use_weights) "- population weighted" else "- unweighted")) +
    theme_minimal()
  
  ggsave(file.path(output_dir, "mortality_temp_relationship.pdf"), p1)
  log_info("Saved plot: mortality_temp_relationship.pdf")
  
  # **2. Graph for residuals and time relationship**
  p2 <- ggplot(globaldf, aes(x = year, y = resids)) +
    geom_point(alpha = 0.5) +
    geom_smooth(method = "loess", se = TRUE) +
    labs(x = "Year",
         y = "Residuals",
         title = paste("Global model residuals over time -",
                       gamma_filter,
                       if(use_weights) "- population weighted" else "- unweighted")) +
    theme_minimal()
  
  ggsave(file.path(output_dir, "residuals_time.pdf"), p2)
  log_info("Saved plot: residuals_time.pdf")
  
  
  # Run regional analysis, passing the test flag
  regional_results <- run_regional_analysis(data, gamma$values, gamma, globaldf, output_dir, test = test, save_regional_results = TRUE, create_regional_plots = TRUE)
  
  log_info("Scenario analysis complete.")
  return(list(
    gamma = gamma,
    globaldf = globaldf,
    mod_global = mod_global,
    main_model = mod,  # Will be NULL if skipping
    regional_results = regional_results,
    base_path = base_path
  ))
}
