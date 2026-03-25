#!/usr/bin/env python3
"""
Build standardized parameter database from existing results.

Scans multiple directories, standardizes all results to v3 format,
and builds a manifest for Zenodo upload.

Usage:
    python scripts/build_database.py \
        --input-dirs /path/to/results1 /path/to/results2 \
        --output-dir ./parameters \
        --version 0.1.0
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flexdamage.database.discovery import discover_results
from flexdamage.database.standardize_legacy import standardize_to_v3, validate_v3_output
from flexdamage.export.manifest import ManifestBuilder
from flexdamage.utils import setup_logging


def main():
    parser = argparse.ArgumentParser(
        description="Build standardized parameter database from results",
    )

    parser.add_argument(
        "--input-dirs",
        nargs="+",
        required=True,
        help="Directories containing results to process",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="./parameters",
        help="Output directory for standardized files (default: ./parameters)",
    )

    parser.add_argument(
        "--version",
        type=str,
        required=True,
        help="Version string (e.g., 1.0.0)",
    )

    parser.add_argument(
        "--title",
        type=str,
        default="FlexDamage Parameters",
        help="Dataset title",
    )

    parser.add_argument(
        "--description",
        type=str,
        default="Regional climate damage function parameters",
        help="Dataset description",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing files",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    setup_logging(level=logging.INFO if args.verbose else logging.WARNING)
    logger = logging.getLogger("build_database")
    logger.setLevel(logging.INFO)

    output_dir = Path(args.output_dir)

    # Step 1: Discover results
    logger.info("Step 1: Discovering results...")
    results = discover_results(args.input_dirs, recursive=True)

    if not results:
        logger.error("No results found")
        sys.exit(1)

    logger.info(f"Found {len(results)} result files")

    for r in results:
        logger.info(f"  {r['path']} (v{r['format_version']}, {r['n_regions']} regions)")

    if args.dry_run:
        logger.info("Dry run - not writing files")
        return

    # Step 2: Standardize each file
    logger.info("Step 2: Standardizing to v3 format...")
    output_dir.mkdir(parents=True, exist_ok=True)

    standardized = []
    errors = []

    for result in results:
        try:
            output_path = standardize_to_v3(result, output_dir)

            # Validate output
            if validate_v3_output(output_path):
                standardized.append(output_path)
                logger.info(f"  [ok] {output_path.name}")
            else:
                errors.append((result["path"], "Validation failed"))
                logger.error(f"  [fail] {result['path']}: validation failed")

        except Exception as e:
            errors.append((result["path"], str(e)))
            logger.error(f"  [fail] {result['path']}: {e}")

    # Step 3: Build manifest
    logger.info("Step 3: Building manifest...")

    builder = ManifestBuilder(
        output_dir=output_dir,
        version=args.version,
        title=args.title,
        description=args.description,
    )

    for path in standardized:
        builder.add_file(path)

    # Validate
    validation_errors = builder.validate()
    if validation_errors:
        for err in validation_errors:
            logger.error(f"  Manifest error: {err}")

    # Save manifest
    manifest_path = builder.save()
    logger.info(f"Wrote manifest: {manifest_path}")

    # Summary
    print("\n" + "=" * 60)
    print("Build Summary")
    print("=" * 60)
    print(f"  Version: {args.version}")
    print(f"  Output: {output_dir}")
    print(f"  Files standardized: {len(standardized)}")
    print(f"  Errors: {len(errors)}")
    print(f"  Manifest: {manifest_path}")
    print("=" * 60)

    if errors:
        print("\nErrors:")
        for path, error in errors:
            print(f"  {path}: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
