"""
Projection evaluation and model diagnostics for FlexDamage parameters.

Provides:
- F2-style projections: M(T) = alpha*T + beta*T^2 at specific temperatures
- Gamma sensitivity analysis under different specifications
- Literature comparison tables
- R-squared quantile tables
- Modelled variance statistics
- Zero crossing analysis with exact document-matching statistics
- Maximum slope analysis for 0-10°C range
- Convexity breakdown by country

These functions match the methodology document's "Evaluating the functions" section.
"""

import logging
from pathlib import Path
from typing import Optional, Union, List, Dict, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# Literature comparison values (FUND 3.6 and other sources)
# =============================================================================

LITERATURE_ELASTICITIES = {
    "Storm morbidity": {"elasticity": -0.514, "source": "FUND 3.6"},
    "Storm mortality": {"elasticity": -0.501, "source": "FUND 3.6"},
    "Diarrhoea morbidity": {"elasticity": -0.418, "source": "FUND 3.6"},
    "Diarrhoea mortality": {"elasticity": -1.579, "source": "FUND 3.6"},
    "Cardiovascular": {"elasticity": 0.0, "source": "FUND 3.6"},
    "Vector borne disease": {"elasticity": -2.65, "source": "FUND 3.6"},
}


def _filter_to_median_gamma(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to median gamma quantile if multiple quantiles present."""
    if "gamma" in df.columns and df["gamma"].nunique() > 1:
        median_gamma = df["gamma"].median()
        return df[abs(df["gamma"] - median_gamma) < 0.0001].copy()
    return df.copy()


def _extract_country_code(region: str) -> str:
    """Extract ISO-3 country code from Impact Region ID."""
    if pd.isna(region):
        return ""
    region_str = str(region)
    if "." in region_str:
        return region_str.split(".")[0][:3].upper()
    if len(region_str) == 3:
        return region_str.upper()
    return region_str[:3].upper()


# =============================================================================
# Section 2: Gamma Sensitivity Table (doc p.8)
# =============================================================================


def gamma_sensitivity_table(
    global_results: Dict,
    alternative_specs: Optional[Dict[str, Dict]] = None,
) -> pd.DataFrame:
    """
    Create gamma sensitivity table showing estimates under different specifications.

    Since we can't re-run estimations automatically, this function uses
    pre-computed results if available, or shows just the baseline if not.

    Args:
        global_results: Dict with gamma, gamma_se from baseline estimation
        alternative_specs: Optional dict mapping spec names to their gamma results

    Returns:
        DataFrame with columns: Specification, Gamma, SE, 95% CI
    """
    rows = []

    # Baseline estimate
    gamma = global_results.get("gamma", 0)
    gamma_se = global_results.get("gamma_se", 0)
    ci_low = gamma - 1.96 * gamma_se
    ci_high = gamma + 1.96 * gamma_se

    rows.append({
        "Specification": "Baseline (year FE, pop weight, clustered SE)",
        "Gamma": f"{gamma:.4f}",
        "SE": f"{gamma_se:.2e}",
        "95% CI": f"[{ci_low:.4f}, {ci_high:.4f}]",
    })

    # Alternative specifications if provided
    if alternative_specs:
        for spec_name, spec_results in alternative_specs.items():
            g = spec_results.get("gamma", 0)
            se = spec_results.get("gamma_se", 0)
            rows.append({
                "Specification": spec_name,
                "Gamma": f"{g:.4f}",
                "SE": f"{se:.2e}" if se > 0 else "—",
                "95% CI": f"[{g - 1.96*se:.4f}, {g + 1.96*se:.4f}]" if se > 0 else "—",
            })

    return pd.DataFrame(rows)


# =============================================================================
# Section 3: Literature Comparison Table (doc p.8)
# =============================================================================


def gamma_literature_comparison(
    estimated_gamma: float,
    sector_name: str = "This study",
) -> pd.DataFrame:
    """
    Create table comparing estimated gamma to literature values.

    Args:
        estimated_gamma: Our estimated gamma value
        sector_name: Name for our estimate row

    Returns:
        DataFrame with columns: Sector, Elasticity, Reference
    """
    rows = [{"Sector": sector_name, "Elasticity": f"{estimated_gamma:.4f}", "Reference": "This study"}]

    for sector, data in LITERATURE_ELASTICITIES.items():
        rows.append({
            "Sector": sector,
            "Elasticity": f"{data['elasticity']:.3f}",
            "Reference": data["source"],
        })

    return pd.DataFrame(rows)


# =============================================================================
# Section 5: Zero Crossings Statistics (doc p.9)
# =============================================================================


def compute_zero_crossing_stats(
    params_df: pd.DataFrame,
    T_max: float = 20.0,
) -> Dict:
    """
    Compute zero crossing statistics matching methodology document.

    Reports:
    - beta = 0 (no crossing): X%
    - T > 20 (beyond graph): X%
    - T < 0 (never crossing in positive T): X%
    - Histogram data for crossing temperatures

    The zero crossing is T* = -alpha / (2*beta) for a parabola.
    For concave curves (beta < 0), this is the maximum.
    For convex curves (beta > 0), this is the minimum.

    Args:
        params_df: DataFrame with alpha, beta
        T_max: Maximum temperature to consider (default 20°C per doc)

    Returns:
        Dict with statistics and crossing temperatures
    """
    df = _filter_to_median_gamma(params_df)
    n_total = len(df)

    # Categories
    n_beta_zero = (abs(df["beta"]) < 1e-10).sum()

    crossings = []
    n_beyond_max = 0
    n_negative = 0

    for _, row in df.iterrows():
        alpha, beta = row.get("alpha", 0), row.get("beta", 0)

        if abs(beta) < 1e-10:
            continue  # No crossing (linear)

        T_cross = -alpha / (2 * beta)

        if T_cross > T_max:
            n_beyond_max += 1
        elif T_cross < 0:
            n_negative += 1
        else:
            crossings.append(T_cross)

    return {
        "n_total": n_total,
        "n_beta_zero": n_beta_zero,
        "pct_beta_zero": 100 * n_beta_zero / n_total if n_total > 0 else 0,
        "n_beyond_max": n_beyond_max,
        "pct_beyond_max": 100 * n_beyond_max / n_total if n_total > 0 else 0,
        "n_negative": n_negative,
        "pct_negative": 100 * n_negative / n_total if n_total > 0 else 0,
        "n_valid_crossings": len(crossings),
        "pct_valid_crossings": 100 * len(crossings) / n_total if n_total > 0 else 0,
        "crossing_temps": crossings,
        "T_max": T_max,
    }


# =============================================================================
# Section 6: Maximum Slope Analysis (doc p.10)
# =============================================================================


def compute_max_slope_stats(
    params_df: pd.DataFrame,
    T_range: Tuple[float, float] = (0, 10),
) -> Dict:
    """
    Compute maximum slope between 0 and 10°C.

    Slope = d(M)/dT = alpha + 2*beta*T

    For concave curves (beta < 0), max slope is at T=0 (slope = alpha)
    For convex curves (beta > 0), max slope is at T=10

    Args:
        params_df: DataFrame with alpha, beta
        T_range: Range to evaluate (default 0-10°C per doc)

    Returns:
        Dict with slope statistics and distribution
    """
    df = _filter_to_median_gamma(params_df)

    max_slopes = []
    for _, row in df.iterrows():
        alpha, beta = row.get("alpha", 0), row.get("beta", 0)

        # Evaluate slope at both endpoints
        slope_0 = alpha + 2 * beta * T_range[0]
        slope_10 = alpha + 2 * beta * T_range[1]

        # Maximum (most positive or least negative)
        max_slope = max(slope_0, slope_10)
        max_slopes.append(max_slope)

    max_slopes = np.array(max_slopes)

    return {
        "slopes": max_slopes,
        "mean": float(np.mean(max_slopes)),
        "median": float(np.median(max_slopes)),
        "std": float(np.std(max_slopes)),
        "min": float(np.min(max_slopes)),
        "max": float(np.max(max_slopes)),
        "n_positive": int((max_slopes > 0).sum()),
        "pct_positive": 100 * (max_slopes > 0).sum() / len(max_slopes),
        "n_negative": int((max_slopes <= 0).sum()),
        "pct_negative": 100 * (max_slopes <= 0).sum() / len(max_slopes),
        "T_range": T_range,
    }


# =============================================================================
# Section 7: Convexity by Country (doc p.10)
# =============================================================================


def compute_convexity_by_country(
    params_df: pd.DataFrame,
    beta_tolerance: float = 1e-8,
) -> pd.DataFrame:
    """
    Compute fraction of convex (beta > 0) regions per country.

    Args:
        params_df: DataFrame with region, beta
        beta_tolerance: Threshold for considering beta as zero

    Returns:
        DataFrame with country, n_regions, n_convex, frac_convex
    """
    df = _filter_to_median_gamma(params_df)
    df = df.copy()
    df["country"] = df["region"].apply(_extract_country_code)
    df["is_convex"] = df["beta"] > beta_tolerance

    country_stats = df.groupby("country").agg({
        "region": "count",
        "is_convex": "sum",
    }).reset_index()

    country_stats.columns = ["country", "n_regions", "n_convex"]
    country_stats["frac_convex"] = country_stats["n_convex"] / country_stats["n_regions"]

    # Sort by fraction convex descending
    country_stats = country_stats.sort_values("frac_convex", ascending=False)

    return country_stats


# =============================================================================
# Section 9: rsqr2 Quantiles Table (doc p.13)
# =============================================================================


def compute_rsqr2_quantiles(
    params_df: pd.DataFrame,
    quantiles: List[float] = [0.0, 0.25, 0.5, 0.75, 1.0],
) -> pd.DataFrame:
    """
    Compute quantiles of rsqr2 (error model R-squared).

    Args:
        params_df: DataFrame with rsqr2
        quantiles: Quantile values to compute

    Returns:
        DataFrame with one row showing quantile values
    """
    df = _filter_to_median_gamma(params_df)

    if "rsqr2" not in df.columns:
        logger.warning("rsqr2 column not found")
        return pd.DataFrame()

    rsqr2 = df["rsqr2"].dropna()

    result = {}
    for q in quantiles:
        pct_label = f"{int(q*100)}%"
        result[pct_label] = rsqr2.quantile(q)

    return pd.DataFrame([result])


# =============================================================================
# Section 11: Modelled Variance (doc p.14)
# =============================================================================


def compute_modelled_variance(
    params_df: pd.DataFrame,
) -> Dict:
    """
    Compute modelled variance statistic.

    Modelled variance = 1 - sum(eta_i^2) / sum(M_i^2)

    where eta is residual SD and M is the damage value.
    Since we don't have M directly, we approximate using the parameters.

    For a proper calculation, we'd need the fitted values.
    As a proxy, we compute: 1 - mean(eta^2) / var(predictions at T=3°C)

    Args:
        params_df: DataFrame with alpha, beta, eta

    Returns:
        Dict with modelled variance and component stats
    """
    df = _filter_to_median_gamma(params_df)

    if "eta" not in df.columns:
        logger.warning("eta column not found")
        return {"modelled_variance": None, "note": "eta column not found"}

    # Compute M at representative temperature (T=3°C)
    T_ref = 3.0
    df["M_ref"] = df["alpha"] * T_ref + df["beta"] * (T_ref ** 2)

    eta_squared_sum = (df["eta"] ** 2).sum()
    M_squared_sum = (df["M_ref"] ** 2).sum()

    if M_squared_sum < 1e-10:
        return {"modelled_variance": None, "note": "M values too small"}

    modelled_var = 1 - eta_squared_sum / M_squared_sum

    return {
        "modelled_variance": modelled_var,
        "eta_squared_sum": eta_squared_sum,
        "M_squared_sum": M_squared_sum,
        "T_reference": T_ref,
        "n_regions": len(df),
    }


# =============================================================================
# F2-style Projections (doc Sec. 12)
# =============================================================================


def compute_projections_at_temperatures(
    params_df: pd.DataFrame,
    temperatures: List[float] = [1.0, 2.0, 3.0, 4.0],
) -> pd.DataFrame:
    """
    Compute M(T) = alpha*T + beta*T^2 for each region at given temperatures.

    This is the core damage function evaluation WITHOUT income scaling.
    For full flexible damage: M_scaled = M(T) * Y^gamma

    Args:
        params_df: DataFrame with columns: region, alpha, beta (and optionally gamma)
        temperatures: List of temperature anomalies to evaluate

    Returns:
        DataFrame with columns: region, M_1C, M_2C, M_3C, M_4C (or whatever temps)
    """
    df = _filter_to_median_gamma(params_df)

    if "alpha" not in df.columns or "beta" not in df.columns:
        raise ValueError("DataFrame must have 'alpha' and 'beta' columns")

    result = df[["region"]].copy()

    for T in temperatures:
        col_name = f"M_{T:.0f}C" if T == int(T) else f"M_{T:.1f}C"
        result[col_name] = df["alpha"] * T + df["beta"] * (T ** 2)

    return result


def compute_projection_summary(
    params_df: pd.DataFrame,
    temperatures: List[float] = [1.0, 2.0, 3.0, 4.0],
) -> pd.DataFrame:
    """
    Compute summary statistics of M(T) across all regions.

    Args:
        params_df: DataFrame with alpha, beta columns
        temperatures: Temperature anomalies to evaluate

    Returns:
        DataFrame with rows for each temperature and columns for statistics
    """
    projections = compute_projections_at_temperatures(params_df, temperatures)

    summary_rows = []
    for T in temperatures:
        col_name = f"M_{T:.0f}C" if T == int(T) else f"M_{T:.1f}C"
        values = projections[col_name]

        summary_rows.append({
            "Temperature": f"{T}°C",
            "Mean": values.mean(),
            "Median": values.median(),
            "Std": values.std(),
            "Min": values.min(),
            "Max": values.max(),
            "Pct_Negative": 100 * (values < 0).sum() / len(values),
            "N": len(values),
        })

    return pd.DataFrame(summary_rows)


def plot_projection_map(
    params_df: pd.DataFrame,
    T_value: float = 3.0,
    shapefile_path: Optional[Union[str, Path]] = None,
    cmap: str = "RdBu",
    title: Optional[str] = None,
    output_path: Optional[Union[str, Path]] = None,
    return_fig: bool = False,
):
    """
    Map of M(T) for all regions at a given temperature.

    This is the F2-style projection map showing spatial pattern of damage.

    Args:
        params_df: DataFrame with region, alpha, beta
        T_value: Temperature anomaly to evaluate
        shapefile_path: Path to IR shapefile (auto-detected if None)
        cmap: Colormap (default RdBu: red=damage, blue=benefit)
        title: Plot title
        output_path: Path to save figure
        return_fig: Return figure object

    Returns:
        Figure if return_fig=True
    """
    try:
        import matplotlib.pyplot as plt
        import geopandas as gpd
    except ImportError:
        raise ImportError("matplotlib and geopandas required for projection maps")

    from .maps import _find_ir_shapefile, _is_impact_region_data, _aggregate_to_country

    # Compute projections
    df = _filter_to_median_gamma(params_df)
    col_name = f"M_{T_value:.0f}C" if T_value == int(T_value) else f"M_{T_value:.1f}C"
    df = df.copy()
    df[col_name] = df["alpha"] * T_value + df["beta"] * (T_value ** 2)

    # Find shapefile
    is_ir_data = _is_impact_region_data(df)
    ir_shp = shapefile_path or _find_ir_shapefile()

    if is_ir_data and ir_shp and Path(ir_shp).exists():
        logger.info(f"Using IR shapefile for projection map: {ir_shp}")
        gdf = gpd.read_file(ir_shp)
        if "hierid" in gdf.columns:
            gdf = gdf.merge(df, left_on="hierid", right_on="region", how="inner")
        else:
            gdf = gdf.merge(df, on="region", how="inner")
        geo_level = "ir"
    else:
        # Fall back to country
        if is_ir_data:
            df = _aggregate_to_country(df, col_name)
        geo_level = "country"
        try:
            world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
            gdf = world.merge(df, left_on="iso_a3", right_on="region", how="inner")
        except Exception:
            logger.error("Could not load geometries")
            return None

    if len(gdf) == 0:
        logger.warning("No matching regions found")
        return None

    # Symmetric color limits centered at zero
    vmin = gdf[col_name].quantile(0.02)
    vmax = gdf[col_name].quantile(0.98)
    abs_max = max(abs(vmin), abs(vmax))
    vmin, vmax = -abs_max, abs_max

    # Build title
    if title is None:
        if geo_level == "ir":
            title = f"Projected Damage at T = {T_value}°C\n(n={len(gdf)} Impact Regions)"
        else:
            title = f"Projected Damage at T = {T_value}°C\n(Country-level average)"

    fig, ax = plt.subplots(figsize=(15, 10))

    gdf.plot(
        column=col_name,
        ax=ax,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        legend=True,
        legend_kwds={"label": f"M(T={T_value}°C)", "shrink": 0.5},
        edgecolor="black",
        linewidth=0.1 if geo_level == "ir" else 0.2,
        missing_kwds={"color": "lightgray", "edgecolor": "gray", "linewidth": 0.1},
    )

    ax.set_axis_off()
    ax.set_title(title, fontsize=14)

    # Add interpretation annotation
    ax.annotate(
        "Red = yield loss (damage)\nBlue = yield gain (benefit)",
        xy=(0.02, 0.02), xycoords="axes fraction",
        fontsize=9, ha="left", va="bottom",
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8)
    )

    plt.tight_layout()

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Saved: {output_path}")

    if return_fig:
        return fig

    plt.show()
    plt.close(fig)
    return None


def plot_projection_curves(
    params_df: pd.DataFrame,
    T_range: tuple = (-2, 6),
    n_samples: int = 500,
    highlight_temps: List[float] = [2.0, 3.0, 4.0],
    title: Optional[str] = None,
    output_path: Optional[Union[str, Path]] = None,
    return_fig: bool = False,
):
    """
    Plot M(T) curves for all regions with highlighted temperature points.

    Args:
        params_df: DataFrame with alpha, beta
        T_range: Temperature range
        n_samples: Max regions to plot
        highlight_temps: Temperatures to highlight with vertical lines
        title: Plot title
        output_path: Save path
        return_fig: Return figure

    Returns:
        Figure if return_fig=True
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        raise ImportError("matplotlib required")

    df = _filter_to_median_gamma(params_df)
    if len(df) > n_samples:
        df = df.sample(n_samples, random_state=42)

    T = np.linspace(T_range[0], T_range[1], 100)

    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot individual curves
    for _, row in df.iterrows():
        y = row["alpha"] * T + row["beta"] * T**2
        ax.plot(T, y, color="steelblue", alpha=0.03, linewidth=0.5)

    # Median curve
    alpha_med = df["alpha"].median()
    beta_med = df["beta"].median()
    y_med = alpha_med * T + beta_med * T**2
    ax.plot(T, y_med, color="darkred", linewidth=2.5, label="Median response")

    # Percentile bands
    all_y = np.array([row["alpha"] * T + row["beta"] * T**2 for _, row in df.iterrows()])
    y_25, y_75 = np.percentile(all_y, [25, 75], axis=0)
    ax.fill_between(T, y_25, y_75, alpha=0.2, color="steelblue", label="25-75th percentile")

    # Reference lines
    ax.axhline(0, color="black", linestyle="-", linewidth=1)
    ax.axvline(0, color="black", linestyle="-", linewidth=0.5, alpha=0.5)

    # Highlight specific temperatures
    for T_hl in highlight_temps:
        ax.axvline(T_hl, color="gray", linestyle="--", linewidth=1, alpha=0.7)
        # Compute mean M at this temperature
        M_mean = (df["alpha"] * T_hl + df["beta"] * T_hl**2).mean()
        ax.text(T_hl, ax.get_ylim()[1] * 0.95, f"{T_hl}°C\nM={M_mean:.3f}",
                ha="center", va="top", fontsize=8,
                bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

    ax.set_xlabel("Temperature Anomaly (°C)")
    ax.set_ylabel("M(T) = αT + βT²")
    ax.set_title(title or f"Projected Damage Curves (n={len(df)} regions)")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Saved: {output_path}")

    if return_fig:
        return fig

    plt.show()
    plt.close(fig)
    return None


def plot_projection_curves_interactive(
    params_df: pd.DataFrame,
    T_range: tuple = (0, 20),
    n_samples: int = 500,
    title: Optional[str] = None,
    return_fig: bool = True,
):
    """
    Interactive spaghetti plot using Plotly.

    Shows curves from T=0 to T=20 per methodology document.
    Hover shows region, alpha, beta, R^2, zero crossing T.

    Args:
        params_df: DataFrame with alpha, beta, rsqr1, region
        T_range: Temperature range (default 0-20 per doc)
        n_samples: Max regions to plot
        title: Plot title
        return_fig: Return figure

    Returns:
        Plotly figure if return_fig=True
    """
    try:
        import plotly.graph_objects as go
    except ImportError:
        raise ImportError("plotly required for interactive plots")

    df = _filter_to_median_gamma(params_df)
    if len(df) > n_samples:
        df = df.sample(n_samples, random_state=42)

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
            f"α: {alpha:.4f}<br>"
            f"β: {beta:.6f}<br>"
            f"R²: {rsqr1:.3f}<br>"
            f"Zero crossing: {cross_text}"
        )

        fig.add_trace(go.Scatter(
            x=T, y=y,
            mode="lines",
            line=dict(color="steelblue", width=0.5),
            opacity=0.1,
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
        name=f"Median (α={alpha_med:.3f}, β={beta_med:.5f})",
    ))

    # Add zero line
    fig.add_hline(y=0, line_dash="dash", line_color="black")

    fig.update_layout(
        title=title or f"Regional Damage Functions (n={len(df)} regions)",
        xaxis_title="Climatic temperature change (°C)",
        yaxis_title="Regional damage function",
        hovermode="closest",
        template="plotly_white",
    )

    if return_fig:
        return fig

    fig.show()
    return None


# =============================================================================
# Multi-temperature projection maps (4 panels)
# =============================================================================


def plot_projection_maps_grid(
    params_df: pd.DataFrame,
    temperatures: List[float] = [1.0, 2.0, 3.0, 4.0],
    shapefile_path: Optional[Union[str, Path]] = None,
    output_path: Optional[Union[str, Path]] = None,
    return_fig: bool = False,
):
    """
    Generate 2x2 grid of projection maps at different temperatures.

    Args:
        params_df: DataFrame with region, alpha, beta
        temperatures: List of 4 temperature values
        shapefile_path: Path to IR shapefile
        output_path: Path to save figure
        return_fig: Return figure object

    Returns:
        Figure if return_fig=True
    """
    try:
        import matplotlib.pyplot as plt
        import geopandas as gpd
    except ImportError:
        raise ImportError("matplotlib and geopandas required")

    from .maps import _find_ir_shapefile, _is_impact_region_data, _aggregate_to_country

    df = _filter_to_median_gamma(params_df)

    # Compute projections for all temperatures
    for T in temperatures:
        col_name = f"M_{T:.0f}C"
        df[col_name] = df["alpha"] * T + df["beta"] * (T ** 2)

    # Find shapefile
    is_ir_data = _is_impact_region_data(df)
    ir_shp = shapefile_path or _find_ir_shapefile()

    if is_ir_data and ir_shp and Path(ir_shp).exists():
        gdf = gpd.read_file(ir_shp)
        if "hierid" in gdf.columns:
            gdf = gdf.merge(df, left_on="hierid", right_on="region", how="inner")
        else:
            gdf = gdf.merge(df, on="region", how="inner")
        geo_level = "ir"
    else:
        if is_ir_data:
            df = _aggregate_to_country(df, f"M_{temperatures[0]:.0f}C")
        geo_level = "country"
        try:
            world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
            gdf = world.merge(df, left_on="iso_a3", right_on="region", how="inner")
        except Exception:
            logger.error("Could not load geometries")
            return None

    if len(gdf) == 0:
        return None

    # Get global symmetric limits across all temps
    all_values = []
    for T in temperatures:
        col_name = f"M_{T:.0f}C"
        if col_name in gdf.columns:
            all_values.extend(gdf[col_name].dropna().tolist())

    if not all_values:
        return None

    abs_max = max(abs(np.percentile(all_values, 2)), abs(np.percentile(all_values, 98)))
    vmin, vmax = -abs_max, abs_max

    # Create 2x2 grid
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    axes = axes.flatten()

    for i, (ax, T) in enumerate(zip(axes, temperatures)):
        col_name = f"M_{T:.0f}C"

        gdf.plot(
            column=col_name,
            ax=ax,
            cmap="RdBu",
            vmin=vmin,
            vmax=vmax,
            legend=i == 1,  # Only one colorbar
            legend_kwds={"label": "M(T)", "shrink": 0.6} if i == 1 else {},
            edgecolor="black",
            linewidth=0.05,
            missing_kwds={"color": "lightgray"},
        )
        ax.set_axis_off()
        ax.set_title(f"T = {T:.0f}°C", fontsize=12)

    plt.suptitle(
        f"Projected Damage at Different Temperature Anomalies\n"
        f"(n={len(gdf)} {'Impact Regions' if geo_level == 'ir' else 'countries'})",
        fontsize=14
    )
    plt.tight_layout()

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Saved: {output_path}")

    if return_fig:
        return fig

    plt.show()
    plt.close(fig)
    return None
