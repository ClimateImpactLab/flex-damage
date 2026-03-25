"""
Diagnostic plots for FlexDamage v3.

Ported from flexdamage-dev/diagnostics/visualizer.py with adaptations for:
- v3 parameter CSV format (12 columns, 19 gamma quantiles per region)
- v3 global_results.json format
- return_fig=True for Quarto/Jupyter embedding

Plots follow methodology document's "Evaluating the functions" section.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.ticker as ticker
    from matplotlib.lines import Line2D
    from matplotlib.gridspec import GridSpec
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

try:
    import seaborn as sns
    HAS_SEABORN = True
except ImportError:
    HAS_SEABORN = False

from .styles import apply_style, get_style, PARAM_LABELS, StyleConfig


def _check_deps():
    if not HAS_MATPLOTLIB:
        raise ImportError("matplotlib required: pip install matplotlib")
    if not HAS_SEABORN:
        raise ImportError("seaborn required: pip install seaborn")


def _filter_to_median_gamma(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to median gamma quantile if multiple quantiles present."""
    if "gamma" in df.columns and df["gamma"].nunique() > 1:
        median_gamma = df["gamma"].median()
        return df[abs(df["gamma"] - median_gamma) < 0.0001].copy()
    return df.copy()


# =============================================================================
# 1. Gamma Distribution (comparison to literature)
# =============================================================================


def plot_gamma_distribution(
    global_results: Dict,
    literature_values: Optional[Dict[str, float]] = None,
    style: Union[str, StyleConfig] = "scientific",
    output_dir: Optional[Union[str, Path]] = None,
    return_fig: bool = False,
):
    """
    Plot gamma point estimate with quantile distribution and literature comparison.

    Args:
        global_results: Dict with gamma, gamma_se, gamma_quantiles
        literature_values: Dict mapping labels to gamma values for comparison
        style: Style name or StyleConfig
        output_dir: Directory to save plot
        return_fig: Return figure object

    Returns:
        Figure if return_fig=True
    """
    _check_deps()
    style_cfg = get_style(style) if isinstance(style, str) else style
    apply_style(style_cfg)

    gamma = global_results.get("gamma", 0)
    gamma_se = global_results.get("gamma_se", 0)
    quantiles = global_results.get("gamma_quantiles", [])

    fig, ax = plt.subplots(figsize=(7, 4))

    # Plot density from quantiles or normal
    if quantiles and len(quantiles) > 3:
        from scipy.stats import gaussian_kde
        samples = np.array(quantiles)
        kde = gaussian_kde(samples)
        x_range = np.linspace(samples.min() - gamma_se, samples.max() + gamma_se, 200)
        ax.fill_between(x_range, kde(x_range), alpha=0.3, color=style_cfg.colors.ci_color)
        ax.plot(x_range, kde(x_range), color=style_cfg.colors.primary, linewidth=1.5)
    elif gamma_se > 0:
        from scipy.stats import norm
        x_range = np.linspace(gamma - 4*gamma_se, gamma + 4*gamma_se, 200)
        y = norm.pdf(x_range, loc=gamma, scale=gamma_se)
        ax.fill_between(x_range, y, alpha=0.3, color=style_cfg.colors.ci_color)
        ax.plot(x_range, y, color=style_cfg.colors.primary, linewidth=1.5)

    # Point estimate and CI
    ax.axvline(gamma, color=style_cfg.colors.mean_color, linewidth=2,
               label=f"gamma = {gamma:.4f}")
    if gamma_se > 0:
        ax.axvline(gamma - 1.96*gamma_se, color=style_cfg.colors.mean_color,
                   linestyle="--", alpha=0.5, label="95% CI")
        ax.axvline(gamma + 1.96*gamma_se, color=style_cfg.colors.mean_color,
                   linestyle="--", alpha=0.5)

    # Literature comparison
    if literature_values:
        colors = ["#27AE60", "#8E44AD", "#E67E22", "#16A085"]
        for i, (label, value) in enumerate(literature_values.items()):
            ax.axvline(value, color=colors[i % len(colors)], linestyle=":",
                       linewidth=1.5, label=f"{label}: {value:.3f}")

    ax.set_xlabel("Gamma (income elasticity)")
    ax.set_ylabel("Density")
    ax.set_title(f"Gamma Distribution: {gamma:.4f} (SE: {gamma_se:.2e})")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(output_dir) / "gamma_distribution.png", dpi=150, bbox_inches="tight")
        logger.info("Saved gamma_distribution.png")

    if return_fig:
        return fig
    plt.close(fig)
    return None


