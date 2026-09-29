#!/usr/bin/env python3
"""Regenerate the reports repo's index.html from whatever report HTMLs are
present - no exclusions, so every report that exists gets listed.

This is the single source of truth for the index: deploy_all_reports.sh,
render_missing_reports.sh, deploy_report.sh and generate_all_reports.sh
all call it instead of carrying their own generators, which used to
disagree about both format and exclusions.

Prints per-sector counts and, loudly, any HTML file it could not parse
into (sector, subsector, resolution) - an unparsed report would otherwise
silently vanish from the index.

Usage: python3 update_index.py /path/to/flex-damage-reports
"""

import glob
import os
import sys

RES_ORDER = ["ir", "country", "country_collapsed", "country_unconstrained"]
RES_HEADER = {
    "ir":                    "Impact Region",
    "country":               "Country",
    "country_collapsed":     "Country (collapse-MC)",
    "country_unconstrained": "Country (unconstrained, diagnostic)",
}
# longest first, so agriculture_value never parses as agriculture
SECTORS = ["agriculture_value", "agriculture", "mortality", "labor", "energy"]


def parse(name):
    stem = name[: -len(".html")]
    for suffix, res in [("_country_unconstrained", "country_unconstrained"),
                        ("_country_collapsed",     "country_collapsed"),
                        ("_country",               "country"),
                        ("_ir",                    "ir")]:
        if stem.endswith(suffix):
            base = stem[: -len(suffix)]
            for sec in SECTORS:
                if base == sec:
                    return None
                if base.startswith(sec + "_"):
                    return sec, base[len(sec) + 1:], res
    return None


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    os.chdir(repo)

    groups = {}
    unparsed = []
    for r in sorted(f for f in glob.glob("*.html") if f != "index.html"):
        p = parse(r)
        if not p:
            unparsed.append(r)
            continue
        sector, sub, res = p
        groups.setdefault(sector, {}).setdefault(sub, {})[res] = r

    html = ['<html><head><title>FlexDamage Reports</title>',
            '<style>body{font-family:sans-serif;max-width:1100px;margin:2em auto;padding:0 1em}',
            'h1{color:#1f4e79}h2{color:#1f4e79;border-bottom:1px solid #d0d7de;padding-bottom:.3em;margin-top:2em}',
            'table{border-collapse:collapse;width:100%;margin:0.5em 0}',
            'th,td{padding:6px 10px;border-bottom:1px solid #eee;text-align:left}',
            'th{background:#f6f8fa;font-weight:600;font-size:.95em}',
            'a{color:#2c5c8f;text-decoration:none}a:hover{text-decoration:underline}',
            '.meta{color:#666;font-size:0.9em;margin-top:3em;border-top:1px solid #d0d7de;padding-top:1em}</style>',
            '</head><body>',
            '<h1>Flexible Damage Function Reports</h1>',
            '<p>Climate Impact Lab &mdash; diagnostic reports for region-specific damage functions, '
            'estimated at impact-region and country resolutions. '
            '<a href="https://climateimpactlab.github.io/flex-damage/units/">Units &amp; methodology</a> | '
            '<a href="https://zenodo.org/concept/19199919">Parameters on Zenodo</a></p>']

    total = 0
    for sector in sorted(groups):
        html.append(f'<h2>{sector.replace("_", " ").title()}</h2>')
        html.append('<table><thead><tr><th>Subsector</th>'
                    + ''.join(f'<th>{RES_HEADER[r]}</th>' for r in RES_ORDER)
                    + '</tr></thead><tbody>')
        for sub in sorted(groups[sector]):
            cells = [f'<td>{sub.replace("_", " ").title()}</td>']
            for res in RES_ORDER:
                f = groups[sector][sub].get(res)
                cells.append(f'<td><a href="{f}">view</a></td>' if f else '<td>n/a</td>')
                total += 1 if f else 0
            html.append('<tr>' + ''.join(cells) + '</tr>')
        html.append('</tbody></table>')

    html += ['<p class="meta">',
             '  <a href="https://climateimpactlab.github.io/flex-damage/">Documentation</a> | ',
             '  <a href="https://github.com/ClimateImpactLab/flex-damage">GitHub repo</a> | ',
             '  <a href="https://zenodo.org/concept/19199919">Zenodo concept</a>',
             '</p></body></html>']
    open("index.html", "w").write("\n".join(html))

    for sector in sorted(groups):
        by_res = {}
        n_sec = 0
        for resmap in groups[sector].values():
            for res in resmap:
                by_res[res] = by_res.get(res, 0) + 1
                n_sec += 1
        detail = ", ".join(f"{r} {by_res[r]}" for r in RES_ORDER if r in by_res)
        print(f"  {sector}: {n_sec} ({detail})")
    print(f"index.html: {total} report links across {len(groups)} sectors")
    if unparsed:
        print(f"WARNING: {len(unparsed)} html files not parsed and NOT listed: "
              + ", ".join(unparsed))


if __name__ == "__main__":
    main()
