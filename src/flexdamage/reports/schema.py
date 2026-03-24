"""
Report configuration schema.
"""

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class ReportConfig(BaseModel):
    """Configuration for report generation."""

    sector: str = Field(..., description="Sector name")
    subsector: str = Field(..., description="Subsector name")
    results_dir: Path = Field(..., description="Directory containing results")
    assets_dir: Optional[Path] = Field(None, description="Directory with diagnostic PNGs")
    output_dir: Path = Field(Path("./reports/_output"), description="Output directory")
    formats: List[str] = Field(["html"], description="Output formats")
    version: str = Field("0.1.0", description="Version string")