# =============================================================================
# 2. Parameter Distributions (8-panel: gamma, alpha, beta, rsqr1, rho, zeta, eta, rsqr2)
# =============================================================================


def plot_parameter_distributions(
    regional_results: pd.DataFrame,
    global_results: Optional[Dict] = None,
    style: Union[str, StyleConfig] = "scientific",
    output_dir: Optional[Union[str, Path]] = None,
    return_fig: bool = False,
):
    """
    Plot distributions of all 8 parameters in 2x4 grid.

    Matches R alphafit.R layout: gamma, alpha, beta, rsqr1 (row1), rho, zeta, eta, rsqr2 (row2).

    Args:
        regional_results: DataFrame with 12 parameter columns
        global_results: Dict with gamma, gamma_se for sampling
        style: Style name or StyleConfig
        output_dir: Directory to save
        return_fig: Return figure

    Returns:
        Figure if return_fig=True
    """
    _check_deps()
    style_cfg = get_style(style) if isinstance(style, str) else style
    apply_style(style_cfg)

    cols_order = ["gamma", "alpha", "beta", "rsqr1", "rho", "zeta", "eta", "rsqr2"]

    # Build data dict
    plot_data = {}

    # Gamma: sample from normal if global_results provided
    if global_results:
        gamma_mu = global_results.get("gamma", 0)
        gamma_se = global_results.get("gamma_se", 0.001)
        if gamma_se <= 0:
            gamma_se = abs(gamma_mu) * 0.1 if gamma_mu != 0 else 0.001
        plot_data["gamma"] = np.random.normal(gamma_mu, gamma_se, 10000)
    elif "gamma" in regional_results.columns:
        plot_data["gamma"] = regional_results["gamma"].dropna().values

    # Other params from regional results (use median gamma quantile)
    df = _filter_to_median_gamma(regional_results)
    for col in ["alpha", "beta", "rsqr1", "rho", "zeta", "eta", "rsqr2"]:
        if col in df.columns:
            plot_data[col] = df[col].dropna().values

    available = [c for c in cols_order if c in plot_data and len(plot_data[c]) > 0]
    if not available:
        logger.warning("No parameter columns found")
        return None

    fig, axes = plt.subplots(2, 4, figsize=(14, 6))
    axes = axes.flatten()

    for idx, col in enumerate(cols_order):
        ax = axes[idx]
        if col not in plot_data or len(plot_data[col]) == 0:
            ax.set_visible(False)
            continue

        data = plot_data[col]
        ax.hist(data, bins=40, color=style_cfg.colors.primary, alpha=0.7, edgecolor="white")

        mean_val = np.mean(data)
        median_val = np.median(data)
        ax.axvline(mean_val, color=style_cfg.colors.mean_color, linestyle="--",
                   linewidth=1.5, label=f"mean={mean_val:.3g}")
        ax.axvline(median_val, color=style_cfg.colors.median_color, linestyle=":",
                   linewidth=1.5, label=f"med={median_val:.3g}")

        ax.set_title(PARAM_LABELS.get(col, col), fontsize=11)
        ax.legend(fontsize=7, loc="best")
        ax.grid(True, alpha=0.3)

    for idx in range(len(cols_order), 8):
        axes[idx].set_visible(False)

    plt.suptitle("Regional Parameter Distributions", fontsize=13, y=1.02)
    plt.tight_layout()

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(output_dir) / "parameter_distributions.png", dpi=150, bbox_inches="tight")
        logger.info("Saved parameter_distributions.png")

    if return_fig:
        return fig
    plt.close(fig)
    return None


# =============================================================================
# 3. Polynomial Summary (mean curve with uncertainty band)
# =============================================================================


