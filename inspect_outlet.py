"""Look inside one outlet's cleaned headlines for one year, optionally one URL section.
Usage: python inspect_outlet.py wfp 2024 [url_section]
"""
import collections
import sys

from db import connect

if len(sys.argv) not in (3, 4):
    sys.exit("usage: python inspect_outlet.py <outlet_id> <year> [url_section]")
outlet, year = sys.argv[1], sys.argv[2]
section = sys.argv[3] if len(sys.argv) == 4 else None

query = ("SELECT c.headline FROM headlines_clean c JOIN headlines h USING (id) "
         "WHERE c.outlet_id = ? AND substr(c.published_at, 1, 4) = ?")
params = [outlet, year]
if section:
    query += " AND instr(h.url, '/' || ? || '/') > 0"
    params.append(section)

conn = connect()
rows = [r[0] for r in conn.execute(query, params)]
label = f"{outlet} {year}" + (f" /{section}/" if section else "")
print(f"{len(rows):,} headlines for {label}\n")

starts = collections.Counter(" ".join(h.split()[:2]).lower() for h in rows)
print("Most common first two words:")
for words, n in starts.most_common(10):
    print(f"  {n:6,}  {words}")

print("\n25 random headlines:")
for (h,) in conn.execute(query + " ORDER BY RANDOM() LIMIT 25", params):
    print("  ", h)