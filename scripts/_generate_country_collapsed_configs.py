#!/usr/bin/env python3
"""Generate `_country_collapsed` variants of the country configs.

These mirror the existing `_country` configs but set collapse_mc: true and
point at the collapse-MC parquet path. Subsector becomes
`<orig>_country_collapsed` so outputs coexist with the keep-MC ones.
"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = "/scratch/midway3/cadavidsanchez/flex-damages"

PAIRS = [
    ("mortality", "allcause"),
    ("labor", "combined"), ("labor", "high_risk"), ("labor", "low_risk"),
    ("energy", "total"), ("energy", "electricity"), ("energy", "non_electricity"),
    ("agriculture", "corn"), ("agriculture", "rice"), ("agriculture", "soy"),
    ("agriculture", "sorghum"), ("agriculture", "cassava"),
    ("agriculture", "wheat_combined"), ("agriculture", "wheat_spring"),
    ("agriculture", "wheat_winter"),
]


def build_collapsed_source(sector: str, subsector: str) -> str:
    """Path to the collapse-MC parquet that the new prep will produce."""
    if sector == "agriculture":
        return f"{SCRATCH}/agriculture/country_full/agriculture_{subsector}_aggregated_country_full.parquet"
    if sector == "mortality":
        return f"{SCRATCH}/mortality/country_full/mortality_aggregated_country_full.parquet"
    if sector == "labor":
        return f"{SCRATCH}/labor/country_full/labor_aggregated_country_full.parquet"
    if sector == "energy":
        return f"{SCRATCH}/energy/country_full/energy_aggregated_country_full.parquet"
    raise ValueError(sector)


def main():
    n = 0
    for sector, subsector in PAIRS:
        src = ROOT / "configs" / sector / f"{subsector}_country.yaml"
        if not src.exists():
            print(f"SKIP missing: {src}")
            continue
        text = src.read_text()
        # Mutations:
        # - subsector: <orig>_country  ->  <orig>_country_collapsed
        # - run.name: ..._country_ir  ->  ..._country_collapsed_ir
        # - data.collapse_mc: false  ->  true
        # - data.source -> the collapse-MC parquet path
        new_subsector = f"{subsector}_country_collapsed"
        new_source = build_collapsed_source(sector, subsector)
        text = re.sub(rf"^(\s*subsector:\s*){subsector}_country\s*$",
                      rf"\1{new_subsector}", text, flags=re.M)
        text = re.sub(rf"^(\s*name:\s*){sector}_{subsector}_country_ir\s*$",
                      rf"\1{sector}_{new_subsector}_ir", text, flags=re.M)
        text = re.sub(r"^(\s*collapse_mc:\s*)false.*$",
                      r"\1true   # collapse-MC variant for IR-comparable results", text, flags=re.M)
        text = re.sub(r"^(\s*source:\s*).*$",
                      lambda m: f"{m.group(1)}{new_source}", text, count=1, flags=re.M)
        # Also tweak description and results_dir for clarity
        text = re.sub(r"(description:\s*\".*Country resolution)", r"\1 (collapse-MC)", text)
        text = re.sub(rf"(results_dir:\s*[^\n]+){subsector}_country",
                      rf"\1{new_subsector}", text)

        dst = ROOT / "configs" / sector / f"{subsector}_country_collapsed.yaml"
        dst.write_text(text)
        print(f"  wrote {dst.relative_to(ROOT)}")
        n += 1
    print(f"\nWrote {n} _country_collapsed configs")


if __name__ == "__main__":
    main()
