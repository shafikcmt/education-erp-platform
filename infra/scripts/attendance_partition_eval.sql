-- Phase 8 M7 (ADR-080): partition evaluation for attendance_record.
--
-- Run against a THROWAWAY database only (never a real one), as a superuser:
--   createdb erp_partition_eval && psql -d erp_partition_eval -f attendance_partition_eval.sql
-- It builds two copies of the attendance_record shape with ~5M generated rows (50 tenants x
-- 2 000 students x 50 school days), one plain and one range-partitioned by month on "date",
-- with the production indexes and the standard tenant RLS policy, then times the report
-- queries as a non-owner, NOBYPASSRLS role with the transaction-scoped tenant setting.
-- No real data is read or written.

\timing on
SET client_min_messages = warning;

DROP ROLE IF EXISTS eval_app;
CREATE ROLE eval_app NOLOGIN NOBYPASSRLS;

-- ------------------------------------------------------------------ generated source rows
CREATE TABLE src AS
SELECT
    md5('t' || t)::uuid                                   AS tenant_id,
    md5('i' || t)::uuid                                   AS institution_id,
    md5('s' || t || '-' || s)::uuid                       AS student_id,
    md5('r' || t || '-' || (s / 40) || '-' || d)::uuid    AS register_id,
    (date '2026-01-04' + (d * 7 / 5) + (d % 5))           AS date,
    (ARRAY['present','present','present','present','present','present','present','late',
           'absent','leave'])[1 + ((s * 7 + d * 13) % 10)] AS status
FROM generate_series(1, 50) t, generate_series(0, 1999) s, generate_series(0, 49) d;

-- ------------------------------------------------------------------ plain table (today)
CREATE TABLE rec (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL, institution_id uuid NOT NULL, register_id uuid NOT NULL,
    student_id uuid NOT NULL, date date NOT NULL, status varchar(16) NOT NULL,
    late_minutes smallint, remark varchar(160) NOT NULL DEFAULT ''
);
INSERT INTO rec (tenant_id, institution_id, register_id, student_id, date, status)
SELECT tenant_id, institution_id, register_id, student_id, date, status FROM src;
CREATE UNIQUE INDEX rec_unique ON rec (tenant_id, register_id, student_id);
CREATE INDEX rec_student_date ON rec (tenant_id, student_id, date);
CREATE INDEX rec_inst_date ON rec (tenant_id, institution_id, date);

-- ------------------------------------------------------------------ partitioned (candidate)
CREATE TABLE rec_p (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL, institution_id uuid NOT NULL, register_id uuid NOT NULL,
    student_id uuid NOT NULL, date date NOT NULL, status varchar(16) NOT NULL,
    late_minutes smallint, remark varchar(160) NOT NULL DEFAULT '',
    PRIMARY KEY (id, date)
) PARTITION BY RANGE (date);
CREATE TABLE rec_p_2026_01 PARTITION OF rec_p FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE rec_p_2026_02 PARTITION OF rec_p FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
CREATE TABLE rec_p_2026_03 PARTITION OF rec_p FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
CREATE TABLE rec_p_2026_04 PARTITION OF rec_p FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
INSERT INTO rec_p (tenant_id, institution_id, register_id, student_id, date, status)
SELECT tenant_id, institution_id, register_id, student_id, date, status FROM src;
-- A unique key on a partitioned table must include the partition key.
CREATE UNIQUE INDEX rec_p_unique ON rec_p (tenant_id, register_id, student_id, date);
CREATE INDEX rec_p_student_date ON rec_p (tenant_id, student_id, date);
CREATE INDEX rec_p_inst_date ON rec_p (tenant_id, institution_id, date);

DROP TABLE src;
ANALYZE rec;
ANALYZE rec_p;

-- ------------------------------------------------------------------ standard tenant RLS
ALTER TABLE rec ENABLE ROW LEVEL SECURITY;
ALTER TABLE rec FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_rec ON rec USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
ALTER TABLE rec_p ENABLE ROW LEVEL SECURITY;
ALTER TABLE rec_p FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_rec_p ON rec_p
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
GRANT SELECT ON rec, rec_p TO eval_app;

SELECT 'rec' AS t, count(*) AS rows, pg_size_pretty(pg_total_relation_size('rec')) AS size
FROM rec
UNION ALL
SELECT 'rec_p', count(*), pg_size_pretty(pg_total_relation_size('rec_p')) FROM rec_p;

-- ------------------------------------------------------------------ the report queries
-- Tenant 7, institution 7, student 7-123 (unit 3 = students 120..159).
BEGIN;
SET LOCAL ROLE eval_app;
SELECT set_config('app.tenant_id', md5('t7')::uuid::text, true);

\echo Q1 portal month (one student, one month)
EXPLAIN (ANALYZE, BUFFERS, SUMMARY ON, COSTS OFF)
SELECT date, status FROM rec
WHERE student_id = md5('s7-123')::uuid AND date >= '2026-03-01' AND date <= '2026-03-31';
EXPLAIN (ANALYZE, BUFFERS, SUMMARY ON, COSTS OFF)
SELECT date, status FROM rec_p
WHERE student_id = md5('s7-123')::uuid AND date >= '2026-03-01' AND date <= '2026-03-31';

\echo Q2 unit summary (40 students, whole range)
EXPLAIN (ANALYZE, BUFFERS, SUMMARY ON, COSTS OFF)
SELECT student_id, status, count(*) FROM rec
WHERE student_id IN (SELECT md5('s7-' || s)::uuid FROM generate_series(120, 159) s)
  AND date >= '2026-01-01' AND date <= '2026-04-30'
GROUP BY student_id, status;
EXPLAIN (ANALYZE, BUFFERS, SUMMARY ON, COSTS OFF)
SELECT student_id, status, count(*) FROM rec_p
WHERE student_id IN (SELECT md5('s7-' || s)::uuid FROM generate_series(120, 159) s)
  AND date >= '2026-01-01' AND date <= '2026-04-30'
GROUP BY student_id, status;

\echo Q3 institution day (daily status)
EXPLAIN (ANALYZE, BUFFERS, SUMMARY ON, COSTS OFF)
SELECT status, count(*) FROM rec
WHERE institution_id = md5('i7')::uuid AND date = '2026-02-10' GROUP BY status;
EXPLAIN (ANALYZE, BUFFERS, SUMMARY ON, COSTS OFF)
SELECT status, count(*) FROM rec_p
WHERE institution_id = md5('i7')::uuid AND date = '2026-02-10' GROUP BY status;

\echo Q4 institution month (2 000 students x one month)
EXPLAIN (ANALYZE, BUFFERS, SUMMARY ON, COSTS OFF)
SELECT student_id, status, count(*) FROM rec
WHERE institution_id = md5('i7')::uuid AND date >= '2026-02-01' AND date < '2026-03-01'
GROUP BY student_id, status;
EXPLAIN (ANALYZE, BUFFERS, SUMMARY ON, COSTS OFF)
SELECT student_id, status, count(*) FROM rec_p
WHERE institution_id = md5('i7')::uuid AND date >= '2026-02-01' AND date < '2026-03-01'
GROUP BY student_id, status;

\echo RLS check: rows visible to tenant 7 (expect 100000)
SELECT count(*) FROM rec;
COMMIT;
