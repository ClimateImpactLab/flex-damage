"""
FlexDamage: Flexible Climate Damage Function Estimation.

A complete redesign with robust architecture:
- Standardized parquet with fixed columns
- No conditional SQL
- Parquet-based communication between workers
- Per-process DuckDB connections

Usage:
    from flexdamage import FlexDamagePipeline

    pipeline = FlexDamagePipeline("config.yaml")
    results = pipeline.run()

Or from command line:
    python -m flexdamage.run config.yaml
"""

__version__ = "1.0.0"

from .config import RunConfig, load_config
from .pipeline import FlexDamagePipeline, run_pipeline

__all__ = [
    "FlexDamagePipeline",
    "run_pipeline",
    "RunConfig",
    "load_config",
    "__version__",
]
