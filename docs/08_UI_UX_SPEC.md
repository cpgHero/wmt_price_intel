# UI / UX Specification

## Navigation

- Dashboard
- Collections
  - New Collection
  - Definitions
  - Run History
  - Scheduling
- Analyses
  - Current
  - Historical
  - Compare Runs
- Product Packs
- Reports
- Data Quality
- Automation
  - Collection schedules
  - Alert definitions and evidence-backed events
  - Email delivery status
- Admin
  - Retailers / Adapters
  - Location Master
  - Provider Usage / Credits
  - Users / Settings

## New Collection wizard

### Step 1 - What to analyze
Name, keyword, Product Pack, benchmark retailer, competitors.

### Step 2 - Geography
All locations, benchmark ZIP universe, union ZIPs, states, custom ZIP/location list. Show counts before proceeding.

### Step 3 - Collection depth
Sort mode, pages 1-10, retailer-specific overrides.

### Step 4 - Estimate
For each retailer show location units, max pages, credits/page, estimated max pages/credits. Show total and configured budget.

### Step 5 - Analysis options
Comparison profiles and optional proximity validation.

### Step 6 - Review & Run
Persist a versioned definition, create run, enqueue tasks.

## Run monitor

Show task counts by retailer/status, pages completed, estimated/actual credits, current global provider rate, 429 cooldown banner, retries, failures, elapsed time, and cancel action.

## Analysis workspace tabs

- Executive Summary
- Geographic Coverage
- Price Position
- Segment Analysis
- Product Matches
- Assortment
- Data Quality / QA
- Methodology
- Exports

## Product Pack administration

V1: read-only JSON/config viewer with version history. Editing can remain developer/admin managed until the schema stabilizes.
