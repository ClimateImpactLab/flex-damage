# File: R/R/scenario_analysis.R
library(dplyr)
library(lfe)
library(ggplot2)
library(logger)

# Run the overall scenario analysis.
# Optional parameters:
#   - base_model_fn: a function(data, weights) returning the overall model.
#   - regional_model_fn: a function(subdf, regional_formula) for regional regressions.
#   - regional_formula: the regression formula to be used in regional models.
run_scenario_analysis <- function(data, gamma_filter, 
                                  use_weights = TRUE, 
                                  collapse_batch = FALSE, 
                                  parallel = FALSE,
                                  ncores = 1,
                                  base_model_fn = NULL, 
                                  regional_model_fn = NULL,
                                  regional_formula = mean_normed ~ delta_temp + I(delta_temp^2)) {
  
  log_info("Running scenario analysis with gamma_filter: {gamma_filter}, use_weights: {use_weights}, collapse_batch: {collapse_batch}, parallel: {parallel}, ncores: {ncores}")
  
  # Set default overall model function if not provided.
  if (is.null(base_model_fn)) {
    base_model_fn <- function(data, weights) {
      felm(log_delta_mortality ~ loggdppc | group + year | 0 | group + year,
           data = data, weights = weights)
    }
  }
  
  # Determine weights.
  weights <- if (use_weights) ifelse(!is.na(data$population), data$population, 1) else rep(1, nrow(data))
  log_info("Using weights: {use_weights}. Number of non-NA population values: {sum(!is.na(data$population))}")
  
  # Set up directories for results.
  base_path <- setup_environment(collapse_flag = collapse_batch, collapse_batch = collapse_batch)
  
  log_info("Base path for results: {base_path}")
  
  # Fit the overall (base) model.
  mod <- base_model_fn(data, weights)
  log_info("Base model fit completed. Number of coefficients estimated: {length(mod$coefficients)}")
  
  # Compute gamma parameters from the overall model.
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
  
  # Prepare global data for further analysis.
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
  
  # Save gamma statistics.
  output_dir <- file.path(base_path, "analysis_scenarios", gamma_filter,
                          if (use_weights) "population_weighted" else "unweighted")
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  log_info("Output directory created: {output_dir}")
  
  gamma_df <- data.frame(
    mu = gamma$mu,
    se = gamma$se,
    ci_lower = gamma$mu - 2 * gamma$se,
    ci_upper = gamma$mu + 2 * gamma$se
  )
  write.csv(gamma_df, file.path(output_dir, "gamma_statistics.csv"), row.names = FALSE)
  
  # Save additional global outputs.
  gamma_values_df <- data.frame(
    quantile = seq(0.05, 0.95, length.out = length(gamma$values)),
    value = gamma$values
  )
  write.csv(gamma_values_df, file.path(output_dir, "gamma_values.csv"), row.names = FALSE)
  
  write.csv(globaldf, file.path(output_dir, "global_analysis.csv"), row.names = FALSE)
  log_info("Saved global analysis results in {output_dir}.")
  
  global_model_coef <- data.frame(
    term = names(coef(mod_global)),
    estimate = coef(mod_global),
    std_error = summary(mod_global)$coefficients[, "Std. Error"],
    t_value = summary(mod_global)$coefficients[, "t value"],
    p_value = summary(mod_global)$coefficients[, "Pr(>|t|)"]
  )
  write.csv(global_model_coef, file.path(output_dir, "global_model_coefficients.csv"), row.names = FALSE)
  
  # Generate a simple density plot for gamma values.
  pdf(file.path(output_dir, "gamma_distribution.pdf"))
  plot(density(gamma$values),
       main = paste("Distribution of gamma values -", gamma_filter,
                    if (use_weights) "- population weighted" else "- unweighted"),
       xlab = "Gamma", ylab = "Density")
  abline(v = gamma$mu, col = "red")
  abline(v = gamma$mu + 2 * gamma$se, col = "blue", lty = 2)
  abline(v = gamma$mu - 2 * gamma$se, col = "blue", lty = 2)
  dev.off()
  
  p1 <- ggplot(globaldf, aes(x = tas_preind, y = mean_normed)) +
    geom_point(alpha = 0.5) +
    geom_smooth(method = "lm", formula = y ~ poly(x, 2), se = TRUE) +
    labs(x = "Temperature anomaly (°C)",
         y = "Normalized mortality",
         title = paste("Global mortality response to temperature -", gamma_filter,
                       if (use_weights) "- population weighted" else "- unweighted")) +
    theme_minimal()
  ggsave(file.path(output_dir, "mortality_temp_relationship.pdf"), p1)
  
  p2 <- ggplot(globaldf, aes(x = year, y = resids)) +
    geom_point(alpha = 0.5) +
    geom_smooth(method = "loess", se = TRUE) +
    labs(x = "Year",
         y = "Residuals",
         title = paste("Global model residuals over time -", gamma_filter,
                       if (use_weights) "- population weighted" else "- unweighted")) +
    theme_minimal()
  ggsave(file.path(output_dir, "residuals_time.pdf"), p2)
  
  # Run regional analysis.
  regional_results <- run_regional_analysis(data, globaldf, output_dir,
                                            collapse_data = collapse_batch,
                                            parallel = parallel, ncores = ncores,
                                            regional_model_fn = regional_model_fn,
                                            regional_formula = regional_formula)
  
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
