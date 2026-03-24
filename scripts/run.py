#!/usr/bin/env python3
"""
Run FlexDamage pipeline from config.

Usage:
    python scripts/run.py config.yaml
    python scripts/run.py configs/agriculture/corn.yaml --verbose
    python scripts/run.py configs/agriculture/corn.yaml --output-dir ./results
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flexdamage import FlexDamagePipeline
from flexdamage.utils import setup_logging


def main():
    parser = argparse.ArgumentParser(
        description="Run FlexDamage estimation pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "config",
        type=str,
        help="Path to YAML configuration file",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Override output directory",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.debug else (logging.INFO if args.verbose else logging.WARNING)
    setup_logging(level=level)

    logger = logging.getLogger("flexdamage")
    logger.setLevel(logging.INFO)  # Always show pipeline progress

    # Validate config path
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    # Run pipeline
    try:
        pipeline = FlexDamagePipeline(config_path)

        # Override output dir if specified
        if args.output_dir:
            pipeline.config.output.parameters_dir = args.output_dir
            pipeline.config.output.results_dir = args.output_dir

        summary = pipeline.run()

        # Print summary
        print("\n" + "=" * 60)
        print("Pipeline Summary")
        print("=" * 60)
        print(f"  Status: {summary['status']}")
        print(f"  Run: {summary['run_name']}")
        print(f"  Observations: {summary['n_observations']:,}")
        print(f"  Regions: {summary['n_regions']:,}")
        print(f"  Gamma: {summary['gamma']:.6f} ± {summary['gamma_se']:.6f}")
        print(f"  Total time: {summary['timings']['total']:.2f}s")
        print(f"  Output: {summary['output_csv']}")
        print("=" * 60)

    except Exception as e:
        logger.exception("Pipeline failed")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
