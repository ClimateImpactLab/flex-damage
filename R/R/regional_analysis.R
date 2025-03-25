# File: R/R/regional_analysis.R
library(dplyr)
library(ggplot2)
library(future.apply)
library(logger)
library(progressr)

# Run regional analysis for each region.
# If `test = TRUE`, only a subset of 10 regions is analyzed.
run_regional_analysis <- function(data, gamma_values, gamma, globaldf, output_dir, test = FALSE, 
                                  save_regional_results = TRUE, create_regional_plots = TRUE) {
  results <- data.frame()
  all_regions <- unique(data$region)
  
  # Predefined test regions (ISO codes)
  preferred_test_regions <- c("USA", "CHN")
  
  # Select test regions
  if (test) {
    log_info("Test mode active: Only running analysis for 10 regions.")
    selected_regions <- intersect(preferred_test_regions, all_regions)
    if (length(selected_regions) < 2) {
      remaining <- setdiff(all_regions, selected_regions)
      selected_regions <- c(selected_regions, sample(remaining, min(10 - length(selected_regions), length(remaining))))
    }
  } else {
    selected_regions <- all_regions
  }
  
  total_regions <- length(selected_regions)
  
  # Spinner characters for progress display
  spinner <- c("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
  
  # Set up progress handlers
  handlers(global = TRUE)
  handlers("progress")
  
  with_progress({
    p <- progressor(steps = total_regions)
    
    for (i in seq_along(selected_regions)) {
      reg <- selected_regions[i]
      if (reg == "") next
      
      percentage <- as.character(round((i / total_regions) * 100, 1))
      spin_char <- spinner[(i %% length(spinner)) + 1]
      progress_msg <- sprintf("%s %s | Progress: %s/%s [%s%%] %s",
                              spin_char, reg, i, total_regions, percentage,
                              ifelse(i == total_regions, "✓", ""))
      p(progress_msg)
      
      # # Subset data for the current region and drop 5% lowest absolute impacts
      subdf_region <- data %>%
        filter(region == reg) %>%
        mutate(abs_impact = abs(delta_mortality)) %>%
        filter(abs_impact >= quantile(abs_impact, 0.05, na.rm = TRUE)) %>%
        select(-abs_impact)
      
      
      # Loop over each gamma value
      for (gamma_val in gamma_values) {
        # Recompute normalized mortality using the current gamma value
        subdf <- subdf_region
        subdf$mean_normed <- subdf$delta_mortality / (exp(subdf$lgdp_delta)^gamma_val)
        subdf$tas_preind2 <- subdf$delta_temp^2
        
        # Skip if insufficient non-missing data
        if (sum(!is.na(subdf$mean_normed) & !is.na(subdf$delta_temp)) < 3)
          next
        
        # Fit the regional regression
        mod <- lm(mean_normed ~ delta_temp + tas_preind2, data = subdf)
        
        # Force convexity if necessary
        if (coef(mod)[3] < 0) {
          mod <- lm(mean_normed ~ delta_temp, data = subdf)
          coeff <- c(coef(mod), 0)
          vcv <- vcov(mod)
          vcv <- cbind(rbind(vcv, c(0, 0)), c(0, 0, 0))
        } else {
          coeff <- coef(mod)
          vcv <- vcov(mod)
        }
        
        # Calculate residuals
        subdf$resids <- if (!is.null(mod$na.action)) {
          x <- rep(NA, nrow(subdf))
          x[-mod$na.action] <- residuals(mod)
          x
        } else {
          residuals(mod)
        }
        
        # Merge with global data for diagnostics
        merged_df <- subdf %>%
          left_join(globaldf %>% select(year, rcp, ssp, gcm, model, resids),
                    by = c("year", "rcp", "ssp", "model", "gcm"),
                    suffix = c("_reg", "_glob"))
        rho <- cor(merged_df$resids_reg, merged_df$resids_glob, use = 'complete')
        
        # Calculate scaled total standard deviation
        subdf$totalsd_scaled <- sqrt(subdf$resids^2)
        subdf$totalsd_scaled[!is.finite(subdf$totalsd_scaled)] <- NA
        mod2 <- lm(totalsd_scaled ~ 0 + delta_temp, data = subdf)
        
        # Store results for this region and gamma value
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
  
  # Save results and create plots only if requested
  if (save_regional_results) {
    # Determine the output filename based on test mode
    output_filename <- if (test) "regional_polynomials_test.csv" else "regional_polynomials.csv"
    
    # Save regional results
    write.csv(results, file.path(output_dir, output_filename), row.names = FALSE)
    log_info("Results saved to %s", file.path(output_dir, output_filename))
  }
  
  if (create_regional_plots) {
    # Generate an example plot (distribution of the alpha coefficient)
    p <- ggplot(results, aes(x = alpha)) +
      geom_histogram(bins = 30) +
      ggtitle("Distribution of Alpha Coefficients")
    ggsave(file.path(output_dir, "regional_alpha_distribution.pdf"), p)
    log_info("Plot saved to %s", file.path(output_dir, "regional_alpha_distribution.pdf"))
  }
  
  log_info("Regional analysis complete.")
  return(results)
}
