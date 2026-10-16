"""Build headlines_clean from headlines. The raw table is never modified.

Steps: decode HTML entities, strip boilerplate suffixes (site/section names
learned from the data), drop obvious non-news pages, and flag headlines that
appear at several outlets in the same month (wire/syndicated copy).

Uses ONE database connection throughout: reading on one connection while
writing on another deadlocks SQLite.
"""
import collections
import html
import re
import unicodedata

from db import connect

SEPS = (" | ", " – ", " - ", " — ")
SAMPLE_PER_OUTLET = 30000   # rows used to learn each outlet's boilerplate suffixes
MIN_SUFFIX_COUNT = 20       # a tail seen this often in the sample counts as boilerplate
MAX_STRIP_ROUNDS = 3
CHUNK = 100000

DROP_TEXT = re.compile(
    r"^(weather|sports scores)\s*:|^sunshine girl|horoscope|\b\d+\s+bedroom\b|^news briefs for\b",
    re.I,
)
POSTAL = re.compile(r"\b[A-Z]\d[A-Z] ?\d[A-Z]\d\b")  # Canadian postal code: real-estate listings
# Obituary pages and hub pages are not headlines: drop rows carrying these tags
DROP_RAW = re.compile(
    r"\s[|–—-]\s(Obituaries|In Memoriams|Winnipeg Free Press Passages|Winnipeg Free Press Homes|Top Stories|Top News Headlines)\b",
    re.I,
)
# Content words that look like suffixes but belong to real headlines: never strip
NEVER_STRIP = {"CDC", "source", "sources", "minister", "and why"}


def clean_text(s):
    s = html.unescape(s)
    s = unicodedata.normalize("NFC", s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def split_tail(s):
    """Split at the rightmost separator. Returns (head, tail), or (s, None)."""
    best, sep_len = -1, 0
    for sep in SEPS:
        i = s.rfind(sep)
        if i > best:
            best, sep_len = i, len(sep)
    if best <= 0:
        return s, None
    return s[:best], s[best + sep_len:]


def learn_suffixes(conn):
    boiler = collections.defaultdict(set)
    for (oid,) in conn.execute("SELECT outlet_id FROM outlets").fetchall():
        print(f"  learning suffixes: {oid}", flush=True)
        rows = [clean_text(r[0]) for r in conn.execute(
            "SELECT headline FROM headlines WHERE outlet_id=? ORDER BY RANDOM() LIMIT ?",
            (oid, SAMPLE_PER_OUTLET)).fetchall()]
        for _ in range(MAX_STRIP_ROUNDS):
            counts = collections.Counter()
            for s in rows:
                _, tail = split_tail(s)
                if tail:
                    counts[tail] += 1
            found = {t for t, n in counts.items()
                     if n >= MIN_SUFFIX_COUNT and t not in NEVER_STRIP}
            if not found:
                break
            boiler[oid] |= found
            rows = [split_tail(s)[0] if split_tail(s)[1] in found else s for s in rows]
    return boiler


def strip_suffixes(s, tails):
    for _ in range(MAX_STRIP_ROUNDS):
        head, tail = split_tail(s)
        if tail in tails and head:
            s = head
        else:
            break
    return s


def main():
    conn = connect()
    conn.executescript("""
        DROP TABLE IF EXISTS headlines_clean;
        CREATE TABLE headlines_clean (
            id            INTEGER PRIMARY KEY,   -- same id as headlines.id
            outlet_id     TEXT NOT NULL,
            published_at  TEXT NOT NULL,
            month         TEXT NOT NULL,         -- YYYY-MM
            headline      TEXT NOT NULL,
            norm          TEXT NOT NULL,         -- lowercase, punctuation removed
            is_syndicated INTEGER NOT NULL DEFAULT 0
        );
    """)

    print("Stage 1 of 3: learning suffixes", flush=True)
    boiler = learn_suffixes(conn)
    print("\nSuffixes learned (check these look like site/section names):")
    for oid, tails in sorted(boiler.items()):
        print(f"  {oid} ({len(tails)}): {sorted(tails)[:15]}")

    print("\nStage 2 of 3: cleaning headlines", flush=True)
    dropped, batch = collections.Counter(), []

    def flush():
        conn.executemany("INSERT INTO headlines_clean VALUES (?,?,?,?,?,?,0)", batch)
        conn.commit()
        batch.clear()

    last_id, done = 0, 0
    while True:
        rows = conn.execute(
            "SELECT id, outlet_id, published_at, headline FROM headlines "
            "WHERE id > ? ORDER BY id LIMIT ?", (last_id, CHUNK)).fetchall()
        if not rows:
            break
        last_id = rows[-1][0]
        for id_, oid, pub, raw in rows:
            text = clean_text(raw)
            if DROP_RAW.search(text):
                dropped["obituary/hub page"] += 1
                continue
            s = strip_suffixes(text, boiler.get(oid, set())).replace(" | ", ": ")
            if s in boiler.get(oid, ()):
                dropped["site name only"] += 1
                continue
            if len(s.split()) < 3:
                dropped["too short"] += 1
                continue
            if DROP_TEXT.search(s) or POSTAL.search(s):
                dropped["non-news pattern"] += 1
                continue
            norm = re.sub(r"\W+", " ", s.lower()).strip()
            batch.append((id_, oid, pub, pub[:7], s, norm))
        flush()
        done += len(rows)
        print(f"  processed {done:,} rows", flush=True)

    print("\nStage 3 of 3: building indexes and flagging syndicated headlines "
          "(quiet for a few minutes)", flush=True)
    conn.executescript("""
        CREATE INDEX idx_clean_norm ON headlines_clean(norm, month);
        CREATE INDEX idx_clean_outlet_month ON headlines_clean(outlet_id, month);

        UPDATE headlines_clean SET is_syndicated = 1
        WHERE (norm, month) IN (
            SELECT norm, month FROM headlines_clean
            WHERE length(norm) >= 25
            GROUP BY norm, month
            HAVING COUNT(DISTINCT outlet_id) >= 2);

        DROP VIEW IF EXISTS outlet_quarter_coverage;
        CREATE VIEW outlet_quarter_coverage AS
        SELECT outlet_id,
               substr(published_at,1,4) || '-Q' ||
                   ((CAST(substr(published_at,6,2) AS INTEGER) + 2) / 3) AS quarter,
               COUNT(*) AS n
        FROM headlines_clean
        WHERE is_syndicated = 0
        GROUP BY 1, 2;
    """)
    conn.commit()

    kept, synd = conn.execute(
        "SELECT COUNT(*), SUM(is_syndicated) FROM headlines_clean").fetchone()
    print(f"\nDONE: kept {kept:,} headlines; {synd:,} flagged as syndicated")
    for reason, n in dropped.items():
        print(f"dropped ({reason}): {n:,}")


if __name__ == "__main__":
    main()