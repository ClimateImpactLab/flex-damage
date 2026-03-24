"""
Diagnostics module: Visualization of estimation results.

Provides:
- Parameter distribution plots (gamma, alpha, beta, sigma, etc.)
- Spaghetti curves for damage functions (static and interactive)
- Polynomial analysis (zero crossings, convexity, slopes)
- Choropleth maps (static and interactive)
- Projection evaluation (F2-style maps)
- Gamma sensitivity and literature comparison tables
- Model diagnostics (rsqr2 quantiles, modelled variance)
- Comprehensive report generation support
"""

from .plots import (
    plot_gamma_distribution,
    plot_parameter_distributions,
    plot_polynomial_summary,
    plot_spaghetti_curves,
    plot_spaghetti_curves_interactive,
    plot_zero_crossings,
    plot_slope_distribution,
    plot_max_slope_distribution,
    plot_convexity_summary,
    plot_rsquared_distribution,
    plot_worst_offenders,
    generate_all_diagnostics,
)

from .maps import (
    generate_all_maps,
    plot_choropleth,
)

from .evaluator import (
    # Gamma analysis
    gamma_sensitivity_table,
    gamma_literature_comparison,
    LITERATURE_ELASTICITIES,
    # Zero crossings & slope analysis
    compute_zero_crossing_stats,
    compute_max_slope_stats,
    # Convexity by country
    compute_convexity_by_country,
    # rsqr2 quantiles
    compute_rsqr2_quantiles,
    # Modelled variance
    compute_modelled_variance,
    # F2-style projections
    compute_projections_at_temperatures,
    compute_projection_summary,
    plot_projection_map,
    plot_projection_curves,
    plot_projection_curves_interactive,
    plot_projection_maps_grid,
)

__all__ = [
    # Core parameter plots
    "plot_gamma_distribution",
    "plot_parameter_distributions",
    # Polynomial analysis
    "plot_polynomial_summary",
    "plot_zero_crossings",
    "plot_slope_distribution",
    "plot_max_slope_distribution",
    "plot_convexity_summary",
    # Diagnostic curves
    "plot_spaghetti_curves",
    "plot_spaghetti_curves_interactive",
    "plot_rsquared_distribution",
    "plot_worst_offenders",
    # Maps
    "generate_all_maps",
    "plot_choropleth",
    # Gamma analysis
    "gamma_sensitivity_table",
    "gamma_literature_comparison",
    "LITERATURE_ELASTICITIES",
    # Statistics
    "compute_zero_crossing_stats",
    "compute_max_slope_stats",
    "compute_convexity_by_country",
    "compute_rsqr2_quantiles",
    "compute_modelled_variance",
    # Projections (F2-style)
    "compute_projections_at_temperatures",
    "compute_projection_summary",
    "plot_projection_map",
    "plot_projection_curves",
    "plot_projection_curves_interactive",
    "plot_projection_maps_grid",
    # Batch generation
    "generate_all_diagnostics",
]
