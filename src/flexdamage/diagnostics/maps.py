"""
Choropleth maps for regional parameters.

Supports both static (matplotlib) and interactive (plotly) maps.

For Impact Region (IR) level data (e.g., "USA.14.648", "ARG.1.95"):
- If IR shapefile is provided, plots at IR level
- Otherwise, aggregates to country level with clear labeling

Color scale convention for agriculture damage functions:
- NEGATIVE alpha/beta = MORE damage (yield decreases with temperature)
- RED/warm colors = more damage (more negative values)
- BLUE/cool colors = less damage or benefit (positive values)
- Diverging colorscale centered at zero
"""

import logging
from pathlib import Path
from typing import Optional, Union, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Default Impact Region shapefile paths
DEFAULT_IR_SHAPEFILE_PATHS = [
    "/project/cil/sacagawea_shares/gcp/climate/_spatial_data/world-combo-new-nytimes/new_shapefile.shp",
    "/Volumes/cil/sacagawea_shares/gcp/climate/_spatial_data/world-combo-new-nytimes/new_shapefile.shp",
]

# Optional imports
try:
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

try:
    import geopandas as gpd
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False


def _find_ir_shapefile() -> Optional[Path]:
    """Find the Impact Region shapefile."""
    for path in DEFAULT_IR_SHAPEFILE_PATHS:
        if Path(path).exists():
            return Path(path)
    return None


def _extract_country_code(region: str) -> str:
    """
    Extract ISO-3 country code from Impact Region ID.

    Impact Region IDs have format: "XXX.n.m" where XXX is ISO-3 code.
    Examples: "USA.14.648" -> "USA", "ARG.1.95" -> "ARG"
    """
    if pd.isna(region):
        return ""
    region_str = str(region)
    if "." in region_str:
        return region_str.split(".")[0][:3].upper()
    if len(region_str) == 3:
        return region_str.upper()
    return region_str[:3].upper()


def _is_impact_region_data(df: pd.DataFrame) -> bool:
    """
    Detect if DataFrame contains Impact Region level data.

    Returns True if region IDs contain dots (e.g., "USA.14.648").
    """
    if "region" not in df.columns:
        return False
    sample = df["region"].dropna().head(100)
    n_with_dots = sum(1 for r in sample if "." in str(r))
    return n_with_dots > len(sample) * 0.5


