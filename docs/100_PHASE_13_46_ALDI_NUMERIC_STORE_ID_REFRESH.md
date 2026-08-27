# Phase 13.46 — ALDI Numeric Store-ID Refresh

## Outcome

The owner-supplied MetricsCart ALDI location export dated 2026-08-27 replaces the prior ALDI
current-location roster. The new file changes the provider-facing `Store_No` values from legacy
district-style identifiers such as `463-048` to numeric identifiers such as `24469`. Search and PDP
requests must use the new `Store_No` together with that store's normalized ZIP. The
`mc_location_id` remains separate lineage and is not substituted into the API `store` parameter.

No MetricsCart Search or PDP request was made during this roster refresh. Whether the numeric IDs
resolve the prior billable 404 responses must be established by a separately scoped, approved
preflight after the production location import is verified.

## Source profile

- Source: `fixtures/location_master/retailer_updates/aldi-locations-2026-08-27.csv`
- SHA-256: `fc36bd75740776cbb6ee47732b26f634ffb1ed107333d4a30accd8aa0687ee9d`
- 2,687 rows, 2,687 unique numeric `Store_No` values, and 2,687 unique `mc_location_id` values
- 41 state or district abbreviations and 2,550 normalized five-digit ZIPs
- all rows are `active`, `USA`, and provider `ALDI`
- zero missing required identifiers, ZIPs, cities, states, coordinates, addresses, or provider IDs
- zero duplicate normalized street/city/state/ZIP locations and zero duplicate coordinates at five
  decimal places
- 150 source ZIPs begin with zero and remain strings throughout import and request planning

The canonical master now contains 157,866 rows: the former 2,627-row ALDI slice is replaced by the
2,687-row source while every non-ALDI row remains unchanged.

## Control-location reconciliation

The new export changes the provider-facing identifier while retaining the same physical store and
ZIP for the former diagnostic controls:

| Prior Store_No | New Store_No | ZIP | Physical location |
| --- | --- | --- | --- |
| `463-048` | `24469` | `44906` | Ontario, Ohio |
| `479-098` | `24681` | `93215` | Delano, California |
| `474-031` | `24079` | `33809` | Lakeland, Florida |
| `468-051` | `24597` | `61764` | Pontiac, Illinois |
| `461-002` | `24030` | `43015` | Delaware, Ohio |
| `469-066` | `32124` | `17009` | Burnham, Pennsylvania |
| `482-033` | `177620` | `32548` | Fort Walton Beach, Florida |

Nearest-coordinate reconciliation places 2,563 of the 2,627 prior stores within 0.25 miles of a
new-roster store and 2,590 within 0.5 miles. The new source also contains 60 more rows and adds the
District of Columbia. It is therefore an authoritative current roster, not a safe in-place ID
mapping for historical observations. Historical collection geography snapshots and provider
evidence retain their original identifiers.

## Authoritative replacement behavior

The location importer now accepts the provider-native 13-column export without requiring empty
legacy metadata columns. An explicit repeatable `--authoritative-retailer` option performs a safe
current-dimension replacement:

1. every valid source row is upserted and tied to the new checksummed import;
2. an authoritative refresh is rejected if the requested retailer is absent or any row was
   skipped;
3. older locations for only the named retailer remain stored for audit but become `superseded`,
   collection-ineligible, and labeled `superseded_by_authoritative_import`;
4. other retailers and immutable historical geography snapshots are not changed.

The ALDI catalog eligibility rule now admits numeric Store IDs and rejects legacy hyphenated IDs,
preventing both identifier generations from entering a new collection estimate.

## Verification

- The source, canonical fixture, profile, cost-estimate example, and handoff validators agree on
  2,687 current ALDI locations.
- Location import, collection planning, geography, API location, and contract tests pass.
- The authoritative replacement regression proves that the legacy ALDI ID is retained but retired,
  the numeric replacement is eligible, and a Walmart control remains eligible.
- Ruff formatting/lint and repository-wide Python type checking pass.
- Commit `9a73da8` deployed successfully to all four Railway application services. GitHub Actions
  run `33107649907` passed the complete Python, TypeScript, browser, migration, contract, and
  service-container release gate.
- Production import `f7182e06-1a40-498d-b6d8-4b5b4e651cab` imported all 2,687 rows with zero
  skips and the expected source checksum. Post-import reconciliation found 2,687 eligible numeric
  ALDI IDs, zero eligible legacy hyphenated IDs, 2,687 unique eligible provider location IDs, 2,550
  eligible ZIPs, and all 2,627 prior IDs preserved as superseded.
- No paid provider preflight is implied by this import verification. Search/PDP callability remains
  a separate fact that should be tested under an explicit bounded scope.
