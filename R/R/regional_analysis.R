# File: R/R/regional_analysis.R
library(dplyr)
library(ggplot2)
library(future.apply)
library(logger)

# Run regional analysis for each region.
# This function assumes that the data already contains a user-supplied "mean_normed" column.
# The user can specify the regression functional form via the 'regional_formula' parameter.
# Optionally, a custom regional model function (regional_model_fn) can be provided.
run_regional_analysis <- function(data, globaldf, output_dir, 
                                  collapse_data = FALSE, parallel = FALSE, ncores = 1,
                                  regional_model_fn = NULL,
                                  regional_formula = mean_normed ~ delta_temp + I(delta_temp^2)) {
  # Set default regional model function if not provided.
  if (is.null(regional_model_fn)) {
    regional_model_fn <- function(subdf, reg_formula) {
      if (!"mean_normed" %in% names(subdf)) {
        stop("The data must contain a 'mean_normed' column.")
      }
      mod <- lm(reg_formula, data = subdf)
      return(list(model = mod, coeff = coef(mod), vcv = vcov(mod)))
    }
  }
  
  regions <- unique(data$region)
  total_regions <- length(regions)
  
  # Function to process one region.
  process_region <- function(reg, idx) {
    if (reg == "") return(NULL)
    start_time <- Sys.time()
    subdf <- subset(data, region == reg)
    
    # Fit the regional model using the user-specified functional form.
    result <- regional_model_fn(subdf, regional_formula)
    if (is.null(result)) return(NULL)
    
    # Calculate residuals.
    subdf$resids <- if (!is.null(result$model$na.action)) {
      x <- rep(NA, nrow(subdf))
      x[-result$model$na.action] <- residuals(result$model)
      x
    } else {
      residuals(result$model)
    }
    
    # Merge with global data for diagnostics.
    if (collapse_data) {
      merged_df <- subdf %>%
        left_join(globaldf %>% select(year, rcp, ssp, gcm, model, resids),
                  by = c("year", "rcp", "ssp", "model", "gcm"),
                  suffix = c("_reg", "_glob"))
    } else {
      merged_df <- subdf %>%
        left_join(globaldf %>% select(batch, year, rcp, ssp, gcm, model, resids),
                  by = c("batch", "year", "rcp", "ssp", "model", "gcm"),
                  suffix = c("_reg", "_glob"))
    }
    rho <- cor(merged_df$resids_reg, merged_df$resids_glob, use = 'complete')
    
    subdf$totalsd_scaled <- sqrt(subdf$resids^2)
    subdf$totalsd_scaled[!is.finite(subdf$totalsd_scaled)] <- NA
    mod2 <- lm(totalsd_scaled ~ 0 + delta_temp, data = subdf)
    
    region_result <- data.frame(
      region = reg,
      alpha = result$coeff[2],
      beta = result$coeff[3],
      sigma11 = result$vcv[2, 2],
      sigma12 = result$vcv[2, 3],
      sigma22 = result$vcv[3, 3],
      rho = rho,
      zeta = coef(mod2),
      eta = sd(residuals(mod2)),
      rsqr1 = summary(result$model)$r.squared,
      rsqr2 = summary(mod2)$r.squared
    )
    elapsed <- as.numeric(difftime(Sys.time(), start_time, units = "secs"))
    log_info("Region {reg}: processing time = {round(elapsed,1)} sec")
    return(region_result)
  }
  
  results <- list()
  if (parallel) {
    plan(multisession, workers = ncores)
    results <- future_lapply(seq_along(regions), function(i) {
      process_region(regions[i], i)
    })
    results <- do.call(rbind, results)
    plan(sequential)
  } else {
    for (i in seq_along(regions)) {
      res <- process_region(regions[i], i)
      if (!is.null(res)) results <- rbind(results, res)
    }
  }
  
  write.csv(results, file.path(output_dir, "regional_polynomials.csv"), row.names = FALSE)
  
  # Generate an example plot (distribution of the alpha coefficient).
  p <- ggplot(results, aes(x = alpha)) +
    geom_histogram(bins = 30) +
    ggtitle("Distribution of Alpha Coefficients")
  ggsave(file.path(output_dir, "regional_alpha_distribution.pdf"), p)
  
  log_info("Regional analysis complete.")
  return(results)
}
