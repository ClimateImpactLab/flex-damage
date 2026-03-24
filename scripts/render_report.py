#!/usr/bin/env python3
"""
Render a report for a specific sector/subsector.

This script writes a JSON config file that the .qmd reads at runtime,
completely bypassing Quarto's broken parameter caching.

Usage:
    python scripts/render_report.py \
        --sector agriculture \
        --subsector corn \
        --params-csv /path/to/regional_parameters.csv \
        --global-json /path/to/global_results.json \
        --source-data /path/to/ir.zarr \
        --output /path/to/output.html
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Render a FlexDamage report")
    parser.add_argument("--sector", required=True, help="Sector name (e.g., agriculture)")
    parser.add_argument("--subsector", required=True, help="Subsector name (e.g., corn)")
    parser.add_argument("--params-csv", required=True, help="Path to regional_parameters.csv")
    parser.add_argument("--global-json", required=True, help="Path to global_results.json")
    parser.add_argument("--source-data", default="", help="Path to source zarr (optional)")
    parser.add_argument("--output", default=None, help="Output path (default: _output/{sector}_{subsector}_ir.html)")
    parser.add_argument("--version", default="1.0.0", help="Version string")
    args = parser.parse_args()

    reports_dir = Path(__file__).parent.parent / "reports"
    template = reports_dir / "sector_vignette.qmd"
    config_file = reports_dir / "_current_report.json"

    if not template.exists():
        print(f"ERROR: Template not found: {template}")
        sys.exit(1)

    # Write config JSON that the .qmd will read
    config = {
        "sector": args.sector,
        "subsector": args.subsector,
        "params_csv": str(args.params_csv),
        "global_json": str(args.global_json),
        "source_data": str(args.source_data) if args.source_data else "",
        "version": args.version,
    }

    print(f"Rendering {args.sector}/{args.subsector}...")
    print(f"  Params CSV: {args.params_csv}")
    print(f"  Global JSON: {args.global_json}")
    print(f"  Source data: {args.source_data or '(none)'}")

    # Write config file
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)
    print(f"  Config written to: {config_file}")

    try:
        # Aggressively clear ALL caches
        for d in ["_freeze", ".quarto", "_output/.jupyter_cache"]:
            p = reports_dir / d
            if p.exists():
                shutil.rmtree(p)
                print(f"  Cleared cache: {d}")

        # Also clear any ipynb checkpoints
        for checkpoint in reports_dir.glob("**/.ipynb_checkpoints"):
            shutil.rmtree(checkpoint)

        # Render
        cmd = [
            "quarto", "render", str(template),
            "--execute",
            "--to", "html",
            "--embed-resources",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(reports_dir),
        )

        if result.returncode != 0:
            print(f"ERROR: Quarto render failed")
            print(result.stderr)
            sys.exit(1)

        # Find rendered output
        rendered = reports_dir / "_output" / "sector_vignette.html"
        if not rendered.exists():
            # Check if it's directly in reports dir
            rendered = reports_dir / "sector_vignette.html"
            if not rendered.exists():
                print(f"ERROR: Rendered file not found")
                print(f"  Looked for: {reports_dir / '_output' / 'sector_vignette.html'}")
                sys.exit(1)

        # Determine output path
        if args.output:
            output_path = Path(args.output)
        else:
            output_path = reports_dir / "_output" / f"{args.sector}_{args.subsector}_ir.html"

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy to final location
        shutil.copy2(rendered, output_path)

        size_mb = output_path.stat().st_size / 1e6
        print(f"Output: {output_path} ({size_mb:.1f}MB)")

    finally:
        # Clean up config file
        if config_file.exists():
            config_file.unlink()


if __name__ == "__main__":
    main()