def plot_polynomial_summary(
    regional_results: pd.DataFrame,
    T_range: Tuple[float, float] = (0, 10),
    style: Union[str, StyleConfig] = "scientific",
    output_dir: Optional[Union[str, Path]] = None,
    return_fig: bool = False,
):
    """
    Plot mean damage function with percentile bands.

    Args:
        regional_results: DataFrame with alpha, beta
        T_range: Temperature range
        style: Style config
        output_dir: Save directory
        return_fig: Return figure

    Returns:
        Figure if return_fig=True
    """
    _check_deps()
    style_cfg = get_style(style) if isinstance(style, str) else style
    apply_style(style_cfg)

    df = _filter_to_median_gamma(regional_results)
    if "alpha" not in df.columns or "beta" not in df.columns:
        logger.warning("Missing alpha/beta columns")
        return None

    T = np.linspace(T_range[0], T_range[1], 100)
    alpha = df["alpha"].values[:, None]
    beta = df["beta"].values[:, None]
    Y = alpha * T[None, :] + beta * (T[None, :] ** 2)

    mean_curve = Y.mean(axis=0)
    q05, q25, q75, q95 = [np.percentile(Y, p, axis=0) for p in [5, 25, 75, 95]]

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.fill_between(T, q05, q95, alpha=0.1, color=style_cfg.colors.tertiary, label="5-95th pctl")
    ax.fill_between(T, q25, q75, alpha=0.3, color=style_cfg.colors.tertiary, label="25-75th pctl")
    ax.plot(T, mean_curve, color=style_cfg.colors.primary, linewidth=2.5, label="Mean")
    ax.axhline(0, color="black", linestyle="--", linewidth=0.8, alpha=0.5)

    ax.set_xlabel("Temperature Anomaly (C)")
    ax.set_ylabel("Regional Damage Function")
    ax.set_title(f"Mean Regional Damage Function (n={len(df)} regions)")
    ax.set_xlim(T_range)
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(output_dir) / "polynomial_summary.png", dpi=150, bbox_inches="tight")
        logger.info("Saved polynomial_summary.png")

    if return_fig:
        return fig
    plt.close(fig)
    return None


# =============================================================================
# 4. Spaghetti Curves (all regional polynomials)
# =============================================================================


def plot_spaghetti_curves(
    regional_results: pd.DataFrame,
    T_range: Tuple[float, float] = (-2, 8),
    n_regions: int = 500,
    style: Union[str, StyleConfig] = "scientific",
    output_dir: Optional[Union[str, Path]] = None,
    return_fig: bool = False,
):
    """
    Plot spaghetti curves showing all regional response functions.

    Args:
        regional_results: DataFrame with alpha, beta
        T_range: Temperature range
        n_regions: Max regions to sample
        style: Style config
        output_dir: Save directory
        return_fig: Return figure

    Returns:
        Figure if return_fig=True
    """
    _check_deps()
    style_cfg = get_style(style) if isinstance(style, str) else style
    apply_style(style_cfg)

    df = _filter_to_median_gamma(regional_results)
    if len(df) > n_regions:
        df = df.sample(n_regions, random_state=42)

    T = np.linspace(T_range[0], T_range[1], 100)
    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot each region
    for _, row in df.iterrows():
        alpha, beta = row.get("alpha", 0), row.get("beta", 0)
        y = alpha * T + beta * T**2
        ax.plot(T, y, color=style_cfg.colors.primary, alpha=0.05, linewidth=0.5)

    # Median response
    alpha_med = df["alpha"].median() if "alpha" in df.columns else 0
    beta_med = df["beta"].median() if "beta" in df.columns else 0
    y_med = alpha_med * T + beta_med * T**2
    ax.plot(T, y_med, color=style_cfg.colors.mean_color, linewidth=2.5,
            label=f"Median: alpha={alpha_med:.2f}, beta={beta_med:.4f}")

    # Percentile bands
    all_y = np.array([row.get("alpha", 0) * T + row.get("beta", 0) * T**2 for _, row in df.iterrows()])
    if len(all_y) > 0:
        y_25, y_75 = np.percentile(all_y, [25, 75], axis=0)
        ax.fill_between(T, y_25, y_75, alpha=0.15, color=style_cfg.colors.tertiary, label="25-75th pctl")

    ax.axhline(0, color="black", linestyle="-", linewidth=0.8)
    ax.axvline(0, color="black", linestyle="-", linewidth=0.5, alpha=0.5)

    ax.set_xlabel("Climatic temperature change (°C)")
    ax.set_ylabel("Regional damage function")
    ax.set_title(f"Regional Response Functions (n={len(df)} regions)")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(output_dir) / "spaghetti_curves.png", dpi=150, bbox_inches="tight")
        logger.info("Saved spaghetti_curves.png")

    if return_fig:
        return fig
    plt.close(fig)
    return None


