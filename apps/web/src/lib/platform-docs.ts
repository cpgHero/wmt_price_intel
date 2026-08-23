export type PlatformDocGroupId =
  "orientation" | "workflows" | "governance" | "operations" | "reference";

export interface PlatformDocLink {
  href: string;
  label: string;
}

export interface PlatformDocStep {
  detail: string;
  link?: PlatformDocLink;
  title: string;
}

export type PlatformDocBlock =
  | {
      kind: "paragraphs";
      paragraphs: string[];
      title?: string;
    }
  | {
      items: string[];
      kind: "list";
      title?: string;
    }
  | {
      items: PlatformDocStep[];
      kind: "steps";
      title?: string;
    }
  | {
      items: Array<{ definition: string; term: string }>;
      kind: "definitions";
      title?: string;
    }
  | {
      columns: string[];
      kind: "table";
      rows: string[][];
      title?: string;
    }
  | {
      kind: "callout";
      text: string;
      title: string;
      tone: "attention" | "information" | "success";
    };

export interface PlatformDocGuide {
  audience: string;
  blocks: PlatformDocBlock[];
  group: PlatformDocGroupId;
  id: string;
  lastVerified: string;
  links?: PlatformDocLink[];
  readingTime: string;
  status: "Current" | "Current with limitations";
  summary: string;
  title: string;
}

export interface PlatformDocumentation {
  baseline: string;
  guides: PlatformDocGuide[];
  lastVerified: string;
  maintenanceOwner: string;
  title: string;
  version: string;
}

export const platformDocGroups: ReadonlyArray<{
  id: PlatformDocGroupId;
  label: string;
}> = [
  { id: "orientation", label: "Start here" },
  { id: "workflows", label: "Workflows" },
  { id: "governance", label: "Trust & governance" },
  { id: "operations", label: "Operations" },
  { id: "reference", label: "Reference" },
];

const lastVerified = "August 23, 2026";

