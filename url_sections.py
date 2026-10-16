"""Count an outlet's cleaned headlines by URL section (first path segment), per year.
Usage: python url_sections.py wfp
"""
import collections
import sys
from urllib.parse import urlparse

from db import connect

if len(sys.argv) != 2:
    sys.exit("usage: python url_sections.py <outlet_id>")
outlet = sys.argv[1]

conn = connect()
counts = collections.defaultdict(collections.Counter)
for url, pub in conn.execute(
        "SELECT h.url, c.published_at FROM headlines_clean c "
        "JOIN headlines h USING (id) WHERE c.outlet_id = ?", (outlet,)):
    parts = [p for p in urlparse(url).path.split("/") if p]
    counts[parts[0] if parts else "(root)"][pub[:4]] += 1

years = sorted({y for c in counts.values() for y in c})
top = sorted(counts, key=lambda s: -sum(counts[s].values()))[:15]
print(f"{outlet}: top URL sections by year\n")
print("section".ljust(28), *[y.rjust(7) for y in years])
for s in top:
    print(s[:27].ljust(28), *[str(counts[s].get(y, 0)).rjust(7) for y in years])