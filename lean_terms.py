"""Find the terms most characteristic of each leaning group, and follow them over time.

Needs: outlets.csv with 'leaning' (and 'owner') filled in, plus the tables built by
build_terms.py. Writes three CSV files next to this script:
  distinctive_terms.csv   top terms per group, whole period
  term_trends.csv         those terms' rate per 1,000 headlines, per quarter and group
  coverage_by_quarter.csv which outlets/owners/headlines each group rests on, per quarter

Usage: python lean_terms.py
"""
import collections
import csv
import math
import sys

from db import HERE, connect

# --- settings you may want to change -------------------------------------------------
GROUP_MAP = {"left": "left", "lean_left": "left", "center": "center",
             "lean_right": "right", "right": "right"}
MIN_OUTLET_QUARTER_HEADLINES = 300  # an outlet-quarter with fewer usable headlines is ignored
MIN_TERM_HEADLINES = 40             # a term needs this many headlines within the group
MIN_OWNERS = 2                      # ...and must be used by this many different owners
MIN_COUNT_PER_OWNER = 5             # an owner "uses" a term if it appears in this many headlines
PRIOR_STRENGTH = 500                # higher = more skeptical of rare terms
MIN_OUTLETS = 3                     # ...and by this many different outlets
EXCLUDE_FILE = "exclude_terms.txt"  # words to ignore: places, site boilerplate (one per line)
TOP_N = 100                         # terms per group written to distinctive_terms.csv
TREND_TOP = 30                      # terms per group followed over time
# -------------------------------------------------------------------------------------


