#!/usr/bin/env python3
"""
Generate FlexDamage parameter reports using Quarto.

Usage:
    # Generate HTML report for corn
    python scripts/generate_report.py --sector agriculture --subsector corn

    # Generate PDF report
    python scripts/generate_report.py --sector agriculture --subsector corn --format pdf

    # Generate all formats
    python scripts/generate_report.py --sector agriculture --subsector corn --format all

    # Custom results directory
    python scripts/generate_report.py --sector agriculture --subsector corn \
        --results-dir /project/cil/gcp/flex_damage_funcs/parameters

    # Generate diagnostics only (no Quarto)
    python scripts/generate_report.py --sector agriculture --subsector corn --diagnostics-only

    # Generate all agriculture reports
    python scripts/generate_report.py --all-agriculture

    # Deploy to docs/ for GitHub Pages
    python scripts/generate_report.py --sector agriculture --subsector corn --deploy
"""

import argparse
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Agriculture subsectors
AGRICULTURE_SUBSECTORS = [
    "corn", "wheat", "rice", "soy", "cotton",
    "maize", "sorghum", "millet", "barley", "groundnut"
]


def find_quarto():
    """Find quarto executable."""
    quarto = shutil.which("quarto")
    if quarto:
        return quarto

    # Common locations
    for path in [
        "/usr/local/bin/quarto",
        "/opt/homebrew/bin/quarto",
        Path.home() / ".local/bin/quarto",
        Path.home() / "quarto/bin/quarto",
    ]:
        if Path(path).exists():
            return str(path)

    return None


def generate_diagnostics(
    sector: str,
    subsector: str,
    results_dir: Path,
    output_dir: Path,
):
    """Generate diagnostic plots using flexdamage.diagnostics."""
    import pandas as pd

    from flexdamage.diagnostics.plots import generate_all_diagnostics
    from flexdamage.diagnostics.maps import generate_all_maps

    base_name = f"{sector}__{subsector}"
    csv_path = results_dir / f"{base_name}__regional_parameters.csv"
    global_json_path = results_dir / f"{base_name}__global_results.json"

    if not csv_path.exists():
        logger.error(f"Regional parameters not found: {csv_path}")
        return False

    regional_df = pd.read_csv(csv_path)

    global_results = {}
    if global_json_path.exists():
        with open(global_json_path) as f:
            global_results = json.load(f)

    logger.info(f"Generating diagnostics for {sector}/{subsector}")
    logger.info(f"  Regions: {regional_df['region'].nunique()}")
    logger.info(f"  Gamma quantiles: {regional_df['gamma'].nunique() if 'gamma' in regional_df.columns else 1}")

    # Generate plots
    diag_dir = output_dir / "diagnostics"
    generate_all_diagnostics(regional_df, global_results, diag_dir)

    # Generate maps (interactive HTML)
    maps_dir = output_dir / "maps"
    try:
        generate_all_maps(regional_df, maps_dir, interactive=True)
    except Exception as e:
        logger.warning(f"Could not generate maps: {e}")

    return True


def render_quarto(
    template: Path,
    output_dir: Path,
    output_name: str,
    format: str,
    params: dict,
):
    """Render Quarto template."""
    quarto = find_quarto()
    if not quarto:
        logger.error("quarto not found. Install from https://quarto.org/")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        quarto, "render", str(template),
        "--to", format,
        "--output-dir", str(output_dir),
        "--output", output_name,
    ]

    # Add parameters
    for key, value in params.items():
        cmd.extend(["-P", f"{key}:{value}"])

    logger.info(f"Running: {' '.join(cmd[:6])}...")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=template.parent,
    )

    if result.returncode != 0:
        logger.error(f"Quarto failed: {result.stderr}")
        return None

    output_path = output_dir / output_name
    if output_path.exists():
        logger.info(f"Generated: {output_path}")
        return output_path

    # Check for alternate extensions
    for ext in [".html", ".pdf", ".typ"]:
        alt_path = output_dir / f"{output_name.rsplit('.', 1)[0]}{ext}"
        if alt_path.exists():
            logger.info(f"Generated: {alt_path}")
            return alt_path

    return None


