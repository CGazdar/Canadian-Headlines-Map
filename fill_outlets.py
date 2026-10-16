"""Fill leaning / leaning_checked_on / owner in outlets.csv by outlet_id.
Other columns are left as they are. Usage: python fill_outlets.py
Writes outlets.csv.bak first, so you can undo.
"""
import csv
import shutil
from db import HERE

CHECKED = "2026-10-15"

# outlet_id: (leaning, owner).  leaning = Ground News rating, blank = not found.
FILL = {
    "cbc":            ("lean_left",  "CBC"),
    "ctv":            ("center",     "Bell Media"),
    "global":         ("lean_left",  "Corus"),
    "globe":          ("center",     "Woodbridge"),
    "natpost":        ("lean_right", "Postmedia"),
    "macleans":       ("lean_left",  "St. Joseph Communications"),
    "star":           ("lean_left",  "Torstar"),
    "torontosun":     ("right",      "Postmedia"),
    "ottawacitizen":  ("lean_right", "Postmedia"),
    "ottawasun":      ("lean_right", "Postmedia"),
    "vansun":         ("lean_right", "Postmedia"),
    "province":       ("lean_right", "Postmedia"),
    "tyee":           ("lean_left",  "The Tyee"),
    "calgaryherald":  ("lean_right", "Postmedia"),
    "edmontonjournal":("lean_right", "Postmedia"),
    "calgarysun":     ("right",      "Postmedia"),
    "edmontonsun":    ("lean_right", "Postmedia"),
    "leaderpost":     ("lean_right", "Postmedia"),
    "starphoenix":    ("lean_right", "Postmedia"),
    "wfp":            ("center",     "FP Canadian Newspapers"),
    "winnipegsun":    ("lean_right", "Postmedia"),
    "gazette":        ("lean_right", "Postmedia"),
    "lapresse":       ("",           "La Presse"),
    "ledevoir":       ("center",     "Le Devoir"),
    "jdm":            ("right",      "Quebecor"),
    "chronicleherald":("",           "Halifax Herald"),
    "saltwire":       ("",           "SaltWire"),
}

path = HERE / "outlets.csv"
shutil.copy(path, HERE / "outlets.csv.bak")
with open(path, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    cols = reader.fieldnames
    rows = list(reader)

for r in rows:
    r.pop(None, None)                     # drop any stray extra fields
    if r["outlet_id"] in FILL:
        lean, owner = FILL[r["outlet_id"]]
        r["leaning"], r["owner"] = lean, owner
        r["leaning_checked_on"] = CHECKED if lean else ""
    else:
        print("no entry for", r["outlet_id"])

with open(path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

for r in rows:
    print(r["outlet_id"].ljust(16), (r["leaning"] or "-").ljust(11), r["owner"])