def load_outlets():
    info, skipped = {}, []
    with open(HERE / "outlets.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("language") or "en").strip() != "en":
                continue
            lean = (r.get("leaning") or "").strip().lower()
            owner = (r.get("owner") or "").strip() or r["outlet_id"]
            if lean in GROUP_MAP:
                info[r["outlet_id"]] = (GROUP_MAP[lean], owner)
            else:
                skipped.append(r["outlet_id"])
    return info, skipped


def load_excluded():
    path = HERE / EXCLUDE_FILE
    if not path.exists():
        return set()
    return {ln.strip().lower() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


def write_csv(name, header, rows):
    path = HERE / name
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"wrote {path}")


def main():
    info, skipped = load_outlets()
    excluded = load_excluded()
    if skipped:
        print(f"Excluded (no usable leaning yet): {', '.join(skipped)}\n")
    conn = connect()

    # Which outlet-quarters have enough data to count
    conn.execute("DROP TABLE IF EXISTS temp.eligible_oq")
    conn.execute("CREATE TEMP TABLE eligible_oq (quarter TEXT, outlet_id TEXT, "
                 "grp TEXT, owner TEXT, headlines INTEGER)")
    rows = [(q, oid, info[oid][0], info[oid][1], n)
            for q, oid, n in conn.execute(
                "SELECT quarter, outlet_id, headlines FROM quarter_totals").fetchall()
            if oid in info and n >= MIN_OUTLET_QUARTER_HEADLINES]
    if not rows:
        sys.exit("No outlet-quarters pass the thresholds. Check 'leaning' in outlets.csv.")
    conn.executemany("INSERT INTO eligible_oq VALUES (?,?,?,?,?)", rows)
    conn.execute("CREATE INDEX temp.idx_eoq ON eligible_oq(quarter, outlet_id)")

    N = dict(conn.execute("SELECT grp, SUM(headlines) FROM eligible_oq GROUP BY grp"))
    if len(N) < 2:
        sys.exit(f"Need at least two leaning groups with data; have: {list(N)}")
    print("Usable headlines per group:", {g: f"{n:,}" for g, n in sorted(N.items())})
    for g, o, q in conn.execute(
            "SELECT grp, COUNT(DISTINCT outlet_id), COUNT(DISTINCT quarter) "
            "FROM eligible_oq GROUP BY grp"):
        print(f"  {g}: {o} outlets, {q} quarters")
    N_all = sum(N.values())

    write_csv("coverage_by_quarter.csv", ["quarter", "group", "outlets", "owners", "headlines"],
              conn.execute("SELECT quarter, grp, COUNT(*), COUNT(DISTINCT owner), SUM(headlines) "
                           "FROM eligible_oq GROUP BY quarter, grp ORDER BY quarter, grp"))

    # Headlines containing each term, per group (only terms big enough in some group)
    Y = collections.defaultdict(dict)
    for term, grp, s in conn.execute("""
            WITH g AS (
                SELECT t.term AS term, e.grp AS grp, SUM(t.n) AS s
                FROM term_counts t JOIN eligible_oq e
                  ON e.quarter = t.quarter AND e.outlet_id = t.outlet_id
                GROUP BY t.term, e.grp)
            SELECT term, grp, s FROM g
            WHERE term IN (SELECT term FROM g WHERE s >= ?)""", (MIN_TERM_HEADLINES,)):
        if not any(w in excluded for w in term.split()):
            Y[term][grp] = s

    # How many different owners and outlets use each candidate term, per group
    conn.execute("DROP TABLE IF EXISTS temp.cand_terms")
    conn.execute("CREATE TEMP TABLE cand_terms (term TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO cand_terms VALUES (?)", [(t,) for t in Y])
    group_owners = dict(conn.execute("SELECT grp, COUNT(DISTINCT owner) FROM eligible_oq GROUP BY grp"))
    group_outlets = dict(conn.execute("SELECT grp, COUNT(DISTINCT outlet_id) FROM eligible_oq GROUP BY grp"))
    for g in sorted(N):
        print(f"  {g}: {group_owners[g]} owners")
        if group_owners[g] < MIN_OWNERS:
            print(f"  NOTE: the {g} group has only {group_owners[g]} owner(s), so the owner "
                  f"rule is relaxed for it; its terms may reflect one company's house style.")
    users = collections.defaultdict(lambda: (set(), set()))
    for term, grp, oid, owner in conn.execute("""
            SELECT t.term, e.grp, e.outlet_id, e.owner
            FROM term_counts t JOIN eligible_oq e
              ON e.quarter = t.quarter AND e.outlet_id = t.outlet_id
            WHERE t.term IN (SELECT term FROM cand_terms)
            GROUP BY t.term, e.grp, e.outlet_id
            HAVING SUM(t.n) >= ?""", (MIN_COUNT_PER_OWNER,)):
        users[(term, grp)][0].add(owner)
        users[(term, grp)][1].add(oid)

    # Smoothed log-odds z-score: this group versus all other groups combined
    scored = {g: [] for g in N}
    for term, ys in Y.items():
        y_all = sum(ys.values())
        p = y_all / N_all
        a, b = PRIOR_STRENGTH * p, PRIOR_STRENGTH * (1 - p)
        for g, y_g in ys.items():
            ow, ou = users.get((term, g), (set(), set()))
            if (y_g < MIN_TERM_HEADLINES or len(ow) < min(MIN_OWNERS, group_owners[g])
                    or len(ou) < min(MIN_OUTLETS, group_outlets[g])):
                continue
            n_g, y_r, n_r = N[g], y_all - y_g, N_all - N[g]
            s1, f1 = y_g + a, (n_g - y_g) + b
            s2, f2 = y_r + a, (n_r - y_r) + b
            z = (math.log(s1 / f1) - math.log(s2 / f2)) / math.sqrt(1/s1 + 1/f1 + 1/s2 + 1/f2)
            scored[g].append((z, term, y_g, 1000 * y_g / n_g, 1000 * y_r / n_r, len(ow), len(ou)))

    out_rows, trend_terms = [], {}
    for g in sorted(scored):
        ranked = sorted(scored[g], reverse=True)
        print(f"\nTop terms for the {g} group:")
        for i, (z, term, y_g, rg, rr, ow, ou) in enumerate(ranked[:TOP_N], 1):
            out_rows.append((g, i, term, round(z, 2), y_g, round(rg, 2), round(rr, 2), ow, ou))
            if i <= 20:
                print(f"  {i:2d}. {term:28s} z={z:6.1f}  {rg:6.2f} vs {rr:6.2f} per 1,000  ({ow} owners, {ou} outlets)")
        for z, term, *_ in ranked[:TREND_TOP]:
            trend_terms.setdefault(term, g)
    write_csv("distinctive_terms.csv",
              ["group", "rank", "term", "z", "headlines_in_group",
               "per_1000_in_group", "per_1000_in_other_groups", "owners", "outlets"], out_rows)

    # Rate per 1,000 headlines over time: average of each outlet's own rate (so big
    # outlets don't dominate), for every quarter where the group has data
    conn.execute("DROP TABLE IF EXISTS temp.trend_terms")
    conn.execute("CREATE TEMP TABLE trend_terms (term TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO trend_terms VALUES (?)", [(t,) for t in trend_terms])
    rate = collections.defaultdict(float)
    for term, q, g, n, hl in conn.execute("""
            SELECT t.term, t.quarter, e.grp, t.n, e.headlines
            FROM term_counts t JOIN eligible_oq e
              ON e.quarter = t.quarter AND e.outlet_id = t.outlet_id
            WHERE t.term IN (SELECT term FROM trend_terms)"""):
        rate[(term, q, g)] += 1000.0 * n / hl
    cells = conn.execute("SELECT quarter, grp, COUNT(*) FROM eligible_oq "
                         "GROUP BY quarter, grp ORDER BY quarter, grp").fetchall()
    trend_rows = [(term, trend_terms[term], q, g, round(rate.get((term, q, g), 0.0) / k, 3), k)
                  for term in sorted(trend_terms) for q, g, k in cells]
    write_csv("term_trends.csv",
              ["term", "distinctive_for", "quarter", "group", "per_1000", "outlet_count"], trend_rows)


if __name__ == "__main__":
    main()