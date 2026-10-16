"""Count terms per outlet per quarter from the cleaned headlines.

Uses only: headlines in URL sections marked keep=1 in sections.csv, headlines not
flagged as syndicated, and English-language outlets (language column in outlets.csv).
A term (single word or two-word phrase) is counted once per headline.
Uses ONE database connection throughout (no reader/writer deadlocks).

Usage: python build_terms.py
"""
import collections
import csv
import random
import re
from urllib.parse import urlparse

from db import HERE, connect

MIN_QUARTER_TOTAL = 3   # drop a term in a quarter if it appears fewer times than this overall
MAX_PER_OUTLET_QUARTER = 1500   # random sample cap per outlet per quarter, so big outlets
                                # (CBC) can't swamp their group. Same sample every run.

STOPWORDS = set("""
a about above after again against all also am amid among an and any are as at be because been
before being below between both but by can could did do does doing down during each few for from
further get gets got had has have having he her here hers him his how if in into is it its just
may me might more most my new no nor not now of off on once one only or other our out over own
per same say says said she should so some still such than that the their them then there these
they this those through to too two three under until up us very via was we were what when where
which while who whom why will with would you your yours amp vs
""".split())

TOKEN = re.compile(r"[a-z0-9]+(?:['\-][a-z0-9]+)*")


def section_key(url):
    """Must match make_section_config.py."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    if not parts:
        return "(root)"
    if parts[0].lower() == "news" and len(parts) > 1 and not parts[1].isdigit():
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def terms_of(headline):
    """Set of single words and adjacent two-word phrases in a headline."""
    text = headline.replace("’", "'")
    text = re.sub(r"\bU\.S\.A?\.?", "usa", text, flags=re.I)
    text = re.sub(r"\bU\.K\.?", "uk", text, flags=re.I)
    text = re.sub(r"\bB\.C\.?", "bc", text, flags=re.I)
    toks = [re.sub(r"'s$", "", t) for t in TOKEN.findall(text.lower())]
    ok = [len(t) >= 2 and not t.isdigit() and t not in STOPWORDS for t in toks]
    uni = {t for t, k in zip(toks, ok) if k}
    bi = {f"{a} {b}" for a, b, ka, kb in zip(toks, toks[1:], ok, ok[1:]) if ka and kb}
    return uni | bi


def load_keep():
    keep = {}
    with open(HERE / "sections.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            keep[(r["outlet_id"], r["section"])] = (
                (r.get("keep") or "").strip().lower() in ("1", "1.0", "true", "yes"))
    return keep


def load_english_outlets():
    with open(HERE / "outlets.csv", newline="", encoding="utf-8") as f:
        return {r["outlet_id"] for r in csv.DictReader(f)
                if (r.get("language") or "en").strip() == "en"}


def quarter_of(month):  # 'YYYY-MM' -> 'YYYY-Qn'
    return f"{month[:4]}-Q{(int(month[5:7]) - 1) // 3 + 1}"


def main():
    keep, english = load_keep(), load_english_outlets()
    conn = connect()
    conn.executescript("""
        DROP TABLE IF EXISTS term_counts;
        DROP TABLE IF EXISTS quarter_totals;
        CREATE TABLE term_counts (quarter TEXT, outlet_id TEXT, term TEXT, n INTEGER);
        CREATE TABLE quarter_totals (quarter TEXT, outlet_id TEXT, headlines INTEGER);
        CREATE INDEX IF NOT EXISTS idx_clean_month ON headlines_clean(month);
    """)

    quarters = collections.OrderedDict()
    for (month,) in conn.execute(
            "SELECT DISTINCT month FROM headlines_clean ORDER BY month").fetchall():
        quarters.setdefault(quarter_of(month), []).append(month)

    for quarter, months in quarters.items():
        marks = ",".join("?" * len(months))
        rows = conn.execute(
            "SELECT c.outlet_id, c.headline, h.url FROM headlines_clean c "
            "JOIN headlines h ON h.id = c.id "
            f"WHERE c.is_syndicated = 0 AND c.month IN ({marks}) ORDER BY c.id", months).fetchall()

        by_outlet = collections.defaultdict(list)
        for oid, headline, url in rows:
            if oid in english and keep.get((oid, section_key(url))):
                by_outlet[oid].append(headline)

        counts, totals = collections.Counter(), collections.Counter()
        rng = random.Random(quarter)            # same sample every run
        for oid, heads in by_outlet.items():
            if len(heads) > MAX_PER_OUTLET_QUARTER:
                heads = rng.sample(heads, MAX_PER_OUTLET_QUARTER)
            totals[oid] = len(heads)
            for headline in heads:
                for term in terms_of(headline):
                    counts[(oid, term)] += 1

        term_totals = collections.Counter()
        for (oid, term), n in counts.items():
            term_totals[term] += n
        out = [(quarter, oid, term, n) for (oid, term), n in counts.items()
               if term_totals[term] >= MIN_QUARTER_TOTAL]

        conn.executemany("INSERT INTO term_counts VALUES (?,?,?,?)", out)
        conn.executemany("INSERT INTO quarter_totals VALUES (?,?,?)",
                         [(quarter, oid, n) for oid, n in totals.items()])
        conn.commit()
        print(f"{quarter}: {sum(totals.values()):,} headlines used, "
              f"{len(out):,} term rows kept", flush=True)

    conn.executescript("""
        CREATE INDEX idx_tc_qo ON term_counts(quarter, outlet_id);
        CREATE INDEX idx_tc_term ON term_counts(term);
    """)
    conn.commit()
    print("\nDONE. Next: python lean_terms.py")


if __name__ == "__main__":
    main()