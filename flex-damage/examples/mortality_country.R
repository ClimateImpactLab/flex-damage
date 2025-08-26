library(flexdamage)

# Run analysis 
config_path <- "/project/cil/home_dirs/scadavidsanchez/repos/flex-damage-dev/flex-damage/inst/configs/mortality_config.yaml"
results <- run_damage_analysis(config_path = config_path)

print("Analysis complete!")
print(paste("Results saved to:", results$output_directory))

# =============================================================================  
# METHOD 2: Custom configuration
# =============================================================================

# Create a custom configuration file
config_path <- "/project/cil/home_dirs/scadavidsanchez/repos/flex-damage-dev/flex-damage/inst/configs/mortality_config.yaml"
create_analysis_config(config_path)

cat("Custom configuration created at:", config_path)
cat("\nEdit this file to customize:")
cat("\n  - data_path: path to your data file")
cat("\n  - impact_variable: your impact column name")
cat("\n  - output_dir: where to save results") 
cat("\n  - analysis parameters")
cat("\nThen run:")
cat("\n\nresults <- run_damage_analysis(config_path = '", config_path, "')", sep = "")

# =============================================================================
# RESULTS SUMMARY
# =============================================================================

cat("\n\n=== Analysis Summary ===\n")
cat("Data processed:")
cat("\n  - Total observations:", results$data_summary$total_rows)
cat("\n  - Regions:", results$data_summary$regions)
cat("\n  - Years:", paste(results$data_summary$years, collapse = " - "))
cat("\n  - Impact variable:", results$data_summary$impact_variable)

cat("\n\nScenarios analyzed:")
for (scenario_name in names(results$results)) {
  cat("\n  -", scenario_name)
}

cat("\n\nOutput structure:")
cat("\n  - Base directory:", results$output_directory)