"""Export the numbers the website needs to site/data.js.

Uses the terms in watch_terms.txt (same file as track_terms.py), the leaning/owner
columns in outlets.csv, and the tables made by build_terms.py.
Usage: python export_site_data.py     then open site/index.html in a browser
"""
import csv
import json

from db import HERE, connect
from lean_terms import MIN_OUTLET_QUARTER_HEADLINES, load_outlets
from track_terms import load_watch

# Outlets whose scope is "national" in outlets.csv go in the National tile.
# To force an outlet into a province or National, add it here, e.g. {"natpost": "NAT"}.
OVERRIDE = {}


def main():
    watch = load_watch()
    info, _ = load_outlets()                      # outlet_id -> (group, owner), eligible only
    meta = {}
    with open(HERE / "outlets.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["outlet_id"] in info:
                prov = "NAT" if (r.get("scope") or "").strip().lower() == "national" \
                    else (r.get("home_province") or "").strip().upper()
                prov = OVERRIDE.get(r["outlet_id"], prov) or "NAT"
                meta[r["outlet_id"]] = {"name": r["name"], "province": prov,
                                        "group": info[r["outlet_id"]][0],
                                        "leaning": (r.get("leaning") or "").strip().lower(),
                                        "owner": info[r["outlet_id"]][1]}
    conn = connect()
    totals = {(q, o): n for q, o, n in conn.execute(
        "SELECT quarter, outlet_id, headlines FROM quarter_totals")
        if o in meta and n >= MIN_OUTLET_QUARTER_HEADLINES}
    quarters = sorted({q for q, _ in totals})
    marks = ",".join("?" * len(watch))
    counts = {(t, q, o): n for t, q, o, n in conn.execute(
        f"SELECT term, quarter, outlet_id, n FROM term_counts WHERE term IN ({marks})", watch)}

    rates = {}
    for t in watch:
        rates[t] = {}
        for o in meta:
            rates[t][o] = [round(1000.0 * counts.get((t, q, o), 0) / totals[(q, o)], 2)
                           if (q, o) in totals else None for q in quarters]
    used = sorted({o for (_, o) in totals})
    data = {"quarters": quarters, "terms": watch,
            "outlets": {o: meta[o] for o in used},
            "rates": {t: {o: rates[t][o] for o in used} for t in watch},
            "totals": {o: [totals.get((q, o)) for q in quarters] for o in used}}
    out = HERE / "docs"
    out.mkdir(exist_ok=True)
    (out / "data.js").write_text("window.DATA = " + json.dumps(data) + ";\n", encoding="utf-8")
    print(f"wrote {out / 'data.js'}: {len(watch)} terms, {len(used)} outlets, {len(quarters)} quarters")
    print("\nWhere each outlet lands on the map (check this):")
    for o in used:
        print(f"  {o:16s} {meta[o]['province']:4s} {meta[o]['group']}")


if __name__ == "__main__":
    main()