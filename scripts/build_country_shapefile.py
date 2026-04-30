#!/usr/bin/env python3
"""
One-time: dissolve the IR shapefile to a country-level shapefile.

The IR shapefile has 24,378 polygons with a `hierid` field like
"USA.14.648" or "ABW". Dissolving by the top-level country code (the
part before the first dot) produces a country-level shapefile with
matching projection, ready to use in country-resolution reports.

Output: <output-dir>/country_shapefile.shp (+ .shx, .dbf, .prj)

Usage:
    python scripts/build_country_shapefile.py \\
        --output-dir /project/cil/sacagawea_shares/gcp/climate/_spatial_data/country
"""

import argparse
import logging
from pathlib import Path

import geopandas as gpd

IR_SHAPEFILE = Path(
    "/project/cil/sacagawea_shares/gcp/climate/_spatial_data/world-combo-new-nytimes/new_shapefile.shp"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output-dir", required=True, help="Where to write country_shapefile.shp")
    p.add_argument("--ir-shapefile", default=str(IR_SHAPEFILE))
    p.add_argument("--simplify-tol", type=float, default=0.0,
                   help="Optional Douglas-Peucker simplification tolerance (degrees). 0 = no simplification.")
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "country_shapefile.shp"

    log.info(f"Reading IR shapefile: {args.ir_shapefile}")
    gdf_ir = gpd.read_file(args.ir_shapefile)
    log.info(f"IR shapefile: {len(gdf_ir):,} polygons, columns={list(gdf_ir.columns)}")

    if "hierid" not in gdf_ir.columns:
        raise RuntimeError(f"Expected 'hierid' field in IR shapefile; got {list(gdf_ir.columns)}")

    # Country = top-level segment of hierid (everything before first dot)
    gdf_ir["country"] = gdf_ir["hierid"].str.split(".").str[0]
    n_countries = gdf_ir["country"].nunique()
    log.info(f"Found {n_countries} unique country codes")

    # Clean topology before dissolve. The IR shapefile has tiny invalid
    # geometries (slivers, self-intersections, holes that don't match shells)
    # which cause GEOSException during union_all. buffer(0) is a fast,
    # idempotent topology repair that resolves these issues.
    n_invalid = (~gdf_ir.geometry.is_valid).sum()
    if n_invalid > 0:
        log.info(f"Repairing {n_invalid:,} invalid geometries via buffer(0)")
        gdf_ir["geometry"] = gdf_ir.geometry.buffer(0)

    log.info("Dissolving by country (this may take a couple minutes)...")
    try:
        gdf_country = gdf_ir.dissolve(by="country").reset_index()
    except Exception as e:
        log.warning(f"First dissolve attempt failed: {e}")
        log.info("Retrying with make_valid() for stronger topology repair")
        from shapely import make_valid
        gdf_ir["geometry"] = gdf_ir.geometry.apply(make_valid)
        gdf_country = gdf_ir.dissolve(by="country").reset_index()

    if args.simplify_tol > 0:
        log.info(f"Simplifying geometries with tol={args.simplify_tol}")
        gdf_country["geometry"] = gdf_country["geometry"].simplify(args.simplify_tol)

    log.info(f"Country shapefile: {len(gdf_country)} polygons")
    log.info(f"Sample country codes: {sorted(gdf_country['country'].head(10).tolist())}")

    log.info(f"Writing {out_path}")
    gdf_country.to_file(out_path)
    log.info(f"Done. Files written: {sorted(p.name for p in out_dir.glob('country_shapefile.*'))}")


if __name__ == "__main__":
    main()
