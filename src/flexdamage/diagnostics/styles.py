"""
Professional visualization styles for FlexDamage diagnostics.

Tufte-inspired design principles:
- Maximize data-ink ratio
- Remove chartjunk
- Use subtle, purposeful color
- Clear typography
"""

import matplotlib.pyplot as plt
import seaborn as sns
from dataclasses import dataclass, field
from typing import Dict, Literal


@dataclass
class ColorPalette:
    """Professional color palette (colorblind-friendly)."""

    primary: str = "#2C3E50"
    secondary: str = "#E74C3C"
    tertiary: str = "#3498DB"

    mean_color: str = "#C0392B"
    median_color: str = "#2980B9"
    ci_color: str = "#7F8C8D"

    grid: str = "#E8E8E8"
    background: str = "#FFFFFF"
    text: str = "#2C3E50"
    text_light: str = "#7F8C8D"

    header_bg: str = "#F5F5F5"
    header_border: str = "#CCCCCC"

    sequential: str = "YlGnBu"
    diverging: str = "RdBu_r"

    categorical: tuple = (
        "#4C72B0",  # Blue
        "#DD8452",  # Orange
        "#55A868",  # Green
        "#C44E52",  # Red
        "#8172B3",  # Purple
        "#937860",  # Brown
        "#DA8BC3",  # Pink
        "#8C8C8C",  # Gray
    )


@dataclass
class Typography:
    """Typography settings."""

    font_family: str = "sans-serif"
    title_size: float = 12
    label_size: float = 10
    tick_size: float = 9
    annotation_size: float = 8
    legend_size: float = 9
    title_weight: str = "semibold"
    label_weight: str = "medium"


@dataclass
class StyleConfig:
    """Complete style configuration."""

    name: str
    colors: ColorPalette = field(default_factory=ColorPalette)
    typography: Typography = field(default_factory=Typography)

    figure_dpi: int = 150
    save_dpi: int = 300

    grid_alpha: float = 0.5
    grid_linewidth: float = 0.5

    axes_linewidth: float = 0.8
    spine_visible: bool = True

    marker_size: float = 30
    marker_alpha: float = 0.7
    marker_edgewidth: float = 0.3

    legend_frameon: bool = False


SCIENTIFIC_STYLE = StyleConfig(
    name="scientific",
    colors=ColorPalette(
        primary="#2C3E50",
        secondary="#E74C3C",
        tertiary="#3498DB",
        mean_color="#C0392B",
        median_color="#2980B9",
        grid="#ECECEC",
        header_bg="#F7F7F7",
        header_border="#D0D0D0",
    ),
    typography=Typography(
        font_family="sans-serif",
        title_size=11,
        label_size=10,
        tick_size=9,
        annotation_size=8,
    ),
    grid_alpha=0.6,
    axes_linewidth=0.6,
    marker_alpha=0.75,
    legend_frameon=False,
)

PRESENTATION_STYLE = StyleConfig(
    name="presentation",
    colors=ColorPalette(
        primary="#1A1A2E",
        secondary="#E94560",
        tertiary="#0F3460",
        mean_color="#E94560",
        median_color="#0F3460",
        grid="#E0E0E0",
        header_bg="#F0F0F0",
        header_border="#C0C0C0",
    ),
    typography=Typography(
        font_family="sans-serif",
        title_size=13,
        label_size=11,
        tick_size=10,
        annotation_size=9,
        title_weight="bold",
    ),
    grid_alpha=0.4,
    axes_linewidth=1.0,
    marker_size=40,
    marker_alpha=0.8,
    legend_frameon=True,
)

STYLES: Dict[str, StyleConfig] = {
    "scientific": SCIENTIFIC_STYLE,
    "presentation": PRESENTATION_STYLE,
}


# Parameter labels (LaTeX-safe)
PARAM_LABELS = {
    "gamma": r"$\gamma$",
    "alpha": r"$\alpha$",
    "beta": r"$\beta$",
    "rsqr1": r"$R^2_1$",
    "rsqr2": r"$R^2_2$",
    "rho": r"$\rho$",
    "zeta": r"$\zeta$",
    "eta": r"$\eta$",
}


def get_style(name: str = "scientific") -> StyleConfig:
    """Get a style configuration by name."""
    if name not in STYLES:
        raise ValueError(f"Unknown style: {name}. Available: {list(STYLES.keys())}")
    return STYLES[name]


def apply_style(style: StyleConfig = None, name: str = "scientific"):
    """Apply a style configuration to matplotlib/seaborn."""
    if style is None:
        style = get_style(name)

    plt.rcdefaults()

    sns.set_theme(
        style="white",
        context="paper",
        font_scale=1.0,
        rc={"font.family": style.typography.font_family},
    )

    plt.rcParams.update({
        "figure.facecolor": style.colors.background,
        "figure.dpi": style.figure_dpi,
        "savefig.dpi": style.save_dpi,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.1,

        "axes.facecolor": style.colors.background,
        "axes.edgecolor": style.colors.text_light,
        "axes.linewidth": style.axes_linewidth,
        "axes.labelsize": style.typography.label_size,
        "axes.labelweight": style.typography.label_weight,
        "axes.titlesize": style.typography.title_size,
        "axes.titleweight": style.typography.title_weight,
        "axes.labelcolor": style.colors.text,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": style.spine_visible,
        "axes.spines.bottom": style.spine_visible,

        "axes.grid": True,
        "axes.grid.axis": "both",
        "grid.color": style.colors.grid,
        "grid.alpha": style.grid_alpha,
        "grid.linewidth": style.grid_linewidth,
        "grid.linestyle": "-",

        "xtick.labelsize": style.typography.tick_size,
        "ytick.labelsize": style.typography.tick_size,
        "xtick.color": style.colors.text,
        "ytick.color": style.colors.text,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.width": style.axes_linewidth,
        "ytick.major.width": style.axes_linewidth,
        "xtick.major.size": 4,
        "ytick.major.size": 4,

        "legend.fontsize": style.typography.legend_size,
        "legend.frameon": style.legend_frameon,
        "legend.edgecolor": style.colors.header_border,
        "legend.facecolor": style.colors.background,
        "legend.framealpha": 0.9,

        "text.color": style.colors.text,
        "font.size": style.typography.label_size,
    })

    return style


def get_colormap(style: StyleConfig, kind: Literal["sequential", "diverging"] = "sequential"):
    """Get colormap for the given style."""
    palette_name = style.colors.sequential if kind == "sequential" else style.colors.diverging
    return sns.color_palette(palette_name, as_cmap=True)


def get_categorical_colors(style: StyleConfig, n: int = 8) -> list:
    """Get categorical colors from style."""
    return list(style.colors.categorical[:n])
