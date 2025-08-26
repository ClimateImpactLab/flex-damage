# Analysis Component Functions
# Individual analysis steps that can be called separately

#' Run global analysis
#' 
#' Performs population-weighted global analysis
#' 
#' @param data Processed data
#' @param gamma Gamma statistics
#' @param use_weights Whether to use population weights
#' @return Global analysis results
run_global_analysis <- function(data, gamma, use_weights) {
  
  # Global aggregation
  globaldf <- data %>%
    group_by(year, rcp, ssp, model, gcm) %>%
    summarize(
      mean = sum(delta_impact * population, na.rm = TRUE) / sum(population, na.rm = TRUE),
      tas_preind = sum(delta_temp * population, na.rm = TRUE) / sum(population, na.rm = TRUE),
      gdp_diff = sum(exp(lgdp_delta) * population, na.rm = TRUE) / sum(population, na.rm = TRUE),
      population = sum(population, na.rm = TRUE),
      .groups = 'drop'
    ) %>%
    mutate(
      mean_normed = mean / (gdp_diff^gamma$mu),
      tas_preind2 = tas_preind^2
    )
  
  # Fit global model
  mod_global <- lm(mean_normed ~ tas_preind + tas_preind2,
                   data = globaldf,
                   weights = if(use_weights) globaldf$population else NULL)
  
  # Calculate residuals
  globaldf$resids <- NA
  if (!is.null(mod_global$na.action)) {
    globaldf$resids[-mod_global$na.action] <- residuals(mod_global)
  } else {
    globaldf$resids <- residuals(mod_global)
  }
  
  return(list(
    globaldf = globaldf,
    mod_global = mod_global
  ))
}