def plot_spaghetti_curves_interactive(
    regional_results: pd.DataFrame,
    T_range: Tuple[float, float] = (0, 20),
    n_regions: int = 500,
    return_fig: bool = True,
):
    """
    Interactive spaghetti plot using Plotly.

    Shows curves from T=0 to T=20 per methodology document.
    Hover shows region, alpha, beta, R^2, zero crossing T.

    Args:
        regional_results: DataFrame with alpha, beta, rsqr1, region
        T_range: Temperature range (default 0-20 per doc)
        n_regions: Max regions to plot
        return_fig: Return figure

    Returns:
        Plotly figure if return_fig=True
    """
    try:
        import plotly.graph_objects as go
    except ImportError:
        raise ImportError("plotly required for interactive plots: pip install plotly")

    df = _filter_to_median_gamma(regional_results)
    if len(df) > n_regions:
        df = df.sample(n_regions, random_state=42)

    T = np.linspace(T_range[0], T_range[1], 100)

    fig = go.Figure()

    # Add individual curves
    for idx, row in df.iterrows():
        alpha = row.get("alpha", 0)
        beta = row.get("beta", 0)
        region = row.get("region", f"Region {idx}")
        rsqr1 = row.get("rsqr1", 0)

        y = alpha * T + beta * T**2

        # Compute zero crossing
        if abs(beta) > 1e-10:
            T_cross = -alpha / (2 * beta)
            cross_text = f"{T_cross:.1f}°C" if 0 <= T_cross <= 20 else "N/A"
        else:
            cross_text = "Linear"

        hover_text = (
            f"Region: {region}<br>"
            f"alpha: {alpha:.4f}<br>"
            f"beta: {beta:.6f}<br>"
            f"R2: {rsqr1:.3f}<br>"
            f"Zero crossing: {cross_text}"
        )

        fig.add_trace(go.Scatter(
            x=T, y=y,
            mode="lines",
            line=dict(color="steelblue", width=0.5),
            opacity=0.15,
            hovertemplate=hover_text,
            showlegend=False,
        ))

    # Add median curve
    alpha_med = df["alpha"].median()
    beta_med = df["beta"].median()
    y_med = alpha_med * T + beta_med * T**2

    fig.add_trace(go.Scatter(
        x=T, y=y_med,
        mode="lines",
        line=dict(color="darkred", width=3),
        name=f"Median (alpha={alpha_med:.3f}, beta={beta_med:.5f})",
    ))

    # Add zero line
    fig.add_hline(y=0, line_dash="dash", line_color="black")

    fig.update_layout(
        title=f"Regional Damage Functions (n={len(df)} regions)",
        xaxis_title="Climatic temperature change (°C)",
        yaxis_title="Regional damage function",
        hovermode="closest",
        template="plotly_white",
        height=500,
    )

    if return_fig:
        return fig

    fig.show()
    return None


# =============================================================================
# 5. Zero Crossings (optimal temperature distribution)
# =============================================================================


def plot_zero_crossings(
    regional_results: pd.DataFrame,
    T_range: Tuple[float, float] = (-5, 15),
    style: Union[str, StyleConfig] = "scientific",
    output_dir: Optional[Union[str, Path]] = None,
    return_fig: bool = False,
):
    """
    Plot histogram of optimal temperatures (extremum of parabola).

    T* = -alpha / (2*beta)

    Args:
        regional_results: DataFrame with alpha, beta
        T_range: Valid temperature range
        style: Style config
        output_dir: Save directory
        return_fig: Return figure

    Returns:
        Figure if return_fig=True
    """
    _check_deps()
    style_cfg = get_style(style) if isinstance(style, str) else style
    apply_style(style_cfg)

    df = _filter_to_median_gamma(regional_results)

    crossings_concave, crossings_convex = [], []
    for _, row in df.iterrows():
        alpha, beta = row.get("alpha", 0), row.get("beta", 0)
        if abs(beta) > 1e-10:
            T_opt = -alpha / (2 * beta)
            if T_range[0] <= T_opt <= T_range[1]:
                (crossings_concave if beta < 0 else crossings_convex).append(T_opt)

    if not crossings_concave and not crossings_convex:
        logger.warning("No valid zero crossings found")
        return None

    fig, ax = plt.subplots(figsize=(9, 5))

    if crossings_concave:
        ax.hist(crossings_concave, bins=40, color="#27AE60", alpha=0.6, edgecolor="white",
                label=f"Concave beta<0 (n={len(crossings_concave)})")
        ax.axvline(np.median(crossings_concave), color="#27AE60", linestyle="--", linewidth=2)

    if crossings_convex:
        ax.hist(crossings_convex, bins=40, color="#E74C3C", alpha=0.6, edgecolor="white",
                label=f"Convex beta>0 (n={len(crossings_convex)})")
        ax.axvline(np.median(crossings_convex), color="#E74C3C", linestyle="--", linewidth=2)

    ax.set_xlabel("Optimal Temperature (C)")
    ax.set_ylabel("Count")
    ax.set_title(f"Distribution of Extremum Temperatures (n={len(crossings_concave)+len(crossings_convex)})")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(output_dir) / "zero_crossings.png", dpi=150, bbox_inches="tight")
        logger.info("Saved zero_crossings.png")

    if return_fig:
        return fig
    plt.close(fig)
    return None


