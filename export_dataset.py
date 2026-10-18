"""Write the public dataset the Data tab offers for download.

Output (in docs/, so GitHub Pages serves it):
  docs/downloads/headline_terms.csv   one row per term x outlet x quarter
  docs/downloads/dataset_info.js      small summary the Data page reads (row count, date, quarters)

Only derived numbers go in: term counts and rates. No headline text and no URLs.
Run it after export_site_data.py:   python export_dataset.py
"""
import csv
import json
from datetime import date

from db import HERE, connect
from export_site_data import OVERRIDE
from lean_terms import MIN_OUTLET_QUARTER_HEADLINES, load_outlets
from track_terms import load_watch

OUT = HERE / "docs" / "downloads"
COLUMNS = ["term", "quarter", "outlet_id", "outlet", "province", "leaning_group", "leaning",
           "owner", "mentions", "headlines_analysed", "rate_per_100k"]


def main():
    watch = load_watch()
    info, _ = load_outlets()                       # outlet_id -> (group, owner), outlets with a usable leaning
    meta = {}
    with open(HERE / "outlets.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            o = r["outlet_id"]
            if o not in info:
                continue
            prov = "NAT" if (r.get("scope") or "").strip().lower() == "national" \
                else (r.get("home_province") or "").strip().upper()
            prov = OVERRIDE.get(o, prov) or "NAT"
            if prov in ("YT", "NT", "NU"):
                prov = "TER"                       # the site shows the territories as one region
            meta[o] = {"outlet": r["name"], "province": prov, "group": info[o][0],
                       "leaning": (r.get("leaning") or "").strip().lower(), "owner": info[o][1]}
    conn = connect()
    totals = {(q, o): n for q, o, n in conn.execute(
        "SELECT quarter, outlet_id, headlines FROM quarter_totals")
        if o in meta and n >= MIN_OUTLET_QUARTER_HEADLINES}
    marks = ",".join("?" * len(watch))
    counts = {(t, q, o): n for t, q, o, n in conn.execute(
        f"SELECT term, quarter, outlet_id, n FROM term_counts WHERE term IN ({marks})", watch)}

    OUT.mkdir(parents=True, exist_ok=True)
    rows = 0
    with open(OUT / "headline_terms.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for t in watch:
            for (q, o) in sorted(totals, key=lambda k: (k[0], meta[k[1]]["outlet"])):
                n, tot = counts.get((t, q, o), 0), totals[(q, o)]
                m = meta[o]
                w.writerow([t, q, o, m["outlet"], m["province"], m["group"], m["leaning"], m["owner"],
                            n, tot, round(100000.0 * n / tot, 1)])
                rows += 1
    quarters = sorted({q for q, _ in totals})
    outlets = sorted({o for _, o in totals})
    summary = {"rows": rows, "terms": len(watch), "outlets": len(outlets), "quarters": len(quarters),
               "first": quarters[0], "last": quarters[-1], "updated": date.today().isoformat()}
    (OUT / "dataset_info.js").write_text("window.DATASET = " + json.dumps(summary) + ";\n", encoding="utf-8")
    print(f"wrote {OUT / 'headline_terms.csv'}: {rows:,} rows ({len(watch)} terms, {len(outlets)} outlets, "
          f"{quarters[0]} to {quarters[-1]})")


if __name__ == "__main__":
    main()