#!/bin/bash
# One-time: build a country-level shapefile by dissolving the IR shape.
# Output: /project/cil/sacagawea_shares/.../country/country_shapefile.shp
#
#SBATCH --job-name=build_country_shapefile
#SBATCH --account=cil
#SBATCH --partition=caslake
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=slurm/logs/%x_%j.out
#SBATCH --error=slurm/logs/%x_%j.err

source slurm/_env.sh

OUT_DIR="/project/cil/sacagawea_shares/gcp/climate/_spatial_data/country"

# If the shapefile dir is read-only on /project/cil, fall back to a writeable
# location under home_dirs/scadavidsanchez. Try the canonical place first.
if ! mkdir -p "$OUT_DIR" 2>/dev/null; then
    OUT_DIR="/project/cil/home_dirs/scadavidsanchez/projects/flex-damages-data/_spatial/country"
    mkdir -p "$OUT_DIR"
    echo "Note: using fallback output dir $OUT_DIR (canonical location not writeable)"
fi

python scripts/build_country_shapefile.py --output-dir "$OUT_DIR"

ls -lh "$OUT_DIR/"
