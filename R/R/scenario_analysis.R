# File: R/R/scenario_analysis.R
library(dplyr)
library(lfe)
library(ggplot2)
library(logger)

# Run the overall scenario analysis.
run_scenario_analysis <- function(data, gamma_filter, 
                                  use_weights = TRUE, 
                                  collapse_batch = FALSE, 
                                  parallel = FALSE,
                                  ncores = 1,
                                  test = FALSE,  # Test flag
                                  base_model_fn = NULL, 
                                  regional_model_fn = NULL,
                                  regional_formula = mean_normed ~ delta_temp + I(delta_temp^2)) {
  
  log_info("Running scenario analysis with gamma_filter: {gamma_filter}, use_weights: {use_weights}, collapse_batch: {collapse_batch}, parallel: {parallel}, ncores: {ncores}, test: {test}")
  
  if ("delta_mortality" %in% names(data)) {
    data$log_delta_mortality <- log(data$delta_mortality)
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
  
  base_path <- setup_environment(collapse_batch = collapse_batch)
  output_dir <- file.path(base_path, "analysis_scenarios", gamma_filter,
                          if (use_weights) "population_weighted" else "unweighted")
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  
  log_info("Base path for results: {base_path}")
  
  # Check if the global model already exists
  gamma_file <- file.path(output_dir, "gamma_statistics.csv")
  global_model_path <- file.path(output_dir, "global_model_coefficients.csv")
  
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
    
    if (gamma_filter == "positive_gamma_only") {
      gamma$values <- gamma$values[gamma$values > 0]
      gamma$mu <- mean(gamma$values, na.rm = TRUE)
      gamma$se <- sd(gamma$values, na.rm = TRUE) / sqrt(length(gamma$values))
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
    write.csv(gamma_df, gamma_file, row.names = FALSE)
    
    write.csv(globaldf, file.path(output_dir, "global_analysis.csv"), row.names = FALSE)
    
    global_model_coef <- data.frame(
      term = names(coef(mod_global)),
      estimate = coef(mod_global),
      std_error = summary(mod_global)$coefficients[, "Std. Error"],
      t_value = summary(mod_global)$coefficients[, "t value"],
      p_value = summary(mod_global)$coefficients[, "Pr(>|t|)"]
    )
    write.csv(global_model_coef, global_model_path, row.names = FALSE)
  }
  
  # Run regional analysis, passing the test flag
  regional_results <- run_regional_analysis(data, gamma$values, gamma, globaldf, output_dir, test = test)
  
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
