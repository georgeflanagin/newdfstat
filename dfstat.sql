DROP TABLE IF EXISTS stats;
DROP TABLE IF EXISTS konstants;
DROP TABLE IF EXISTS filldates;

-- Keep this stuff in here rather than in a config file.
CREATE TABLE konstants (
    id INTEGER PRIMARY KEY CHECK (id=1),
    recent_days INTEGER NOT NULL CHECK (recent_days BETWEEN 1 AND 30),
    sample_rate INTEGER NOT NULL CHECK (sample_rate BETWEEN 3 AND 30),
    kpss_level REAL NOT NULL CHECK (kpss_level BETWEEN 0.45 AND 0.50),
    kpss_trend REAL NOT NULL CHECK (kpss_trend BETWEEN 0.14 AND 0.15),
    min_samples INTEGER NOT NULL CHECK (min_samples BETWEEN 24 AND 760),
    alert_threshold REAL NOT NULL CHECK (alert_threshold BETWEEN 0.5 AND 0.9),
    remote_command TEXT NOT NULL,
    remote_file TEXT NOT NULL
    ) WITHOUT ROWID;


-- Sane values if we are building the database.
INSERT INTO konstants (id, recent_days, sample_rate,
    kpss_level, kpss_trend, min_samples, alert_threshold,
    remote_command, remote_file)
    VALUES (1, 7, 5, 0.45, 0.142, 24, 0.8,
    'python3.12 dfstub.py', '/tmp/dfdata');

CREATE TABLE IF NOT EXISTS logins (
    login TEXT PRIMARY KEY
    );

INSERT INTO logins (login) VALUES
    ('root@aamy'),
    ('root@adam'),
    ('root@alexis'),
    ('root@boyi'),
    ('root@camryn'),
    ('root@cooper'),
    ('root@evan'),
    ('root@hamilton'),
    ('root@irene2'),
    ('root@josh'),
    ('root@justin'),
    ('root@kevin'),
    ('root@khanh'),
    ('root@mayer'),
    ('root@michael'),
    ('root@sarah'),
    ('root@thais'),
    ('installer@spydur'),
    ('installer@spiderweb'),
    ('zeus@arachne'),
    ('root@sarahvaughan'),
    ('root@natkingcole'),
    ('root@franksinatra'),
    ('root@trueuser');


CREATE TABLE IF NOT EXISTS filldates (
    host TEXT NOT NULL,
    mountpoint TEXT NOT NULL,
    filldate DATETIME DEFAULT NULL,
    measured_on DATETIME DEFAULT CURRENT_TIMESTAMP
    );

CREATE INDEX idx_filldate on filldates(host, mountpoint);


CREATE VIEW IF NOT EXISTS filldates_view AS
    SELECT * FROM filldates ORDER BY host, mountpoint, measured_on;


-- Straightforward fact table.
CREATE TABLE IF NOT EXISTS stats (
    host TEXT,
    mountpoint TEXT,
    total INTEGER DEFAULT NULL CHECK (total > 0),
    used INTEGER DEFAULT NULL CHECK (used >= 0 AND used <= total),
    free INTEGER GENERATED ALWAYS AS (total - used) VIRTUAL,
    time DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (host, mountpoint, time)
    ) WITHOUT ROWID;


-- Just one compound index.
CREATE INDEX idx_time on stats(host, mountpoint, time);

-- Recent readings base on the value in the database.
CREATE VIEW IF NOT EXISTS recent_stats AS
    SELECT s.* FROM stats AS s
        WHERE s.time >= datetime('now',
            printf('-%d days', (SELECT recent_days FROM konstants WHERE id=1))
    );

CREATE VIEW IF NOT EXISTS old_stats AS
    SELECT s.* FROM stats AS s
        WHERE s.time < datetime('now',
            printf('-%d days', (SELECT recent_days FROM konstants WHERE id=1))
    );

CREATE TRIGGER IF NOT EXISTS delete_trigger
    INSTEAD OF DELETE ON old_stats
        BEGIN
            DELETE FROM stats
            WHERE time IN (
                SELECT time from old_stats
                );
        END;

-- Rollup of recent data to provide a summary.
CREATE VIEW IF NOT EXISTS recent_usage AS SELECT
    host,
    mountpoint,
    COUNT(*)                            AS n_samples,
    MIN(time)                           AS first_sample,
    MAX(time)                           AS last_sample,
    AVG(used * 1.0 / total)             AS avg_utilization,
    MAX(used * 1.0 / total)             AS peak_utilization,
    MIN(free * 1.0 / total)             AS min_free_pct
        FROM recent_stats
            GROUP BY host, mountpoint;

-- Check completeness. This will keep the Python code from
-- blowing up from bad data. This view summarizes the completeness.
CREATE VIEW IF NOT EXISTS recent_coverage AS
    WITH k AS (SELECT sample_rate, min_samples FROM konstants WHERE id=1),
        u AS (SELECT * FROM recent_usage)
    SELECT
        u.host,
        u.mountpoint,
        u.n_samples,
        u.first_sample,
        u.last_sample,
  -- Expected count = elapsed_minutes / cadence + 1
  ( (julianday(u.last_sample) - julianday(u.first_sample)) * 1440.0
      / (SELECT sample_rate FROM k) + 1.0 )        AS expected_samples,
  u.n_samples * 1.0 /
  ( (julianday(u.last_sample) - julianday(u.first_sample)) * 1440.0
      / (SELECT sample_rate FROM k) + 1.0 )        AS sample_ratio,
        CASE
            WHEN u.n_samples >= (SELECT min_samples FROM k) THEN 1 ELSE 0
        END
        AS has_min_samples
    FROM u;

-- And this view selects which ones are worth analyzing.
CREATE VIEW IF NOT EXISTS eligible_series AS
    SELECT * FROM recent_coverage
        WHERE has_min_samples = 1 AND sample_ratio >= 0.60;


-- What's bad right now? This view collects the data.
CREATE VIEW IF NOT EXISTS current_latest AS
    WITH latest AS (
        SELECT s.* FROM stats s
            JOIN (SELECT host, mountpoint, MAX(time) AS max_t FROM stats
                GROUP BY host, mountpoint ) m
                    ON s.host=m.host AND
                        s.mountpoint=m.mountpoint AND
                        s.time=m.max_t )
    SELECT host, mountpoint, time AS last_time,
            used * 1.0 / total AS utilization,
            free * 1.0 / total AS free_pct
        FROM latest;

-- And these are the ones that are over the limits.
CREATE VIEW IF NOT EXISTS alerts AS
    SELECT c.host, c.mountpoint, c.last_time, c.utilization, c.free_pct,
        (SELECT alert_threshold FROM konstants WHERE id=1) AS threshold
    FROM current_latest c
        WHERE c.utilization >= (SELECT threshold FROM konstants WHERE id=1)
    ORDER BY c.utilization DESC, c.free_pct ASC;



