-- Reference DDL for Snowflake (OLAP). Run manually against a Snowflake account —
-- this is not executed automatically by any local service.
--
-- Pipeline: telemetry_raw (loaded from Kafka topics via Snowflake Kafka Connector)
--           -> 5-minute aggregation
--           -> device_summary_5m (what the Django dashboard API reads)

CREATE TABLE IF NOT EXISTS telemetry_raw (
    device_id       NUMBER,
    site            VARCHAR,
    recorded_at     TIMESTAMP_NTZ,
    temperature     FLOAT,
    humidity        FLOAT,
    ingested_at     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS device_summary_5m (
    window_start    TIMESTAMP_NTZ,
    site            VARCHAR,
    avg_temp        FLOAT,
    max_temp        FLOAT,
    alert_count     NUMBER,
    PRIMARY KEY (window_start, site)
);

-- Stream captures inserts on telemetry_raw since the last time the task consumed it.
CREATE STREAM IF NOT EXISTS telemetry_raw_stream ON TABLE telemetry_raw;

-- Scheduled task: runs every 5 minutes, rolls up new raw telemetry into the summary table.
CREATE TASK IF NOT EXISTS aggregate_device_summary_5m
    WAREHOUSE = COMPUTE_WH
    SCHEDULE = '5 MINUTE'
WHEN
    SYSTEM$STREAM_HAS_DATA('telemetry_raw_stream')
AS
    MERGE INTO device_summary_5m AS target
    USING (
        SELECT
            TIME_SLICE(recorded_at, 5, 'MINUTE') AS window_start,
            site,
            AVG(temperature) AS avg_temp,
            MAX(temperature) AS max_temp,
            0 AS alert_count
        FROM telemetry_raw_stream
        GROUP BY window_start, site
    ) AS source
    ON target.window_start = source.window_start AND target.site = source.site
    WHEN MATCHED THEN UPDATE SET
        avg_temp = source.avg_temp,
        max_temp = source.max_temp
    WHEN NOT MATCHED THEN INSERT (window_start, site, avg_temp, max_temp, alert_count)
        VALUES (source.window_start, source.site, source.avg_temp, source.max_temp, source.alert_count);

ALTER TASK aggregate_device_summary_5m RESUME;
