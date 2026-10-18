"""Pull CBC's North coverage out of the main CBC feed so the territories get their own outlet, "cbcnorth".

Step 1 (safe, changes nothing):   python split_cbc_north.py
   Prints how many CBC North headlines you have per quarter, plus a few examples.
Step 2 (after you add the cbcnorth row to outlets.csv):   python split_cbc_north.py --apply
   Moves those headlines from "cbc" to "cbcnorth". Run it again any time new CBC headlines have been collected.

CBC North stories mostly live under /news/canada/north/ in the web address. Some North stories
are filed under plain /news/canada/ instead, so this finds most of the history but not all of it.
(The live RSS feed for North, added in outlets.csv, catches everything from now on.)
"""
import sys

from db import connect, sync_outlets

PATTERN = "%/news/canada/north/%"
QUARTER = "substr(published_at,1,4) || '-Q' || ((cast(substr(published_at,6,2) as integer) + 2) / 3)"


def main():
    apply = "--apply" in sys.argv
    conn = connect()
    sync_outlets(conn)
    have = conn.execute("SELECT 1 FROM outlets WHERE outlet_id='cbcnorth'").fetchone()
    rows = conn.execute(
        f"SELECT {QUARTER} AS q, count(*) FROM headlines "
        "WHERE outlet_id='cbc' AND url LIKE ? GROUP BY q ORDER BY q", (PATTERN,)).fetchall()
    already = conn.execute("SELECT count(*) FROM headlines WHERE outlet_id='cbcnorth'").fetchone()[0]
    total_cbc = conn.execute("SELECT count(*) FROM headlines WHERE outlet_id='cbc'").fetchone()[0]
    n = sum(c for _, c in rows)
    print(f"CBC headlines in total: {total_cbc:,}.  With /news/canada/north/ in the address: {n:,}.  Already moved: {already:,}\n")
    print("quarter    North headlines")
    for q, c in rows:
        print(f"{q}   {c:6,d}   {'#' * min(60, c // 20)}")
    print("\nA few examples:")
    for h, u in conn.execute("SELECT headline, url FROM headlines WHERE outlet_id='cbc' AND url LIKE ? "
                             "ORDER BY random() LIMIT 6", (PATTERN,)):
        print(f"  {h}\n    {u}")
    if not apply:
        print("\nNothing was changed. Add the cbcnorth row to outlets.csv, then run: python split_cbc_north.py --apply")
        return
    if not have:
        sys.exit("\nThere is no cbcnorth row in outlets.csv yet. Add it, then run this again with --apply.")
    cur = conn.execute("UPDATE headlines SET outlet_id='cbcnorth' WHERE outlet_id='cbc' AND url LIKE ?", (PATTERN,))
    conn.commit()
    print(f"\nMoved {cur.rowcount:,} headlines to cbcnorth. Now rerun: python clean.py")


if __name__ == "__main__":
    main()