"""
FlexDamage v3 Configuration Schema.

Pydantic models for YAML configuration with validation.
Key changes from v2:
- scenario_columns: List[str] replaces separate rcp/ssp
- income_is_log: bool indicates if income is pre-logged
- No conditional column handling — standardize.py handles all that
"""

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# Basic Settings
# =============================================================================


class RunSettings(BaseModel):
    """Run identification."""

    name: str = Field(..., description="Unique run identifier")
    description: str = Field("", description="Human-readable description")


class SectorSettings(BaseModel):
    """Sector metadata."""

    name: str = Field(..., description="Sector name: agriculture, mortality, energy, labor")
    subsector: str = Field(..., description="Subsector: corn, heat, total, high_risk, etc.")
    units: Literal["physical", "monetary"] = Field(
        "physical", description="Output units type"
    )
    adaptation: Literal["na", "with_costs", "without_costs"] = Field(
        "na", description="Adaptation assumption"
    )


# =============================================================================
# Data Settings
# =============================================================================


class ColumnMapping(BaseModel):
    """
    Maps source column names to standard internal names.

    After standardize.py, all data has these fixed columns:
    region, year, y, T, log_income, w, sdev, scenario, y_sign
    """

    # Required columns
    y: str = Field(..., description="Outcome variable column name")
    temperature: str = Field(..., description="Temperature anomaly column name")
    income: str = Field(..., description="GDP per capita column name")
    weight: str = Field(..., description="Population weight column name")
    region: str = Field(..., description="Region identifier column name")
    year: str = Field(..., description="Year column name")

    # Optional columns
    sdev: Optional[str] = Field(
        None, description="MC standard deviation column (NULL if unavailable)"
    )

    # Scenario handling: combine multiple columns into single "scenario" string
    scenario_columns: List[str] = Field(
        default_factory=list,
        description="Columns to concatenate into scenario identifier (e.g., ['rcp', 'ssp'])",
    )


class DataSettings(BaseModel):
    """Data source configuration."""

    source: str = Field(..., description="Path to source data (zarr, parquet, csv, nc4)")
    format: Optional[str] = Field(
        None,
        description="Data format (auto-detected from extension if not specified)",
    )

    columns: ColumnMapping = Field(..., description="Column name mappings")

    # Income transformation
    income_is_log: bool = Field(
        False,
        description="Set True if income column is already log-transformed",
    )

    # Optional external socioeconomic data
    socioeconomic_source: Optional[str] = Field(
        None,
        description="Path to external GDP/pop data if needs joining",
    )


# =============================================================================
# Estimation Settings
# =============================================================================


class GammaSettings(BaseModel):
    """Gamma (income elasticity) estimation settings."""

    method: Literal["fixed_effects", "ols"] = Field(
        "fixed_effects",
        description="Estimation method: fixed_effects (R reference) or simple ols",
    )

    temperature_bins: float = Field(
        0.5,
        gt=0,
        description="Temperature bin width for FE groups (°C)",
    )

    robust_se: bool = Field(
        True,
        description="Use HC0 heteroskedasticity-robust standard errors",
    )

    cluster_se: bool = Field(
        True,
        description="Use two-way clustered SE (Cameron, Gelbach & Miller 2011)",
    )

    include_sign_in_fe: bool = Field(
        True,
        description="Include sign(y) in FE group construction (matches R reference)",
    )

    n_quantiles: int = Field(
        19,
        ge=1,
        description="Number of gamma quantiles to estimate (19 = vigintiles)",
    )

    trim_percentile: float = Field(
        0.05,
        ge=0.0,
        lt=1.0,
        description="Trim bottom X% of |y| values before estimation",
    )


class RegionalSettings(BaseModel):
    """Regional polynomial estimation settings."""

    min_observations: int = Field(
        10,
        ge=1,
        description="Minimum observations per region",
    )

    ridge_lambda: float = Field(
        1e-8,
        ge=0,
        description="Ridge regularization for numerical stability",
    )


class Constraint(BaseModel):
    """
    Parameter constraint specification.

    Examples:
    - beta <= 0 (concavity for agriculture): parameter="beta", type="max", value=0
    - beta >= 0 (convexity for mortality): parameter="beta", type="min", value=0
    """

    parameter: Literal["alpha", "beta"] = Field(..., description="Parameter to constrain")
    type: Literal["max", "min", "bounds"] = Field(..., description="Constraint type")
    value: Optional[float] = Field(
        None, description="Boundary value for max/min constraints"
    )
    min: Optional[float] = Field(None, description="Lower bound for bounds constraint")
    max: Optional[float] = Field(None, description="Upper bound for bounds constraint")

    @model_validator(mode="after")
    def validate_constraint(self) -> "Constraint":
        if self.type in ("max", "min") and self.value is None:
            raise ValueError(f"Constraint type '{self.type}' requires 'value'")
        if self.type == "bounds" and self.min is None and self.max is None:
            raise ValueError("Constraint type 'bounds' requires 'min' and/or 'max'")
        return self


class EstimationSettings(BaseModel):
    """Estimation configuration."""

    formula: str = Field(
        "alpha * T + beta * T**2",
        description="Functional form (for documentation; always quadratic)",
    )

    gamma: GammaSettings = Field(default_factory=GammaSettings)
    regional: RegionalSettings = Field(default_factory=RegionalSettings)
    constraints: List[Constraint] = Field(default_factory=list)


# =============================================================================
# Output Settings
# =============================================================================


class OutputSettings(BaseModel):
    """Output directory configuration."""

    results_dir: str = Field(..., description="Directory for results output")
    parameters_dir: str = Field(..., description="Directory for parameter CSV files")


# =============================================================================
# Execution Settings
# =============================================================================


class ExecutionSettings(BaseModel):
    """Parallelization and resource configuration."""

    workers: int = Field(
        0,
        ge=0,
        description="Number of parallel workers (0 = auto-detect based on cores/memory)",
    )

    memory_limit_gb: float = Field(
        200.0,
        gt=0,
        description="Total memory limit in GB",
    )

    memory_per_worker_gb: float = Field(
        4.0,
        gt=0,
        description="Memory allocation per worker in GB",
    )


# =============================================================================
# Master Configuration
# =============================================================================


class RunConfig(BaseModel):
    """Master configuration container."""

    run: RunSettings
    sector: SectorSettings
    data: DataSettings
    estimation: EstimationSettings = Field(default_factory=EstimationSettings)
    output: OutputSettings
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)

    @property
    def output_filename_base(self) -> str:
        """
        Generate standardized output filename prefix.

        Format: {sector}__{subsector}
        Double underscore separates levels for Zenodo flat namespace.

        Examples:
            agriculture__corn
            agriculture__wheat_spring
            mortality__heat
            energy__total
        """
        return f"{self.sector.name}__{self.sector.subsector}"


# =============================================================================
# Config Loading
# =============================================================================


def load_config(path: Union[str, Path]) -> RunConfig:
    """
    Load and validate configuration from YAML file.

    Parameters
    ----------
    path : str or Path
        Path to YAML configuration file.

    Returns
    -------
    RunConfig
        Validated configuration object.

    Raises
    ------
    FileNotFoundError
        If config file does not exist.
    pydantic.ValidationError
        If config file has invalid structure or values.

    Examples
    --------
    >>> config = load_config("configs/agriculture_corn.yaml")
    >>> print(config.sector.name)
    'agriculture'
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    return RunConfig.model_validate(raw)