def deploy_to_docs(
    output_dir: Path,
    docs_dir: Path,
    sector: str,
    subsector: str,
):
    """
    Deploy generated reports to docs/ for GitHub Pages hosting.

    Copies HTML reports and updates index.html.
    """
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Find HTML report
    html_name = f"{sector}_{subsector}_report.html"
    html_path = output_dir / html_name

    if not html_path.exists():
        logger.warning(f"HTML report not found: {html_path}")
        return False

    # Copy to docs/
    dest_path = docs_dir / html_name
    shutil.copy2(html_path, dest_path)
    logger.info(f"Deployed: {dest_path}")

    # Update index.html
    update_docs_index(docs_dir)

    return True


def update_docs_index(docs_dir: Path):
    """
    Update docs/index.html with links to all available reports.
    """
    # Find all HTML reports
    reports = {}
    for html_file in docs_dir.glob("*_report.html"):
        # Parse sector_subsector_report.html
        parts = html_file.stem.replace("_report", "").split("_")
        if len(parts) >= 2:
            sector = parts[0]
            subsector = "_".join(parts[1:])

            if sector not in reports:
                reports[sector] = []
            reports[sector].append({
                "subsector": subsector,
                "filename": html_file.name,
            })

    # Generate index.html
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FlexDamage Parameter Reports</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            line-height: 1.6;
        }
        h1 { color: #1A5276; border-bottom: 2px solid #2E86C1; padding-bottom: 0.5rem; }
        h2 { color: #2E86C1; margin-top: 2rem; }
        ul { list-style: none; padding: 0; }
        li { margin: 0.5rem 0; }
        a {
            color: #2E86C1;
            text-decoration: none;
            padding: 0.3rem 0.6rem;
            border-radius: 4px;
            transition: background-color 0.2s;
        }
        a:hover { background-color: #EBF5FB; }
        .meta { color: #666; font-size: 0.9rem; margin-top: 3rem; }
    </style>
</head>
<body>
    <h1>FlexDamage Parameter Reports</h1>
    <p>Flexible damage function parameters estimated at the Impact Region level.</p>
"""

    for sector in sorted(reports.keys()):
        html_content += f"\n    <h2>{sector.title()}</h2>\n    <ul>\n"
        for report in sorted(reports[sector], key=lambda x: x["subsector"]):
            subsector = report["subsector"]
            filename = report["filename"]
            html_content += f'        <li><a href="{filename}">{subsector.title()}</a></li>\n'
        html_content += "    </ul>\n"

    html_content += """
    <p class="meta">
        Generated with <a href="https://github.com/ClimateImpactLab/flexdamage">FlexDamage</a>
    </p>
</body>
</html>
"""

    index_path = docs_dir / "index.html"
    index_path.write_text(html_content)
    logger.info(f"Updated: {index_path}")


def generate_single_report(
    sector: str,
    subsector: str,
    results_dir: Path,
    output_dir: Path,
    template: Path,
    formats: list,
    version: str,
    deploy: bool = False,
    docs_dir: Optional[Path] = None,
):
    """Generate report for a single sector/subsector combination."""

    # Generate diagnostics
    try:
        success = generate_diagnostics(
            sector,
            subsector,
            results_dir,
            output_dir,
        )
        if not success:
            logger.error(f"Diagnostics generation failed for {sector}/{subsector}")
            return []
    except ImportError as e:
        logger.warning(f"Could not generate diagnostics: {e}")
        logger.info("Continuing with Quarto rendering...")

    # Render Quarto
    params = {
        "sector": sector,
        "subsector": subsector,
        "results_dir": str(results_dir),
        "version": version,
    }

    generated = []
    for fmt in formats:
        ext = {"html": "html", "pdf": "pdf", "typst": "typ"}[fmt]
        output_name = f"{sector}_{subsector}_report.{ext}"

        result = render_quarto(
            template=template,
            output_dir=output_dir,
            output_name=output_name,
            format=fmt,
            params=params,
        )

        if result:
            generated.append(result)

    # Deploy if requested
    if deploy and docs_dir and any(str(p).endswith(".html") for p in generated):
        deploy_to_docs(output_dir, docs_dir, sector, subsector)

    return generated


def main():
    parser = argparse.ArgumentParser(
        description="Generate FlexDamage parameter reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--sector", "-s",
        help="Sector name (e.g., agriculture, mortality, energy, labor)",
    )
    parser.add_argument(
        "--subsector", "-u",
        help="Subsector name (e.g., corn, heat, total, high_risk)",
    )
    parser.add_argument(
        "--results-dir", "-r",
        type=Path,
        default=Path("/project/cil/gcp/flex_damage_funcs/parameters"),
        help="Directory containing parameter files",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=None,
        help="Output directory (default: reports/_output/{sector}_{subsector})",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["html", "pdf", "typst", "all"],
        default="html",
        help="Output format (default: html)",
    )
    parser.add_argument(
        "--template", "-t",
        type=Path,
        default=None,
        help="Custom Quarto template (default: reports/sector_vignette.qmd)",
    )
    parser.add_argument(
        "--diagnostics-only",
        action="store_true",
        help="Generate diagnostic plots only, skip Quarto rendering",
    )
    parser.add_argument(
        "--version",
        default="1.0.0",
        help="Version string for report",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--all-agriculture",
        action="store_true",
        help="Generate reports for all agriculture subsectors",
    )
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Deploy HTML reports to docs/ for GitHub Pages",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=None,
        help="Documentation directory for deployment (default: docs/)",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Paths
    project_root = Path(__file__).parent.parent
    reports_dir = project_root / "reports"
    template = args.template or reports_dir / "sector_vignette.qmd"
    docs_dir = args.docs_dir or project_root / "docs"

    if not template.exists():
        logger.error(f"Template not found: {template}")
        sys.exit(1)

    formats = ["html", "pdf", "typst"] if args.format == "all" else [args.format]

    # Determine which reports to generate
    if args.all_agriculture:
        tasks = [("agriculture", sub) for sub in AGRICULTURE_SUBSECTORS]
    elif args.sector and args.subsector:
        tasks = [(args.sector, args.subsector)]
    else:
        parser.error("Must specify --sector and --subsector, or use --all-agriculture")

    all_generated = []

    for sector, subsector in tasks:
        logger.info(f"\n{'='*60}")
        logger.info(f"Generating report for {sector}/{subsector}")
        logger.info(f"{'='*60}")

        output_dir = args.output_dir or reports_dir / "_output" / f"{sector}_{subsector}"
        output_dir.mkdir(parents=True, exist_ok=True)

        if args.diagnostics_only:
            try:
                success = generate_diagnostics(
                    sector,
                    subsector,
                    args.results_dir,
                    output_dir,
                )
                if success:
                    logger.info(f"Diagnostics generated for {sector}/{subsector}")
            except ImportError as e:
                logger.error(f"Could not generate diagnostics: {e}")
            continue

        generated = generate_single_report(
            sector=sector,
            subsector=subsector,
            results_dir=args.results_dir,
            output_dir=output_dir,
            template=template,
            formats=formats,
            version=args.version,
            deploy=args.deploy,
            docs_dir=docs_dir,
        )
        all_generated.extend(generated)

    if args.diagnostics_only:
        logger.info("\nDiagnostics generation complete.")
        sys.exit(0)

    if all_generated:
        logger.info("")
        logger.info("=" * 60)
        logger.info("Generated reports:")
        for p in all_generated:
            logger.info(f"  {p}")
        logger.info("=" * 60)

        if args.deploy:
            logger.info(f"\nReports deployed to: {docs_dir}")
            logger.info(f"Index page: {docs_dir / 'index.html'}")
    else:
        logger.error("No reports generated")
        sys.exit(1)


if __name__ == "__main__":
    main()