def _aggregate_to_country(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """
    Aggregate Impact Region data to country level.

    Computes mean of the specified column per country.
    """
    df = df.copy()
    df["country"] = df["region"].apply(_extract_country_code)

    # Aggregate - use mean for parameters
    agg_cols = {"country": "first"}
    for col in ["alpha", "beta", "rho", "zeta", "eta", "rsqr1", "rsqr2"]:
        if col in df.columns:
            agg_cols[col] = "mean"

    country_df = df.groupby("country").agg(agg_cols).reset_index(drop=True)
    country_df["n_regions"] = df.groupby("country").size().values
    country_df = country_df.rename(columns={"country": "region"})

    return country_df


def _get_colorscale_for_param(column: str) -> Tuple[str, bool]:
    """
    Get appropriate colorscale for a parameter.

    For damage function parameters (alpha, beta):
    - Negative values = more damage = should be RED
    - Use RdBu (not RdBu_r) so negative is red, positive is blue

    For R-squared:
    - Higher is better = sequential scale

    Returns:
        (colorscale_name, center_at_zero)
    """
    if column in ["rsqr1", "rsqr2"]:
        # Sequential: higher R^2 is better
        return "Blues", False
    elif column in ["alpha", "beta", "rho"]:
        # Diverging centered at zero
        # RdBu: red for negative (damage), blue for positive (benefit)
        return "RdBu", True
    else:
        # Default diverging
        return "RdBu", True


def _get_symmetric_limits(values: pd.Series) -> Tuple[float, float]:
    """Get symmetric color limits centered at zero."""
    vmin = values.quantile(0.02)
    vmax = values.quantile(0.98)
    # Make symmetric around zero
    abs_max = max(abs(vmin), abs(vmax))
    return -abs_max, abs_max


def plot_choropleth(
    regional_results: pd.DataFrame,
    column: str = "alpha",
    geometry: Optional[Union[str, Path]] = None,
    interactive: bool = False,
    cmap: Optional[str] = None,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    title: Optional[str] = None,
    output_path: Optional[Union[str, Path]] = None,
    return_fig: bool = False,
    use_ir_shapefile: bool = True,
):
    """
    Plot choropleth map of regional parameter values.

    Creates a geographic visualization of parameter distributions.
    Color convention: RED = more damage (negative), BLUE = less damage (positive).

    Parameters
    ----------
    regional_results : pandas.DataFrame
        Regional parameters with 'region' column and parameter columns.
    column : str, optional
        Column to visualize. Default is 'alpha'.
    geometry : str or Path, optional
        Path to shapefile or GeoJSON. Auto-detects IR shapefile if None.
    interactive : bool, optional
        If True, creates interactive Plotly map. Default is False (static).
    cmap : str, optional
        Colormap name. Auto-selected based on parameter if None.
    vmin, vmax : float, optional
        Color scale limits. Auto-centered at 0 for diverging scales.
    title : str, optional
        Plot title. Auto-generated if None.
    output_path : str or Path, optional
        Path to save figure (PNG or HTML).
    return_fig : bool, optional
        If True, returns figure object instead of displaying.
    use_ir_shapefile : bool, optional
        Try to use Impact Region shapefile for IR-level data. Default True.

    Returns
    -------
    matplotlib.figure.Figure or plotly.graph_objects.Figure or None
        Figure object if return_fig=True, else None.
    """
    if interactive:
        return _plot_choropleth_plotly(
            regional_results, column, geometry, cmap, vmin, vmax, title,
            output_path, return_fig, use_ir_shapefile
        )
    else:
        return _plot_choropleth_static(
            regional_results, column, geometry, cmap, vmin, vmax, title,
            output_path, return_fig, use_ir_shapefile
        )


def _plot_choropleth_static(
    regional_results: pd.DataFrame,
    column: str,
    geometry: Optional[Union[str, Path]],
    cmap: Optional[str],
    vmin: Optional[float],
    vmax: Optional[float],
    title: Optional[str],
    output_path: Optional[Union[str, Path]],
    return_fig: bool,
    use_ir_shapefile: bool = True,
):
    """Static choropleth using matplotlib + geopandas."""
    if not HAS_MATPLOTLIB or not HAS_GEOPANDAS:
        raise ImportError("matplotlib and geopandas required for static maps")

    # Use median gamma if multiple quantiles
    if "gamma" in regional_results.columns:
        median_gamma = regional_results["gamma"].median()
        df = regional_results[abs(regional_results["gamma"] - median_gamma) < 0.01].copy()
    else:
        df = regional_results.copy()

    # Detect data level and find appropriate geometry
    is_ir_data = _is_impact_region_data(df)
    geo_level = "ir"  # Default assumption

    if is_ir_data and use_ir_shapefile:
        # Try to find IR shapefile
        ir_shp = geometry or _find_ir_shapefile()
        if ir_shp and Path(ir_shp).exists():
            logger.info(f"Using IR shapefile: {ir_shp}")
            gdf = gpd.read_file(ir_shp)
            # Match on hierid column (standard IR shapefile column name)
            if "hierid" in gdf.columns:
                gdf = gdf.merge(df, left_on="hierid", right_on="region", how="inner")
            else:
                gdf = gdf.merge(df, on="region", how="inner")
            geo_level = "ir"
        else:
            # Fall back to country aggregation
            logger.info("IR shapefile not found, aggregating to country level")
            df = _aggregate_to_country(df, column)
            geo_level = "country"
            try:
                world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
                gdf = world.merge(df, left_on="iso_a3", right_on="region", how="inner")
            except Exception:
                logger.error("Could not load country geometries")
                return None
    else:
        # Country-level data or no IR shapefile requested
        if is_ir_data:
            df = _aggregate_to_country(df, column)
        geo_level = "country"
        try:
            world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
            gdf = world.merge(df, left_on="iso_a3", right_on="region", how="inner")
        except Exception:
            logger.error("Could not load country geometries")
            return None

    if len(gdf) == 0:
        logger.warning("No matching regions found for map")
        return None

    # Get appropriate colorscale
    auto_cmap, center_at_zero = _get_colorscale_for_param(column)
    if cmap is None:
        cmap = auto_cmap

    # Set color limits
    if vmin is None or vmax is None:
        if center_at_zero:
            vmin, vmax = _get_symmetric_limits(df[column])
        else:
            vmin = df[column].quantile(0.02) if vmin is None else vmin
            vmax = df[column].quantile(0.98) if vmax is None else vmax

    # Build title
    if title is None:
        if geo_level == "country" and is_ir_data:
            title = f"Country-level average {column}\n(aggregated from {len(regional_results)} Impact Regions)"
        elif geo_level == "ir":
            title = f"Impact Region {column} values (n={len(df)})"
        else:
            title = f"Regional {column} values"

    fig, ax = plt.subplots(figsize=(15, 10))

    gdf.plot(
        column=column,
        ax=ax,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        legend=True,
        legend_kwds={"label": column, "shrink": 0.5},
        edgecolor="black",
        linewidth=0.1 if geo_level == "ir" else 0.2,
        missing_kwds={"color": "lightgray", "edgecolor": "gray", "linewidth": 0.1},
    )

    ax.set_axis_off()
    ax.set_title(title, fontsize=14)

    # Add colorbar annotation for damage interpretation
    if column in ["alpha", "beta"]:
        ax.annotate(
            "Red = more damage\nBlue = less damage",
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


def _plot_choropleth_plotly(
    regional_results: pd.DataFrame,
    column: str,
    geometry: Optional[Union[str, Path]],
    cmap: Optional[str],
    vmin: Optional[float],
    vmax: Optional[float],
    title: Optional[str],
    output_path: Optional[Union[str, Path]],
    return_fig: bool,
    use_ir_shapefile: bool = True,
):
    """Interactive choropleth using plotly."""
    if not HAS_PLOTLY:
        raise ImportError("plotly required for interactive maps: pip install plotly")

    # Use median gamma if multiple quantiles
    if "gamma" in regional_results.columns:
        median_gamma = regional_results["gamma"].median()
        df = regional_results[abs(regional_results["gamma"] - median_gamma) < 0.01].copy()
    else:
        df = regional_results.copy()

    # Detect data level
    is_ir_data = _is_impact_region_data(df)

    # For plotly standard choropleth, we need ISO-3 codes
    # IR-level data must be aggregated (plotly doesn't support custom geometries easily)
    if is_ir_data:
        logger.info("Aggregating Impact Region data to country level for interactive map")
        n_ir_regions = len(df)
        df = _aggregate_to_country(df, column)
        geo_level = "country_from_ir"
    else:
        geo_level = "country"
        n_ir_regions = 0

    # Get appropriate colorscale
    auto_cmap, center_at_zero = _get_colorscale_for_param(column)
    if cmap is None:
        cmap = auto_cmap

    # Set color limits
    if vmin is None or vmax is None:
        if center_at_zero:
            vmin, vmax = _get_symmetric_limits(df[column])
        else:
            vmin = df[column].quantile(0.02) if vmin is None else vmin
            vmax = df[column].quantile(0.98) if vmax is None else vmax

    # Build title
    if title is None:
        if geo_level == "country_from_ir":
            title = f"Country-level average {column} (aggregated from {n_ir_regions} Impact Regions)"
        else:
            title = f"Regional {column} values"

    # Build hover data
    hover_cols = ["region"]
    if "n_regions" in df.columns:
        hover_cols.append("n_regions")
    hover_cols.extend([c for c in ["alpha", "beta", "rho", "rsqr1"] if c in df.columns])

    fig = px.choropleth(
        df,
        locations="region",
        locationmode="ISO-3",
        color=column,
        color_continuous_scale=cmap,
        range_color=[vmin, vmax],
        color_continuous_midpoint=0 if center_at_zero else None,
        title=title,
        hover_name="region",
        hover_data={col: True for col in hover_cols if col in df.columns},
    )

    fig.update_layout(
        geo=dict(
            showframe=False,
            showcoastlines=True,
            coastlinecolor="gray",
            projection_type="natural earth",
            bgcolor="rgba(240,240,240,1)",
            landcolor="lightgray",
            showland=True,
        ),
        margin={"l": 0, "r": 0, "t": 50, "b": 0},
    )

    # Add annotation for damage interpretation
    if column in ["alpha", "beta"]:
        fig.add_annotation(
            text="Red = more damage | Blue = less damage",
            xref="paper", yref="paper",
            x=0.5, y=-0.05,
            showarrow=False,
            font=dict(size=10),
        )

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.suffix == ".html":
            fig.write_html(output_path)
        else:
            fig.write_image(output_path)
        logger.info(f"Saved: {output_path}")

    if return_fig:
        return fig

    fig.show()
    return None


def generate_all_maps(
    regional_results: pd.DataFrame,
    output_dir: Union[str, Path],
    geometry: Optional[Union[str, Path]] = None,
    interactive: bool = True,
    use_ir_shapefile: bool = True,
) -> None:
    """
    Generate choropleth maps for all key parameters.

    Color convention:
    - alpha, beta: Diverging (red=damage, blue=benefit)
    - rsqr1: Sequential (darker=better fit)

    Args:
        regional_results: DataFrame with regional parameters
        output_dir: Directory to save maps
        geometry: Path to geometry file
        interactive: Generate interactive HTML maps
        use_ir_shapefile: Try to use IR shapefile for IR-level data
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    params = ["alpha", "beta", "rho", "rsqr1"]

    for param in params:
        if param not in regional_results.columns:
            continue

        ext = ".html" if interactive else ".png"
        output_path = output_dir / f"map_{param}{ext}"

        try:
            plot_choropleth(
                regional_results,
                column=param,
                geometry=geometry,
                interactive=interactive,
                output_path=output_path,
                use_ir_shapefile=use_ir_shapefile,
            )
        except Exception as e:
            logger.warning(f"Could not generate map for {param}: {e}")

    logger.info(f"Generated maps in {output_dir}")