export const platformDocumentation: PlatformDocumentation = {
  title: "Platform Owner & Administrator Guide",
  version: "1.3.49",
  lastVerified,
  baseline:
    "Production implementation through Phase 13.41 monthly PDP freshness governance plus the test-verified Spring Valley collection foundation, built on the Phase 13.30 five-category certified baseline",
  maintenanceOwner: "Platform owner and engineering lead",
  guides: [
    {
      id: "start-here",
      group: "orientation",
      title: "Start here",
      summary:
        "What the platform does, how the major workspaces fit together, and the rules that protect trust.",
      audience: "Platform owner · Platform administrator",
      readingTime: "6 min",
      lastVerified,
      status: "Current",
      links: [
        { href: "/", label: "Open Home" },
        { href: "/data-quality", label: "Open Data Quality" },
      ],
      blocks: [
        {
          kind: "callout",
          tone: "information",
          title: "The platform's job",
          text: "First, preserve the price observed for each retailer product at each retailer location. Second, compare same or governed-similar products at geographically relevant locations. Every summary must remain traceable to those atomic observations.",
        },
        {
          kind: "definitions",
          title: "The five operating layers",
          items: [
            {
              term: "Price Intelligence",
              definition:
                "Examines a retailer's own products, prices, distribution, sponsorship, and store-level exceptions. It does not claim that products are competitive substitutes.",
            },
            {
              term: "Competitive Intelligence",
              definition:
                "Compares Walmart products with eligible competitor products using governed relationships, comparison bases, and local store or ZIP correspondence.",
            },
            {
              term: "Operations",
              definition:
                "Creates collection definitions, resolves geography, controls paid calls, monitors runs, schedules work, and surfaces data-quality exceptions.",
            },
            {
              term: "Administration",
              definition:
                "Governs brands, matches, study discovery, Product Packs, and independent Matching v2 certification.",
            },
            {
              term: "Evidence storage",
              definition:
                "Postgres stores control state and audit history. The private bucket stores immutable raw responses and versioned analytical artifacts.",
            },
          ],
        },
        {
          kind: "list",
          title: "Trust rules that never change",
          items: [
            "Search data owns store-specific price, observed availability, sponsorship, and collection time.",
            "The location master owns current store identity, ZIP, city, state, country, latitude, and longitude. A roster's active status does not prove that a retailer Search page is callable.",
            "PDP data may improve identity, package attributes, imagery, seller, and descriptive context; it never overwrites Search price or location.",
            "Product Packs own category qualification, attribute, comparison-basis, and reporting rules. Retailer Packs own retailer-specific identifiers, seller policy, endpoints, and location behavior.",
            "Deterministic code computes every authoritative count, price, median, rate, distance, denominator, match rule, and unit conversion.",
            "AI may interpret, propose, extract, and prioritize. It cannot silently approve matches or calculate authoritative metrics.",
            "Raw evidence and published versions are immutable. Corrections create a new version or append-only decision.",
          ],
        },
        {
          kind: "callout",
          tone: "attention",
          title: "Current authority boundary",
          text: "The existing governed matcher remains authoritative unless an administrator explicitly creates a Matching v2 gold-set replay from an exhaustive operational certification queue. Sampled validation gold sets measure matcher quality but cannot drive reporting. A cutover replay is checksum-bound to one certified snapshot, uses certified comparable relationships only, excludes certified not-comparable and final insufficient-evidence cases from price metrics, and disables automatic match fallback. Human certification governs whether a product pair is comparable; Product Pack brand policies separately govern which reporting views may include that certified pair. Inclusive ignore-brand views retain every certified-comparable pair, while private-label and same-brand views require affirmative governed brand evidence and fail closed when it is missing. Final insufficient-evidence decisions remain in an immutable exclusion ledger with reviewer, rationale, and evidence provenance; cases without any final human outcome block publication. Repeating the same source and release is idempotent by default. A current-code rebuild requires an explicit force-rebuild instruction and audit reason; it increments the immutable replay generation and creates a new report ID rather than mutating the prior publication. Certification decisions never silently rewrite a published report.",
        },
      ],
    },
    {
      id: "application-map",
      group: "orientation",
      title: "Application map",
      summary:
        "A plain-language guide to every primary module and when an administrator should use it.",
      audience: "Platform owner · Platform administrator",
      readingTime: "7 min",
      lastVerified,
      status: "Current",
      blocks: [
        {
          kind: "table",
          title: "Primary navigation",
          columns: ["Area", "Use it for", "Important boundary"],
          rows: [
            [
              "Home",
              "Recent analyses, collection activity, and operating health.",
              "A launch point, not an alternate analytics engine.",
            ],
            [
              "Price Intelligence",
              "One-retailer product, price, footprint, architecture, store review, and future history.",
              "Search price > 0 is observed/in-stock; non-observation is not confirmed out-of-stock.",
            ],
            [
              "Competitive Intelligence",
              "Retailer scorecards, price/cohort views, products, geography, assortment, match review, and methodology.",
              "Comparison basis, competitor, geography, and evidence readiness govern every result.",
            ],
            [
              "Collections",
              "Definitions, new collection wizard, approved geography, estimates, launches, and run monitoring.",
              "No paid call occurs until an estimate is explicitly approved and launched.",
            ],
            [
              "Schedules & Alerts",
              "Recurring collections, metric conditions, alert events, and email delivery.",
              "Uses versioned definitions, durable leases, cooldowns, and idempotent delivery.",
            ],
            [
              "Data Quality",
              "Readiness, source exclusions, evidence gaps, collection failures, and trust exceptions.",
              "A failed readiness gate must remain visible; narrative cannot hide it.",
            ],
          ],
        },
        {
          kind: "table",
          title: "Administration workspaces",
          columns: ["Workspace", "Purpose", "Effect"],
          rows: [
            [
              "Match Certification",
              "Inspect evidence and approve or reject Matching v2 relationships.",
              "One decision is final until flagged; governed reporting replay remains explicit.",
            ],
            [
              "Brand Workbench",
              "Confirm private-label, regional, national, alias, and unresolved brand classifications.",
              "Creates governed overrides without corrupting the approved brand foundation.",
            ],
            [
              "Study Discovery",
              "Profile Search results, remove noise, plan selective PDP enrichment, and create evidence for a Product Pack.",
              "Discovery precedes certification and retains Search/PDP source authority.",
            ],
            [
              "Report Publishing",
              "Monitor queued and running report materialization, trust-audit outcomes, retries, and atomic activation.",
              "A pending or blocked replacement never displaces the current trusted report.",
            ],
            [
              "Product Packs",
              "Author, validate, publish, and activate versioned category rules and report blueprints.",
              "Published versions are immutable and require certification evidence.",
            ],
          ],
        },
      ],
    },
    {
      id: "data-lifecycle",
      group: "workflows",
      title: "Data lifecycle: collection to reporting",
      summary:
        "The complete processing order, including source authority, enrichment, matching, analytics, AI, and publication gates.",
      audience: "Platform owner · Administrator · Analyst",
      readingTime: "12 min",
      lastVerified,
      status: "Current with limitations",
      links: [
        { href: "/collections", label: "Open Collections" },
        { href: "/analyses", label: "Open Competitive Intelligence" },
      ],
      blocks: [
        {
          kind: "steps",
          title: "Start-to-finish flow",
          items: [
            {
              title: "1. Discover the category",
              detail:
                "Profile representative Search results to learn the product universe, retailer payloads, likely noise, attributes, brands, package structures, and evidence gaps before final rules are certified.",
              link: { href: "/admin/studies", label: "Study Discovery" },
            },
            {
              title: "2. Govern category and retailer behavior",
              detail:
                "Pin a Product Pack for category admission, attributes, price bases, matching tiers, and report rules. Pin Retailer Packs for endpoint, identifier, store, seller, sponsorship, and PDP behavior.",
              link: { href: "/admin/product-packs", label: "Product Packs" },
            },
            {
              title: "3. Define the study and geography",
              detail:
                "Select the primary retailer, competitors, keyword, page depth, all/state/sample/city/ZIP/location scope, and exact same-ZIP or 1/3/5-mile competitor correspondence. Review the immutable resolved geography before launch.",
              link: { href: "/collections/new", label: "New collection" },
            },
            {
              title: "4. Estimate and approve spend",
              detail:
                "The server calculates maximum Search credits by retailer from the frozen definition and geography checksums. The estimate expires after 30 minutes. PDP and AI spend remain separate approvals.",
            },
            {
              title: "5. Plan durable collection tasks",
              detail:
                "Postgres creates idempotent retailer/location/page tasks. Workers claim rows with FOR UPDATE SKIP LOCKED, leases, bounded retries, cancellation, and hard credit caps.",
            },
            {
              title: "6. Collect and preserve raw evidence",
              detail:
                "All new collections call MetricsCart Search by ZIP APIs under shared per-retailer/type limits and cooldowns. Raw responses are written once to the private bucket as immutable, checksummed objects. HTTP 200 and 404 calls may be billable; costs remain auditable. The August 22 live acceptance collected 75 rows from Walmart, ALDI, and Amazon Same Day for five credits with no retry, 404, or schema drift. Historical CSVs remain replay evidence only and do not define the live API contract.",
            },
            {
              title: "7. Normalize without losing identifiers",
              detail:
                "Adapters first audit each successful Search payload against a versioned catalog-driven response contract, then map it into shared offers. Store IDs, retailer product IDs, ASINs, provider IDs, and leading-zero ZIPs stay strings. A provider shape or required-field change fails closed as schema_drift after raw persistence; it cannot masquerade as an empty result page.",
            },
            {
              title: "8. Build the canonical product-location population",
              detail:
                "Keep in-scope positive-USD Search observations with usable locations. Deduplicate to the latest retailer × product × location × collection row, retain sponsorship evidence, disclose conflicts, and enrich geography from the location master.",
            },
            {
              title: "9. Exclude noise and known marketplace sellers",
              detail:
                "Product Pack qualification returns include, exclude, or review with reason codes. Retailer seller policy removes known non-first-party marketplace sellers. Live Search payloads did not supply seller, so retailer site identity is never treated as first-party proof: PDP seller evidence verifies first party where available, and permitted blank sellers remain explicitly unverified.",
            },
            {
              title: "10. Enrich distinct admitted products",
              detail:
                "Create a read-only, cache-adjusted estimate first. Reuse fresh PDP cache, then collect at most one representative observed location per distinct in-scope product unless contradictory evidence or a governed price-regime diagnostic requires another sample. PDP enhances identity—not local price.",
            },
            {
              title: "11. Resolve identity, brands, and attributes",
              detail:
                "Create retailer listing identity, optional exact trade-item links, governed brand role, package semantics, and attribute facts with source, reliability, timestamp, extraction method, and conflict state. Unknown remains unknown.",
            },
            {
              title: "12. Generate and govern product relationships",
              detail:
                "High-recall candidates are blocked by known hard conflicts, evaluated against Product Pack tiers, and scoped to local distribution overlap. Price similarity is never a semantic matching signal.",
              link: {
                href: "/admin/matching-v2",
                label: "Match Certification",
              },
            },
            {
              title: "13. Materialize local comparisons",
              detail:
                "Apply same-ZIP, 1/3/5-mile, or delivery-market correspondence; retain all eligible offers; choose the controlling local offer by explicit policy; and assign a reason to every unscored context.",
            },
            {
              title: "14. Calculate deterministic analytics",
              detail:
                "Compute product-location outcomes first, then reconcile item, store, cohort, brand, assortment, geography, and retailer rollups. Renderers receive the canonical result and never recalculate it.",
            },
            {
              title: "15. Add governed interpretation",
              detail:
                "AI may turn verified facts into readable insights. A deterministic critic verifies claims and evidence references. The report must still work when AI is disabled or unavailable.",
            },
            {
              title: "16. Gate and publish",
              detail:
                "The immutable result enters a pending state and activates a durable Postgres job. A leased worker stages Price Architecture and every configured comparison-basis × 1/3/5-mile portfolio, then runs the semantic trust audit. Only one final transaction marks the replacement ready and recoverably archives its predecessor. A failed replacement remains pending or blocked while the current trusted report stays active.",
              link: {
                href: "/admin/report-publishing",
                label: "Report Publishing",
              },
            },
            {
              title: "17. Monitor drift and repeat",
              detail:
                "Schedules create new runs from pinned versions. Identifier, seller, package, attribute, brand, image, distribution, and policy drift queue affected evidence for review rather than silently changing history.",
            },
          ],
        },
        {
          kind: "callout",
          tone: "attention",
          title: "Historical versus current results",
          text: "A new Product Pack, Retailer Pack, matcher, or normalizer does not mutate an old analysis. Replaying a dataset creates a new versioned result so the original remains reproducible.",
        },
      ],
    },
    {
      id: "study-collection",
      group: "workflows",
      title: "Study discovery & collection setup",
      summary:
        "How to onboard a category, approve its footprint, control paid collection, and preserve reproducibility.",
      audience: "Platform administrator · Analyst",
      readingTime: "10 min",
      lastVerified,
      status: "Current",
      links: [
        { href: "/admin/studies", label: "Study Discovery" },
        { href: "/collections/new", label: "New collection" },
      ],
      blocks: [
        {
          kind: "steps",
          title: "Recommended administrator workflow",
          items: [
            {
              title: "Create a discovery study",
              detail:
                "Use a clear business question and representative Search inputs. Discovery is where the platform learns the observed population; it is not yet a certified Product Pack.",
            },
            {
              title: "Review the product population",
              detail:
                "Confirm included, excluded, and review products. Inspect brands, package evidence, payload coverage, and retailer-specific anomalies. Unknown brands stay candidates until governed.",
            },
            {
              title: "Plan selective PDP evidence",
              detail:
                "Enrich admitted or provisional products only. Review the distinct-product count and separate credit ceiling. Cache hits cost no provider credits.",
            },
            {
              title: "Create or revise the Product Pack",
              detail:
                "Translate discovery evidence into generic capabilities: scope terms, exclusions, attributes, units, comparison lenses, missing-value policy, report questions, and certification fixtures.",
            },
            {
              title: "Build the collection definition",
              detail:
                "Choose exact Pack versions, retailer roles, keyword, page depth, geography strategy, correspondence rule, PDP cadence, schedule, delivery, and hard Search credit cap.",
            },
            {
              title: "Approve the geography snapshot",
              detail:
                "Inspect the map, counts, locations, proximity edges, ZIP-only scopes, and exclusions. Download the CSV when a human audit is useful. The approved snapshot is frozen for the run.",
            },
            {
              title: "Approve the estimate and launch",
              detail:
                "Confirm the maximum Search credits. If configuration, geography, or the 30-minute approval window changes, obtain a fresh estimate. Launch is idempotent for the same approved estimate.",
            },
          ],
        },
        {
          kind: "list",
          title: "Geography options currently governed",
          items: [
            "All primary-retailer locations.",
            "All locations in selected states.",
            "A deterministic, geographically dispersed number of locations per state.",
            "Selected state/city pairs, custom ZIPs, or canonical location IDs.",
            "Competitors in the same ZIP, across primary states, or within an exact 1-, 3-, or 5-mile radius.",
            "ZIP/service-area scopes for retailers such as Amazon Same Day without fabricated physical stores.",
          ],
        },
        {
          kind: "callout",
          tone: "information",
          title: "Not yet governed",
          text: "Population, county, and demographic-driven geography remain intentionally unavailable until a source, freshness policy, metric definition, and validation contract are approved.",
        },
      ],
    },
    {
      id: "product-evidence",
      group: "workflows",
      title: "Search, PDP, identity & brand evidence",
      summary:
        "Which source owns each fact, how PDP enrichment is selected, and how brands and marketplace sellers are governed.",
      audience: "Platform administrator · Analyst",
      readingTime: "9 min",
      lastVerified,
      status: "Current with limitations",
      links: [
        { href: "/workspace/brands", label: "Brand Workbench" },
        { href: "/price-intelligence", label: "Price Intelligence" },
      ],
      blocks: [
        {
          kind: "table",
          title: "Source authority",
          columns: ["Fact", "Authoritative source", "Supporting sources"],
          rows: [
            [
              "Store package price",
              "Search at that location",
              "None may overwrite it",
            ],
            [
              "Observed/in-stock",
              "Positive Search price",
              "PDP stock is contextual only",
            ],
            [
              "Sponsored placement",
              "Search is_sponsored",
              "No inferred promotion signal",
            ],
            [
              "Store geography",
              "Location master",
              "Search ZIP is supporting evidence",
            ],
            [
              "Product identity",
              "Governed PDP/canonical identity",
              "Search title and identifiers",
            ],
            [
              "Package attributes",
              "Product Pack-normalized evidence",
              "PDP, Search, OCR, vision, human review",
            ],
            [
              "Brand role",
              "Brand foundation plus approved override",
              "Search/PDP brand text and retailer evidence",
            ],
            [
              "Seller eligibility",
              "Retailer Pack seller policy",
              "PDP seller; blank may remain unverified",
            ],
          ],
        },
        {
          kind: "list",
          title: "PDP selection and reuse",
          items: [
            "Exclude Search noise before enrichment; do not spend PDP credits on unrelated products.",
            "Enrich each distinct admitted retailer product once per freshness policy, not once per store.",
            "The current default freshness window is 30 days. New or unenriched products remain eligible immediately; a separately estimated owner-approved identity refresh may override the cadence.",
            "Use a representative location where Search observed the product with a positive price.",
            "Add a targeted location sample only for contradictory identity evidence or a separately governed diagnostic; a price difference alone never changes Search price authority.",
            "Reuse immutable cached payloads and run zero-credit re-normalization when the normalizer improves.",
            "Live Search PDP launches convert the owner-approved USD ceiling to an integer credit ceiling at $0.002 per credit, fail closed when the qualified plan exceeds it, and refuse to create duplicate work when the same governed request is already queued or running.",
            "Validate retailer-specific parameters from the versioned endpoint catalog. Catalog fixed parameters override incompatible Search terminology; for example, Walgreens Search SFS evidence is retained while its PDP contract always sends pickup. This is configuration, not category code.",
            "PDP workers claim jobs fairly across retailers within each priority and run up to 18 jobs concurrently by default. The shared Postgres limiter still enforces 3 requests per second and 180 per minute independently for each retailer across every replica.",
            "Retain useful identity, descriptions, identifiers, package facts, media, fulfillment, reviews, demand, and relationships; leave oversized provider-native bodies in raw evidence until a governed use exists.",
            "Audit PDP completeness separately from schema coverage. Zero unmapped fields means the provider payload was mapped; it does not mean every product supplied brand, identifiers, package specifications, descriptions, or multiple usable images.",
          ],
        },
        {
          kind: "callout",
          tone: "information",
          title: "Kroger PDP contract is verified",
          text: "A controlled August 17 preflight used an Egg product observed at the supplied store and ZIP and returned HTTP 200 from /kroger/pdp/zipcode/. The provider-catalog route is enabled; the prior /mc route is retired.",
        },
        {
          kind: "callout",
          tone: "information",
          title: "Egg PDP collection is complete",
          text: "The initial production run completed with 269 new normalized PDPs, 527 fresh cache hits, 117 billable 404s, and one non-billable terminal 500. A corrected Product Pack 1.2.1 retry then added 38/38 HTTP 200 results for Target, Sam's Club, and Trader Joe's under an exact 91-credit ceiling. ALDI and Walmart retain substantial HTTP 200 coverage and their small remaining 404 subsets are product/location investigations rather than a broad contract retry.",
        },
        {
          kind: "callout",
          tone: "information",
          title: "404-heavy Egg contracts are remediated",
          text: "Target and Sam's Club use the owner-verified trailing-slash, URL-only request shape, while Trader Joe's preserves six-digit product IDs. Four bounded preflight requests returned HTTP 200. The old analysis pin estimated 65 calls / 168 credits; audited reclassification with Egg Product Pack 1.2.1 reduced this to 38 calls / 91 credits. Run 81311e57-f31f-4a82-838b-4f94dc7c8c99 completed Target 17/17, Sam's Club 19/19, and Trader Joe's 2/2 with HTTP 200 and no failures.",
        },
        {
          kind: "callout",
          tone: "attention",
          title: "Marketplace filtering",
          text: "For Walmart and Amazon Same Day, a known seller outside the Retailer Pack first-party allowlist is excluded before matching and reporting. A missing seller is not assumed to be first-party; it remains seller_unverified when permitted. Target's seller policy is defined but still needs live-value certification.",
        },
        {
          kind: "paragraphs",
          title: "Brand governance",
          paragraphs: [
            "The governed brand universe resolves canonical names, aliases, retailer ownership, private-label status, regional or national role, and evidence provenance. Private label is the most important distinction, but it never overrides incompatible product or package attributes.",
            "Brand Workbench records human confirmation or rejection as an override. Unknown or ambiguous brands remain visible rather than being forced into a class. Future collections reuse the governed decision while preserving the evidence version used by each historical result.",
          ],
        },
      ],
    },
    {
      id: "matching",
      group: "workflows",
      title: "Matching, cohorts & certification",
      summary:
        "How product relationships are proposed, scoped to locations, reviewed, certified, and used without double counting.",
      audience: "Platform owner · Match administrator · Analyst",
      readingTime: "14 min",
      lastVerified,
      status: "Current with limitations",
      links: [{ href: "/admin/matching-v2", label: "Match Certification" }],
      blocks: [
        {
          kind: "definitions",
          title: "Relationship vocabulary",
          items: [
            {
              term: "Retailer listing",
              definition:
                "A retailer product ID with its Search/PDP representation, seller, URL, and fulfillment context.",
            },
            {
              term: "Trade item",
              definition:
                "A verified physical package, normally supported by GTIN/UPC or manufacturer evidence plus non-conflicting package facts.",
            },
            {
              term: "Pairwise edge",
              definition:
                "One benchmark listing and one competitor listing with tier, evidence, policy, scope, and version. A listing may participate in several defensible edges.",
            },
            {
              term: "Comparable cohort",
              definition:
                "A Product Pack-governed family such as gallon 2% milk. Cohorts summarize compatible pairwise evidence; they do not manufacture product identity.",
            },
            {
              term: "Assortment rollup",
              definition:
                "Brands, breadth, exclusives, gaps, and whitespace. It remains separate from direct price comparison unless a governed product relationship exists.",
            },
          ],
        },
        {
          kind: "table",
          title: "Matching v2 tiers",
          columns: ["Tier", "Meaning", "Current release treatment"],
          rows: [
            [
              "Exact item",
              "Same verified physical trade item and package.",
              "Certification required; automatic approval remains off until precision gates pass.",
            ],
            [
              "Exact specification",
              "Different identity/brand but all required specification and package facts agree.",
              "Certification required.",
            ],
            [
              "Equivalent product",
              "Same consumer need and quality proposition with only permitted differences.",
              "Human approval required.",
            ],
            [
              "Comparable substitute",
              "Relevant alternative with material differences kept visible.",
              "Human approval required and reported as such.",
            ],
            [
              "Custom approved",
              "Human-approved for a named purpose, scope, and period.",
              "Must retain rationale and effective scope.",
            ],
          ],
        },
        {
          kind: "callout",
          tone: "information",
          title: "Milk and eggs are spec-first and brand-aware",
          text: "For Fresh Fluid Milk and Fresh Shell Eggs, a different, regional, private-label, national, or unknown brand cannot independently reject or stall a product relationship. Package and category specifications determine comparability. A verified same-brand relationship remains valuable identity evidence, and brand name/type remain available for separate private-label, regional, national, and same-brand reporting. Brand agreement never overrides a conflicting hard-blocker specification. Milk's primary scorecard uses the specification-equivalent profile; its same-brand and private-label profiles remain secondary analytical lenses.",
        },
        {
          kind: "steps",
          title: "How a relationship becomes usable",
          items: [
            {
              title: "Create high-recall candidates",
              detail:
                "Use category blocks, identifiers, package and attribute evidence, and no known hard conflicts. Price similarity is excluded from semantic evidence. Known third-party marketplace offers are removed by Retailer Pack policy before candidates exist.",
            },
            {
              title: "Evaluate deterministic evidence",
              detail:
                "Product Pack policy marks each attribute matched, conflicting, unknown, or ignored and calculates evidence coverage separately from similarity. A comparable certification requires every current hard blocker to be known and compatible, even when an immutable older queue recorded a softer historical role.",
            },
            {
              title: "Resolve local applicability",
              detail:
                "A relationship applies only where the products are observed within the governed ZIP, radius, or service-area context. This supports four regional Walmart milk listings compared with one ALDI listing without averaging or double counting them globally.",
            },
            {
              title: "Review current authoritative relationships",
              detail:
                "Match Certification is the authoritative relationship surface. Inspect product images, PDP and attribute evidence, approve or reject once, and reopen a final decision only by explicitly flagging it. Reporting replay remains explicit.",
            },
            {
              title: "Independently certify Matching v2",
              detail:
                "Match Certification presents the immutable shadow evidence. One identified reviewer approves or rejects once. That decision is final until someone explicitly flags it; the next decision resolves the flag and becomes final.",
            },
            {
              title: "Cut over only after release gates",
              detail:
                "Candidate recall, precision, hard-conflict, coverage-reason, reconciliation, and deterministic checksum gates must pass per Product Pack before v2 can replace the current matcher.",
            },
          ],
        },
        {
          kind: "callout",
          tone: "information",
          title: "AI and vision",
          text: "A user may request AI drafts for explicit page selections or every currently eligible candidate in the active review queue and competitor-retailer filter. One governed run may contain up to 1,500 cases, enough for every current five-category release queue. Before any paid work is created, the UI discloses the exact case count, model, per-case ceiling, and worst-case aggregate exposure and requires an identified administrator to confirm. Each request is one idempotent durable Postgres batch with queue-wide queued, reviewing, ready, and needs-attention counts; the latest batch shows completed items, timestamps, estimated remaining time, and recorded cost. The worker processes two cases concurrently by default and automatically attempts each task twice. Existing AI tasks, final comparable/not-comparable decisions, known third-party listings, and any candidate missing nonzero Search-derived benchmark or competitor observed-location evidence cannot cross this paid-call boundary. After a terminal needs-attention failure, an identified administrator may confirm an individual or filtered-page bulk retry. A retry creates a new task linked to the failed task and preserves every prior attempt, safe error, and recorded cost; it never resets history. Each case permits at most four administrator retry rounds. Structured evidence is always supplied. When critical attributes are missing or conflicting, the evidence packet adds the primary and available secondary PDP images, interleaved across both products and bounded to six per product. Image proposals must cite visible text and the exact supplied image URL. A blocked retailer image host causes a recorded structured-only fallback, never an invented visual claim. Every draft remains advisory and requires a human decision.",
        },
        {
          kind: "callout",
          tone: "success",
          title: "Administrator-confirmed bulk acceptance",
          text: "An administrator may assess completed comparable and not-comparable AI recommendations across the full pending queue and active retailer filter. The client submits up to 500 candidates, while the server binds no more than 50 confirmable cases into each confirmation and defers additional passing cases to the next batch. Comparable recommendations require a supported match tier and every current Product Pack hard blocker to be known and compatible; a hard-blocker conflict or unresolved value is a server-enforced exclusion that cannot be overridden. Not-comparable recommendations must have no tier and may be certified when a hard conflict supports rejection. Insufficient-evidence recommendations remain non-final and blocked. Deterministic tier disagreement, incomplete nonblocking evidence, AI conflicts, and confidence limits remain visible advisory warnings. A final decision, invalid draft, known third-party seller, or missing immutable evidence remains a blocking exclusion. The preview binds each recommended verdict and tier with case checksums, AI task/output checksums, queue version, and policy version into one confirmation checksum. One explicit administrator confirmation writes an immutable bulk-action audit record plus the same final human submission used by individual approval, including all warnings and the complete AI evidence rationale in the reviewer comment. The completion result separately counts comparable and not-comparable decisions. No report reanalysis runs automatically; decisions remain final until flagged.",
        },
        {
          kind: "callout",
          tone: "information",
          title: "Observed footprint completeness",
          text: "Every certification product shows the number of distinct normalized store/location keys where Search observed that retailer product with a non-null price greater than zero. Modern queue documents carry the count directly. A versioned reconciliation catalog fills the field for older immutable queues without replacing their AI work or human decisions. Existing queue evidence is never overwritten. The same compatibility view supplements missing seller-governance status, suppresses any known third-party case, and leaves permitted blank sellers explicitly unverified.",
        },
        {
          kind: "callout",
          tone: "attention",
          title: "Milk package volume is exact",
          text: "Fresh Fluid Milk Product Pack 1.6.0 preserves package volume as a hard compatibility requirement and adds observed-footprint eligibility before a pair can enter certification. A gallon, half gallon, quart, and pint are different products for matching; unit-price normalization may support price analysis only after a valid semantic relationship exists. Match Certification visibly blocks comparable approval when volume conflicts or is unresolved, and preserves historical queue roles for audit. Brand agreement never rescues a volume mismatch.",
        },
        {
          kind: "callout",
          tone: "attention",
          title: "Certification identity limitation",
          text: "Reviewer identity is currently manually entered inside the protected administrator session. Individual login/RBAC-backed identity is required before external production release.",
        },
      ],
    },
    {
      id: "analytics-reporting",
      group: "workflows",
      title: "Analytics, insight & reporting",
      summary:
        "How atomic evidence becomes Price Intelligence, Competitive Intelligence, scorecards, and readable narrative.",
      audience: "Platform owner · Administrator · Analyst",
      readingTime: "11 min",
      lastVerified,
      status: "Current with limitations",
      links: [
        { href: "/price-intelligence", label: "Price Intelligence" },
        { href: "/analyses", label: "Competitive Intelligence" },
      ],
      blocks: [
        {
          kind: "definitions",
          title: "Two analytical experiences, one foundation",
          items: [
            {
              term: "Price Intelligence",
              definition:
                "Aggregates the canonical product-location observations without requiring product matches. Home selects an exact retailer product. The cross-retailer Price Architecture Matrix places every eligible SKU into Walmart-defined or fixed package-price bands. Product Overview combines identity, presence, price, sponsorship, and map evidence; product Price Architecture explains one SKU's store-price distribution; Store Review focuses unusual prices and non-observations.",
            },
            {
              term: "Competitive Intelligence",
              definition:
                "Adds governed product relationships and location correspondence. Its focused report tabs are Retailer Scorecards, Cohort Scorecards, Competitive Footprint, Matched Price Matrix, Match Summary, Price Ladders, Store Comparisons, Competitive History, and Assortment Scorecards. Market Performance is consolidated into Competitive Footprint; Store Exceptions is a Store Comparisons view; report-level Data Integrity is administered from Operations > Data Quality. Product leadership tabs share one retailer, comparison basis, benchmark product, 1/3/5-mile radius, and benchmark geography.",
            },
          ],
        },
        {
          kind: "list",
          title: "Metric integrity rules",
          items: [
            "Calculate at product × location grain before rolling up to products, stores, cohorts, brands, markets, or retailers.",
            "Name every denominator: observed locations, eligible network locations, matched observations, scored benchmark stores, or another explicit governed population.",
            "Count a benchmark store once in executive scorecards even when several product relationships contribute evidence.",
            "Keep package price and normalized unit price as distinct comparison bases; use a unit price only when package evidence supports it.",
            "Assign every unscored local context a reason such as no eligible match, no overlap, product not observed, stale/missing price, collection failure, incomplete attributes, or review required.",
            "Preserve retailer, Product Pack, relationship, geography, period, policy, evidence checksum, and freshness context with each result.",
            "Bind every live read model to the exact immutable artifact set cited by the published AnalysisResult evidence checksum. If more than one generation exists and none reconciles exactly, fail closed instead of merging generations.",
            "Apply Retailer Pack first-party seller policy at both classification and canonical product-location projection. Known third-party marketplace offers never enter price, coverage, assortment, matching, or competitive metrics; permitted blank sellers remain explicitly unverified.",
            "Apply the selected competitor and comparison basis to every scorecard and supporting product view. A context selector must never be presentation-only.",
            "For physical retailers, radius-native scorecards rebuild certified product relationships at product × observed Walmart store grain and require the competitor store to be within the selected 1, 3, or 5 mile radius. Service-area retailers remain explicitly same-delivery-ZIP because they do not expose a comparable physical store footprint.",
            "Cohort Scorecards aggregate those same certified product-location outcomes by Product Pack segment; cohort membership never creates a new match. Assortment Scorecards keep global assortment breadth separate while applying the selected radius to local comparable coverage.",
            "Default competitive portfolios are persisted per immutable analysis, comparison profile, and 1/3/5-mile radius. Retailer selection filters one materialized all-retailer document; state and city combinations remain on-demand. Rebuilding these read models does not call MetricsCart or OpenAI.",
            "Report Walmart-lower, competitor-lower, parity, and clear-leader rates separately. A narrow Walmart lead is Walmart-lower but not a clear leader; labels must not substitute one measure for the other.",
            "Distinguish no governed relationship, no admissible store observation, and a measured zero. These states are not interchangeable and must never share an unlabeled 0.",
            "A Matching v2 replay is decision-ready only when certified labels, final insufficient-evidence exclusions, and pending counts reconcile to the queue; no candidate lacks a final human outcome; the AnalysisResult validation is ready; and every configured retailer has reported evidence or an explicit limitation. A final insufficient-evidence case is an explicit nonblocking limitation, not a match and not unfinished work.",
            "Build local price ladders only from governed matched products and positive Search prices. At each benchmark store, retain the lowest local offer per matched competitor product within the selected 1, 3, or 5 mile radius; rank from opening price upward and preserve rung gaps, Walmart rank, retailer, product, location, and relationship identity.",
            "Treat price ladders as governed match-group × geography × snapshot constructs. Never sort unrelated category products into a ladder and imply substitutability.",
            "Keep the Price Architecture Matrix independent from matching. Assign each retailer SKU exactly once from its median positive Search package price across observed locations. In benchmark-anchored mode, deduplicate Walmart median price points and use the true midpoint between adjacent points as the boundary; in fixed mode use stable $0.50 or $1.00 bands.",
            "Read Price Architecture Matrix rungs from the lowest Walmart price position to the highest. Exact canonical-brand filtering changes the displayed assortment but preserves the Walmart-defined rung boundaries; every product card identifies the retailer product ID, observed-location footprint, and seller-governance state.",
            "Calculate matrix store coverage as the distinct union of eligible retailer locations reached by any product in a cell. Never sum individual product coverage. An empty cell means no eligible SKU was observed in that price band; it is not proof of retailer assortment absence.",
            "Keep every admitted benchmark product visible across the leadership tabs. A product without a governed relationship remains an explicit unscored product; it is never removed from the selector or represented as a measured zero.",
            "Prefer transparent retailer coverage, readiness, matched evidence, win/tie/loss, price gaps, and ladder rank over an opaque composite score. Any future index must publish its formula, direction, denominator, and exclusions beside the result.",
          ],
        },
        {
          kind: "table",
          title: "Current analytical capability boundary",
          columns: ["Available now", "Requires additional governed data"],
          rows: [
            [
              "Certified product relationships; package and supported unit price; win/tie/loss; price gaps; local price ladders and rank",
              "Historical response, persistence, volatility, stability, and trend",
            ],
            [
              "Retailer/product/store/state/city/radius geography; snapshot dispersion and exceptions",
              "Basket indexes, KVI weighting, consumer price image, demand elasticity, sales, margin, and ROI",
            ],
            [
              "Brand/type and assortment where evidence exists; Search sponsorship; evidence/readiness coverage",
              "Promotion dependency unless a governed promotion field and definition are added; sponsorship is not promotion",
            ],
          ],
        },
        {
          kind: "table",
          title: "Narrative pipeline",
          columns: ["Stage", "Owner", "Responsibility"],
          rows: [
            [
              "Facts and semantic brief",
              "Deterministic engine",
              "Produces authoritative metrics, evidence references, definitions, caveats, and ranked decision facts.",
            ],
            [
              "Interpretation",
              "Governed AI roles",
              "Drafts clear executive insights and product-level explanation within bounded evidence.",
            ],
            [
              "Claim verification",
              "Deterministic critic",
              "Rejects unsupported numbers, retailer claims, comparisons, or evidence references.",
            ],
            [
              "Presentation",
              "Shared report projection",
              "Serves the app and later synchronized export surfaces without recalculating analytics.",
            ],
          ],
        },
        {
          kind: "callout",
          tone: "attention",
          title: "Current reporting limitations",
          text: "The current governed Egg release contains one compatible snapshot, so Product History, price response, persistence, and stability remain unavailable. Basket, KVI, consumer price-image, elasticity, sales, margin, and ROI measures also lack governed source data. Primary app pages are the current reporting surface; export, shareable HTML, email, and workbook parity will be reintroduced after the main workspaces are finalized. The completed queue reconciles 185 certification cases: 183 comparable, one not comparable, and one final insufficient-evidence Kroger housing-method case. That final case remains an explicit audited exclusion rather than a match or unfinished review.",
        },
      ],
    },
    {
      id: "admin-playbooks",
      group: "governance",
      title: "Administrator playbooks",
      summary:
        "The routine operating sequence for quality review, brand governance, match changes, Product Packs, and incident handling.",
      audience: "Platform administrator",
      readingTime: "10 min",
      lastVerified,
      status: "Current",
      blocks: [
        {
          kind: "steps",
          title: "Before publishing or relying on an analysis",
          items: [
            {
              title: "Confirm pinned context",
              detail:
                "Verify the analysis, retailers, Product Pack version, comparison basis, competitor, geography, period, and relationship revision shown in the app.",
            },
            {
              title: "Review source and readiness",
              detail:
                "Inspect canonical population counts, exclusions, collection failures, unknown locations, PDP completeness, seller policy, and match readiness in Data Quality and methodology details.",
              link: { href: "/data-quality", label: "Data Quality" },
            },
            {
              title: "Resolve brand exceptions",
              detail:
                "Confirm or reject unknown and ambiguous brands. Do not use retailer ownership or private-label classification to bypass product/package compatibility.",
              link: { href: "/workspace/brands", label: "Brand Workbench" },
            },
            {
              title: "Resolve relationship exceptions",
              detail:
                "Inspect pair evidence, images, attributes, scope, and alternate lenses in Match Certification. Approve or reject once, reopen only when explicitly flagged, and trigger governed reporting replay after the review set is ready.",
              link: {
                href: "/admin/matching-v2",
                label: "Match Certification",
              },
            },
            {
              title: "Certify v2 independently",
              detail:
                "Work the queue in descending observed-location exposure. Approve or reject once; use Needs evidence/Flag only when a final decision needs to be reopened. For completed comparable or not-comparable AI drafts, use guarded bulk acceptance only after reading the eligible set, warnings, and exclusion reasons; the administrator—not AI—confirms the final decisions. Insufficient-evidence drafts remain in review.",
              link: {
                href: "/admin/matching-v2",
                label: "Match Certification",
              },
            },
            {
              title: "Validate the decision surface",
              detail:
                "Drill from scorecards, products, cohorts, assortment, geography, local price ladders, and the retailer certification funnel to the underlying relationship and store evidence. Change competitor, comparison basis, and 1/3/5-mile radius and verify that the evidence changes with the context. Totals must reconcile before the result is promoted or shared.",
            },
          ],
        },
        {
          kind: "steps",
          title: "When category logic must change",
          items: [
            {
              title: "Create a new Product Pack version",
              detail:
                "Clone the certified pack or start from a generic template. Never patch category behavior into core collection, matching, analytics, or rendering code.",
            },
            {
              title: "Attach immutable evidence",
              detail:
                "Bind compact/full source manifests and checksums to the draft revision. Evidence files stay private; Postgres stores metadata and links.",
            },
            {
              title: "Run certification suites",
              detail:
                "Quick checks schemas and capabilities; compact and full add golden evidence; publication is the only suite that can support publish.",
            },
            {
              title: "Publish and optionally activate",
              detail:
                "Publishing creates an immutable Product Pack/report-blueprint pair. Activation only changes the default for new definitions; historical definitions remain pinned.",
            },
          ],
        },
      ],
    },
    {
      id: "trust-governance",
      group: "governance",
      title: "Trust, security & spending controls",
      summary:
        "The controls that prevent metric drift, secret exposure, duplicate work, uncontrolled provider spend, and silent evidence changes.",
      audience: "Platform owner · Platform administrator",
      readingTime: "9 min",
      lastVerified,
      status: "Current with limitations",
      blocks: [
        {
          kind: "list",
          title: "Evidence and metric governance",
          items: [
            "Raw provider snapshots, published Product Packs, report blueprints, AnalysisResults, certification submissions, and gold labels are immutable.",
            "Every behavioral contract change updates schemas, examples, migrations when needed, Python/TypeScript types, docs, and tests together.",
            "Golden metric changes require an explicit benchmark update and rationale; renderers cannot recalculate results.",
            "Unknown evidence stays unknown, and incomplete coverage must remain visible.",
            "Manual brand and match changes are revisioned and require explicit reanalysis rather than an immediate silent report rewrite.",
          ],
        },
        {
          kind: "list",
          title: "Cost controls",
          items: [
            "Search estimates are checksum-bound, expire, and require explicit launch approval.",
            "Definitions may enforce daily and monthly credit budgets; queued/running work reserves its estimate and completed work counts actual credits.",
            "Search, PDP, and AI have separate approval and limiter domains.",
            "PDP planning deduplicates to distinct admitted identities and reuses cache according to cadence.",
            "The PDP estimate is read-only and reports eligible requests, exact fresh-cache hits, blocked contracts, calls, and credits before --confirm-paid-calls can enqueue anything.",
            "Historical PDP replanning may select an exact published Product Pack version; the audit records both the immutable source-analysis version and the enrichment version so newer noise governance cannot be applied silently.",
            "OpenAI model IDs, output limits, reasoning effort, timeouts, and maximum request cost are explicit worker configuration.",
            "HTTP 200 and 404 provider responses may be billable and are retained in the cost ledger; retries remain bounded and idempotent.",
          ],
        },
        {
          kind: "list",
          title: "Security controls",
          items: [
            "MetricsCart and OpenAI keys exist only on the worker. Database, bucket, SMTP, admin token, and session secrets remain server-side Railway variables.",
            "The browser talks to same-origin Next.js routes; the API, worker, scheduler, Postgres, and bucket have no public application domain.",
            "The bucket is private and downloads use short-lived signed URLs.",
            "Administrator sessions are eight-hour, HttpOnly, Secure-in-production, SameSite=Strict, and HMAC-signed. Writes require same-origin validation.",
            "Logs redact provider authentication parameters and record IDs, attempts, statuses, costs, and failure classes without credentials.",
          ],
        },
        {
          kind: "callout",
          tone: "attention",
          title: "Current access-control limitation",
          text: "The implemented administrator surface uses one protected admin session rather than individual accounts and role-based permissions. The intended roles are Admin, Analyst, and Viewer, but full accounts/RBAC remain future work.",
        },
      ],
    },
    {
      id: "railway-operations",
      group: "operations",
      title: "Railway services & operating model",
      summary:
        "What each production resource owns, how work is coordinated, and what to check when the platform is unhealthy.",
      audience: "Platform owner · Platform administrator · Engineering",
      readingTime: "11 min",
      lastVerified,
      status: "Current",
      blocks: [
        {
          kind: "table",
          title: "Production topology",
          columns: ["Resource", "Responsibility", "State boundary"],
          rows: [
            [
              "web",
              "Next.js UI, same-origin backend-for-frontend routes, protected admin session.",
              "Only resource with a public domain.",
            ],
            [
              "api",
              "FastAPI control plane, read models, definitions, launches, admin APIs, presigned evidence access.",
              "Private network; owns Alembic pre-deploy migration.",
            ],
            [
              "worker",
              "Collection, normalization, analysis, PDP, Product Pack validation, AI, and bounded-concurrency Matching v2 review batches.",
              "Durable Postgres claims; provider and OpenAI credentials live here.",
            ],
            [
              "scheduler",
              "Schedules, alert evaluation, and email delivery.",
              "Postgres leases make ticks replica-safe.",
            ],
            [
              "Postgres",
              "Definitions, versions, queues, leases, limits, audit events, reviews, delivery, and metadata.",
              "Authoritative control plane.",
            ],
            [
              "artifacts bucket",
              "Raw json.gz, normalized Parquet, AnalysisResults, evidence, reports, and audit artifacts.",
              "Private immutable/versioned data plane.",
            ],
          ],
        },
        {
          kind: "steps",
          title: "When a run appears stuck",
          items: [
            {
              title: "Check service readiness",
              detail:
                "Verify web /health/ready, API /health/ready, and worker/scheduler readiness in Railway. An online badge is not enough if a dependency check is failing.",
            },
            {
              title: "Inspect run and task state",
              detail:
                "Use Collections and Railway logs to identify pending, leased, retrying, failed, cancelled, or completed tasks. Confirm run ID, retailer, location, page, attempt, and failure class.",
            },
            {
              title: "Check shared limiter/cooldown",
              detail:
                "A healthy worker may wait because another replica consumed the retailer/type allowance or a 429 opened a shared cooldown. Do not bypass it with another replica.",
            },
            {
              title: "Check lease ownership",
              detail:
                "Expired leases are reclaimable. Completion is accepted only from the current owner, so a deploy or crash does not create two successful writes.",
            },
            {
              title: "Check budget and availability gates",
              detail:
                "A hard credit cap, daily/monthly budget, retailer-specific availability gate, disabled feature flag, or missing separate PDP/AI approval may intentionally stop work. A failed retailer no longer blocks retailers that passed.",
            },
            {
              title: "Retry through the governed path",
              detail:
                "Use the application's retry/cancel/replay controls. Never mutate raw artifacts or directly mark a task successful.",
            },
          ],
        },
        {
          kind: "list",
          title: "Deployment order",
          items: [
            "Require the main CI workflow: contracts, lint, types, migrations up/down, tests, build, end-to-end, and every container image.",
            "Deploy API first when a migration is involved; its pre-deploy Alembic step must complete before traffic shifts.",
            "Deploy worker and scheduler with lease-safe drain and reclaim behavior.",
            "Deploy web after compatible API behavior is ready.",
            "Verify readiness, one representative read path, protected admin access, and any changed workflow in production.",
            "Rollback code without deleting additive evidence. Historical artifacts and versioned contracts must remain readable.",
          ],
        },
      ],
    },
    {
      id: "schedules-alerts",
      group: "operations",
      title: "Schedules, alerts & delivery",
      summary:
        "How recurring collections, historical metric checks, cooldowns, and email delivery remain idempotent.",
      audience: "Platform administrator · Analyst",
      readingTime: "7 min",
      lastVerified,
      status: "Current with limitations",
      links: [{ href: "/automation", label: "Schedules & Alerts" }],
      blocks: [
        {
          kind: "steps",
          title: "Recurring workflow",
          items: [
            {
              title: "Publish a versioned schedule",
              detail:
                "Use a five-field cron expression and IANA timezone on a pinned collection-definition version. Invalid schedules are rejected before publication.",
            },
            {
              title: "Materialize one run per slot",
              detail:
                "Scheduler rows are leased with FOR UPDATE SKIP LOCKED. A unique schedule-and-time constraint prevents duplicate runs across retries or replicas.",
            },
            {
              title: "Compare compatible results",
              detail:
                "History uses successful results for the same Product Pack and collection definition. Current and baseline values retain evidence paths and version context.",
            },
            {
              title: "Evaluate versioned alert rules",
              detail:
                "Selectors identify one governed metric; generic operators test thresholds or changes. Each evaluation records triggered, suppressed, or not triggered plus current/baseline evidence.",
            },
            {
              title: "Apply cooldown and deliver",
              detail:
                "Postgres decides cooldown suppression atomically. Triggered alerts enqueue immutable, idempotent email jobs with leased retries and terminal failure state.",
            },
          ],
        },
        {
          kind: "callout",
          tone: "attention",
          title: "Delivery must fail honestly",
          text: "EMAIL_PROVIDER=unavailable records bounded failures; fake is test-only; smtp requires configured credentials. A queued leadership report is not treated as delivered until the provider succeeds.",
        },
      ],
    },
    {
      id: "testing-release",
      group: "operations",
      title: "Testing, release & rollback",
      summary:
        "The evidence required before code, Product Packs, matching rules, metrics, or presentations can be trusted in production.",
      audience: "Platform owner · Platform administrator · Engineering",
      readingTime: "9 min",
      lastVerified,
      status: "Current",
      blocks: [
        {
          kind: "steps",
          title: "Release gate sequence",
          items: [
            {
              title: "Contracts",
              detail:
                "Validate normative JSON Schemas, examples, generated Python/TypeScript types, and backward compatibility.",
            },
            {
              title: "Adapters and normalization",
              detail:
                "Replay retailer fixtures, provider errors, identifier strings, Search authority, sponsorship, location normalization, and PDP payload mappings.",
            },
            {
              title: "Control-plane concurrency",
              detail:
                "Exercise queue claims, leases, retries, cancellation, idempotency, shared rate limits, cooldowns, and budget admission with multiple workers.",
            },
            {
              title: "Product Pack behavior",
              detail:
                "Test classification, attributes, units, qualification, matching policy, unknown handling, and category abstraction without core branches.",
            },
            {
              title: "Golden analytics",
              detail:
                "Run compact and full-source golden regressions. Reconcile metrics to atomic evidence and document any intentional benchmark update.",
            },
            {
              title: "Presentation and workflow",
              detail:
                "Run unit, accessibility-relevant, browser end-to-end, drill-down, error-state, and renderer contract checks. The UI may not reinterpret a metric.",
            },
            {
              title: "Container and migration",
              detail:
                "Build all four service images and run Alembic upgrade, downgrade where practical, and upgrade again.",
            },
            {
              title: "Production acceptance",
              detail:
                "Confirm Railway readiness and walk the changed live path without making unnecessary provider or AI calls.",
            },
          ],
        },
        {
          kind: "list",
          title: "Five-category regression order",
          items: [
            "Fresh shell eggs — broad retailer coverage and critical attribute evidence gaps.",
            "Fresh fluid milk — regional distribution and many-to-one local applicability.",
            "Fresh ground beef — package weight, lean/fat, claims, and price-per-pound.",
            "Fresh strawberries — package normalization and physical-store proximity.",
            "Fresh bananas — selling unit, organic/conventional, and produce variation.",
          ],
        },
        {
          kind: "callout",
          tone: "success",
          title: "Rollback principle",
          text: "Prefer additive contracts and reversible migrations. Disable a feature flag or restore the prior service build without deleting new immutable evidence. Historical Product Pack versions, results, and publications remain readable.",
        },
      ],
    },
    {
      id: "metric-dictionary",
      group: "reference",
      title: "Metric & evidence dictionary",
      summary:
        "Plain-language definitions for the terms most likely to affect how an administrator interprets a report.",
      audience: "Platform owner · Platform administrator · Analyst",
      readingTime: "9 min",
      lastVerified,
      status: "Current",
      blocks: [
        {
          kind: "definitions",
          items: [
            {
              term: "Observed location",
              definition:
                "An eligible retailer location where the exact product had an admitted positive-price Search observation in the collection.",
            },
            {
              term: "Not observed location",
              definition:
                "An eligible planned location where the exact product was not found in the admitted Search evidence. This is not proof of out-of-stock or confirmed non-carriage.",
            },
            {
              term: "In-stock / available",
              definition:
                "A product-location Search observation with price greater than zero. The platform does not substitute PDP stock for this store-specific signal.",
            },
            {
              term: "Distribution",
              definition:
                "Observed exact-product locations divided by the eligible retailer-location population under the current geography. It is distinct from in-stock among observed rows.",
            },
            {
              term: "Sponsored",
              definition:
                "Search is_sponsored=true for the product-location evidence. It is not a generalized promotion label.",
            },
            {
              term: "Package price",
              definition:
                "The positive Search shelf price for the offered package at that location.",
            },
            {
              term: "Unit price",
              definition:
                "Search package price divided by a Product Pack-governed, unambiguous package quantity, such as $/lb, $/gal, $/dozen, or $/each.",
            },
            {
              term: "Modal price",
              definition:
                "The price observed most often for the exact product in the selected retailer/geography. Ties follow the deterministic engine policy.",
            },
            {
              term: "IQR price exception",
              definition:
                "A location price outside Q1 − 1.5×IQR or Q3 + 1.5×IQR when the middle-50% range is nonzero. If it is zero, the Product Pack tolerance around the modal price is used.",
            },
            {
              term: "Matched observation",
              definition:
                "One benchmark product-location and one eligible competitor offer admitted under a named relationship, price basis, geography rule, and period.",
            },
            {
              term: "Lower-price share",
              definition:
                "The share of scored matched observations where the named retailer price is lower. The report must also disclose parity and the opposing retailer share.",
            },
            {
              term: "Paired median gap",
              definition:
                "The median of competitor price minus benchmark price across the same scored pairs. Positive means the benchmark is lower; negative means the competitor is lower.",
            },
            {
              term: "Product leadership",
              definition:
                "The store-level outcome for one benchmark product against the controlling eligible local competitor offer under the selected policy.",
            },
            {
              term: "Coverage",
              definition:
                "The portion of the intended comparison population with sufficient source, match, geography, freshness, and price evidence to score. Semantic, availability, and price coverage are separate.",
            },
            {
              term: "Whitespace / gap",
              definition:
                "A locally relevant assortment need where one retailer has an admitted product and the other has no governed eligible equivalent. It is not inferred solely from a missing Search row.",
            },
            {
              term: "Readiness",
              definition:
                "A deterministic result of evidence minimums, quality checks, comparison coverage, and policy requirements. AI prose cannot upgrade readiness.",
            },
          ],
        },
      ],
    },
    {
      id: "trust-gated-report-publication",
      group: "operations",
      title: "Trust-gated report publishing",
      summary:
        "How durable background materialization, semantic audits, retries, and atomic activation protect every future report.",
      audience: "Platform owner · Platform administrator · Engineering",
      readingTime: "7 min",
      lastVerified,
      status: "Current",
      links: [
        { href: "/admin/report-publishing", label: "Open Report Publishing" },
        { href: "/analyses", label: "Open current reports" },
      ],
      blocks: [
        {
          kind: "callout",
          tone: "success",
          title: "Safe replacement rule",
          text: "A new AnalysisResult is not an active report merely because deterministic analytics finished. It remains pending until every required read model is staged and the semantic trust audit passes. The currently certified report remains visible throughout.",
        },
        {
          kind: "steps",
          title: "Durable publication flow",
          items: [
            {
              title: "1. Queue",
              detail:
                "Creating the immutable governed publication activates one idempotent Postgres materialization job for the AnalysisResult.",
            },
            {
              title: "2. Claim with a lease",
              detail:
                "A worker replica claims the job with FOR UPDATE SKIP LOCKED. Heartbeats extend ownership; an expired lease is reclaimable, and maximum attempts are bounded.",
            },
            {
              title: "3. Stage deterministic read models",
              detail:
                "The worker stages the three default Price Architecture matrices and one Competitive Portfolio for every configured comparison basis at 1, 3, and 5 miles. Completed scopes survive an automatic retry, so successful work is not repeated unnecessarily.",
            },
            {
              title: "4. Run the semantic trust gate",
              detail:
                "The gate reconciles required document coverage, retailer and profile scope, product and relationship rollups, outcome partitions, denominators, rates, weighted gaps, product order, assortment agreement, geography policy, and monotonic 1/3/5-mile evidence behavior. Warnings disclose honest evidence limitations; errors block publication.",
            },
            {
              title: "5. Activate atomically",
              detail:
                "One database transaction installs the complete staged read-model set, records the audit, marks the replacement ready, and recoverably archives older ready reports in the same Product Pack lineage. Users cannot see a half-built replacement.",
            },
          ],
        },
        {
          kind: "definitions",
          title: "Administrator status meanings",
          items: [
            {
              term: "Awaiting publication",
              definition:
                "The immutable result exists, but its governed presentation context has not activated materialization.",
            },
            {
              term: "Queued / running",
              definition:
                "The durable job is waiting for or currently owned by a worker lease. Progress identifies the exact staged scope.",
            },
            {
              term: "Retry wait",
              definition:
                "A temporary failure released the lease and scheduled a bounded backoff. Completed staged scopes are retained.",
            },
            {
              term: "Blocked",
              definition:
                "Attempts are exhausted or a critical condition prevents activation. The prior trusted report remains current; an administrator may inspect the error and explicitly retry.",
            },
            {
              term: "Succeeded",
              definition:
                "All required documents and the semantic audit passed, and the atomic activation transaction completed.",
            },
          ],
        },
        {
          kind: "callout",
          tone: "information",
          title: "Cost and evidence boundary",
          text: "Report materialization uses retained normalized Search, location, PDP, certification, Product Pack, and publication evidence. It does not make a MetricsCart or OpenAI call. A retry never recollects paid source data.",
        },
      ],
    },
    {
      id: "five-category-trust-certification",
      group: "governance",
      title: "Five-category reporting trust certification",
      summary:
        "The Phase 13.30 acceptance baseline for Ground Beef, Strawberries, Bananas, Fresh Shell Eggs, and Fresh Fluid Milk.",
      audience: "Platform owner · Platform administrator · Engineering",
      readingTime: "9 min",
      lastVerified,
      status: "Current",
      links: [
        {
          href: "/analyses/fresh_ground_beef-b01158a0-6ac5-4d8d-9d57-6978cfd61d17-match-v2-a7fb8453-r4",
          label: "Open Ground Beef",
        },
        {
          href: "/analyses/fresh_strawberries-81e1dd0d-450d-49bb-a28c-b32de48ea51c-match-v2-4e6bddc0-r3",
          label: "Open Strawberries",
        },
        {
          href: "/analyses/fresh_bananas-3db3e46c-8a89-4519-9936-5e0c48161a5d-match-v2-00a5061c-r3",
          label: "Open Bananas",
        },
        {
          href: "/analyses/fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-3c967ecc-r3",
          label: "Open Fresh Shell Eggs",
        },
        {
          href: "/analyses/fresh_fluid_milk-19a350ee-90d7-4ec5-92f9-467a15c116b4-match-v2-28e0850f-r4",
          label: "Open Fresh Fluid Milk",
        },
      ],
      blocks: [
        {
          kind: "callout",
          tone: "success",
          title: "Five replacements are certified and active",
          text: "Each category has exactly one active certified replacement in its governed lineage. Every replacement passed exhaustive decision reconciliation, fail-closed relationship projection, all configured basis-by-1/3/5-mile materializations, semantic audit, all nine Competitive Intelligence workspaces, and Price Intelligence acceptance. Obsolete predecessors were archived only after those gates passed.",
        },
        {
          kind: "table",
          title: "Certified reporting baseline",
          columns: [
            "Category",
            "Final decisions",
            "Published views",
            "Semantic audit",
            "Production acceptance",
          ],
          rows: [
            [
              "Ground Beef",
              "51 comparable · 2 reviewed insufficient · 0 pending",
              "Strict and unit price × 1/3/5 miles",
              "0 errors · 0 warnings",
              "Competitive and Price Intelligence passed",
            ],
            [
              "Strawberries",
              "6 comparable · 0 pending",
              "Strict and unit price × 1/3/5 miles",
              "0 errors · 0 warnings",
              "Competitive and Price Intelligence passed",
            ],
            [
              "Bananas",
              "11 comparable · 0 pending",
              "Five profiles × 1/3/5 miles",
              "0 errors · 9 explicit warnings",
              "Competitive and Price Intelligence passed",
            ],
            [
              "Fresh Shell Eggs",
              "183 comparable · 1 not comparable · 1 reviewed insufficient · 0 pending",
              "Compatible and strict × 1/3/5 miles",
              "0 errors · 48 explicit warnings",
              "Competitive and Price Intelligence passed",
            ],
            [
              "Fresh Fluid Milk",
              "887 comparable · 177 not comparable · 0 pending",
              "All brand, private label, and same brand × 1/3/5 miles",
              "0 errors · 21 explicit warnings",
              "Competitive and Price Intelligence passed",
            ],
          ],
        },
        {
          kind: "definitions",
          title: "How to interpret the certification",
          items: [
            {
              term: "Certified relationship",
              definition:
                "A final human-governed comparable pair. The selected Product Pack profile separately determines whether that relationship belongs in the current inclusive, strict, private-label, same-brand, or unit-price view.",
            },
            {
              term: "Scored product-location comparison",
              definition:
                "A certified eligible relationship with admissible positive Search prices under the selected physical-store radius. Amazon Same Day remains explicitly labeled same-ZIP service-area evidence.",
            },
            {
              term: "Explicit warning",
              definition:
                "A truthful non-blocking limitation, such as no local pair within five miles or incomplete cohort attributes. It never becomes a price conclusion or stale fallback metric.",
            },
            {
              term: "Ready to share",
              definition:
                "The result has full metric-reference coverage, zero unsupported numeric claims, zero blocking semantic errors, no uncertified relationship leakage, and successful production acceptance.",
            },
          ],
        },
        {
          kind: "list",
          title: "Trust corrections included in this baseline",
          items: [
            "Certified match tiers and Product Pack profile constraints are applied independently and fail closed.",
            "Ground Beef labeled multipacks use the effective measure for unit-price math and cannot leak into strict package-price views.",
            "Milk profile eligibility uses the same current Search-derived attribute correction as Matching v2 candidate evidence without rewriting authoritative history.",
            "Large analyses receive a 30-second initial application fetch window instead of failing behind the former five-second timeout.",
            "Every warning remains visible; automatic fallback is disabled for all certified replacements.",
          ],
        },
        {
          kind: "callout",
          tone: "information",
          title: "Evidence and cost boundary",
          text: "Phase 13.30 rebuilt the five reports from retained governed evidence and made no MetricsCart or OpenAI call. Search data, raw objects, PDP evidence, certification history, immutable releases, portfolio materializations, archived AnalysisResults, and audit lineage were preserved. Archival is recoverable; deletion was not used.",
        },
        {
          kind: "list",
          title: "Known limitations retained honestly",
          items: [
            "Six Egg competitor retailers have certified identity but no competitor store pair within five miles, so their price scorecards remain explicitly unscored.",
            "Banana specialized empty views and Egg/Milk cohort-attribute gaps remain visible as warnings rather than hidden fallback values.",
            "Amazon Same Day is not assigned fictional physical stores or physical-store radii.",
            "This phase certifies snapshot reporting, not historical price movement.",
            "Phase 13.31 now materializes large reports through a durable leased background task with resumable progress, bounded retries, a fail-closed semantic gate, and atomic activation.",
          ],
        },
      ],
    },
    {
      id: "limitations",
      group: "reference",
      title: "Current limitations & honest boundaries",
      summary:
        "What exists but is not yet authoritative, what is intentionally deferred, and what an administrator must not overstate.",
      audience: "Platform owner · Platform administrator",
      readingTime: "6 min",
      lastVerified,
      status: "Current",
      blocks: [
        {
          kind: "list",
          items: [
            "Matching v2 is shadow/certification evidence and does not replace the authoritative report matcher until per-Product-Pack release gates pass.",
            "Automatic Matching v2 approval tiers are currently empty. Equivalent and substitute tiers remain human-approved.",
            "Egg Search evidence has material critical-attribute gaps; targeted PDP/label/vision evidence and human certification are required.",
            "Kroger Product Details uses the provider-catalog /kroger/pdp/zipcode/ route verified by a controlled HTTP 200 preflight on August 17.",
            "Reviewer identity is manually entered inside the protected admin session; individual accounts, verified identity, and RBAC are not yet implemented.",
            "Target marketplace seller rules are defined but not active until live seller values are certified.",
            "Product History is not presented until comparable cross-run snapshots, version compatibility, and continuity are certified.",
            "Exports, shareable HTML, leadership email, and workbook surfaces will be synchronized after the primary application experience is finalized.",
            "Population/county/demographic geography selectors await a governed data source and validation contract.",
            "Amazon Same Day remains a ZIP/delivery-market comparison rather than a fabricated physical-store model.",
            "A Search non-observation is inconclusive; it is not proof that a store does not carry a product or is out of stock.",
            "Five-region live Search acceptance is currently blocked: five sampled ALDI Strawberry pages returned billable HTTP 404 unavailable-page responses on August 22. The gate prevented Walmart, Amazon, and the sixth ALDI call, so regional collection and reporting are not yet certified.",
          ],
        },
      ],
    },
    {
      id: "change-orders",
      group: "reference",
      title: "Change orders & documentation maintenance",
      summary:
        "How product decisions are recorded and how these docs stay synchronized with implementation, testing, and production.",
      audience: "Platform owner · Platform administrator · Engineering",
      readingTime: "7 min",
      lastVerified,
      status: "Current",
      blocks: [
        {
          kind: "callout",
          tone: "information",
          title: "Definition of done",
          text: "A workflow, metric, source-authority, cost, security, API, service, admin, testing, or presentation change is not complete until the affected guide is updated and a change-order entry is added. Planned behavior must never be described as current production behavior.",
        },
        {
          kind: "steps",
          title: "Required change-order process",
          items: [
            {
              title: "Record the decision",
              detail:
                "State the requested outcome, reason, owner, approval, and whether it changes authoritative behavior or only presentation.",
            },
            {
              title: "Assess impact",
              detail:
                "Inventory contracts, database, API, worker, scheduler, UI, metrics, costs, secrets, audit evidence, fixtures, goldens, and historical compatibility.",
            },
            {
              title: "Update implementation and docs together",
              detail:
                "Revise the applicable guide, plain-language definitions, limitations, links, and the repository phase/architecture record in the same change.",
            },
            {
              title: "Verify",
              detail:
                "Run proportional unit, contract, integration, golden, browser, migration, build, and production checks. Capture any paid-call or AI spend approval.",
            },
            {
              title: "Append the change order",
              detail:
                "Add date, status, summary, affected workflows, compatibility decision, and verification evidence. Never rewrite an older entry to hide history.",
            },
            {
              title: "Deploy and re-read",
              detail:
                "Verify the live behavior, then read the changed guide as an administrator. Correct anything that describes intent rather than reality.",
            },
          ],
        },
        {
          kind: "table",
          title: "Change-order log",
          columns: ["Date", "Status", "Change", "Operational effect"],
          rows: [
            [
              "2026-08-23",
              "Implemented and test-verified; production recovery pending",
              "Product Details contracts gained fixed request parameters and retailer-fair parallel queue claiming.",
              "A controlled Walgreens diagnostic proved that the historical SFS request context produced HTTP 400 while the same observed product, store, and ZIP returned HTTP 200 with fulfillment_type=pickup. The catalog now fixes provider-required parameters after observation values, preserving Search fulfillment as evidence without sending it to an incompatible PDP contract. Queue claims round-robin retailers within priority and the default claim concurrency rises from one to 18; the shared Postgres retailer/type limiter, credit ceiling, SKIP LOCKED claims, leases, retries, cancellation, and idempotency remain authoritative. The initial Spring Valley run completed 1,816 successes and 615 explicit failures for 4,578 credits ($9.156), below its $15 ceiling. No AI call was made.",
            ],
            [
              "2026-08-23",
              "Deployed, owner-approved, and actively processing",
              "Live Search PDP qualification gained an explicit USD-denominated hard ceiling and cross-run duplicate-work guard.",
              "The owner approved $15.00, which converts to a 7,500-credit ceiling at the governed $0.002-per-credit rate without rounding up. The final production gate found 2,431 admitted distinct products, 2,431 valid retailer requests, zero endpoint-ineligible products, zero raw-checksum failures, zero fresh exact-context cache hits, and a 5,336-credit / $10.67 maximum plan. Durable run 9e03fc83-8e2f-4700-9464-d951021ebac7 contains all 2,431 jobs. Exact request checksums already queued or running in another active run block a duplicate launch. Canonical contexts record both immutable live Search run IDs, Pack 1.0.2, observed location, Search price, and selection reason; Search remains price and availability authority. No AI work is created.",
            ],
            [
              "2026-08-23",
              "Implemented and test-verified; deployment and bounded paid pilot pending",
              "Spring Valley vitamins gain a reusable Product Pack, four additional Search-by-ZIP retailers, and governed multi-keyword collection planning.",
              "The immutable 1.0.0 foundation is preserved, and governed Product Pack 1.0.1 keeps Spring Valley as Walmart's private-label anchor while ingredient, strength, strength unit, dosage form, package quantity, serving quantity, release profile, and audience govern exact- and compatible-spec comparisons without a category branch in the engine. The owner-supplied workbook is preserved as an auditable 85-keyword, 322-product anchor catalog. Its Walmart product IDs form an explicit allowlist, and both governed comparison profiles independently require the Spring Valley benchmark brand; other Walmart Search results remain retained raw evidence but cannot enter matching or reporting. Package, item, and serving price bases remain distinct. USP, NSF, MSC, or other certifications require PDP text or label-image evidence; a generic markdown is not labeled Rollback without explicit Walmart evidence. Catalog-driven BJ's, Costco, CVS, and Walgreens Search adapters use provider-safe Store_No plus ZIP contracts, including the owner-verified trailing-slash CVS and Walgreens paths. Collection definitions may carry one keyword plus an optional deduplicated list of up to 500; task and maximum-credit estimates expand per keyword while location counts retain their location grain. Search remains the only approved paid boundary in this pilot. PDP is separately approved after Search qualification and reuses successful evidence for 30 days.",
            ],
            [
              "2026-08-22",
              "Deployed and production-verified",
              "Phase 13.41 changes the governed Product Details freshness default from seven days to 30 days.",
              "Search remains collection-cadence and store-authoritative for price, availability, and sponsorship. PDP planning continues after scope filtering and selects one representative observed context per distinct admitted retailer product. A fresh normalized HTTP 200 snapshot is reused at zero credits; only new, missing, unsuccessful, explicitly refreshed, or at-least-30-day-old identity evidence is eligible for a paid PDP call. The worker, immutable-raw recovery path, environment template, and Railway deployment guide share the 2,592,000-second default. Commit c100b66 is live and the production worker reports 2,592,000 seconds. A bounded operational transition extended 2,768 successful normalized HTTP 200 snapshots to observed_at plus 30 days; the post-check found zero eligible snapshots remaining on the former expiration. Raw payloads, observed timestamps, failures, audit lineage, Search data, and prices were untouched. GitHub Actions run 32615296706 passed every Python, TypeScript, contract, reversible-migration, browser, build, and service-container gate. No Search, PDP, or AI call was made.",
            ],
            [
              "2026-08-22",
              "Live-paid diagnostic completed and production-verified",
              "Phase 13.40 isolates ALDI Search keyword, Store_No, and alternate location-ID behavior with five exact provider attempts.",
              "The production /mc/new_aldi/serp/zipcode adapter returned HTTP 200 for Beef and Milk at the 44432 / 36873 playground control and for Milk at 44906 / 463-048. Beef at 06418 / 473-054 returned the same billable HTTP 404 seen for Milk, proving that failure is location-specific rather than keyword-specific. Replacing Store_No with mc_location_id 2013023 returned a non-billable HTTP 500, so Store_No plus normalized ZIP remains authoritative. Exactly five attempts ran with max_attempts=1, no retries, and eight actual credits (approximately $0.016) under the approved 10-credit ceiling. Every response is preserved with an immutable checksum. The terminal alternate-ID failure correctly stopped the first Beef gate; its uncalled control was completed in a separate immutable one-page recovery run instead of rewriting history. No Walmart, Amazon, PDP, AI, normalization, or report work ran.",
            ],
            [
              "2026-08-22",
              "Deployed and production-verified",
              "Phase 13.39 replaces the run-wide availability gate with durable retailer-isolated decisions.",
              "Walmart, Amazon Same Day, and every selected competitor now receive independent bounded preflights. One request per retailer may be in flight; healthy retailers release immediately, while a retailer stops as soon as its 404 threshold is unrecoverable or a terminal non-404 error occurs. Mixed outcomes remain auditable as partial, retries reopen only the affected retailer, the monitor shows retailer-specific evidence, and failed inputs download as CSV. Commit 34dc2cc and GitHub Actions run 32600392203 passed real-Postgres queue tests, migration upgrade/downgrade/upgrade, Python and TypeScript release gates, 14 browser tests, and all four service-container builds. Production displayed the expected eight passed and four failed retailer decisions for the historical Egg preflight; Walmart and Amazon were correctly not assigned invented backfill evidence because that run predates their gates. The live failure CSV download started successfully. No MetricsCart, PDP, or AI call was made.",
            ],
            [
              "2026-08-22",
              "Fourteen-retailer boundary deployed; provider-safe location gate test-verified; bounded preflight pending",
              "Phase 13.38 expands the catalog-driven MetricsCart Search-by-ZIP boundary to all 14 Fresh Shell Egg retailers.",
              "The owner-supplied 2026-08-16 catalog governs all 14 endpoint paths, credits, parameters, defaults, pagination, and sample contracts. Shared Postgres throttling is partitioned by Search × retailer, and availability samples are evaluated separately so one retailer's successes cannot mask another retailer's 404-heavy gate. Production import fe5e3985-947f-433c-a61c-2fa67f7ebcfa preserved 157,806 source rows with zero skips and supplied all 13 physical-retailer rosters. A provider-safe eligibility policy prevents malformed source identifiers from entering new collection plans without deleting them: 377 Albertsons suffix rows and 114 Wegmans composite/corrupted rows remain auditable but excluded, leaving 376 and 114 eligible stores respectively. All other enabled rosters retain their active provider-safe IDs, including 2,627 ALDI stores. Frozen historical geographies do not change. The release passes 652 Python tests, 72 web tests, mypy, contracts, lint, type checking, and migration-head validation. No provider, PDP, or AI call was made; paid preflight and full collection require separate exact approval.",
            ],
            [
              "2026-08-22",
              "Updated-roster ALDI regional preflight completed; broad rollout remains blocked",
              "Phase 13.37 tested five different active ALDI store/ZIP pairs from the freshly imported MetricsCart roster under an exact 10-credit owner approval.",
              "Run c0f76364-3380-45b7-95cc-60b0a908cf31 made five first-page ALDI Strawberry Search calls and no other provider or AI call. Florida store 482-033 / ZIP 32548 returned HTTP 200 with 14 contract-valid results; California 479-001 / 92399, Illinois 464-033 / 60073, Ohio 461-019 / 45013, and Pennsylvania 469-051 / 15301 returned the same nonretryable billable HTTP 404 unavailable-page body. All compressed objects, decompressed bodies, and byte sizes reconcile; the successful page passed contract 1.0.0, the shared 31-field inventory, positive-price availability authority, and is_sponsored authority. The run used exactly 10 credits (approximately $0.02) with zero retries or 429s. The ALDI-only scope intentionally produced no user-facing competitive report; its generic downstream analysis job failed the required non-empty comparison contract after three bounded attempts and remains visible only as audit history. This proves the adapter remains valid but the active roster is not a callability catalog. Broad ALDI collection remains blocked pending provider-supported regional coverage.",
            ],
            [
              "2026-08-22",
              "Current ALDI location roster reconciled and imported; regional Search availability remains unproven",
              "Phase 13.36 versioned the owner-supplied MetricsCart ALDI roster and refreshed the canonical location dimension without changing historical geography snapshots.",
              "The checksummed source contains 2,627 unique active USA store numbers and MetricsCart location IDs across 40 states and 2,499 normalized ZIPs, with no missing required geography. Its store and physical-location universe is identical to the prior master. Seventy-nine raw ZIP representations normalize identically and the same 79 rows receive corrected MetricsCart location IDs in CT, MA, NH, NJ, RI, and VT. Every prior ALDI diagnostic store/ZIP pair is unchanged, and Search uses Store_No plus ZIP rather than mc_location_id, so the refresh does not cure or explain regional billable 404s. Eleven exact-address/coordinate pairs with two active store numbers remain an explicit North Carolina governance exception before all-location collection. Production import 7c394c4b-2b55-4505-b3c7-ca9e6dbff317 completed 2,627 rows with zero skips; the frozen control geography checksum remains unchanged. Commit 7cd9995 and GitHub Actions run 32588635469 passed the full release gate. No MetricsCart, PDP, or AI call was made.",
            ],
            [
              "2026-08-22",
              "Live-paid ALDI control diagnostic completed; regional coverage remediation required",
              "Phase 13.35 isolated the current ALDI Search contract with one known-success control and one failed-region store/ZIP pair.",
              "Run 0eb24781-e930-4532-9ce3-28be75eaf31d used the exact no-trailing-slash /mc/new_aldi/serp/zipcode route and only keyword, ZIP, store, and page. Control store 463-048 / ZIP 44906 returned HTTP 200 with 15 contract-valid results; California store 479-098 / ZIP 93215 returned a nonretryable billable HTTP 404. Both raw gzip and decompressed body checksums reconcile, and the 404 body matches the prior unavailable-page response. The run completed with warnings, passed the two-sample gate at the configured 50% maximum 404 rate, used exactly four of four approved credits (approximately $0.008), and made no retry, Walmart, or Amazon call. This rules out an ALDI-wide endpoint or trailing-slash defect and retains the adapter unchanged. The diagnostic-only scope produced no user-facing report; its generic no-competitor analysis attempts failed the non-empty comparison contract and remain visible in audit history. The failed multi-region scope will not be replayed until current ALDI regional store coverage is refreshed or validated and replacement pairs pass a new bounded preflight.",
            ],
            [
              "2026-08-22",
              "Live-paid multi-region acceptance blocked safely; diagnostic required",
              "Phase 13.34 exercised the production ALDI availability gate across five Strawberry regions before broader live Search rollout.",
              "Run e9f163bd-024d-4a53-87e6-1141f2975cc9 attempted five of 16 planned pages. All five ALDI samples returned the same billable HTTP 404 unavailable-page body, so the 100% 404 rate exceeded the 50% gate threshold. Ten of 27 approved credits were consumed (approximately $0.02); the gate prevented the remaining 17 credits, including every Walmart and Amazon call and the sixth ALDI call. There were no retries or 429s. All raw gzip and decompressed checksums reconcile. Every sampled store/ZIP pair exists in the location master and produced 13–15 retained Strawberry rows on August 7, while the same endpoint contract passed the prior-day one-ZIP pilot. The evidence therefore does not justify an adapter change or prove bad locations. No normalization, analysis, or report was produced, and full-location rollout remains blocked pending a separately approved two-location ALDI control diagnostic.",
            ],
            [
              "2026-08-22",
              "Live-paid acceptance passed; contract, raw evidence, normalization, analysis, and reporting verified",
              "Phase 13.33 validated the production MetricsCart Search-by-ZIP boundary with a hard-capped three-retailer Strawberry pilot.",
              "Run 4ac82ffa-7ec6-4175-86ed-6bc0ffbbb928 completed three of three pages on the first attempt: Walmart returned 44 rows for one credit, ALDI 15 for two, and Amazon Same Day 16 for two. All 75 raw, normalized, and classified rows reconciled; compressed and decompressed checksums, byte sizes, task counts, stored audits, contract version 1.0.0, result path, price authority, and sponsorship authority passed with no schema drift. The call cost was approximately $0.01 at the owner-supplied $0.002-per-credit rate. Search did not supply seller and brand was sparse, so retailer site identity remains insufficient for first-party proof and PDP/brand-governance evidence remains required. No adapter repair was necessary. After acceptance, blocked smoke AnalysisResult 19f4d89d-c276-4a23-88f1-d28c0ce43ba2 was recoverably archived with a dedicated audit event; exactly five ready active certified reports remain while all collection, raw, analysis, cost, and audit lineage stays preserved. Commit 4593859 and GitHub Actions run 32553613136 passed the complete release gate.",
            ],
            [
              "2026-08-21",
              "Deployed, contract-audited, replayed, semantically audited, and production-verified",
              "Phase 13.32 makes MetricsCart Search by ZIP APIs the only mechanism for new collections and pins a fail-closed live response contract before controlled Strawberry and Milk publication acceptance.",
              "The 2026-08-16 owner-supplied catalog hashes and 14 representative Search endpoint samples govern explicit field aliases and source authority. Positive Search price is observed/in-stock authority; Search is_sponsored is sponsorship authority and may be null. Recognized empty arrays stop pagination, while unknown shapes, non-object rows, missing required identity, nonnumeric price, or incompatible sponsorship types retain the raw billable page and fail as nonretryable schema_drift. Historical CSVs remain reproducible evidence only. Walmart, ALDI, and Amazon Same Day remain the only enabled V1 Search adapters; every additional catalogued retailer requires controlled endpoint, location, billing, and payload preflight. Strawberry generation 4 completed 10/10 durable stages with zero semantic errors or warnings. Milk generation 5 completed 13/13 durable stages with zero semantic errors and 21 explicit nonblocking disclosures. Each old report stayed ready until its replacement activated, then was recoverably archived. Exactly five active reports remain, all ready. Commit e50f538 and GitHub Actions run 32548641460 passed the full release gate. No MetricsCart, PDP, or OpenAI call was made.",
            ],
            [
              "2026-08-21",
              "Deployed, migration-verified, and production-verified",
              "Phase 13.31 made semantic trust certification an automatic publication gate and moved report materialization to a durable background job.",
              "New results remain pending while a leased worker stages Price Architecture and every configured basis-by-1/3/5-mile Competitive Portfolio. Completed scopes resume after transient failure; retries are bounded; administrators see stage, progress, attempts, errors, warnings, and audit counts. One final transaction installs the complete read-model set, marks the replacement ready, and recoverably archives its predecessor. A blocked replacement never displaces the current trusted report. Commit 59b2187 and GitHub Actions run 32545856295 passed Python, TypeScript, browser, migration upgrade/downgrade, and all four service-container gates. Railway deployed the commit and ran migration 0044_report_pub_gate. Production reconciliation found exactly five active results, all ready, no pending or blocked active result, and no unintended materialization job. The worker module and administrator progress page both passed live checks. No MetricsCart or OpenAI call was made.",
            ],
            [
              "2026-08-21",
              "Deployed, replayed, semantically audited, production-verified, and certified",
              "Phase 13.30 established one trusted active reporting replacement for each of the five original categories.",
              "Ground Beef, Strawberries, Bananas, Fresh Shell Eggs, and Fresh Fluid Milk passed exhaustive certification reconciliation, fail-closed profile eligibility, every configured basis-by-1/3/5-mile materialization, semantic audits with zero errors, all nine Competitive Intelligence workspaces, and Price Intelligence acceptance. Corrections cover certified-tier leakage, multipack effective measures, role-specific Product Pack profiles, current Search evidence at the Milk profile gate, and large-report initial load tolerance. The final lineage reconciliation found exactly five active certified replacements and no active predecessor in those same lineages. Obsolete predecessors were recoverably archived only after replacement acceptance; source Search data, raw objects, PDP evidence, certification history, immutable releases, materializations, archived results, and audit lineage remain preserved. No MetricsCart or OpenAI call was made during the phase.",
            ],
            [
              "2026-08-21",
              "Deployed, refreshed, semantically audited, and production-verified",
              "Displayed Price and Competitive Intelligence metrics were reconciled across product, relationship, cohort, assortment, geography, and price-architecture grains.",
              "The audit reconciled every one of 649 Walmart Milk products to the same 4,683-store identity universe, including observed/not-observed counts and percentages; reconciled all 174,883 positive Search observations to the product and category price distributions; validated positive prices and ordered price ranges; and reconciled all 859 products in the Price Architecture Matrix, including 57 collapsed records. Competitive scorecard status partitions, weighted gaps, included-product identities, relationship ledgers, store-level outcomes, exceptions, geography rows, ladders, and certified basis populations were checked against their materialized evidence. Corrections prevent a narrower comparison basis from retaining an ineligible product and displaying a false all-zero view; calculate assortment match coverage only from certified identities actually observed in Search; replace stale exact-ZIP assortment narrative with the selected 1/3/5-mile evidence; and disclose certified relationships excluded from cohorts because governed attributes are incomplete. All nine Milk basis-by-radius documents were rebuilt from retained evidence with zero provider calls. The enhanced semantic audit passed with zero errors and 12 explicit warnings: nine disclose incomplete cohort-attribute signatures and three are the expected ALDI same-brand no-relationship states. All report tabs and Price Intelligence workspaces load without NaN, undefined, stale loading, or server-error states. Commit 1491df1 and GitHub Actions run 32499229475 passed the full release gate. No Search data, PDP evidence, certification outcome, provider call, AI call, immutable release, or audit lineage changes.",
            ],
            [
              "2026-08-21",
              "Deployed, replayed, semantically audited, and production-verified",
              "Certified product relationships are segmented into reporting views by each Product Pack's governed brand policy.",
              "Certification remains the authority on comparability, while reporting eligibility now distinguishes inclusive ignore-brand, strict private-label-equivalent, and normalized same-brand views. The unchanged 1,064-label gold set contains 887 comparable and 177 not-comparable outcomes. Corrected replay generation two (run 45ab5aba-c993-4f47-bcf1-b70e4d1982eb; AnalysisResult d643df96-4686-4e29-8479-374d13b823a2) retains 887 All Brand relationships, 87 Private Label relationships, and 49 Same Brand Exact relationships. All nine basis-by-1/3/5-mile documents materialized and the semantic audit passed with zero errors; three explicit warnings are the expected ALDI same-brand no-relationship states. Metric-reference coverage is 100%, unsupported numeric claims are zero, and automatic fallback is disabled. Live controls change the relationship population and physical-store radius evidence, while Amazon Same Day correctly remains same-ZIP service-area evidence. Exactly one active Milk result remains. The rejected first-generation result was recoverably archived with an audit event; no source, PDP, certification, immutable release, materialization, superseded report, or audit lineage was deleted. Commit ab89783 and GitHub Actions run 32485954699 passed the full release gate; no provider or AI call was made.",
            ],
            [
              "2026-08-20",
              "Deployed; corrected queue imported and AI-assisted; human certification pending",
              "Milk Matching v2 candidate generation now requires observed footprint evidence and fails closed on essential package-spec uncertainty.",
              "The rejected 6,396-case queue is not used. Product Pack 1.6.0 and policy 2.1.0-shadow.1 require physical-store overlap within five miles or same-ZIP Amazon Same Day service-area overlap, retain brand-independent regional matching, and separate attribute exclusions from no-geography exclusions. Current title evidence can correct a contradictory static override only inside candidate evidence with explicit provenance; authoritative classification and historical metrics remain unchanged. Numeric indexing treats 64 and 64.0 equally and honors tolerance. Production queue 2.5.0 contains 1,064 unique cases—253 ALDI and 811 Amazon—with zero duplicate pairs, missing essential volume/fat evidence, known seller-ineligible listings, or obvious title/fat contradictions. AI batch c1192df2-b766-44a7-b642-84f1c3549eff completed all 1,064 drafts with zero terminal failures at an estimated model cost of $34.4601425. The guarded preview proposes 887 comparable and 177 not-comparable outcomes; every recommendation still requires explicit human confirmation and none automatically changes reporting. No Search, PDP, prior queue, decision, report, or audit lineage was deleted.",
            ],
            [
              "2026-08-20",
              "Deployed, replayed, semantically audited, and production-verified for three categories; Milk remains fail-closed",
              "Certified multi-category replays now project governed identity only through exact-location Product Pack profiles before radius-native reporting.",
              "The exhaustive operational Banana, Strawberry, and Ground Beef queues preserve 70 prior final decisions only after exact Product Pack, policy, pair, and structured-evidence reconciliation; added images and observed-location counts remain additive evidence. The worker no longer sends certified relationships through obsolete radius profiles or mistakes unknown-value policy for tier eligibility. The active replacements are ready to share, have full metric-reference coverage and zero unsupported numeric claims. Their 27 portfolio documents cover every configured comparison basis at 1, 3, and 5 miles and pass the semantic audit with zero errors; three Banana warnings explicitly identify no-scored-evidence views. A concurrency-safe immutable Product Pack cache prevents large Ground Beef projections from stampeding Postgres. Production Competitive Intelligence and Price Intelligence routes pass. All exact predecessors were already recoverably archived; no Search data, raw object, PDP evidence, certification history, materialization, failed replay, or audit lineage was deleted. At this checkpoint Milk remained fail-closed behind a 6,396-case Product Pack 1.5.0 scope; the following change order rejects and supersedes that queue. No provider or AI call was made.",
            ],
            [
              "2026-08-20",
              "Deployed, semantically audited, and production-verified",
              "The certified Egg release now drives one accepted radius-native Competitive Intelligence report, and its superseded reports are recoverably archived.",
              "Generation two retained all 183 certified-comparable relationships and materialized Compatible-spec and Strict exact-spec at 1, 3, and 5 miles. The six-document semantic audit passed with zero errors; 51 explicit warnings describe honest no-scored-evidence limitations. Compatible-spec exposes all 13 competitors, with locally scored price evidence for seven and zero-scored identity continuity for six. Production API, all nine report tabs, retailer/basis/radius controls, included-product evidence, maps, and export controls passed live acceptance with a clean browser console. The no-query landing now defaults to the broadest certified Compatible-spec basis and its executive summary is derived from the same radius-native document instead of legacy exact-ZIP narrative. GitHub Actions runs 32433669906 and 32434666036 passed the complete gates. Only after validation, four exact obsolete Egg AnalysisResults were recoverably archived; no Search data, raw object, PDP evidence, review or certification history, immutable release, materialization, or audit lineage was deleted.",
            ],
            [
              "2026-08-20",
              "Test-verified; deployment and governed replay pending",
              "Matching v2 releases distinguish final human insufficient-evidence exclusions from cases that still lack review.",
              "The final Egg Kroger case is complete with an insufficient-evidence disposition because required housing-method evidence remains unknown. Gold-set 2.0.0 now preserves that outcome in a separate immutable exclusion ledger, changes the release checksum, retains reviewer/rationale/evidence provenance, and reconciles it to the current queue transactionally. Report readiness blocks only candidates without a final human outcome; reviewed exclusions remain outside comparable and not-comparable metrics and appear as explicit warnings. No relationship is inferred, no provider call occurs, and no source data, PDP evidence, certification history, or audit lineage is deleted.",
            ],
            [
              "2026-08-20",
              "Deployed and release-gate verified; governed replay and production acceptance pending",
              "Matching v2 certified identity is preserved independently of exact-ZIP price overlap, with a fail-closed Egg reporting acceptance audit.",
              "A governed replay now begins with every certified-comparable gold-set pair and carries eligible relationships into 1/3/5-mile scoring even when the products were never co-observed in one ZIP. Worker and report-readiness reconciliation block missing or invented relationships overall and per retailer; assortment and Product Pack cohorts retain the same certified relationship population. Publication refuses a report with blocking readiness defects, then audits all comparison-basis × 1/3/5-mile materializations for count partitions, rates, product and relationship rollups, retailer scope, denominator stability, and monotonic radius behavior. The correction addresses the prior loss of Sam's Club, ShopRite, and Trader Joe's relationships. GitHub Actions run 32427778056 passed contracts, reversible Postgres migrations, Python and TypeScript gates, 13 browser tests, production builds, and all four service containers; Railway API and worker services expose the new code from commit 04aab97. The platform owner subsequently completed the final Egg Kroger case with an explicit insufficient-evidence disposition; no automatic decision, paid provider call, source deletion, or history mutation occurs.",
            ],
            [
              "2026-08-20",
              "Deployed and production-verified",
              "Observed Brand Breadth product evidence no longer links to the separate Price Intelligence product-footprint workspace.",
              "Brand drill-downs retain the complete governed product list, imagery, identities, and observed-location counts while removing the cross-module Open product footprint action. Live Egg verification opened Walmart Great Value directly from Observed Brand Breadth, reconciled all 43 product records, and found zero footprint links in the drawer. GitHub Actions run 32424338633 passed contracts, formatting, lint, type checking, all Python and web tests, 13 browser tests, reversible migrations, production builds, and all four service containers. Other assortment evidence paths preserve their existing behavior. No metric, brand membership, Search evidence, PDP evidence, certification decision, or audit lineage changes.",
            ],
            [
              "2026-08-20",
              "Deployed and production-verified",
              "Retailer Scorecards now expose every Walmart and competitor product included in certified relationships.",
              "Competitive portfolio schema 1.2.0 adds paired relationship evidence with both product identities, imagery, competitor brand context, comparison basis, and relationship-selected local outcomes. The action count includes distinct products from both retailers, and the drawer renders compact Walmart-versus-competitor rows searchable by either product name, ID, or competitor brand. Stored schema 1.1.0 portfolio materializations rebuild from retained certified evidence instead of serving the prior Walmart-only drill-through. All six Egg portfolio documents were refreshed with zero provider calls. Live Target verification found 15 distinct products (nine Walmart and six Target) across 12 complete relationship rows; images render at 58 pixels, the 980-pixel drawer has no horizontal overflow, competitor-ID search works, and the console is clean. GitHub Actions run 32422896275 passed the full release gate. Aggregate scorecard formulas and selection rules are unchanged; no report, source evidence, certification history, or audit lineage is deleted.",
            ],
            [
              "2026-08-20",
              "Deployed and production-verified",
              "Retailer and Cohort Scorecard presentation was reconciled without changing radius-native metrics, and assortment brand drawers now preserve governed brand membership.",
              "Retailer Scorecards restore the prior high-density table presentation while continuing to consume pre-materialized certified product-location outcomes. Included-product evidence uses 58-pixel bounded imagery, readable wrapping, search, pagination, and reconciling product/location totals; live measurement found no horizontal drawer overflow. Cohort Scorecards explicitly separate overall retailer Price Position from Product Pack Segment Drivers and Reversals, suppress the legacy duplicate tables, and export both views to CSV or Excel. Observed Brand Breadth opens the complete retailer brand list; every brand links to all products assigned to that exact governed Search brand identity even when PDP supplies a different display label. Live Egg reconciliation checked all 161 retailer-brand rows with zero count-to-product-membership mismatches, including the historical blank-Search-brand/PDP-brand edge case. GitHub Actions run 32420363332 passed the full Python, contract, migration, TypeScript, build, and 13-test browser suite. This is a presentation and evidence-join correction only: no metric formula, source evidence, certification decision, report archive, provider call, or AI call changes.",
            ],
            [
              "2026-08-20",
              "Deployed and production-verified",
              "Cohort and Assortment Scorecards now consume the radius-native competitive portfolio and gain durable publication-time read models.",
              "Cohort rates, medians, gaps, denominators, and product contributions are projected by the API from certified product-location outcomes under the selected retailer, basis, geography, and 1/3/5-mile context; the browser no longer presents legacy exact-ZIP cohort metrics. Assortment preserves global product/brand breadth while adding explicit local comparable coverage and clickable evidence cards. Migration 0043_competitive_portfolio_materialization stores one all-retailer document per immutable analysis, profile, and radius; publication builds these documents sequentially with bounded inner concurrency and zero provider or AI calls. The Egg publication materialized six documents in 236.6 seconds. Compatible-spec exposes 104 certified relationships, 41 cohorts, and 7,597 / 13,596 / 16,846 scored product-locations at 1 / 3 / 5 miles; strict exact-spec exposes four relationships, five cohorts, and 508 / 519 / 531 scored product-locations. Every populated scorecard reconciles Walmart-lower, competitor-lower, and parity to 100%, and cached API reads completed in 2–25 ms. GitHub Actions run 32405497085 passed 597 Python tests, 66 web/contract tests, 13 browser tests, reversible migrations, builds, and all four containers. State/city variants remain on-demand. No report or source evidence was archived by this change.",
            ],
            [
              "2026-08-20",
              "Deployed and production-verified",
              "Price and Competitive Intelligence reporting navigation, radius scorecards, matrix evidence, maps, exports, and workspace consolidation were aligned to the decision workflow.",
              "Price Intelligence Home no longer offers a duplicate Store Review action; matrix products are ordered by observed footprint and display PDP seller evidence. Competitive Intelligence renames the executive and cohort workspaces, adds a matched-product matrix, merges market KPIs and the geographic scorecard into Competitive Footprint, moves exceptions into Store Comparisons, removes duplicate Market Performance and report Data Integrity tabs, and adds CSV/Excel evidence exports. The new portfolio scorecard contract computes certified product-location outcomes using the selected physical-store radius or explicitly labeled service-area ZIP rule; Walmart-lower includes clear and narrow leads while clear-leader remains separate. Production ALDI reconciliation holds 5,377 Walmart product-locations constant while scored overlap grows monotonically from 1,572 at one mile to 2,825 at three and 3,356 at five; Walmart-lower, competitor-lower, and parity reconcile to 100% at every radius. The current Egg matrix was refreshed with zero provider calls: all 346 populated cells sort products by observed footprint, 645 of 680 products retain supplied PDP seller names, and all 680 retain seller-governance status. GitHub Actions run 32401469538 passed 599 Python tests, 66 web/contract tests, 13 Playwright tests, migrations, type/lint/format/contract gates, production builds, and all four containers. No report was archived in this release. Obsolete publications may be recoverably archived only after their replacements validate; source Search data, PDP evidence, certification decisions, and audit lineage are never deleted.",
            ],
            [
              "2026-08-20",
              "Deployed and production-verified",
              "Fresh Shell Eggs Product Pack 1.2.3 removes prepared-food, substitute, appliance, bakery, and personal-care scope noise and adds fail-closed scope-only certification continuity.",
              "A full 393,110-row source rebuild removes 47 product identities and 5,651 observations while retaining the exact same 185 governed listing pairs across 13 competitors. Queue 4.0.0 carried all 184 finalized decisions from its exact predecessor and left one unresolved case. Gold-set release 80afd160-5d31-45ff-a5bb-ac36bd648a38 produced immutable replay fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-80afd160 with 183 comparable, one not-comparable, one unresolved, and automatic fallback disabled. Publication pre-materialized all three default matrix methods; live validation found 83 ascending Walmart-anchored rungs, 172 priced Walmart SKUs, 508 competitor SKUs, complete product IDs/location counts, zero known third-party sellers, and zero governed scope-noise titles. Compatible-spec exposes 11,062 matched observations across 11 competitors; strict exposes 537 across three. No paid provider or AI call was made. GitHub Actions run 32336364329 passed every gate.",
            ],
            [
              "2026-08-19",
              "Deployed and production-verified",
              "Price Architecture Matrix gained low-to-high price order, exact brand filtering, product-footprint and seller evidence, plus durable pre-materialization.",
              "Each visible product now carries its retailer product ID and distinct observed-location count. Known third-party marketplace sellers remain excluded while verified-first-party, seller-unverified, and not-governed states remain explicit. Exact brand filters preserve Walmart's reference rungs. Migration 0042_price_arch_matrix stores parameter-scoped matrix documents; both API publication and worker publication pre-materialize the three default matrix methods, while other filter combinations persist after first use. Both retained Egg generations were materialized in Railway with three default matrices apiece and zero paid provider calls. The current generation returns its stored 83-rung, 14-retailer matrix in about 0.6 seconds. GitHub Actions run 32332101868 passed all Python, mypy, contract, migration, TypeScript, browser, build, and container gates.",
            ],
            [
              "2026-08-19",
              "Deployed and production-verified",
              "Price Intelligence gained a cross-retailer Price Architecture Matrix independent of product matching.",
              "Walmart's distinct product-level median positive Search shelf prices define the primary rungs, with true midpoint boundaries; fixed $0.50 and $1.00 bands support stable longitudinal comparison. Every eligible SKU is assigned exactly once by price alone. Cells toggle among product evidence, SKU count, assortment share, distinct-union store coverage, average price, and finite-band price density, and open a product evidence drawer. Brand and geography filters apply to the canonical first-party product-location population. Empty cells remain explicitly inconclusive rather than asserting assortment absence. Fixed grids use Walmart-bounded open edge bands so competitor outliers stay visible without generating empty rows. The Egg production view exposes 83 anchored rungs or 23 fixed $0.50 bands across 14 retailers; metric switching, private-label filtering, and the evidence drawer were verified live. Revision-aware API caching retains the complete retailer set, and the web proxy cannot serve stale matrices. GitHub Actions runs 32304567351 and 32305117053 passed Python, contracts, migrations, TypeScript, 13 browser tests, builds, and all four service containers.",
            ],
            [
              "2026-08-19",
              "Deployed and production-verified",
              "Governed Matching v2 releases support explicit immutable current-code rebuild generations.",
              "A normal source-analysis plus gold-set replay remains idempotent. A forced rebuild now requires a non-empty audit reason, serializes concurrent generation allocation, increments replay_generation, and produces a new analysis ID with an -rN suffix while retaining the exact source result, Product Pack, gold-set release, checksum, coverage, certified labels, and automatic-fallback prohibition. The prior analysis and publication remain immutable. Migration downgrade fails closed if rebuilt generations exist.",
            ],
            [
              "2026-08-19",
              "Implemented and test-verified; deployment pending",
              "Retailer scorecard zero states now reconcile certified relationships independently from admissible store-price observations.",
              "A retailer with certified comparable products but no positive-price observations under the selected comparison basis and geography is labeled as having no admissible observations. It is never mislabeled as having no governed relationships. This preserves the distinction between match certification and reportable store-price overlap for sparse retailer evidence such as Sam's Club and Trader Joe's.",
            ],
            [
              "2026-08-19",
              "Deployed and production-verified",
              "Competitive Product Leadership was flattened into eight first-class report tabs while retaining one shared analytical context.",
              "The nested Product Leadership tab and internal workspace rail are removed. Leadership Overview, Competitive Footprint, Match Group Analysis, Price Ladders, Store Comparisons, Market Performance, Competitive Exceptions, and Competitive History now sit beside Executive Overview, Price Architecture, Assortment & Whitespace, and Data Integrity. Legacy bookmarked Product Leadership URLs are translated to the corresponding first-class tab. An idle prewarm and shared immutable response cache remove repeated cold requests when moving among leadership tabs. Current-code rebuilds now allocate immutable replay generations under an advisory lock and require a reason; only that explicit rebuild path may resolve an archived immutable source after recoverable report cleanup. Ordinary replay behavior remains active-source-only and idempotent. Egg generation 2 run 7ff16d97-8fb4-4d26-8698-a59339343ac2 succeeded as fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-de5fc82e-r2 with exact 185-case coverage, 183 comparable decisions, one not-comparable decision, one unresolved exclusion, and no automatic fallback. Compatible-spec exposes 11 of 13 retailer views and 11,062 matched observations; strict exact-spec independently exposes three retailer views and 537 observations. A Target check for product 10449724 increases monotonically from 496 scored benchmark stores at one mile to 1,255 at three miles and 1,743 at five miles against the same 3,068-store denominator. All twelve first-class tabs render. GitHub Actions runs 32288372400, 32288974552, 32289709810, and 32290777122 passed the full Python, contract, migration, TypeScript, browser, and container gates.",
            ],
            [
              "2026-08-19",
              "Deployed and production-verified",
              "Retailer scorecard product drilldowns distinguish authoritative aggregate metrics from relationship-level evidence availability.",
              "The drawer first uses persisted per-relationship outcomes when they exist. If an immutable publication contains only a retailer-level aggregate, it resolves the certified relationship IDs to governed assortment product identities and labels them as aggregate-only instead of inventing product-level prices, shares, or locations. This closes the ShopRite empty-drawer defect without weakening scorecard authority or changing any metric. GitHub Actions run 32252437430 passed Python, TypeScript, 13 browser tests, migrations, contracts, and all four container builds. Production now exposes all four ShopRite governed relationships behind the unchanged 167-observation / 55-ZIP scorecard, and the live browser console is clean.",
            ],
            [
              "2026-08-18",
              "Deployed and production-verified",
              "Trust Recovery binds Price and Competitive Intelligence to one published artifact generation and restores the complete admitted benchmark assortment.",
              "The Price read path now reconciles classified Parquet artifacts to the AnalysisResult evidence row count and manifest checksum, with explicit analysis-run generation lineage for future replays and fail-closed handling of ambiguity. Canonical product-location projection rechecks Retailer Pack first-party seller policy, so known marketplace sellers cannot leak from historical artifacts. Interactive report payloads omit audit-only scope arrays while immutable evidence remains intact. Scorecard product drawers bind contributing decision rows to the authoritative relationship ledger, so a missing duplicate status field cannot hide admitted product evidence. Production Egg reconciliation returns 119,172 classified rows, 108,701 eligible observations, 172 Walmart products, 166 Walmart.com sellers, six policy-permitted blank sellers, and zero known third-party sellers. Product Leadership lists all 172 products and renders unmatched items as explicit unscored states. The complete Python suite passes with 558 tests and 13 environment-gated skips; GitHub Actions run 32216053425 passed Python, TypeScript, 13 browser tests, migrations, contracts, and all four container builds.",
            ],
            [
              "2026-08-18",
              "Deployed and production-verified",
              "Competitive Intelligence was consolidated into a decision-led five-workspace reporting architecture with explicit analytical capability boundaries.",
              "Executive Overview now begins with transparent retailer evidence, readiness, matched-observation, and retailer-view leadership summaries. Price Architecture, Product Leadership, Assortment & Whitespace, and Data Integrity retain the strongest governed drill-downs; sparse outer Products and Geography tabs no longer compete with those workflows. Unavailable explicit Product Leadership profiles/products fail closed instead of silently showing stale fallback metrics. Current data supports snapshot price ladders and gaps, but not history/response, basket, KVI, elasticity, margin, ROI, or consumer price-image claims.",
            ],
            [
              "2026-08-18",
              "Deployed, certified, and production-verified",
              "Fresh Shell Eggs matching distinguishes known specification conflicts from explicitly tolerated unknown evidence.",
              "Product Pack and report blueprint 1.2.2 make a known shell-color mismatch a hard non-comparable conflict. Unknown organic evidence no longer independently blocks certification, while a known organic-versus-non-organic conflict still blocks. The capability is generic Product Pack policy, not an Egg branch. The platform owner completed exhaustive queue 3.0.0 with 183 comparable decisions, one not-comparable decision, and one intentionally flagged housing-unknown case. Immutable release de5fc82e-27e9-40c4-a284-ffea2989f261 now drives the live governed Egg replay with automatic fallback disabled and exact 185-case coverage reconciliation.",
            ],
            [
              "2026-08-18",
              "Production-verified",
              "The Competitive Intelligence library was reset to the certified Egg release candidate.",
              "Six obsolete publications were recoverably archived after resolving their exact IDs. The sole active report is fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-de5fc82e; raw Search/PDP data, artifacts, certification decisions, immutable releases, and audit history remain intact. Browser verification shows one of one reports and opens Egg with the Compatible-spec basis when reviewing broad retailer coverage.",
            ],
            [
              "2026-08-18",
              "Deployed and production-verified",
              "Matching v2 review queues gained governed evidence-only succession with certified-decision carry-forward.",
              "An administrator must name the exact predecessor version. Product Pack version and policy checksum must remain identical, every certified case must remain present, every prior primary image must remain in the successor image set, and case documents must be byte-equivalent after removing only image-reference fields. Egg queue 2.1.0 carried all 94 finalized decisions and left 132 pending. Its bounded gpt-5.6-terra remediation batch completed 132/132 with zero task failures for $8.2524; every draft remained insufficient evidence and no AI result was auto-certified.",
            ],
            [
              "2026-08-18",
              "Implemented and test-verified; production remediation replay pending",
              "Matching v2 PDP evidence now retains secondary product images and audits field-level completeness.",
              "Only incomplete or conflicting cases receive vision evidence. The request uses up to six deduplicated PDP images per product, balances both retailer sides, requires exact image citations, and preserves structured-only fallback. PDP normalization audits now distinguish seller, brand, description, identifiers, specifications, physical properties, primary imagery, and multi-image coverage from unmapped-field schema drift. No paid AI or PDP calls run automatically.",
            ],
            [
              "2026-08-17",
              "Implemented and test-verified; operational Egg reset pending",
              "Matching v2 now separates sampled model-validation queues from exhaustive operational match certification and fails closed when a sampled queue is used for reporting.",
              "The prior 1,305-case Egg queue is recognized as a partial validation sample and will not be replayed as a complete match graph. New evidence profiles emit every governed candidate into an operational certification queue; raw Search, PDP, location, Product Pack, and audit evidence remain immutable. Match Certification also has a protected governed-replay control. No paid calls or live match decisions were made.",
            ],
            [
              "2026-08-17",
              "Implemented and test-verified; production replay pending",
              "Competitive Intelligence gained retailer certification funnels, authoritative comparison-basis filtering, explicit zero states, stricter readiness, and store-level price ladders.",
              "Every configured basis now has a scorecard state; changing the basis selects only that evidence. Matching v2 releases persist candidate, comparable, not-comparable, and unresolved counts per retailer under coverage contract 1.0.0. Incomplete certification and non-ready AnalysisResults block decision readiness. Product Leadership uses the existing governed 1/3/5-mile geography engine to rank Walmart and the lowest local Search offer per matched product, with rung gaps and drillable product/location identity. API, analytics, report-contract, TypeScript, and web tests pass locally; no paid calls or live decisions were made.",
            ],
            [
              "2026-08-17",
              "Deployed and production-verified",
              "Matching v2 certified gold sets gained an explicit governed reporting cutover.",
              "A checksum-bound release can queue an idempotent replay from an existing analysis. Production Egg release 0dd6df6d-9f9c-4251-9041-7d294c7042c5 replayed 99 certified-comparable and 431 certified-not-comparable decisions while excluding 775 unresolved cases and disabling automatic fallback. The published report contains only certified comparable relationships with admissible Search co-observations; zero uncertified or not-comparable pairs leaked into metrics. Result validation reports 100% metric-reference coverage and zero unsupported numeric claims. GitHub Actions run 32080559215 passed and Railway worker deployment 883fad41-5f53-4c10-9e5d-04dcda19c487 is active.",
            ],
            [
              "2026-08-17",
              "Deployed and production-verified",
              "Egg PDP 404-heavy subsets gained evidence-specific contract remediation and a bounded retry gate.",
              "Target and Sam's Club use owner-verified trailing-slash, URL-only request shapes; Trader Joe's preserves six-digit product IDs through generic endpoint configuration. Four bounded preflight requests returned HTTP 200 for nine credits. Product Pack 1.2.1 reduced the historical-pin estimate from 65 calls / 168 credits to 38 calls / 91 credits. Run 81311e57-f31f-4a82-838b-4f94dc7c8c99 completed all 38 with HTTP 200: Target 17, Sam's Club 19, and Trader Joe's two. Preflight plus retry cost $0.200. GitHub Actions runs 32053993593 and 32054864329 passed; Railway worker deployments e604761c-21c0-49d7-ba91-c5e7a56e5abb and f5294660-2212-4503-94ad-9f6fd6e2b1b4 succeeded.",
            ],
            [
              "2026-08-17",
              "Deployed and production-verified",
              "The bounded Egg PDP collection completed with immutable-response recovery and an audited credit ledger.",
              "The exact plan admitted 914 products, reused 527 fresh cache entries, and queued 387 calls under a 771-credit ceiling. A downstream path-contract defect was caught after immutable Kroger responses were stored; paid processing was paused, the snapshot schema was corrected, eight HTTP 200 responses and one HTTP 429 response were recovered without duplicate provider calls, and future raw objects now persist HTTP status metadata. The terminal run produced 269 HTTP 200s, 117 billable 404s, one non-billable HTTP 500, and 769 credits ($1.538). Including the one-credit preflight, phase spend was $1.540. GitHub Actions run 32049626190 and the Railway worker deployment passed.",
            ],
            [
              "2026-08-17",
              "Deployed and production-verified",
              "Kroger Product Details contract passed its controlled paid preflight.",
              "One observed Egg product at ZIP 72801 / store 02500624 returned HTTP 200 from /kroger/pdp/zipcode/. The call consumed one credit ($0.002), exposed no credential, and established the catalog route as authoritative; the prior /mc route is retired.",
            ],
            [
              "2026-08-17",
              "Deployed and production-verified",
              "The complete MetricsCart catalog is normalized and all 14 Egg retailers have staged PDP contracts.",
              "The repository records 217 active endpoint contracts without copying provider response bodies, adds eight Retailer Packs, supports generic request defaults, preserves unchanged cache identities, reports fresh cache hits in dry-run estimates, and blocks the conflicting Kroger path before paid execution. GitHub Actions run 32043978815 and all four Railway services passed. The production Egg dry-run found 914 admitted products, 871 valid requests, 527 fresh cache hits, 344 remaining calls (728 credits / $1.456), and 43 blocked Kroger candidates. No provider calls were made.",
            ],
            [
              "2026-08-17",
              "Deployed & verified",
              "Fresh Milk exact package-volume governance closes legacy and current certification paths.",
              "Milk Product Pack 1.5.0 makes volume_oz a hard blocker and blueprint 1.4.0 binds it for new definitions. AI prompt 1.0.4, new reviews, retries, individual approval, bulk approval, adjudication, certified gold-set export, and Match Certification UI all apply the current stricter rule without mutating older queues. Cross-volume comparable decisions are blocked; governed not-comparable decisions remain certifiable. CI run 31999183989 passed the complete release gate and all four commit 83c6f8f Railway deployments succeeded. A read-only audit of all 311 active Milk cases found 128 volume conflicts and 68 unresolved-volume cases; seven prior approvals are now fail-closed and release-excluded, including 32 oz vs 64 oz and 32 oz vs 128 oz relationships. No paid AI or MetricsCart calls were made.",
            ],
            [
              "2026-08-16",
              "Deployed & verified",
              "Fresh Milk and Fresh Eggs matching is explicitly spec-first and brand-aware.",
              "Milk's primary profile now compares compatible specifications without requiring brand equality, while same-brand and private-label views remain secondary analytical lenses. Eggs retain their existing spec-first profiles. Matching v2 keeps brand descriptive/noncritical for both Product Packs, and AI prompt 1.0.3 is prohibited from using a different or unknown descriptive brand as the sole reason for not-comparable or insufficient-evidence. A matching brand remains useful identity evidence but cannot override a hard specification conflict. CI run 31992528978 passed the complete release gate and all four containers. Railway API deployment a5263dc7-6f61-4130-8f08-a7e323d79b36 is active with Milk Product Pack 1.4.0 and versioned blueprint 1.3.0.",
            ],
            [
              "2026-08-16",
              "Deployed & verified",
              "Match Certification adds governed large and queue-wide AI review runs.",
              "Administrators can submit explicit selections larger than 25 or prepare every eligible case in the current queue/retailer filter, up to 1,500 cases in one durable batch. Exact count and worst-case model exposure require confirmation; existing tasks, final decisions, third-party items, and missing observed-location evidence are blocked. Production read-only validation found complete nonzero Milk footprints for all 311 candidates (Walmart 1–4,525 locations; competitors 1–2,595). Migration 0038_large_ai_batches is live, queue-wide selection is enabled, and CI run 31992528978 passed the complete release gate. No paid AI or MetricsCart work was started during validation.",
            ],
            [
              "2026-08-16",
              "Deployed & verified",
              "Bulk certification policy v1.2.0 adds guarded acceptance of not-comparable AI recommendations.",
              "A checksum-bound batch may contain comparable and not-comparable outcomes, each persisted as its own final verdict with the complete AI rationale and advisory warnings. Comparable decisions require a governed tier; not-comparable decisions write no tier; insufficient-evidence proposals remain blocked. CI run 31988362130 passed 487 Python tests, 57 web tests, 11 browser tests, reversible migrations, and all container builds. Production reached migration 0037_bulk_ai_verdicts; all five pending Ground Beef not-comparable recommendations produced an eligible checksum-bound preview while the one insufficient-evidence proposal remained non-final. No live decision was changed.",
            ],
            [
              "2026-08-16",
              "Deployed & verified",
              "Bulk certification policy v1.1.0 allows administrators to confirm every valid affirmative AI match recommendation.",
              "Deterministic disagreement, incomplete evidence, conflicts, and confidence limits are displayed as advisory warnings and copied with the complete AI rationale into each final comment. Invalid/non-affirmative drafts, known third-party sellers, missing evidence, and existing final decisions remain blocked. CI run 31986016902 passed 483 Python tests, 57 web tests, 11 browser tests, reversible migrations, and all container builds. The live preview made the current affirmative Ground Beef recommendation confirmable with both warnings visible; no commit or match decision was made.",
            ],
            [
              "2026-08-16",
              "Deployed & verified",
              "Matching v2 AI review gained request-bound image evidence and queue-wide bulk discovery.",
              "Retries can no longer repeat the known uncited-image invalid state, the fourth bounded retry can remediate legacy terminal lineages, and bulk assessment scans the full pending queue/current retailer filter. CI run 31984408556 passed 482 Python tests, 57 web tests, 11 browser tests, reversible migrations, and all container builds. One live Ground Beef retry succeeded under prompt 1.0.2 in 11.6 seconds for an estimated $0.0387; no human decision was created.",
            ],
            [
              "2026-08-16",
              "Deployed & verified",
              "Terminal Match Certification AI failures gained governed individual and bulk retry controls.",
              "Each confirmed retry creates a new lineage-linked Postgres task, preserves failed attempts/errors/cost, reapplies seller and final-decision guards, blocks evidence-integrity failures, and retains mandatory human review. Phase 13.9 later raised the ceiling from three to four specifically to remediate the request-schema defect while preserving all legacy history. CI run 31979462641 passed migrations in both directions, 480 Python tests, 57 web tests, 10 browser tests, and all container builds. The live protected page and owner docs were verified without a paid AI call; existing failures attached to finalized cases correctly remained non-retryable.",
            ],
            [
              "2026-08-16",
              "Deployed & verified",
              "All active Match Certification queues gained source-reconciled observed footprints and defense-in-depth first-party eligibility.",
              "Legacy queue views recover distinct positive-price Search location counts without replacing immutable queues; known third-party offers are rejected at import, hidden from legacy views, blocked from paid AI review, and blocked from individual or bulk certification. Permitted blank seller evidence remains explicitly unverified.",
            ],
            [
              "2026-08-16",
              "Deployed & verified",
              "Match Certification gained guarded bulk acceptance for corroborated AI match recommendations.",
              "Administrators can preview a checksum-bound safe subset, inspect exclusion reasons, and finalize up to 50 exact/equivalent matches in one auditable human action; substitute/custom tiers remain individual and reporting never reruns automatically. The protected production page and its no-eligible-recommendations state were verified without changing live match decisions.",
            ],
            [
              "2026-08-16",
              "Deployed",
              "Match Certification AI review gained durable batch observability and bounded concurrency.",
              "Administrators now see queue-wide progress, timestamps, ETA, cost, retries, and terminal errors while the worker processes two cases concurrently by default.",
            ],
            [
              "2026-08-16",
              "Verified",
              "Product Pack abstraction audit classified the canonical Platform Docs content file as non-executable content.",
              "Category examples remain available to administrators while every executable Python, TypeScript, and TSX core path stays under the no-category-branch scan.",
            ],
            [
              "2026-08-16",
              "Production baseline",
              "Owner/Admin Docs Center created and current implementation consolidated through Matching v2 Phase 13.5.",
              "Establishes the maintained operating manual and honest current/shadow/planned boundaries.",
            ],
            [
              "2026-08-16",
              "Deployed",
              "Match Certification simplified to one final approve/reject decision with explicit flag-to-reopen.",
              "Removes one-review/two-review/adjudication workflow from the active UI while preserving append-only history and legacy readability.",
            ],
            [
              "2026-08-15",
              "Implemented",
              "Matching v2 deterministic evidence, local comparison shadow model, protected certification queue, and bounded AI draft assistance.",
              "Adds release evidence without changing current authoritative report matches until category certification passes.",
            ],
            [
              "2026-08-14",
              "Deployed",
              "Shared product-location foundation and cohesive Price/Competitive Intelligence workspaces.",
              "Both analytical modules now consume the same Search-authoritative population and governed PDP/brand/location enrichment.",
            ],
            [
              "2026-08-11",
              "Deployed",
              "Dynamic collection builder and governed Product Pack authoring introduced.",
              "Adds approved geography snapshots, checksum-bound estimates, immutable Pack versions, and certification suites.",
            ],
          ],
        },
        {
          kind: "list",
          title: "Maintenance checklist for every future change",
          items: [
            "Update the guide's Last verified date only after the described behavior is tested.",
            "Add or revise links when a route moves.",
            "Update the metric dictionary when a label, formula, grain, denominator, or source changes.",
            "Update limitations when a deferred capability becomes active—or a new honest boundary is discovered.",
            "Update service and security guidance when variables, credentials, limits, or deployment ownership changes.",
            "Append a change-order row; do not silently replace history.",
          ],
        },
      ],
    },
  ],
};