#' Run regional analysis
#' 
#' Performs region-by-region polynomial fitting
#' 
#' @param data Processed data
#' @param gamma Gamma statistics  
#' @param globaldf Global analysis results
#' @param output_dir Output directory
#' @param config Configuration
#' @param impact_var Impact variable name
#' @return Regional analysis results
run_regional_analysis <- function(data, gamma, globaldf, output_dir, config, impact_var) {
  
  results <- data.frame()
  regions <- unique(data$region)
  total_regions <- length(regions)
  
  # Progress tracking
  if (config$progress$show_spinner) {
    spinner <- c("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
  }
  
  cat("Processing", total_regions, "regions...\n")
  
  for (i in seq_along(regions)) {
    reg <- regions[i]
    if (reg == "") next
    
    # Progress display
    if (config$progress$show_spinner) {
      percentage <- round((i/total_regions) * 100, 1)
      spin_char <- spinner[(i %% length(spinner)) + 1]
      cat(sprintf("\r%s %s | Progress: %d/%d [%.1f%%] %s",
                  spin_char, reg, i, total_regions, percentage,
                  ifelse(i == total_regions, "✓", "")))
    }
    
    subdf <- subset(data, region == reg)
    
    for (gamma_val in gamma$values) {
      # Normalize impact by GDP adaptation
      subdf$mean_normed <- subdf$delta_impact / (exp(subdf$lgdp_delta)^gamma_val)
      subdf$tas_preind2 <- subdf$delta_temp^2
      
      # Skip if insufficient data
      if (sum(!is.na(subdf$mean_normed) & !is.na(subdf$delta_temp)) < config$modeling$min_regional_obs) {
        next
      }
      
      # Fit regional model
      mod <- lm(mean_normed ~ delta_temp + tas_preind2, data = subdf)
      
      # Force convexity if needed
      if (config$modeling$force_convexity && coef(mod)[3] < 0) {
        mod <- lm(mean_normed ~ delta_temp, data = subdf)
        coeff <- c(coef(mod), 0)
        vcv <- vcov(mod)
        vcv <- cbind(rbind(vcv, c(0, 0)), c(0, 0, 0))
      } else {
        coeff <- coef(mod)
        vcv <- vcov(mod)
      }
      
      # Calculate residuals and correlation with global
      subdf$resids <- NA
      if (!is.null(mod$na.action)) {
        subdf$resids[-mod$na.action] <- residuals(mod)
      } else {
        subdf$resids <- residuals(mod)
      }
      
      # Match with global residuals
      merged_df <- subdf %>%
        left_join(globaldf %>% select(year, rcp, ssp, gcm, model, resids),
                  by = c("year", "rcp", "ssp", "model", "gcm"),
                  suffix = c("_reg", "_glob"))
      
      rho <- cor(merged_df$resids_reg, merged_df$resids_glob, use = 'complete')
      
      # Calculate heteroskedasticity model
      subdf$totalsd_scaled <- sqrt(subdf$resids^2)
      subdf$totalsd_scaled[!is.finite(subdf$totalsd_scaled)] <- NA
      mod2 <- lm(totalsd_scaled ~ 0 + delta_temp, data = subdf)
      
      # Store results
      results <- rbind(results, data.frame(
        region = reg,
        gamma = gamma_val,
        alpha = coeff[2],
        beta = coeff[3],
        sigma11 = vcv[2, 2],
        sigma12 = vcv[2, 3],
        sigma22 = vcv[3, 3],
        rho = rho,
        zeta = coef(mod2),
        eta = sd(residuals(mod2)),
        rsqr1 = summary(mod)$r.squared,
        rsqr2 = summary(mod2)$r.squared
      ))
    }
  }
  
  if (config$progress$show_spinner) {
    cat("\n")
  }
  
  # Save regional results
  write.csv(results, file.path(output_dir, "regional_polynomials.csv"), row.names = FALSE)
  
  # Create parameter distribution plots if requested
  if (config$output_files$generate_plots) {
    create_parameter_plots(results, gamma, output_dir, config, impact_var)
  }
  
  return(results)
}

#' Save scenario-specific results
#' 
#' Saves gamma statistics and global model results
#' 
#' @param gamma Gamma statistics
#' @param global_results Global analysis results
#' @param output_dir Output directory
#' @param impact_var Impact variable name
#' @param config Configuration list
save_scenario_results <- function(gamma, global_results, output_dir, impact_var, config) {
  
  # Save gamma statistics
  gamma_df <- data.frame(
    mu = gamma$mu,
    se = gamma$se,
    ci_lower = gamma$mu - 2*gamma$se,
    ci_upper = gamma$mu + 2*gamma$se
  )
  write.csv(gamma_df, file.path(output_dir, "gamma_statistics.csv"), row.names = FALSE)
  
  # Save gamma distribution values
  gamma_values_df <- data.frame(
    quantile = seq(0.05, 0.95, length.out = length(gamma$values)),
    value = gamma$values
  )
  write.csv(gamma_values_df, file.path(output_dir, "gamma_values.csv"), row.names = FALSE)
  
  # Save global analysis results
  write.csv(global_results$globaldf, file.path(output_dir, "global_analysis.csv"), row.names = FALSE)
  
  # Save global model coefficients
  global_model_coef <- data.frame(
    term = names(coef(global_results$mod_global)),
    estimate = coef(global_results$mod_global),
    std_error = summary(global_results$mod_global)$coefficients[,"Std. Error"],
    t_value = summary(global_results$mod_global)$coefficients[,"t value"],
    p_value = summary(global_results$mod_global)$coefficients[,"Pr(>|t|)"]
  )
  write.csv(global_model_coef, file.path(output_dir, "global_model_coefficients.csv"), row.names = FALSE)
  
  # Generate additional plots if requested
  if (config$output_files$generate_plots) {
    create_residuals_plots(global_results, output_dir, impact_var, config)
  }
}

#' Create parameter distribution plots
#' 
#' Creates diagnostic plots for parameter distributions
#' 
#' @param results Regional analysis results
#' @param gamma Gamma statistics
#' @param output_dir Output directory  
#' @param config Configuration
#' @param impact_var Impact variable name
create_parameter_plots <- function(results, gamma, output_dir, config, impact_var) {
  
  # Parameter distributions plot
  pdf_data <- rbind(
    data.frame(
      param = rnorm(100000, gamma$mu, gamma$se),
      name = 'gamma'
    ),
    data.frame(
      param = c(results$alpha, results$beta, results$rsqr1,
                results$rho, results$zeta, results$eta, results$rsqr2),
      name = rep(c('alpha', 'beta', 'rsqr1', 'rho', 'zeta', 'eta', 'rsqr2'), 
                 each = nrow(results))
    )
  )
  
  pdf_data$name <- factor(pdf_data$name,
                          c('gamma', 'alpha', 'beta', 'rsqr1', 'rho', 'zeta', 'eta', 'rsqr2'))
  
  p3 <- ggplot(pdf_data, aes(x = param)) +
    facet_wrap(~ name, scales = "free", ncol = 4) +
    geom_histogram(bins = 100) +
    labs(x = "Parameter value",
         y = "Region count",
         title = paste("Parameter Distributions -", impact_var)) +
    theme_bw() +
    scale_x_continuous(expand = c(0, 0)) +
    scale_y_continuous(expand = c(0, 0))
  
  ggsave(file.path(output_dir, "parameter_distributions.pdf"), p3,
         width = config$output_files$plot_width, height = config$output_files$plot_height)
}

#' Create residuals analysis plots
#' 
#' Creates diagnostic plots for residuals analysis
#' 
#' @param global_results Global analysis results
#' @param output_dir Output directory
#' @param impact_var Impact variable name  
#' @param config Configuration
create_residuals_plots <- function(global_results, output_dir, impact_var, config) {
  
  # Global impact vs temperature relationship plot
  p1 <- ggplot(global_results$globaldf, aes(x = tas_preind, y = mean_normed)) +
    geom_point(alpha = 0.5) +
    geom_smooth(method = "lm", formula = y ~ poly(x, 2), se = TRUE) +
    labs(x = "Temperature anomaly (°C)",
         y = paste("Normalized", impact_var),
         title = paste("Global", impact_var, "response to temperature")) +
    theme_minimal()
  ggsave(file.path(output_dir, paste0(impact_var, "_temp_relationship.pdf")), p1,
         width = config$output_files$plot_width, height = config$output_files$plot_height)
  
  # Residuals over time plot
  p2 <- ggplot(global_results$globaldf, aes(x = year, y = resids)) +
    geom_point(alpha = 0.5) +
    geom_smooth(method = "loess", se = TRUE) +
    labs(x = "Year",
         y = "Residuals",
         title = paste("Global model residuals over time -", impact_var)) +
    theme_minimal()
  ggsave(file.path(output_dir, "residuals_time.pdf"), p2,
         width = config$output_files$plot_width, height = config$output_files$plot_height)
}