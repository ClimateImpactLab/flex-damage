# File: R/R/regional_analysis.R
library(dplyr)
library(ggplot2)
library(future.apply)
library(logger)
library(progressr)

# Run regional analysis for each region.
# For each region it computes mean_normed using each gamma value provided.
run_regional_analysis <- function(data, gamma_values, gamma, globaldf, output_dir) {
  results <- data.frame()
  regions <- unique(data$region)
  total_regions <- length(regions)
  
  # Spinner characters for progress display.
  spinner <- c("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
  
  # Set up progress handlers.
  handlers(global = TRUE)
  handlers("progress")
  
  with_progress({
    p <- progressor(steps = total_regions)
    
    for (i in seq_along(regions)) {
      reg <- regions[i]
      if (reg == "") next
      
      percentage <- as.character(round((i / total_regions) * 100, 1))
      spin_char <- spinner[(i %% length(spinner)) + 1]
      progress_msg <- sprintf("%s %s | Progress: %s/%s [%s%%] %s",
                              spin_char, reg, i, total_regions, percentage,
                              ifelse(i == total_regions, "✓", ""))
      p(progress_msg)
      
      # Subset data for the current region.
      subdf_region <- subset(data, region == reg)
      
      # Loop over each gamma value.
      for (gamma_val in gamma_values) {
        # Recompute normalized mortality using the current gamma value.
        subdf <- subdf_region
        subdf$mean_normed <- subdf$delta_mortality / (exp(subdf$lgdp_delta)^gamma_val)
        subdf$tas_preind2 <- subdf$delta_temp^2
        
        # Skip if insufficient non-missing data.
        if (sum(!is.na(subdf$mean_normed) & !is.na(subdf$delta_temp)) < 3)
          next
        
        # Fit the regional regression.
        mod <- lm(mean_normed ~ delta_temp + tas_preind2, data = subdf)
        # Create a prediction dataframe (for diagnostics, if needed).
        preddf <- data.frame(delta_temp = seq(0, 4.5, length.out = 100))
        preddf$tas_preind2 <- preddf$delta_temp^2
        preddf$mean_normed <- predict(mod, preddf)
        
        # Force convexity if necessary.
        if (coef(mod)[3] < 0) {
          mod <- lm(mean_normed ~ delta_temp, data = subdf)
          coeff <- c(coef(mod), 0)
          vcv <- vcov(mod)
          vcv <- cbind(rbind(vcv, c(0, 0)), c(0, 0, 0))
        } else {
          coeff <- coef(mod)
          vcv <- vcov(mod)
        }
        
        # Calculate residuals.
        subdf$resids <- if (!is.null(mod$na.action)) {
          x <- rep(NA, nrow(subdf))
          x[-mod$na.action] <- residuals(mod)
          x
        } else {
          residuals(mod)
        }
        
        # Merge with global data for diagnostics.
        merged_df <- subdf %>%
          left_join(globaldf %>% select(year, rcp, ssp, gcm, model, resids),
                    by = c("year", "rcp", "ssp", "model", "gcm"),
                    suffix = c("_reg", "_glob"))
        rho <- cor(merged_df$resids_reg, merged_df$resids_glob, use = 'complete')
        
        # Calculate scaled total standard deviation.
        subdf$totalsd_scaled <- sqrt(subdf$resids^2)
        subdf$totalsd_scaled[!is.finite(subdf$totalsd_scaled)] <- NA
        mod2 <- lm(totalsd_scaled ~ 0 + delta_temp, data = subdf)
        
        # Store results for this region and gamma value.
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
      } # end loop over gamma values
    } # end loop over regions
  }) # end with_progress
  
  # Save regional results.
  write.csv(results, file.path(output_dir, "regional_polynomials.csv"), row.names = FALSE)
  
  # Generate an example plot (distribution of the alpha coefficient).
  p <- ggplot(results, aes(x = alpha)) +
    geom_histogram(bins = 30) +
    ggtitle("Distribution of Alpha Coefficients")
  ggsave(file.path(output_dir, "regional_alpha_distribution.pdf"), p)
  
  log_info("Regional analysis complete.")
  return(results)
}
