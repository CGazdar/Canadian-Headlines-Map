"""Backfill headlines from GDELT's Global Knowledge Graph (GKG) via BigQuery."""
import argparse
from datetime import date, datetime, timezone

from google.cloud import bigquery

from db import connect, sync_outlets

# Verify this table name and its partitioning in the BigQuery console before running.
TABLE = "`gdelt-bq.gdeltv2.gkg_partitioned`"

QUERY = f"""
SELECT
  DATE AS gdelt_date,
  SourceCommonName AS domain,
  DocumentIdentifier AS url,
  REGEXP_EXTRACT(Extras, r'<PAGE_TITLE>(.*?)</PAGE_TITLE>') AS title
FROM {TABLE}
WHERE _PARTITIONTIME >= TIMESTAMP(@start)
  AND _PARTITIONTIME <  TIMESTAMP(@end)
  AND SourceCommonName IN UNNEST(@domains)
  AND REGEXP_CONTAINS(Extras, r'<PAGE_TITLE>')
"""


def month_ranges(start: str, end: str):
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    y, m = sy, sm
    while (y, m) <= (ey, em):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        yield date(y, m, 1), date(ny, nm, 1)
        y, m = ny, nm


def parse_gdelt_date(n) -> str:
    return datetime.strptime(str(n), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="YYYY-MM")
    ap.add_argument("--end", required=True, help="YYYY-MM (inclusive)")
    ap.add_argument("--dry-run", action="store_true", help="estimate bytes scanned only")
    args = ap.parse_args()

    conn = connect()
    sync_outlets(conn)
    domain_to_outlet = dict(conn.execute("SELECT domain, outlet_id FROM outlets").fetchall())
    client = bigquery.Client()
    now = datetime.now(timezone.utc).isoformat()
    total_bytes = 0

    for m_start, m_end in month_ranges(args.start, args.end):
        job_config = bigquery.QueryJobConfig(
            dry_run=args.dry_run,
            use_query_cache=False,
            query_parameters=[
                bigquery.ScalarQueryParameter("start", "STRING", m_start.isoformat()),
                bigquery.ScalarQueryParameter("end", "STRING", m_end.isoformat()),
                bigquery.ArrayQueryParameter("domains", "STRING", list(domain_to_outlet)),
            ],
        )
        job = client.query(QUERY, job_config=job_config)

        if args.dry_run:
            gb = job.total_bytes_processed / 1e9
            total_bytes += job.total_bytes_processed
            print(f"{m_start:%Y-%m}: ~{gb:,.1f} GB")
            continue

        new = 0
        for row in job.result():
            title = (row.title or "").strip()
            outlet_id = domain_to_outlet.get(row.domain)
            if not title or not outlet_id:
                continue
            cur = conn.execute(
                """INSERT OR IGNORE INTO headlines
                   (outlet_id, headline, url, published_at, fetched_at, source, is_wire)
                   VALUES (?, ?, ?, ?, ?, 'gdelt', 0)""",
                (outlet_id, title, row.url, parse_gdelt_date(row.gdelt_date), now),
            )
            new += cur.rowcount
        conn.commit()
        print(f"{m_start:%Y-%m}: {new} new headlines")

    if args.dry_run:
        print(f"\nTotal estimated scan: ~{total_bytes / 1e12:,.2f} TB "
              f"(BigQuery's free tier is 1 TB/month; check current on-demand pricing)")


if __name__ == "__main__":
    main()