#!/usr/bin/env python3
"""
Generate __README.md files for every parameter set already on disk, using the
existing __metadata.json + __global_results.json. Idempotent: safe to re-run.

After updating the YAML configs with units / methodology, run this once to
backfill READMEs without re-running estimations. Subsequent estimation runs
will write READMEs automatically (via export/parameters.py).
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

# Add src to path so we can import the renderer
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from flexdamage.export.parameters import _render_readme  # noqa: E402

CONFIGS_DIR = ROOT / "configs"


def _refresh_sector_from_config(metadata: dict, base: str) -> dict:
    """If a YAML config exists for this sector/subsector, override the
    metadata's `sector` block with the (presumably more current) config,
    so updated units / methodology / source fields propagate to the README
    without needing a re-estimation."""
    if "__" not in base:
        return metadata
    sector_name, sub_name = base.split("__", 1)
    cfg_path = CONFIGS_DIR / sector_name / f"{sub_name}.yaml"
    if not cfg_path.exists():
        return metadata
    try:
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        cfg_sector = cfg.get("sector", {})
        if cfg_sector:
            merged = {**metadata.get("sector", {}), **cfg_sector}
            metadata["sector"] = merged
    except Exception as e:
        print(f"  [WARN] could not load {cfg_path}: {e}")
    return metadata


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params-dir",
                    default="/project/cil/gcp/flex_damage_funcs/parameters")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pdir = Path(args.params_dir)
    if not pdir.is_dir():
        print(f"ERROR: params dir not found: {pdir}")
        sys.exit(1)

    n_written = 0
    n_missing_units = 0
    for meta_path in sorted(pdir.glob("*__metadata.json")):
        base = meta_path.name.replace("__metadata.json", "")
        global_path = pdir / f"{base}__global_results.json"
        readme_path = pdir / f"{base}__README.md"

        with open(meta_path) as f:
            metadata = json.load(f)
        # Pick up any newer units / source / methodology fields from the YAML
        # config; without this the README would inherit the old "physical"
        # value baked into pre-patch metadata.json files.
        metadata = _refresh_sector_from_config(metadata, base)
        global_results = {}
        if global_path.exists():
            with open(global_path) as f:
                global_results = json.load(f)

        units = metadata.get("sector", {}).get("units")
        if not units or units == "physical":
            n_missing_units += 1
            print(f"  [WARN] {base}: units field is missing or generic ({units!r}); README will note this")

        text = _render_readme(base, metadata, global_results)
        if args.dry_run:
            print(f"  [DRY] would write {readme_path} ({len(text)} chars)")
        else:
            readme_path.write_text(text)
            print(f"  wrote {readme_path.name}")
        n_written += 1

    print(f"\n{'Would write' if args.dry_run else 'Wrote'} {n_written} READMEs.")
    if n_missing_units:
        print(f"{n_missing_units} sets had missing/generic units. Re-run those "
              f"estimations after updating the YAML configs to refresh metadata.")


if __name__ == "__main__":
    main()