# =============================================================================
# 6. Slope Analysis (distribution at specific temperature)
# =============================================================================


def plot_slope_distribution(
    regional_results: pd.DataFrame,
    T_eval: float = 5.0,
    style: Union[str, StyleConfig] = "scientific",
    output_dir: Optional[Union[str, Path]] = None,
    return_fig: bool = False,
):
    """
    Plot distribution of slopes at a given temperature.

    Slope = d(response)/dT = alpha + 2*beta*T

    Args:
        regional_results: DataFrame with alpha, beta
        T_eval: Temperature at which to evaluate slope
        style: Style config
        output_dir: Save directory
        return_fig: Return figure

    Returns:
        Figure if return_fig=True
    """
    _check_deps()
    style_cfg = get_style(style) if isinstance(style, str) else style
    apply_style(style_cfg)

    df = _filter_to_median_gamma(regional_results)
    if "alpha" not in df.columns or "beta" not in df.columns:
        return None

    slopes = df["alpha"] + 2 * df["beta"] * T_eval

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(slopes, bins=50, color=style_cfg.colors.primary, alpha=0.7, edgecolor="white")

    mean_slope, median_slope = slopes.mean(), slopes.median()
    ax.axvline(mean_slope, color=style_cfg.colors.mean_color, linestyle="--", linewidth=2,
               label=f"Mean: {mean_slope:.3f}")
    ax.axvline(median_slope, color=style_cfg.colors.median_color, linestyle=":", linewidth=2,
               label=f"Median: {median_slope:.3f}")
    ax.axvline(0, color="black", linestyle="-", linewidth=1, alpha=0.5)

    n_pos, n_neg = (slopes > 0).sum(), (slopes <= 0).sum()
    ax.text(0.02, 0.98, f"Positive: {n_pos} ({100*n_pos/len(slopes):.1f}%)\nNegative: {n_neg}",
            transform=ax.transAxes, va="top", fontsize=10,
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8))

    ax.set_xlabel(f"Slope at T={T_eval}C")
    ax.set_ylabel("Count")
    ax.set_title(f"Distribution of Response Slopes at {T_eval}C")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(output_dir) / f"slope_distribution_T{T_eval:.0f}.png", dpi=150, bbox_inches="tight")

    if return_fig:
        return fig
    plt.close(fig)
    return None


def plot_max_slope_distribution(
    regional_results: pd.DataFrame,
    T_range: Tuple[float, float] = (0, 10),
    style: Union[str, StyleConfig] = "scientific",
    output_dir: Optional[Union[str, Path]] = None,
    return_fig: bool = False,
):
    """
    Plot distribution of MAXIMUM slopes between 0 and 10°C per methodology doc.

    For each region, computes slope = alpha + 2*beta*T at both endpoints
    and takes the maximum (most positive or least negative).

    Args:
        regional_results: DataFrame with alpha, beta
        T_range: Temperature range (default 0-10°C per doc)
        style: Style config
        output_dir: Save directory
        return_fig: Return figure

    Returns:
        Figure if return_fig=True
    """
    _check_deps()
    style_cfg = get_style(style) if isinstance(style, str) else style
    apply_style(style_cfg)

    df = _filter_to_median_gamma(regional_results)
    if "alpha" not in df.columns or "beta" not in df.columns:
        return None

    # Compute max slope for each region
    max_slopes = []
    for _, row in df.iterrows():
        alpha, beta = row["alpha"], row["beta"]
        slope_0 = alpha + 2 * beta * T_range[0]
        slope_10 = alpha + 2 * beta * T_range[1]
        max_slopes.append(max(slope_0, slope_10))

    max_slopes = np.array(max_slopes)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(max_slopes, bins=50, color=style_cfg.colors.primary, alpha=0.7, edgecolor="white")

    mean_slope, median_slope = np.mean(max_slopes), np.median(max_slopes)
    ax.axvline(mean_slope, color=style_cfg.colors.mean_color, linestyle="--", linewidth=2,
               label=f"Mean: {mean_slope:.4f}")
    ax.axvline(median_slope, color=style_cfg.colors.median_color, linestyle=":", linewidth=2,
               label=f"Median: {median_slope:.4f}")
    ax.axvline(0, color="black", linestyle="-", linewidth=1, alpha=0.5)

    n_pos = (max_slopes > 0).sum()
    n_neg = (max_slopes <= 0).sum()
    ax.text(0.02, 0.98, f"Positive: {n_pos} ({100*n_pos/len(max_slopes):.1f}%)\nNegative: {n_neg}",
            transform=ax.transAxes, va="top", fontsize=10,
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8))

    ax.set_xlabel(f"Maximum slope from {T_range[0]:.0f} to {T_range[1]:.0f}°C")
    ax.set_ylabel("Region count")
    ax.set_title(f"Distribution of Maximum Slopes (T ∈ [{T_range[0]:.0f}, {T_range[1]:.0f}]°C)")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(output_dir) / "max_slope_distribution.png", dpi=150, bbox_inches="tight")

    if return_fig:
        return fig
    plt.close(fig)
    return None


