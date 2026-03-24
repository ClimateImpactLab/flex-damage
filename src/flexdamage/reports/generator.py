"""
Report generation using Quarto.
"""

import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Union

from .schema import ReportConfig

logger = logging.getLogger(__name__)


def generate_report(
    config: Union[ReportConfig, dict],
    template: Optional[Path] = None,
) -> List[Path]:
    """
    Generate report using Quarto.

    Args:
        config: ReportConfig or dict with report parameters
        template: Path to QMD template (default: built-in sector_vignette.qmd)

    Returns:
        List of generated output paths
    """
    if isinstance(config, dict):
        config = ReportConfig(**config)

    # Find template
    if template is None:
        template = Path(__file__).parent.parent.parent.parent / "reports" / "sector_vignette.qmd"

    if not template.exists():
        raise FileNotFoundError(f"Template not found: {template}")

    # Ensure output dir exists
    config.output_dir.mkdir(parents=True, exist_ok=True)

    # Assets dir defaults to results dir
    assets_dir = config.assets_dir or config.results_dir

    output_paths = []

    for fmt in config.formats:
        output_name = f"{config.sector}_{config.subsector}_report.{fmt}"
        output_path = config.output_dir / output_name

        cmd = [
            "quarto", "render", str(template),
            "--to", fmt,
            "--output-dir", str(config.output_dir),
            "--output", output_name,
            "-P", f"sector:{config.sector}",
            "-P", f"subsector:{config.subsector}",
            "-P", f"results_dir:{config.results_dir}",
            "-P", f"assets_dir:{assets_dir}",
            "-P", f"version:{config.version}",
        ]

        logger.info(f"Generating {fmt} report: {output_name}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=template.parent,
            )

            if result.returncode == 0:
                output_paths.append(output_path)
                logger.info(f"Generated: {output_path}")
            else:
                logger.error(f"Quarto failed: {result.stderr}")
                raise RuntimeError(f"Quarto rendering failed: {result.stderr}")

        except FileNotFoundError:
            raise RuntimeError("quarto not found. Install from https://quarto.org/")

    return output_paths
