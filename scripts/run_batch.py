#!/usr/bin/env python3
"""
Run FlexDamage pipeline for all configs in a directory.

Usage:
    python scripts/run_batch.py configs/agriculture/
    python scripts/run_batch.py configs/ --recursive
    python scripts/run_batch.py configs/agriculture/ --parallel 4
"""

import argparse
import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flexdamage import FlexDamagePipeline
from flexdamage.utils import setup_logging


def run_single_config(config_path: Path) -> dict:
    """Run a single config and return summary."""
    try:
        pipeline = FlexDamagePipeline(config_path)
        summary = pipeline.run()
        return {"config": str(config_path), "status": "success", **summary}
    except Exception as e:
        return {"config": str(config_path), "status": "failed", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="Run FlexDamage for all configs in a directory",
    )

    parser.add_argument(
        "directory",
        type=str,
        help="Directory containing YAML config files",
    )

    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Search recursively for configs",
    )

    parser.add_argument(
        "--parallel", "-p",
        type=int,
        default=1,
        help="Number of configs to run in parallel (default: 1)",
    )

    parser.add_argument(
        "--pattern",
        type=str,
        default="*.yaml",
        help="Glob pattern for config files (default: *.yaml)",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    setup_logging(level=logging.INFO if args.verbose else logging.WARNING)
    logger = logging.getLogger("flexdamage.batch")

    # Find config files
    config_dir = Path(args.directory)
    if not config_dir.is_dir():
        print(f"Error: Not a directory: {config_dir}", file=sys.stderr)
        sys.exit(1)

    if args.recursive:
        configs = list(config_dir.rglob(args.pattern))
    else:
        configs = list(config_dir.glob(args.pattern))

    if not configs:
        print(f"No config files found matching {args.pattern} in {config_dir}")
        sys.exit(0)

    print(f"Found {len(configs)} config files")
    print("=" * 60)

    results = []

    if args.parallel > 1:
        # Parallel execution
        with ProcessPoolExecutor(max_workers=args.parallel) as executor:
            futures = {executor.submit(run_single_config, c): c for c in configs}

            for future in as_completed(futures):
                result = future.result()
                results.append(result)

                status = "✓" if result["status"] == "success" else "✗"
                print(f"{status} {result['config']}")

                if result["status"] == "success":
                    print(f"   Time: {result['timings']['total']:.1f}s, "
                          f"Regions: {result['n_regions']}, "
                          f"Gamma: {result['gamma']:.4f}")
    else:
        # Sequential execution
        for config_path in configs:
            result = run_single_config(config_path)
            results.append(result)

            status = "✓" if result["status"] == "success" else "✗"
            print(f"{status} {config_path}")

            if result["status"] == "success":
                print(f"   Time: {result['timings']['total']:.1f}s, "
                      f"Regions: {result['n_regions']}, "
                      f"Gamma: {result['gamma']:.4f}")

    # Summary
    print("=" * 60)
    n_success = sum(1 for r in results if r["status"] == "success")
    n_failed = len(results) - n_success
    print(f"Completed: {n_success} success, {n_failed} failed")

    if n_failed > 0:
        print("\nFailed configs:")
        for r in results:
            if r["status"] == "failed":
                print(f"  {r['config']}: {r.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
