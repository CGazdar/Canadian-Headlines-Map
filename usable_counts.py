"""Usable headlines per outlet per year, after the section and syndication filters.
Run after build_terms.py. Needs no leaning labels.
Usage: python usable_counts.py
"""
import collections

from db import connect

conn = connect()
names = dict(conn.execute("SELECT outlet_id, name FROM outlets"))
rows = conn.execute("SELECT outlet_id, substr(quarter, 1, 4), SUM(headlines) "
                    "FROM quarter_totals GROUP BY 1, 2").fetchall()
counts = collections.defaultdict(dict)
for oid, year, n in rows:
    counts[oid][year] = n
years = sorted({y for _, y, _ in rows})

print("Usable headlines per outlet per year (after section + syndication filters)\n")
print("outlet".ljust(24), *[y.rjust(7) for y in years])
for oid in sorted(counts, key=lambda o: names.get(o, o)):
    print(names.get(oid, oid)[:23].ljust(24), *[str(counts[oid].get(y, 0)).rjust(7) for y in years])