# =============================================================================
# 7. Convexity Summary (beta sign distribution)
# =============================================================================


def plot_convexity_summary(
    regional_results: pd.DataFrame,
    beta_tolerance: float = 1e-8,
    style: Union[str, StyleConfig] = "scientific",
    output_dir: Optional[Union[str, Path]] = None,
    return_fig: bool = False,
):
    """
    Plot summary of curve convexity (beta sign distribution).

    For agriculture, beta <= 0 constraint is typically enforced, meaning:
    - beta > 0: Convex (should be rare or ~0% with constraint)
    - beta = 0: Constrained/Linear (clipped at boundary)
    - beta < 0: Concave (expected majority)

    Args:
        regional_results: DataFrame with beta
        beta_tolerance: Threshold for considering beta as "constrained" (near zero)
        style: Style config
        output_dir: Save directory
        return_fig: Return figure

    Returns:
        Figure if return_fig=True
    """
    _check_deps()
    style_cfg = get_style(style) if isinstance(style, str) else style
    apply_style(style_cfg)

    df = _filter_to_median_gamma(regional_results)
    if "beta" not in df.columns:
        return None

    # Classify beta values into three categories
    n_convex = (df["beta"] > beta_tolerance).sum()  # Convex: beta > 0
    n_constrained = (abs(df["beta"]) <= beta_tolerance).sum()  # Constrained: beta ≈ 0
    n_concave = (df["beta"] < -beta_tolerance).sum()  # Concave: beta < 0
    n_total = len(df)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    # Pie chart with three categories
    sizes = [n_convex, n_constrained, n_concave]
    labels = [
        f"Convex (beta>0)\nn={n_convex} ({100*n_convex/n_total:.1f}%)",
        f"Constrained (beta=0)\nn={n_constrained} ({100*n_constrained/n_total:.1f}%)",
        f"Concave (beta<0)\nn={n_concave} ({100*n_concave/n_total:.1f}%)",
    ]
    colors = ["#E74C3C", "#F39C12", "#27AE60"]  # Red, Orange, Green

    # Only show categories with non-zero counts
    valid_sizes = [s for s in sizes if s > 0]
    valid_labels = [l for l, s in zip(labels, sizes) if s > 0]
    valid_colors = [c for c, s in zip(colors, sizes) if s > 0]

    if valid_sizes:
        axes[0].pie(valid_sizes, labels=valid_labels, colors=valid_colors,
                    autopct="%1.1f%%", startangle=90)
    axes[0].set_title(f"Curve Shape Distribution (n={n_total})")

    # Beta histogram - exclude exact zeros for better visualization
    beta_nonzero = df["beta"][abs(df["beta"]) > beta_tolerance]
    if len(beta_nonzero) > 0:
        axes[1].hist(beta_nonzero, bins=50, color=style_cfg.colors.primary, alpha=0.7,
                     edgecolor="white", label=f"Non-constrained (n={len(beta_nonzero)})")

    # Mark constrained regions
    if n_constrained > 0:
        axes[1].axvline(0, color="#F39C12", linestyle="-", linewidth=3,
                        label=f"Constrained at 0 (n={n_constrained})")
    else:
        axes[1].axvline(0, color="red", linestyle="--", linewidth=2, label="beta=0")

    axes[1].axvline(df["beta"].median(), color=style_cfg.colors.median_color, linestyle=":",
                    linewidth=2, label=f"Median: {df['beta'].median():.4f}")
    axes[1].set_xlabel("Beta (quadratic coefficient)")
    axes[1].set_ylabel("Count")
    axes[1].set_title("Beta Distribution")
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.3)

    # Add text summary
    summary_text = (
        f"Convex (beta>0): {n_convex} ({100*n_convex/n_total:.1f}%)\n"
        f"Constrained (beta=0): {n_constrained} ({100*n_constrained/n_total:.1f}%)\n"
        f"Concave (beta<0): {n_concave} ({100*n_concave/n_total:.1f}%)"
    )
    axes[1].text(0.98, 0.98, summary_text, transform=axes[1].transAxes,
                 va="top", ha="right", fontsize=9,
                 bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8))

    plt.suptitle("Convexity Analysis", fontsize=13, y=1.02)
    plt.tight_layout()

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(output_dir) / "convexity_summary.png", dpi=150, bbox_inches="tight")

    if return_fig:
        return fig
    plt.close(fig)
    return None


