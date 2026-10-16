"""Write sections.csv: one row per outlet + URL section, with a default keep guess.
Open it, edit the 'keep' column (1 = use in the analysis, 0 = ignore), and save.
Safe to rerun: your earlier choices are kept; only new sections get default guesses.
Run after clean.py. Usage: python make_section_config.py
"""
import collections
import csv
from urllib.parse import urlparse

from db import HERE, connect

MIN_COUNT = 200
LIKELY_KEEP = {"news", "local", "canada", "national", "politics", "opinion", "editorial",
               "comment", "commentary", "columnists", "letters", "province", "provincial"}
NEWS_EXCLUDE = {"world", "sports", "entertainment", "business", "health", "science",
                "technology", "life", "lifestyle", "arts", "travel", "weather", "offbeat"}


def section_key(url):
    parts = [p for p in urlparse(url).path.split("/") if p]
    if not parts:
        return "(root)"
    # e.g. cbc.ca/news/politics/... -> "news/politics". A number in second place (an
    # article id or a year, as at globalnews.ca/news/6789012/...) is not a section.
    if parts[0].lower() == "news" and len(parts) > 1 and not parts[1].isdigit():
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def default_keep(key):
    key = key.lower()
    if key.startswith("news/"):
        return key[5:] not in NEWS_EXCLUDE
    return key in LIKELY_KEEP


def main():
    conn = connect()
    counts = collections.defaultdict(collections.Counter)
    for oid, url in conn.execute(
            "SELECT c.outlet_id, h.url FROM headlines_clean c JOIN headlines h USING (id)"):
        counts[oid][section_key(url)] += 1

    out = HERE / "sections.csv"
    previous = {}                      # your earlier choices are kept on a rerun
    if out.exists():
        with open(out, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                previous[(r["outlet_id"], r["section"])] = r["keep"].strip()

    reused = new = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["outlet_id", "section", "headlines", "keep"])
        for oid in sorted(counts):
            for key, n in counts[oid].most_common():
                if n < MIN_COUNT:
                    continue
                if (oid, key) in previous:
                    keep = previous[(oid, key)]
                    reused += 1
                else:
                    keep = 1 if default_keep(key) else 0
                    new += 1
                w.writerow([oid, key, n, keep])
    print(f"wrote {out}: kept {reused} earlier choices, added {new} new rows")


if __name__ == "__main__":
    main()