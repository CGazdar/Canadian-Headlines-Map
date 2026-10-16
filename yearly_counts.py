"""Per-outlet, per-year headline counts.
Usage: python yearly_counts.py [headlines | headlines_clean]
"""
import collections
import sqlite3
import sys

from db import DB_PATH

table = sys.argv[1] if len(sys.argv) > 1 else "headlines_clean"
if table not in ("headlines", "headlines_clean"):
    sys.exit("table must be 'headlines' or 'headlines_clean'")

c = sqlite3.connect(DB_PATH)
rows = c.execute(f"""
    SELECT o.name, substr(h.published_at, 1, 4), COUNT(*)
    FROM {table} h JOIN outlets o USING (outlet_id)
    GROUP BY 1, 2""").fetchall()

counts = collections.defaultdict(dict)
for name, year, n in rows:
    counts[name][year] = n
years = sorted({y for _, y, _ in rows})

print(f"Headlines per outlet per year ({table})\n")
print("outlet".ljust(24), *[y.rjust(7) for y in years])
for name in sorted(counts):
    print(name.ljust(24), *[str(counts[name].get(y, 0)).rjust(7) for y in years])

if table == "headlines_clean":
    print("\nShare of each outlet's headlines flagged as syndicated:\n")
    for name, pct in c.execute("""
            SELECT o.name, ROUND(100.0 * SUM(h.is_syndicated) / COUNT(*), 1)
            FROM headlines_clean h JOIN outlets o USING (outlet_id)
            GROUP BY 1 ORDER BY 2 DESC"""):
        print(f"  {name.ljust(24)} {pct}%")