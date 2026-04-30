#!/usr/bin/env python3
"""
Render a report for a specific sector/subsector.

Each render runs in its own temp working directory to avoid race conditions
when multiple renders execute in parallel (the previous shared
`_current_report.json` + shared `_freeze` cache caused parallel SLURM jobs
to clobber each other's outputs).

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
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Render a FlexDamage report")
    parser.add_argument("--sector", required=True)
    parser.add_argument("--subsector", required=True)
    parser.add_argument("--params-csv", required=True)
    parser.add_argument("--global-json", required=True)
    parser.add_argument("--source-data", default="")
    parser.add_argument("--output", default=None)
    parser.add_argument("--version", default="1.0.0")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    reports_dir = project_root / "reports"
    template = reports_dir / "sector_vignette.qmd"
    if not template.exists():
        print(f"ERROR: Template not found: {template}")
        sys.exit(1)

    # Output filename: keep the legacy `_ir` suffix only for IR-resolution
    # reports. Any country subsector (e.g. `cassava_country`,
    # `cassava_country_collapsed`, `non_electricity_country_unconstrained`)
    # already self-identifies in the name, so the extra `_ir` is misleading.
    sub = args.subsector
    is_country = "_country" in sub
    suffix = "" if is_country else "_ir"
    final_output = (Path(args.output) if args.output
                    else reports_dir / "_output" / f"{args.sector}_{sub}{suffix}.html")
    final_output.parent.mkdir(parents=True, exist_ok=True)

    # Per-run isolated working dir under reports/_runs/<unique>/. Quarto needs
    # the .qmd to live in a real directory (not a tmp filesystem) so jupyter
    # kernels can resolve relative paths consistently. Use a per-PID + timestamp
    # path under the project tree.
    runs_dir = reports_dir / "_runs"
    runs_dir.mkdir(exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix=f"{args.sector}_{args.subsector}_",
                                     dir=str(runs_dir)))
    print(f"Rendering {args.sector}/{args.subsector}...")
    print(f"  Work dir:    {work_dir}")
    print(f"  Params CSV:  {args.params_csv}")
    print(f"  Global JSON: {args.global_json}")
    print(f"  Source data: {args.source_data or '(none)'}")
    print(f"  Final out:   {final_output}")

    try:
        # Copy the template into the work dir so caches/freezes don't collide
        local_qmd = work_dir / "sector_vignette.qmd"
        shutil.copy2(template, local_qmd)

        # Write the per-run config alongside it
        config = {
            "sector": args.sector,
            "subsector": args.subsector,
            "params_csv": str(args.params_csv),
            "global_json": str(args.global_json),
            "source_data": str(args.source_data) if args.source_data else "",
            "version": args.version,
        }
        config_file = work_dir / "_current_report.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        # Quarto runs IN the work dir, uses local qmd + local config
        cmd = ["quarto", "render", "sector_vignette.qmd",
               "--execute", "--to", "html", "--embed-resources"]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(work_dir))
        if result.returncode != 0:
            print("ERROR: Quarto render failed")
            print(result.stdout)
            print(result.stderr)
            sys.exit(1)

        # Quarto writes sector_vignette.html alongside the qmd (or in _output)
        candidates = [work_dir / "sector_vignette.html",
                      work_dir / "_output" / "sector_vignette.html"]
        rendered = next((c for c in candidates if c.exists()), None)
        if rendered is None:
            print(f"ERROR: Rendered HTML not found in {work_dir}")
            sys.exit(1)

        shutil.copy2(rendered, final_output)
        size_mb = final_output.stat().st_size / 1e6
        print(f"Output: {final_output} ({size_mb:.1f}MB)")
    finally:
        # Clean up per-run dir
        try:
            shutil.rmtree(work_dir)
        except Exception as e:
            print(f"WARN: could not clean up {work_dir}: {e}")


if __name__ == "__main__":
    main()
