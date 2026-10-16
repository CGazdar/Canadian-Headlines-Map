-- Headline tracker schema (SQLite)

CREATE TABLE IF NOT EXISTS outlets (
    outlet_id           TEXT PRIMARY KEY,   -- short slug, e.g. 'cbc'
    name                TEXT NOT NULL,
    domain              TEXT NOT NULL UNIQUE, -- as GDELT reports it (SourceCommonName), no 'www.'
    home_province       TEXT NOT NULL,      -- BC AB SK MB ON QC NB NS PE NL YT NT NU, or 'national'
    scope               TEXT NOT NULL,      -- 'national' | 'provincial' | 'local'
    language            TEXT NOT NULL DEFAULT 'en',
    leaning             TEXT,               -- 'left' | 'lean_left' | 'center' | 'lean_right' | 'right' | NULL = undecided
    leaning_checked_on  TEXT,               -- date you read the Ground News rating (YYYY-MM-DD)
    rss_url             TEXT,               -- blank = no RSS collection for this outlet
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS headlines (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    outlet_id    TEXT NOT NULL REFERENCES outlets(outlet_id),
    headline     TEXT NOT NULL,
    url          TEXT NOT NULL UNIQUE,      -- dedupe key
    published_at TEXT NOT NULL,             -- ISO 8601, UTC
    fetched_at   TEXT NOT NULL,             -- ISO 8601, UTC
    source       TEXT NOT NULL,             -- 'rss' | 'gdelt'
    is_wire      INTEGER NOT NULL DEFAULT 0 -- 1 = Canadian Press / Reuters / AP copy, exclude from lean analysis
);

CREATE INDEX IF NOT EXISTS idx_headlines_outlet_time ON headlines(outlet_id, published_at);
CREATE INDEX IF NOT EXISTS idx_headlines_time ON headlines(published_at);