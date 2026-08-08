-- Reference pattern: claim pending tasks safely across worker replicas.
WITH candidates AS (
  SELECT id
  FROM collection_task
  WHERE status = 'pending'
    AND available_at <= now()
    AND (lease_expires_at IS NULL OR lease_expires_at < now())
  ORDER BY priority ASC, created_at ASC
  FOR UPDATE SKIP LOCKED
  LIMIT :claim_limit
)
UPDATE collection_task t
SET status='running',
    locked_by=:worker_id,
    locked_at=now(),
    lease_expires_at=now() + (:lease_seconds || ' seconds')::interval,
    attempt_count=t.attempt_count+1
FROM candidates c
WHERE t.id=c.id
RETURNING t.*;