# =============================================================================
# 8. R-squared Distribution
# =============================================================================


def plot_rsquared_distribution(
    regional_results: pd.DataFrame,
    style: Union[str, StyleConfig] = "scientific",
    output_dir: Optional[Union[str, Path]] = None,
    return_fig: bool = False,
):
    """
    Plot distribution of R-squared values for regional fits.

    Args:
        regional_results: DataFrame with rsqr1
        style: Style config
        output_dir: Save directory
        return_fig: Return figure

    Returns:
        Figure if return_fig=True
    """
    _check_deps()
    style_cfg = get_style(style) if isinstance(style, str) else style
    apply_style(style_cfg)

    df = _filter_to_median_gamma(regional_results)
    if "rsqr1" not in df.columns:
        return None

    rsqr = df["rsqr1"].dropna()

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(rsqr, bins=50, color=style_cfg.colors.primary, alpha=0.7, edgecolor="white")

    ax.axvline(rsqr.mean(), color=style_cfg.colors.mean_color, linestyle="--", linewidth=2,
               label=f"Mean: {rsqr.mean():.3f}")
    ax.axvline(rsqr.median(), color=style_cfg.colors.median_color, linestyle=":", linewidth=2,
               label=f"Median: {rsqr.median():.3f}")

    n_good, n_poor = (rsqr >= 0.5).sum(), (rsqr < 0.3).sum()
    ax.text(0.02, 0.98, f"R^2 >= 0.5: {n_good} ({100*n_good/len(rsqr):.1f}%)\nR^2 < 0.3: {n_poor}",
            transform=ax.transAxes, va="top", fontsize=10,
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8))

    ax.set_xlabel("R-squared")
    ax.set_ylabel("Count")
    ax.set_title(f"Regional Fit Quality (n={len(rsqr)} regions)")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(output_dir) / "rsquared_distribution.png", dpi=150, bbox_inches="tight")

    if return_fig:
        return fig
    plt.close(fig)
    return None


# =============================================================================
# 9. Worst Offenders
# =============================================================================


def plot_worst_offenders(
    regional_results: pd.DataFrame,
    criteria: str = "eta",
    n_regions: int = 12,
    T_range: Tuple[float, float] = (-2, 8),
    style: Union[str, StyleConfig] = "scientific",
    output_dir: Optional[Union[str, Path]] = None,
    return_fig: bool = False,
):
    """
    Plot worst-performing regions by specified criteria.

    Args:
        regional_results: DataFrame with regional parameters
        criteria: 'eta' (high noise), 'rsqr1' (low R^2)
        n_regions: Number of worst regions
        T_range: Temperature range for curves
        style: Style config
        output_dir: Save directory
        return_fig: Return figure

    Returns:
        Figure if return_fig=True
    """
    _check_deps()
    style_cfg = get_style(style) if isinstance(style, str) else style
    apply_style(style_cfg)

    df = _filter_to_median_gamma(regional_results)

    if criteria == "eta" and "eta" in df.columns:
        worst = df.nlargest(n_regions, "eta")
    elif criteria == "rsqr1" and "rsqr1" in df.columns:
        worst = df.nsmallest(n_regions, "rsqr1")
    else:
        logger.warning(f"Criteria '{criteria}' not found")
        return None

    if len(worst) == 0:
        return None

    n_cols = min(4, n_regions)
    n_rows = (n_regions + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(3.5*n_cols, 3*n_rows))
    if n_regions == 1:
        axes = np.array([[axes]])
    elif n_rows == 1:
        axes = axes.reshape(1, -1)

    T = np.linspace(T_range[0], T_range[1], 100)

    for idx, (_, row) in enumerate(worst.iterrows()):
        ax = axes.flatten()[idx]
        alpha, beta = row.get("alpha", 0), row.get("beta", 0)
        region = row.get("region", f"Region {idx}")[:15]
        crit_val = row.get(criteria, 0)

        y = alpha * T + beta * T**2
        ax.plot(T, y, color=style_cfg.colors.secondary, linewidth=2)
        ax.axhline(0, color="black", linestyle="--", linewidth=0.5, alpha=0.5)
        ax.fill_between(T, 0, y, where=(y < 0), alpha=0.2, color=style_cfg.colors.tertiary)
        ax.fill_between(T, 0, y, where=(y > 0), alpha=0.2, color=style_cfg.colors.secondary)

        ax.set_title(f"{region}\n{criteria}={crit_val:.3f}", fontsize=9)
        ax.set_xlabel("T (C)", fontsize=8)
        ax.set_ylabel("Response", fontsize=8)
        ax.grid(True, alpha=0.3)

    for idx in range(len(worst), n_rows * n_cols):
        axes.flatten()[idx].set_visible(False)

    plt.suptitle(f"Worst Regions by {criteria.upper()} (n={len(worst)})", fontsize=13, y=1.02)
    plt.tight_layout()

    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(output_dir) / f"worst_offenders_{criteria}.png", dpi=150, bbox_inches="tight")

    if return_fig:
        return fig
    plt.close(fig)
    return None


