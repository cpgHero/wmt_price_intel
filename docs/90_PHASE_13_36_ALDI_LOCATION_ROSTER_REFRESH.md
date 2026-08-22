# Phase 13.36 — ALDI Location Roster Refresh

## Outcome

The owner-supplied MetricsCart ALDI location export dated 2026-08-22 was profiled, reconciled to
the canonical location master, retained as a versioned source fixture, and imported through the
existing idempotent location-master workflow. No MetricsCart Search or PDP call was made.

The roster is structurally complete at its declared grain of one MetricsCart ALDI row per
`Store_No`: 2,627 rows, 2,627 unique store numbers, 2,627 unique MetricsCart location IDs, 40
states, 2,499 normalized ZIPs, all rows marked `active` and `USA`, and no missing store number, ZIP,
city, state, coordinate, or MetricsCart location ID. Its source SHA-256 is
`6ee18a8a5679d085697253e280620e0120b2f3a48467b5af501acee82947fee6`.

## Reconciliation to the prior canonical roster

The refresh does **not** change ALDI's physical store universe:

- all 2,627 prior store-number identities remain present;
- no store was added or removed;
- names, addresses, cities, states, coordinates, countries, and statuses are unchanged;
- 79 raw ZIP representations changed, but all normalize to the same five-digit ZIPs as before;
- the same 79 rows received new MetricsCart `mc_location_id` values;
- those identity corrections are limited to Connecticut (21), Massachusetts (10), New Hampshire
  (3), New Jersey (38), Rhode Island (5), and Vermont (2);
- all 2,627 source timestamps changed to the new roster-generation timestamp.

The canonical full location fixture now contains the refreshed ALDI rows, and the unmodified
retailer-specific source is retained at
`fixtures/location_master/retailer_updates/aldi-locations-2026-08-22.csv`. Store numbers,
MetricsCart IDs, raw ZIPs, and normalized ZIPs remain strings.

## Data-quality exception

The source contains eleven pairs of different active store numbers at the exact same address and
coordinates, all in North Carolina. They appear to be district/store-number transitions between
`466-*` and `480-*` identifiers. The source itself marks both members active, so the application
does not guess which identifier is authoritative. These collisions must remain visible as a
location-governance exception before a large all-ALDI collection is approved; silently deleting one
could select the wrong API store identifier, while collecting both could duplicate spend and
coverage.

## Effect on the ALDI 404 diagnosis

The refreshed source confirms, rather than changes, the exact store/ZIP pairs used by the live
diagnostics:

| Diagnostic role | Store | ZIP | Roster result |
| --- | --- | --- | --- |
| Known-success Ohio control | `463-048` | `44906` | Present, active, unchanged |
| California 404 control | `479-098` | `93215` | Present, active, unchanged |
| Florida five-region sample | `474-031` | `33809` | Present, active, unchanged |
| Illinois five-region sample | `468-051` | `61764` | Present, active, unchanged |
| Ohio five-region sample | `461-002` | `43015` | Present, active, unchanged |
| Pennsylvania five-region sample | `469-066` | `17009` | Present, active, unchanged |
| Unattempted Florida sample | `474-235` | `33803` | Present, active, unchanged |

MetricsCart Search requests use `Store_No` plus normalized ZIP, not `mc_location_id`. None of the
79 corrected MetricsCart IDs belongs to the diagnostic pairs. The refresh therefore improves
provider identity lineage but cannot explain or cure the regional billable 404 responses. It would
be incorrect to replay the failed stores merely because the roster was reimported.

## Decision

- Keep the working ALDI Search endpoint and parameters unchanged.
- Treat the 2026-08-22 file as the current ALDI location source until superseded by a later
  checksummed roster.
- Preserve prior collection geography snapshots and raw responses; the import updates the current
  dimension only.
- Do not claim regional Search availability from an `active` location-master status. Roster
  membership and endpoint callability are separate facts.
- Before a full multi-region replay, prepare a fresh, explicitly approved ALDI-only preflight using
  different active store/ZIP pairs outside the eleven physical-location collisions. The paid-call
  estimate and hard cap must be presented at action time.

## Verification

- Source profile: 2,627/2,627 unique store identities and MetricsCart IDs; zero missing required
  fields; 2,499 normalized ZIPs; 40 states; all rows active/USA.
- Canonical reconciliation: exact retailer-source parity and zero normalized geography changes.
- Location tests verify source completeness, string ZIP normalization, refreshed identity
  `460-006` / `2014417`, and preservation of both live diagnostic controls.
- Production import `7c394c4b-2b55-4505-b3c7-ca9e6dbff317` completed with 2,627 imported rows,
  zero skipped rows, and the expected source checksum. All 2,627 current ALDI rows point to that
  import; the current dimension still has 2,627 active unique store numbers, 2,627 unique
  MetricsCart IDs, and 2,499 normalized ZIPs.
- Frozen diagnostic geography `0cb7a74f-46ba-45ea-bcc7-f7d552fa2eb1` retains its original
  checksum `dffe849196a6fba064017dd61fc83725125e195242b0b706f81ed81305586987` and two-location
  snapshot after the current-dimension refresh.
- Commit `7cd9995` deployed successfully. GitHub Actions run `32588635469` passed Python, contracts,
  migration upgrade/downgrade, TypeScript, 14 browser tests, and all four container builds.
- No Search, PDP, or AI spend occurred in this phase.
