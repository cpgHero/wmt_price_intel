-- Run this exact read-only reconciliation against production and an isolated
-- restored database, capture both outputs, and require a byte-for-byte diff.
-- Additive schema changes must extend this list before the next restore drill.
\set ON_ERROR_STOP on

begin transaction read only;

select 'migration', version_num from alembic_version;
select 'organization', count(*)::text from organization;
select 'retailer', count(*)::text from retailer;
select 'retailer_location', count(*)::text from retailer_location;
select 'location_import_run', count(*)::text from location_import_run;
select 'collection_definition', count(*)::text from collection_definition;
select 'collection_run', count(*)::text from collection_run;
select 'collection_task', count(*)::text from collection_task;
select 'dataset_artifact', count(*)::text from dataset_artifact;
select 'analysis_run', count(*)::text from analysis_run;
select 'analysis_result', count(*)::text from analysis_result;
select 'analysis_publication', count(*)::text from analysis_publication;
select 'report_artifact', count(*)::text from report_artifact;
select 'report_materialization_job', count(*)::text from report_materialization_job;
select 'product_detail_snapshot', count(*)::text from product_detail_snapshot;
select 'matching_v2_review_case', count(*)::text from matching_v2_review_case;
select 'matching_v2_review_submission', count(*)::text from matching_v2_review_submission;
select 'price_intelligence_snapshot', count(*)::text from price_intelligence_snapshot;
select 'competitive_portfolio_materialization', count(*)::text from competitive_portfolio_materialization;
select 'audit_event', count(*)::text from audit_event;

commit;
