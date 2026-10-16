"""Shared helpers: open the database, load outlets.csv into it."""
import csv
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "headlines.db"


def connect(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.executescript((HERE / "schema.sql").read_text())
    return conn


def sync_outlets(conn, csv_path=HERE / "outlets.csv"):
    """Upsert outlets.csv into the outlets table. The CSV is the source of truth,
    so edit leanings there, not in the database."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row = {k: (v.strip() or None) for k, v in row.items()}
            conn.execute(
                """INSERT INTO outlets (outlet_id, name, domain, home_province, scope,
                                        language, leaning, leaning_checked_on, rss_url, notes)
                   VALUES (:outlet_id, :name, :domain, :home_province, :scope,
                           :language, :leaning, :leaning_checked_on, :rss_url, :notes)
                   ON CONFLICT(outlet_id) DO UPDATE SET
                       name=excluded.name, domain=excluded.domain,
                       home_province=excluded.home_province, scope=excluded.scope,
                       language=excluded.language, leaning=excluded.leaning,
                       leaning_checked_on=excluded.leaning_checked_on,
                       rss_url=excluded.rss_url, notes=excluded.notes""",
                row,
            )
    conn.commit()