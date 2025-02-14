# File: R/R/resources.R
library(parallel)

# Detect the total number of CPU cores.
detect_cores <- function() {
  total_cores <- parallel::detectCores()
  return(total_cores)
}

# Detect available RAM (in MB).
detect_ram <- function() {
  if (.Platform$OS.type == "windows") {
    ram_info <- try(system("wmic computersystem get TotalPhysicalMemory", intern = TRUE), silent = TRUE)
    if (inherits(ram_info, "try-error") || length(ram_info) < 2) {
      max_ram_mb <- 16384  # Default to 16 GB
    } else {
      ram_num <- as.numeric(gsub("[^0-9]", "", ram_info[2]))
      if (is.na(ram_num) || ram_num <= 0) {
        max_ram_mb <- 16384
      } else {
        max_ram_mb <- ram_num / (1024^2)  # Convert bytes to MB.
      }
    }
  } else if (file.exists("/proc/meminfo")) {
    meminfo <- readLines("/proc/meminfo")
    mem_total_line <- meminfo[grep("^MemTotal:", meminfo)]
    max_ram_mb <- as.numeric(gsub("[^0-9]", "", mem_total_line)) / 1024  # kB to MB.
  } else {
    max_ram_mb <- 16384  # Default if undetectable.
  }
  return(max_ram_mb)
}

# Compute a safe number of cores based on average region memory usage.
compute_safe_cores <- function(avg_region_size, max_ram_mb, baseline_cores) {
  max_ram_bytes <- max_ram_mb * 1024^2
  safe_n_cores <- floor(max_ram_bytes / avg_region_size)
  n_cores_safe <- min(baseline_cores, safe_n_cores)
  return(n_cores_safe)
}
