# Phase 13.91 — Report Publishing status clarity

Status: implemented locally; production deployment pending.

## Purpose

The Report Publishing admin page previously showed only materialization jobs. When there were no active jobs, the empty state could be misread as meaning there were no reports available. That ambiguity directly conflicts with the reporting simplification goal: operators should immediately know whether reports are available, pending, blocked, or merely not being reprocessed at the moment.

## Change

- Added a read-only admin summary endpoint at `/api/v1/admin/report-materialization-jobs/summary`.
- The summary reports active report counts by reporting status, the latest ready timestamp, recent job counts, and the five most recently updated materialization jobs.
- Updated the Report Publishing admin UI to show an explicit Active report library status card above the job list.
- Reworded the no-job empty state to say no publishing jobs are running, not that reports are missing.
- Added a direct link from the empty state to the report library.

## Non-goals

This change does not launch reprocessing, mutate analysis results, change report calculations, change source data, alter audit gates, change matching, call external providers, call PDP, call AI services, publish PDFs, or remove old surfaces.

## Verification

Pending local focused verification and CI after implementation.