# =============================================================================
# Generate All Diagnostics
# =============================================================================


def generate_all_diagnostics(
    regional_results: pd.DataFrame,
    global_results: Dict,
    output_dir: Union[str, Path],
    style: str = "scientific",
) -> List[Path]:
    """
    Generate all diagnostic plots and save to directory.

    Creates a comprehensive set of diagnostic visualizations:
    parameter distributions, spaghetti curves, convexity analysis,
    zero crossings, slope distributions, and worst offenders.

    Parameters
    ----------
    regional_results : pandas.DataFrame
        Regional parameters with 12 columns (region, gamma, alpha, beta, etc.).
    global_results : dict
        Global estimation results from estimate_gamma().
    output_dir : str or Path
        Directory to save diagnostic plots.
    style : str, optional
        Plot style name. Default is 'scientific'.

    Returns
    -------
    list of Path
        Paths to successfully generated plot files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Generating diagnostics in {output_dir}")

    generated = []

    try:
        plot_gamma_distribution(global_results, style=style, output_dir=output_dir)
        generated.append(output_dir / "gamma_distribution.png")
    except Exception as e:
        logger.warning(f"gamma_distribution failed: {e}")

    try:
        plot_parameter_distributions(regional_results, global_results, style=style, output_dir=output_dir)
        generated.append(output_dir / "parameter_distributions.png")
    except Exception as e:
        logger.warning(f"parameter_distributions failed: {e}")

    try:
        plot_polynomial_summary(regional_results, style=style, output_dir=output_dir)
        generated.append(output_dir / "polynomial_summary.png")
    except Exception as e:
        logger.warning(f"polynomial_summary failed: {e}")

    try:
        plot_spaghetti_curves(regional_results, style=style, output_dir=output_dir)
        generated.append(output_dir / "spaghetti_curves.png")
    except Exception as e:
        logger.warning(f"spaghetti_curves failed: {e}")

    try:
        plot_zero_crossings(regional_results, style=style, output_dir=output_dir)
        generated.append(output_dir / "zero_crossings.png")
    except Exception as e:
        logger.warning(f"zero_crossings failed: {e}")

    try:
        plot_slope_distribution(regional_results, T_eval=5.0, style=style, output_dir=output_dir)
        generated.append(output_dir / "slope_distribution_T5.png")
    except Exception as e:
        logger.warning(f"slope_distribution failed: {e}")

    try:
        plot_convexity_summary(regional_results, style=style, output_dir=output_dir)
        generated.append(output_dir / "convexity_summary.png")
    except Exception as e:
        logger.warning(f"convexity_summary failed: {e}")

    try:
        plot_rsquared_distribution(regional_results, style=style, output_dir=output_dir)
        generated.append(output_dir / "rsquared_distribution.png")
    except Exception as e:
        logger.warning(f"rsquared_distribution failed: {e}")

    try:
        plot_worst_offenders(regional_results, criteria="eta", style=style, output_dir=output_dir)
        generated.append(output_dir / "worst_offenders_eta.png")
    except Exception as e:
        logger.warning(f"worst_offenders_eta failed: {e}")

    if "rsqr1" in regional_results.columns:
        try:
            plot_worst_offenders(regional_results, criteria="rsqr1", style=style, output_dir=output_dir)
            generated.append(output_dir / "worst_offenders_rsqr1.png")
        except Exception as e:
            logger.warning(f"worst_offenders_rsqr1 failed: {e}")

    logger.info(f"Generated {len(generated)} diagnostic plots")
    return [p for p in generated if p.exists()]
