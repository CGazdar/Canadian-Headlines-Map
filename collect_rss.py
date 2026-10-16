"""Collect current headlines from each outlet's RSS feed into headlines.db."""
import time
from datetime import datetime, timezone

import feedparser

from db import connect, sync_outlets

WIRE_MARKERS = ("canadian press", "the associated press", "reuters", "the canadian press")
USER_AGENT = "headline-research-bot/0.1 (personal research project)"
PAUSE_SECONDS = 2  # be polite between feeds


def entry_time(entry):
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t:
        return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def looks_like_wire(entry):
    blob = " ".join(
        str(entry.get(k, "")) for k in ("author", "source", "summary")
    ).lower()
    return int(any(m in blob for m in WIRE_MARKERS))


def main():
    conn = connect()
    sync_outlets(conn)
    outlets = conn.execute(
        "SELECT outlet_id, name, rss_url FROM outlets WHERE rss_url IS NOT NULL"
    ).fetchall()
    now = datetime.now(timezone.utc).isoformat()

    for outlet_id, name, rss_url in outlets:
        feed = feedparser.parse(rss_url, agent=USER_AGENT)
        if feed.bozo and not feed.entries:
            print(f"[skip] {name}: could not read feed ({feed.get('bozo_exception')})")
            continue
        new = 0
        for e in feed.entries:
            title, link = e.get("title", "").strip(), e.get("link", "").strip()
            if not title or not link:
                continue
            cur = conn.execute(
                """INSERT OR IGNORE INTO headlines
                   (outlet_id, headline, url, published_at, fetched_at, source, is_wire)
                   VALUES (?, ?, ?, ?, ?, 'rss', ?)""",
                (outlet_id, title, link, entry_time(e), now, looks_like_wire(e)),
            )
            new += cur.rowcount
        conn.commit()
        print(f"[ok]   {name}: {new} new of {len(feed.entries)}")
        time.sleep(PAUSE_SECONDS)


if __name__ == "__main__":
    main()