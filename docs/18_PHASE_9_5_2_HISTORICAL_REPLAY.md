# Phase 9.5.2 — Historical Import and Replay

## Status

Implemented. This is the acceptance and operating record for the Phase 9.5.2 checkpoint.

## Outcome

Live provider collections and supplied historical CSV files now share a first-class immutable
`analysis_input_set`. A historical import creates a zero-credit `collection_run` with
`trigger_type=historical_import`, links the source artifacts, and enqueues the existing leased
`analysis_run`. The analytics engine selects behavior by source format, never by product category.

No MetricsCart request occurs during validation, import, or replay.

## Pinned full-source manifests

| Manifest | Walmart | ALDI | Amazon | Total |
|---|---:|---:|---:|---:|
| Strawberries, August 7, 2026 | 192,681 | 37,940 | 66,822 | 297,443 |
| Ground beef, August 7, 2026 | 96,398 | 62,379 | 67,014 | 225,791 |

Every artifact entry records the original filename, retailer, historical adapter, source format,
content type, expected SHA-256, and expected data-row count. Profiling uses a real CSV parser, so
quoted fields and embedded newlines do not corrupt row counts.

## Import transaction

1. Validate the manifest contract and cross-field Product Pack/retailer invariants.
2. Resolve filenames beneath the explicit source root; reject traversal or missing files.
3. Stream each file to calculate SHA-256 and byte size, parse the header, and count data rows.
4. Reject the entire import if any checksum or count differs.
5. Build a canonical realized manifest without local filesystem paths and hash it.
6. Put each original file at a content-addressed bucket key using conditional create semantics.
7. Under a Postgres advisory lock, create or reuse the inactive definition version, zero-credit
   workflow run, input set, artifact links, and queued analysis job in one transaction.
8. Record `historical_input_imported` in the audit log.

Repeating steps 1–7 with identical bytes and configuration returns the existing input set,
collection run, and analysis run. An object-key collision with different bytes fails closed.

## Object layout

```text
raw/source=historical_import/
  input_manifest=<realized-manifest-sha256>/
    retailer_id=<retailer-id>/
      part=<zero-padded-ordinal>/
        <safe-source-name>-<source-sha-prefix>.csv
```

The bucket object contains the original CSV bytes. Store IDs, ZIPs, retailer product IDs, ASINs,
and other provider identifiers are therefore preserved exactly, including leading zeros.

## Commands

Validate the supplied files without database or bucket access:

```bash
uv run rci-import-historical \
  --manifest examples/historical-input-manifest.strawberries.json \
  --source-root /path/to/source/files \
  --validate-only
```

```bash
uv run rci-import-historical \
  --manifest examples/historical-input-manifest.ground-beef.json \
  --source-root /path/to/source/files \
  --validate-only
```

After migration `0010_analysis_input_sets` and with private Postgres/bucket variables available,
remove `--validate-only` to upload and enqueue. The command prints only non-secret IDs, checksums,
counts, and status.

`ANALYSIS_HISTORICAL_REPLAY_ENABLED` defaults to `false` during this checkpoint. This allows both
full input sets to reach the durable queue without a worker claiming them before Phase 9.5.3 adds
the full-source columnar execution and memory acceptance gate. Compact historical replay remains
covered by tests.

## Acceptance evidence

- Both full manifests validate against `historical-input-manifest.schema.json` in Python and AJV.
- The six attached source files match their pinned SHA-256 values and sum to 523,234 rows.
- Unit tests prove immutable byte retention, leading-zero preservation, checksum/count rejection,
  idempotent replay identity, and traversal-safe source resolution.
- A worker test replays historical CSV rows through the same Product Pack normalizer, classifier,
  matcher, Parquet writer, result publisher, and artifact generator as live inputs.
- The optional Postgres integration verifies one input set, one artifact link, one analysis job, and
  a claim exposing `source_kind=historical_import`.
- Migration upgrade SQL is generated through `0010_analysis_input_sets` and downgrade is defined.

Phase 9.5.3 remains responsible for the ground-beef Product Pack and full golden analytical parity.
