# File: R/R/scenario_analysis.R
library(dplyr)
library(lfe)
library(ggplot2)
library(logger)

run_scenario_analysis <- function(data, gamma_filter, 
                                  use_weights = TRUE, 
                                  collapse_batch = FALSE, 
                                  parallel = FALSE,
                                  ncores = 1,
                                  base_model_fn = NULL, 
                                  regional_model_fn = NULL,
                                  regional_formula = mean_normed ~ delta_temp + I(delta_temp^2)) {
  
  log_info("Running scenario analysis with gamma_filter: {gamma_filter}, use_weights: {use_weights}, collapse_batch: {collapse_batch}, parallel: {parallel}, ncores: {ncores}")
  
  # Set up directories for results.
  base_path <- setup_environment(collapse_batch = collapse_batch)
  
  # Define output directory for analysis results
  output_dir <- file.path(base_path, "analysis_scenarios", gamma_filter,
                          if (use_weights) "population_weighted" else "unweighted")
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  
  # Define global model file path
  global_model_path <- file.path(output_dir, "global_model_coefficients.csv")
  
  # If global model exists, load it and skip recalculations
  if (file.exists(global_model_path)) {
    log_info("Global model already exists. Skipping computation.")
    globaldf <- read.csv(file.path(output_dir, "global_analysis.csv"))
  } else {
    log_info("Global model does not exist. Running estimation...")
    
    # Set default model function if not provided
    if (is.null(base_model_fn)) {
      base_model_fn <- function(data, weights) {
        felm(log_delta_mortality ~ loggdppc | group + year | 0 | group + year,
             data = data, weights = weights)
      }
    }
    
    # Determine weights
    weights <- if (use_weights) ifelse(!is.na(data$population), data$population, 1) else rep(1, nrow(data))
    log_info("Using weights: {use_weights}. Number of non-NA population values: {sum(!is.na(data$population))}")
    
    # Compute gamma parameters
    mod <- base_model_fn(data, weights)
    log_info("Base model fit completed. Number of coefficients estimated: {length(mod$coefficients)}")
    
    gamma <- list(
      mu = mod$coefficients[1],
      se = mod$cse[1],
      values = qnorm(seq(0.05, 0.95, by = 0.05), mod$coefficients[1], mod$cse[1])
    )
    
    if (gamma_filter == "positive_gamma_only") {
      gamma$values <- gamma$values[gamma$values > 0]
      gamma$mu <- mean(gamma$values, na.rm = TRUE)
      gamma$se <- sd(gamma$values, na.rm = TRUE) / sqrt(length(gamma$values))
    }
    log_info("Filtered gamma values. Remaining count: {length(gamma$values)}")
    
    # Prepare global data
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
          mean_normed = mean / (gdp_diff^gamma$mu),
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
          mean_normed = mean / (gdp_diff^gamma$mu),
          tas_preind2 = tas_preind^2
        )
    }
    log_info("Global data prepared with {nrow(globaldf)} observations.")
    
    # Run global model estimation
    mod_global <- lm(mean_normed ~ tas_preind + tas_preind2,
                     data = globaldf,
                     weights = if (use_weights) globaldf$population else NULL)
    
    log_info("Global model fit completed. Coefficients estimated: {length(coef(mod_global))}")
    
    globaldf$resids <- if (!is.null(mod_global$na.action)) {
      x <- rep(NA, nrow(globaldf))
      x[-mod_global$na.action] <- residuals(mod_global)
      x
    } else {
      residuals(mod_global)
    }
    
    # Save global model results
    write.csv(globaldf, file.path(output_dir, "global_analysis.csv"), row.names = FALSE)
    
    global_model_coef <- data.frame(
      term = names(coef(mod_global)),
      estimate = coef(mod_global),
      std_error = summary(mod_global)$coefficients[, "Std. Error"],
      t_value = summary(mod_global)$coefficients[, "t value"],
      p_value = summary(mod_global)$coefficients[, "Pr(>|t|)"]
    )
    write.csv(global_model_coef, global_model_path, row.names = FALSE)
    log_info("Global model results saved.")
  }
  
  # Run regional analysis
  regional_results <- run_regional_analysis(data, gamma$values, gamma, globaldf, output_dir)
  
  log_info("Scenario analysis complete.")
  return(list(
    gamma = gamma,
    globaldf = globaldf,
    mod_global = mod_global,
    main_model = mod,
    regional_results = regional_results,
    base_path = base_path
  ))
}
