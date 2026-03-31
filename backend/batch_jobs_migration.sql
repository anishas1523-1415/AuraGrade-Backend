-- ============================================================
-- AuraGrade — In-Memory State Migration
-- Moves batch job tracking from process memory to Supabase
-- Run in Supabase SQL Editor
-- ============================================================

-- ── Table: batch_jobs ─────────────────────────────────────────────────────
-- Replaces the in-process _batch_jobs dict in main.py
-- Survives server restarts and works across multiple workers/containers

CREATE TABLE IF NOT EXISTS batch_jobs (
    id              TEXT PRIMARY KEY,              -- short UUID (12 chars)
    status          TEXT NOT NULL DEFAULT 'processing',
                    -- processing | completed | failed
    total_pages     INT NOT NULL DEFAULT 0,
    processed_pages INT NOT NULL DEFAULT 0,
    errors          JSONB DEFAULT '[]'::jsonb,
    results         JSONB DEFAULT '[]'::jsonb,     -- per-page grading results
    aggregated_result JSONB,                       -- final merged result
    detected_student  JSONB,                       -- header-parser auto-detect
    created_by      UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ DEFAULT (now() + INTERVAL '24 hours')
                    -- auto-cleanup: batch jobs older than 24h are stale
);

CREATE INDEX IF NOT EXISTS idx_batch_jobs_status    ON batch_jobs (status);
CREATE INDEX IF NOT EXISTS idx_batch_jobs_created   ON batch_jobs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_batch_jobs_expires   ON batch_jobs (expires_at);
CREATE INDEX IF NOT EXISTS idx_batch_jobs_created_by ON batch_jobs (created_by);

ALTER TABLE batch_jobs ENABLE ROW LEVEL SECURITY;

-- Users can only see their own batch jobs
CREATE POLICY "Users read own batch jobs" ON batch_jobs
  FOR SELECT USING (created_by = auth.uid());

-- Staff can see all batch jobs
CREATE POLICY "Staff read all batch jobs" ON batch_jobs
  FOR SELECT USING (
    auth.uid() IN (
      SELECT id FROM profiles
      WHERE role IN ('ADMIN_COE', 'HOD_AUDITOR', 'EVALUATOR')
    )
  );

-- Backend inserts/updates batch jobs
CREATE POLICY "Backend manage batch jobs" ON batch_jobs
  FOR ALL WITH CHECK (true);
  -- service_role key bypasses this anyway; policy is for documentation

-- ── Auto-cleanup: delete expired jobs ────────────────────────────────────
-- Schedule this via Supabase pg_cron or run daily as a maintenance query:
/*
DELETE FROM batch_jobs WHERE expires_at < now();
*/

-- Or add a pg_cron job (requires pg_cron extension in Supabase):
/*
SELECT cron.schedule(
  'cleanup-expired-batch-jobs',
  '0 3 * * *',   -- 3 AM daily
  $$ DELETE FROM batch_jobs WHERE expires_at < now() $$
);
*/


-- ── Usage notes for main.py migration ────────────────────────────────────
-- Replace:
--   _batch_jobs: dict = {}
-- With Supabase reads/writes in _process_batch_job() and get_batch_status()
--
-- Key changes needed in main.py:
--
-- 1. On job CREATE (in evaluate_batch):
--    supabase.table("batch_jobs").insert({
--        "id": job_id,
--        "status": "processing",
--        "total_pages": len(pages),
--        "created_by": current_user.get("id"),
--    }).execute()
--
-- 2. On page processed (in _process_batch_job):
--    supabase.table("batch_jobs").update({
--        "processed_pages": job.processed_pages,
--        "results": job.results,
--        "errors": job.errors,
--    }).eq("id", job_id).execute()
--
-- 3. On job COMPLETE:
--    supabase.table("batch_jobs").update({
--        "status": "completed",
--        "aggregated_result": job.aggregated_result,
--        "completed_at": datetime.now(timezone.utc).isoformat(),
--    }).eq("id", job_id).execute()
--
-- 4. In get_batch_status():
--    result = supabase.table("batch_jobs").select("*").eq("id", job_id).single().execute()
--    if not result.data:
--        raise HTTPException(404, "Batch job not found")
--    return result.data
