# File: R/R/results.R
library(logger)

# Save key results and summaries.
save_base_results <- function(data, main_model, base_path) {
  main_model_coef <- data.frame(
    term = names(coef(main_model)),
    estimate = coef(main_model),
    std_error = main_model$cse
  )
  write.csv(main_model_coef, file.path(base_path, "base_model", "main_model_coefficients.csv"),
            row.names = FALSE)
  
  # Save a summary of the input data.
  capture.output(summary(data),
                 file = file.path(base_path, "base_model", "data_summary.txt"))
  
  log_info("Base results saved.")
}
