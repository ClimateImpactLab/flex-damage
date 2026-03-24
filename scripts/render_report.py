#!/usr/bin/env python3
"""
Render a report for a specific sector/subsector.

This script works around Quarto's unreliable -P parameter injection by:
1. Reading sector_vignette.qmd as a template
2. Replacing the params defaults with actual values
3. Writing a temporary .qmd file
4. Calling quarto render on that temp file
5. Copying output to the right place

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
import re
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

    template_dir = Path(__file__).parent.parent / "reports"
    template = template_dir / "sector_vignette.qmd"

    if not template.exists():
        print(f"ERROR: Template not found: {template}")
        sys.exit(1)

    # Read template
    content = template.read_text()

    # Replace params in the YAML front matter
    # Match the params block and replace values
    def replace_param(content, param_name, new_value):
        # Match:   param_name: "old_value" or param_name: "/path/to/something"
        pattern = rf'({param_name}:\s*)"[^"]*"'
        replacement = rf'\1"{new_value}"'
        return re.sub(pattern, replacement, content)

    content = replace_param(content, "sector", args.sector)
    content = replace_param(content, "subsector", args.subsector)
    content = replace_param(content, "results_dir", str(Path(args.params_csv).parent))
    content = replace_param(content, "source_data", args.source_data)
    content = replace_param(content, "version", args.version)

    # Also need to update the params_csv and global_json references in the setup block
    # These are constructed from results_dir in the template, so updating results_dir should work
    # But let's also add explicit paths for safety

    # Write temp .qmd in the reports directory (so _quarto.yml applies)
    temp_qmd = template_dir / f"_render_{args.sector}_{args.subsector}.qmd"
    temp_qmd.write_text(content)

    print(f"Rendering {args.sector}/{args.subsector}...")
    print(f"  Params CSV: {args.params_csv}")
    print(f"  Global JSON: {args.global_json}")
    print(f"  Source data: {args.source_data or '(none)'}")

    try:
        # Clear cache to ensure fresh render
        for d in ["_freeze", ".quarto"]:
            p = template_dir / d
            if p.exists():
                shutil.rmtree(p)

        # Also clear any jupyter cache
        jupyter_cache = template_dir / "_output" / ".jupyter_cache"
        if jupyter_cache.exists():
            shutil.rmtree(jupyter_cache)

        # Render
        cmd = [
            "quarto", "render", str(temp_qmd),
            "--execute",
            "--to", "html",
            "--embed-resources",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(template_dir),
        )

        if result.returncode != 0:
            print(f"ERROR: Quarto render failed")
            print(result.stderr)
            sys.exit(1)

        # Find rendered output
        rendered_name = temp_qmd.stem + ".html"
        rendered = template_dir / "_output" / rendered_name

        if not rendered.exists():
            # Check if it's directly in reports dir
            rendered = template_dir / rendered_name
            if not rendered.exists():
                print(f"ERROR: Rendered file not found")
                print(f"  Looked for: {template_dir / '_output' / rendered_name}")
                print(f"  And: {template_dir / rendered_name}")
                sys.exit(1)

        # Determine output path
        if args.output:
            output_path = Path(args.output)
        else:
            output_path = template_dir / "_output" / f"{args.sector}_{args.subsector}_ir.html"

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy to final location
        shutil.copy2(rendered, output_path)

        size_mb = output_path.stat().st_size / 1e6
        print(f"Output: {output_path} ({size_mb:.1f}MB)")

        # Clean up rendered file if different from output
        if rendered != output_path and rendered.exists():
            rendered.unlink()

    finally:
        # Clean up temp .qmd
        if temp_qmd.exists():
            temp_qmd.unlink()


if __name__ == "__main__":
    main()
