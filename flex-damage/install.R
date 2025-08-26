# install.R — Installer using pak

cat("=== Installing flexdamage ===\n")

# Use multiple cores if compilation is needed
options(Ncpus = max(1L, parallel::detectCores() - 1L))

# Ensure pak is available
if (!requireNamespace("pak", quietly = TRUE)) {
  install.packages("pak")
}

# Install the package from the current directory
pak::pak("local::.", dependencies = TRUE)

cat("\n=== Verifying installation ===\n")
suppressPackageStartupMessages(library(flexdamage))
cat("flexdamage loaded successfully.\n")
