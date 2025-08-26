# Generate F2-style Validation Tables
# Simple script to generate comparison tables using existing results

library(flexdamage)

# =============================================================================  
# CONFIGURATION
# =============================================================================

# Use the same config as mortality_country.R
config_path <- "/project/cil/home_dirs/scadavidsanchez/repos/flex-damage-dev/flex-damage/inst/configs/mortality_config.yaml"

# Load config to get paths
config <- load_config(config_path)

# Point to existing results directory (update this path to match your actual results folder)
results_dir <- "/project/cil/home_dirs/scadavidsanchez/repos/flex-damage-dev/flex-damage/examples/results/mortality_damage_analysis_adjustedmortality_all_population_20250826_004958"

# Use raw data path from config
raw_data_path <- config$data$data_path

# =============================================================================
# GENERATE TABLES
# =============================================================================

# Config already loaded above
# config <- load_config(config_path)

cat("Generating F2-style tables...\n")
cat("Results directory:", results_dir, "\n")
cat("Using scale factor:", config$output_files$scale_factor, "\n")

# Generate F2 tables (function automatically detects F2-only mode from config)
generate_comparison_tables(
  output_dir = results_dir,
  config = config,
  raw_data_path = raw_data_path
)

cat("\n=== F2 Tables Generated ===\n")
cat("Check the estimated_scenarios/ subfolder in your results directory:\n")
cat("  -", file.path(results_dir, "estimated_scenarios"), "\n")
cat("\nGenerated F2 tables:\n")
# Show F2 table settings
f2_settings <- config$output_files$f2_table_settings
if (!is.null(f2_settings$generate_f2_table) && f2_settings$generate_f2_table) {
  if (f2_settings$split_by_ssp) {
    cat("  - estimated_scenarios/ subfolder with separate SSP files (SSP2.csv, SSP3.csv, etc.)\n")
  } else {
    cat("  - estimated_scenarios/all_SSPs.csv (combined F2 projections)\n")
  }
  
  if (!is.null(f2_settings$include_ssps)) {
    cat("    - Filtered to SSPs:", paste(f2_settings$include_ssps, collapse = ", "), "\n")
  }
} else {
  cat("  - F2 table generation disabled in config\n")
}

cat("\n=== Reference Validation ===\n")
ref_scenario <- config$output_files$regional_comparisons$reference_scenario
cat("Reference scenario:", config$data$sector, "-", ref_scenario$rcp, "-", ref_scenario$ssp, "-", ref_scenario$model, "\n")
cat("Validation applied to", ref_scenario$ssp, "2095-2100 period:\n")
for (region in names(config$output_files$regional_comparisons$reference_values)) {
  ref_vals <- config$output_files$regional_comparisons$reference_values[[region]]$values
  cat("  -", region, ": Reference values [", paste(ref_vals, collapse = ", "), "]\n")
}

cat("\nDone! Check the F2 tables for damage projections with validation.\n")