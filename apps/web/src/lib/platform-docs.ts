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

const lastVerified = "August 28, 2026";
const aiIntegrationLastVerified = "August 29, 2026";
const integrationLineageLastVerified = "August 30, 2026";
const productionOperationsLastVerified = "August 29, 2026";
const liveSearchLastVerified = "August 30, 2026";

export const platformDocumentation: PlatformDocumentation = {
  title: "Platform Owner & Administrator Guide",
  version: "1.3.79",
  lastVerified: liveSearchLastVerified,
  baseline:
    "Production implementation through the trust-gated Vitamin governed reporting replay under Product Pack 1.3.1",
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
              "System Operations",
              "Verify release identity, migrations, queues, cooldowns, recent spend, publication state, and recovery evidence.",
              "The page is read-only. Backup and restore timestamps are operator attestations; provider billing remains authoritative.",
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
          kind: "callout",
          tone: "success",
          title: "Resilient availability gates are deployed",
          text: "Existing definitions remain strict. Migration 0049 adds an opt-in successful-sample quorum and a ceiling for retry-exhausted zero-credit provider_5xx, timeout, network, or rate_limit samples. Hard and billable non-404 failures still block, and the billable-404 ceiling remains independent. Exact location-scope exclusions rotate only the deterministic preflight sample; they never remove that location from the frozen full collection. The migration, compatible API, and all five worker replicas are deployed; the first resilient Walmart gate passed before its bulk tasks were released.",
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
            "PDP workers claim a retailer-balanced batch within each priority and maintain up to 18 in-flight jobs by default. As each request finishes, the next loop refills only the free capacity instead of waiting for the slowest request in the batch. Every request obtains a shared account-wide PDP permit at 2 requests per second / 120 per minute and its retailer permit at 3 requests per second / 180 per minute. A provider 429 pauses both Postgres-backed scopes across every replica.",
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
                "Match Certification is the authoritative relationship surface. Product evidence claims collapses eligible pair-level AI observations into one administrator task per retailer listing and Product Pack attribute across the selected batch scope. Every distinct image citation, visible label excerpt, proposed value, affected relationship, and counterpart retailer remains visible; repetition across pairs is context, not independent proof. Conflicting values fail closed until an identified administrator selects a source-bound value or rejects the complete claim with a rationale. Product Pack overrides, governed brand decisions, manual overrides, and previously verified evidence stay locked. A versioned successor queue may preserve those human attribute decisions only through the independent fail-closed succession gate: Product Pack policy, listing, attribute, current value/source, AI output, cited image, visible evidence, and proposal checksum must remain identical. A nonmatching claim stays in immutable predecessor history and is reported as skipped; a global Product Pack or queue-policy mismatch rolls the import back. Then inspect the complete product evidence and approve or reject the relationship once. Reopen a final decision only by explicitly flagging it. Reporting replay remains explicit.",
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
          text: "A user may request AI drafts for explicit page selections or every currently eligible candidate in the active review queue and competitor-retailer filter. One governed run may contain up to 1,500 cases, enough for every current five-category release queue. Before any paid work is created, the UI discloses the exact case count, model, per-case ceiling, and worst-case aggregate exposure and requires an identified administrator to confirm. Each request is one idempotent durable Postgres batch with queue-wide queued, reviewing, ready, and needs-attention counts; the latest batch shows completed items, timestamps, estimated remaining time, and recorded cost. The worker processes two cases concurrently by default and automatically attempts each task twice. Existing AI tasks, final comparable/not-comparable decisions, known third-party listings, and any candidate missing nonzero Search-derived benchmark or competitor observed-location evidence cannot cross this paid-call boundary. After a terminal needs-attention failure, an identified administrator may confirm an individual or filtered-page bulk retry. A retry creates a new task linked to the failed task and preserves every prior attempt, safe error, and recorded cost; it never resets history. Each case permits at most four administrator retry rounds. Match Certification consolidates eligible retry-lineage observations in Product evidence claims, so the platform reasons once about each product attribute while retaining every pair-level citation and affected relationship. Structured evidence is always supplied. When Product Pack attributes are missing or held by reviewable lower-authority extraction, the evidence packet adds primary and available secondary PDP images, interleaved across both products and bounded to six per product. An image proposal must name an active Product Pack attribute, cite visible text, cite an exact image attached to exactly one listing, meet the 85% confidence floor, and normalize under the active Product Pack. The server classifies it as completion, corroboration, refinement, or conflict. Corroboration requires no action. The Auto-reconcile safe claims action handles the complete high-confidence consensus population in one checksum-bound administrator confirmation only when every observation names one value, fills an unknown attribute, has at least 95% confidence, and retains its exact image plus visible label text. Refinements, conflicts, and weaker evidence remain unresolved rather than becoming a mandatory clerical queue. Product Pack/configured constants, governed brand decisions, manual overrides, and previously human-verified values cannot be replaced in this lane. Structured AI proposals remain prohibited. Each append-only decision is bound to the complete proposal membership, selected source citation, queue and Product Pack versions, visible text, normalized and superseded values, policy checksum, and stale-safe claim checksum. The complete batch commits atomically. Raw Search, PDP, AI, and queue evidence never changes; conflicting verified values fail closed. Certification and reporting remain separate explicit gates. Every AI draft remains advisory.",
        },
        {
          kind: "callout",
          tone: "success",
          title: "Administrator-confirmed bulk acceptance",
          text: "An administrator may assess completed comparable and not-comparable AI recommendations across the full pending queue and active retailer filter. The client submits up to 500 candidates, while the server binds no more than 50 confirmable cases into each confirmation and defers additional passing cases to the next batch. Comparable recommendations require the exact deterministic engine tier, a tier permitted by the active Product Pack, a deterministic eligible price basis, and every current Product Pack hard blocker to be known and compatible. A missing, blocked, or disagreeing deterministic tier is a certification blocker, not a warning. Not-comparable recommendations must have no tier and require a known deterministic Product Pack hard-blocker conflict; an AI-only conflict, internally contradictory evidence, or an unknown required value stays in individual review. Insufficient-evidence recommendations remain non-final and blocked. Incomplete nonblocking evidence, descriptive AI conflicts, and confidence limits remain visible advisory warnings. A final decision, invalid draft, known third-party seller, or missing immutable evidence remains a blocking exclusion. The preview binds each recommended verdict, deterministic tier, and eligible price basis with case checksums, AI task/output checksums, queue version, and policy version into one confirmation checksum. One explicit administrator confirmation writes an immutable bulk-action audit record plus the same final human submission used by individual approval, including all warnings and the complete AI evidence rationale in the reviewer comment. No report reanalysis runs automatically; decisions remain final until flagged.",
        },
        {
          kind: "callout",
          tone: "attention",
          title: "Vitamin certification reset",
          text: "Vitamins & Supplements Product Pack 1.1.2 fails closed on product identity. Active ingredient or governed formulation, labeled strength and unit, dosage form, release profile, and life-stage/audience must be known and compatible. Adult, children, prenatal, men, women, senior, and general-audience conflicts are non-comparable. Package-count differences may support normalized-unit equivalent-product analysis only after the identity attributes agree. Broad comparable-substitute certification is prohibited. A bounded lexical candidate may enter PDP/vision evidence review when a critical value is missing, but it cannot be certified until every required value is known and compatible. Queue 2026.08.23-spring-valley-4 and all 300 decisions made from its unsafe policy are quarantined from reporting. Clean successor 2026.08.24-spring-valley-7 contains 203 pending unresolved cases and zero inherited decisions. Owner-approved gpt-5.6-terra review completed successfully for every case at $16.4078975 recorded usage: 81 not-comparable recommendations, 114 insufficient-evidence recommendations, and eight positive match proposals. The audit found that one AI rejection relied on a structured PDP ingredient value that contradicted the title and product image. Bulk policy 1.4.0 now requires a known deterministic hard-blocker conflict for batch rejection; AI-only or internally contradictory evidence stays in individual review. The server also blocks all insufficient-evidence drafts and all eight positive proposals while deterministic hard-blocker evidence remains unresolved. Every draft still requires a human decision; none automatically changed reporting.",
        },
        {
          kind: "callout",
          tone: "information",
          title: "Coverage-first vitamin evidence recovery",
          text: "Product Pack 1.3.0 accounts for the governed Spring Valley catalog against all nine configured competitors while explicitly excluding two cataloged topical skin-oil products. Product compatibility and price-comparison basis are separate governed decisions: active ingredient/formula, strength/unit when applicable, dosage form, release profile, and audience must establish a valid relationship before package or normalized-unit pricing is considered. Package price requires equivalent known package counts. Normalized-unit price requires known positive denominators on both sides, may compare different counts, and can never create or rescue a relationship. New advisory reviews use gpt-5.6-luna for lower cost. Every comparable draft must state package price, normalized unit price, or both; the server verifies the proposal against deterministic edge evidence and binds it into the bulk confirmation checksum. No AI output automatically changes certification or reporting.",
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
            "Comparable Store Coverage is the share of distinct observed benchmark stores with at least one valid local competitor comparison under the selected retailer, comparison basis, period, geography, and radius. Count each benchmark store once even when several products contribute evidence; count each contributing competitor store once. Service-area retailers use distinct delivery ZIPs instead of stores.",
            "Keep package price and normalized unit price as distinct comparison bases; use a unit price only when package evidence supports it.",
            "Assign every unscored local context a reason such as no eligible match, no overlap, product not observed, stale/missing price, collection failure, incomplete attributes, or review required.",
            "Preserve retailer, Product Pack, relationship, geography, period, policy, evidence checksum, and freshness context with each result.",
            "Bind every live read model to the exact immutable artifact set cited by the published AnalysisResult evidence checksum. If more than one generation exists and none reconciles exactly, fail closed instead of merging generations.",
            "Apply Retailer Pack first-party seller policy at both classification and canonical product-location projection. Known third-party marketplace offers never enter price, coverage, assortment, matching, or competitive metrics; permitted blank sellers remain explicitly unverified.",
            "Apply the selected competitor and comparison basis to every scorecard and supporting product view. A context selector must never be presentation-only.",
            "For physical retailers, radius-native scorecards rebuild certified product relationships at product × observed Walmart store grain and require the competitor store to be within the selected 1, 3, or 5 mile radius. Service-area retailers remain explicitly same-delivery-ZIP because they do not expose a comparable physical store footprint.",
            "Cohort Scorecards aggregate those same certified product-location outcomes by Product Pack segment; cohort membership never creates a new match. Assortment Scorecards keep global assortment breadth separate while applying the selected radius to local comparable coverage.",
            "Current Cohort Scorecard drawers read the exact radius-native relationship lineage materialized with each cohort. A cohort's displayed counts, rates, medians, gaps, product rows, and drill-down relationships are release-gated to the same relationship IDs; legacy exact-location candidates cannot populate or empty the drawer.",
            "Cohort price presentation follows the governed package signature. When every member has one fixed fluid-ounce size, the observation-weighted package-equivalent median is primary and price per fluid ounce is secondary. When package volumes differ, price per fluid ounce is primary. The canonical normalized metric remains available in export and audit lineage; presentation never changes eligibility, price outcomes, or stored calculations.",
            "PDP evidence may fill a missing Product Pack attribute at read-model projection time, but never changes Search price, availability, sponsorship, or location. Derived unit price is recomputed only from explicit package evidence. Written singular/plural units are equivalent; day supply is converted to count only when the PDP also explicitly directs exactly one unit daily. Dosage quantities and multi-unit daily regimens are not package counts.",
            "Default competitive portfolios are persisted per immutable analysis, comparison profile, and 1/3/5-mile radius. Retailer selection filters one materialized all-retailer document; state and city combinations remain on-demand. Rebuilding these read models does not call MetricsCart or OpenAI.",
            "Price Intelligence Home reads one publication-time materialized catalog per configured retailer. Search, brand, brand type, seller, and pagination are applied by the API, and the browser receives 40 rows at a time. Opening a product loads its complete product-location, map, price-distribution, and PDP evidence lazily. Catalog materialization uses retained evidence and makes no MetricsCart or OpenAI call.",
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
      id: "ai-integration-map",
      group: "governance",
      title: "AI integration & operating boundaries",
      summary:
        "A complete map of where AI runs, what evidence it receives, what it may produce, and which decisions remain deterministic or human-controlled.",
      audience: "Platform owner · Platform administrator · Engineering lead",
      readingTime: "16 min",
      lastVerified: aiIntegrationLastVerified,
      status: "Current with limitations",
      links: [
        { href: "/admin/matching-v2", label: "Open Match Certification" },
        { href: "/admin/report-publishing", label: "Open Report Publishing" },
        { href: "/data-quality", label: "Open Data Quality" },
      ],
      blocks: [
        {
          kind: "callout",
          tone: "information",
          title: "AI is a bounded assistant, not the analytics engine",
          text: "The production application has three OpenAI-assisted lanes: governed insight drafting, governed narrative drafting, and administrator-requested Matching v2 evidence review. Product-image vision is a conditional input inside the matching-review lane rather than a separate autonomous process. AI may interpret supplied facts, draft prose, propose a match verdict, and propose source-bound image attributes. It cannot collect retailer data, decide source authority, calculate a metric, create a valid product relationship by price similarity, certify a match without an administrator, publish a report, or replace verified evidence.",
        },
        {
          kind: "table",
          title: "Current production AI inventory",
          columns: [
            "AI lane",
            "Trigger and model",
            "Governed input",
            "Permitted output",
            "Final authority",
          ],
          rows: [
            [
              "Insight drafting",
              "Runs late in an eligible baseline analysis when AI_ENABLED and the definition's AI fallback are enabled. Current production model: gpt-5.6-sol.",
              "Deterministic insight candidates, a bounded semantic brief, selected metric/evidence references, Product Pack context, and required caveats.",
              "Clearer titles, summaries, and business implications for existing deterministic insight IDs. Numeric facts must use governed metric placeholders.",
              "The deterministic result and critic. A rejected, unavailable, or over-budget response is discarded and deterministic insight remains.",
            ],
            [
              "Narrative drafting",
              "Runs after eligible analysis facts and any accepted insight draft exist. Current production model: gpt-5.6-sol.",
              "Requested report sections, semantic brief, deterministic metrics, evidence-backed insights, recommendations, caveats, storylines, and at most eight admitted decision-product summaries.",
              "Section headline, subtitle, two-to-five bullets, and a plain-language key point using only allowed metric, storyline, product, and evidence references.",
              "Strict schema validation plus the deterministic narrative critic. Renderers only display the accepted projection and never recalculate analytics.",
            ],
            [
              "Matching v2 evidence review",
              "An identified administrator explicitly selects eligible cases or an eligible queue scope and confirms the disclosed paid exposure. Current production model: gpt-5.6-luna.",
              "One checksum-bound pair case containing governed Search, PDP, brand, seller, Product Pack, deterministic tier/basis, attribute, conflict, and observed-location evidence.",
              "An advisory comparable, not-comparable, or insufficient-evidence proposal; the deterministic tier and price bases when supported; rationale; conflicts; and eligible image-derived attribute proposals.",
              "The Product Pack and deterministic engine constrain the output. Human review is mandatory; individual or guarded bulk certification requires an explicit administrator confirmation.",
            ],
            [
              "Product-image vision",
              "Conditional sub-mode of Matching v2 review only when an active Product Pack attribute is unresolved or comes from reviewable lower-authority extraction.",
              "Primary and available secondary PDP images, interleaved across both products and bounded to six images per product, plus the same structured pair evidence.",
              "A proposal for an active attribute only when it cites exact visible label text, the exact supplied image URL, and the listing shown by that image.",
              "The server classifies completion, corroboration, refinement, or conflict. An administrator confirms any value-changing reconciliation; locked evidence cannot be overwritten.",
            ],
            [
              "Narrative bake-off utility",
              "Engineering-only command, outside the normal application workflow, requiring an explicit paid-call acknowledgement. It may make at most one insight and one narrative request.",
              "A retained AnalysisResult and the same governed prompt/evidence packets used by the narrative pipeline.",
              "A comparison artifact with model responses, usage, validation, and cost for benchmark evaluation.",
              "Engineering review only. It does not activate a report, change evidence, or alter production matching.",
            ],
          ],
        },
        {
          kind: "steps",
          title: "Where AI appears in the end-to-end workflow",
          items: [
            {
              title: "1. Collection and raw preservation — no AI",
              detail:
                "Retailer adapters, Search-by-ZIP calls, shared rate limits, paid-credit guards, immutable raw storage, and response normalization are deterministic. No retailer payload is sent to a model merely because it was collected.",
            },
            {
              title:
                "2. Qualification, PDP enrichment, and brands — no current AI decision",
              detail:
                "Product Pack rules qualify or reject Search products; Retailer Pack seller policy removes known third-party noise; MetricsCart PDP supplies identity context; governed brand foundations, aliases, and administrator decisions classify brands. OPENAI_MODEL_CLASSIFICATION exists only as a reserved environment-template field and has no runtime consumer.",
            },
            {
              title:
                "3. Candidate generation and deterministic evidence — no AI",
              detail:
                "The matcher creates high-recall candidates, applies hard blockers, computes attribute evidence, determines eligible tiers and price bases, and resolves geographic applicability without a model. Price is explicitly excluded from semantic match evidence.",
            },
            {
              title: "4. Optional Matching v2 AI review",
              detail:
                "After candidates exist, an administrator may purchase advisory review. The model cannot widen the deterministic tier or price-basis boundary. Unknown hard blockers remain insufficient evidence, and known Product Pack conflicts remain not comparable.",
              link: {
                href: "/admin/matching-v2",
                label: "Match Certification",
              },
            },
            {
              title: "5. Attribute-evidence reconciliation and certification",
              detail:
                "Source-bound image proposals are consolidated into product-level claims. Safe consensus may be prepared in bulk, but one checksum-bound administrator confirmation is still required. Relationship approval or rejection is also a human decision and does not automatically start reanalysis.",
            },
            {
              title: "6. Deterministic analytics",
              detail:
                "Certified relationships, Search prices, store geography, package evidence, and Product Pack rules produce counts, medians, gaps, unit prices, cohorts, ladders, scorecards, maps, exceptions, and readiness checks. AI performs none of these calculations.",
            },
            {
              title: "7. Optional governed insight and narrative",
              detail:
                "Only eligible baseline analyses enter the current automatic prose lane. Analyses pinned to a human match revision, brand revision, or Matching v2 gold-set release deliberately skip new AI generation; a governed replay never silently creates fresh prose or spend.",
            },
            {
              title: "8. Publication and serving — no AI",
              detail:
                "The durable materialization worker builds Price Intelligence and Competitive Intelligence read models from retained evidence, runs semantic trust gates, and activates the report atomically. Context changes, exports, alerts, and page rendering consume deterministic materializations and do not call OpenAI.",
            },
          ],
        },
        {
          kind: "table",
          title: "Prompt and output contracts",
          columns: ["Prompt", "Current version", "Strict guarantees"],
          rows: [
            [
              "governed_insight",
              "2.5.0",
              "Selects supplied deterministic insight IDs only; preserves direction and references; numeric facts must come from allowed metric placeholders.",
            ],
            [
              "governed_narrative",
              "4.0.3",
              "Returns every requested section once; uses only allowed metrics, evidence, storylines, and products; forbids unsupported numeric literals and prescriptive or ambiguous shorthand.",
            ],
            [
              "matching_v2_evidence_review",
              "1.4.0",
              "Requires human review; cannot exceed deterministic tier or basis; separates compatibility from package/unit pricing; image claims require exact supplied source attribution.",
            ],
          ],
        },
        {
          kind: "table",
          title: "Current live controls and cost boundaries",
          columns: [
            "Control",
            "Governed insight/narrative",
            "Matching v2 review",
          ],
          rows: [
            ["Model", "gpt-5.6-sol for both roles", "gpt-5.6-luna"],
            [
              "Reasoning and output",
              "High reasoning; 12,000 maximum output tokens per request",
              "Medium reasoning; 6,000 maximum output tokens per request",
            ],
            [
              "Per-request ceiling",
              "$3.00 conservative maximum per request",
              "$0.35 conservative maximum per case",
            ],
            [
              "Attempts and concurrency",
              "At most two attempts through a leased, idempotent task",
              "At most two automatic attempts; four cases process concurrently; up to four separately confirmed administrator retry rounds after terminal needs-attention failure",
            ],
            [
              "Usage record",
              "Input/output tokens, latency, estimated cost, prompt/model/input/output checksums, validation, and evidence references",
              "Batch/case, prompt/model/input/output checksums, every attempt, input/output tokens, latency, estimated cost, warnings, safe error, and retry lineage",
            ],
          ],
        },
        {
          kind: "callout",
          tone: "attention",
          title: "A request ceiling is not a project budget",
          text: "The per-request cost guard blocks a request before it is sent when the conservative maximum exceeds policy. Matching v2 additionally discloses case count, per-case ceiling, and worst-case batch exposure before an administrator confirms paid work. OpenAI account/project limits remain the external financial backstop and provider billing remains authoritative. The application persists reported token usage and estimated cost whenever the provider returns usable usage metadata; missing usage is explicitly unknown rather than assumed to be zero.",
        },
        {
          kind: "definitions",
          title: "Durability, idempotency, and failure behavior",
          items: [
            {
              term: "Governed prose task",
              definition:
                "Postgres identifies work by analysis run, role, prompt checksum, provider/model, and input checksum. A succeeded task is reused only after its envelope revalidates. Active work is leased; bounded failures become needs-review and the deterministic report remains usable.",
            },
            {
              term: "Matching-review batch",
              definition:
                "One administrator request creates a durable batch and one task per case. Workers claim tasks with row locks and SKIP LOCKED semantics, retain progress across service restarts, and never merge tasks from different governed inputs.",
            },
            {
              term: "Vision fallback",
              definition:
                "If OpenAI cannot retrieve a supplied image, the worker records a warning and retries that model request with structured evidence only. It cannot invent an image-derived claim in that fallback because the request-specific schema permits zero attribute proposals.",
            },
            {
              term: "Deterministic fallback",
              definition:
                "If governed prose is unavailable, invalid, stale, over-budget, or outside its lease, the application retains deterministic insight/narrative. If matching review fails, the case remains unresolved or needs attention; no relationship changes.",
            },
          ],
        },
        {
          kind: "list",
          title: "Information sent to OpenAI",
          items: [
            "Governed prose receives a bounded semantic packet rather than raw collection files: up to 360 selected metrics, referenced evidence summaries, Product Pack/report context, caveats, storylines, and up to eight admitted decision-product summaries.",
            "Matching review receives one candidate pair at a time with the current governed Search/PDP/brand/seller/attribute/policy evidence and observed-location summaries. It does not receive the MetricsCart or OpenAI API key.",
            "When vision is eligible, requests may include public or provider-returned PDP image URLs already attached to the two listings. Images are used only to read product-label evidence under the active Product Pack.",
            "Responses API requests set store=false. The application persists its own checksum-bound input/output audit, token usage, estimated cost, validation, and reviewer lineage in Postgres.",
            "Secrets remain worker-side environment variables. They are never exposed to browser code, model prompts, reports, exported artifacts, or application logs.",
          ],
        },
        {
          kind: "table",
          title: "Important processes that are not AI-powered today",
          columns: ["Process", "Current authority"],
          rows: [
            [
              "Retailer Search/PDP calls and payload mapping",
              "Retailer adapters, provider catalogs, response contracts, and immutable raw evidence",
            ],
            [
              "Noise removal, seller eligibility, and category admission",
              "Retailer Packs and Product Packs",
            ],
            [
              "Brand identity and private-label/regional/national classification",
              "Governed brand foundations, deterministic alias/evidence rules, and Brand Workbench decisions",
            ],
            [
              "Product Pack or Retailer Pack creation and activation",
              "Administrator authoring, schema validation, certification suites, and immutable versions",
            ],
            [
              "Candidate retrieval, hard blockers, tiers, cohorts, and local scope",
              "Deterministic matching engine and Product Pack policy",
            ],
            [
              "Prices, units, distances, counts, medians, rates, scorecards, ladders, maps, and history",
              "Deterministic analytics over Search/PDP/location/certification evidence",
            ],
            [
              "Publication audit, report activation, context filtering, export, schedules, and alerts",
              "Durable queues, semantic gates, read-model services, and deterministic renderers/evaluators",
            ],
            [
              "Live web research used during development",
              "An engineering activity outside the deployed application's runtime; the application does not browse the web autonomously",
            ],
          ],
        },
        {
          kind: "callout",
          tone: "success",
          title: "Human decision boundary",
          text: "AI can reduce reading and drafting effort, but an administrator remains accountable for evidence reconciliation, final match certification, paid matching-review launch, retries, bulk acceptance, Product Pack/brand changes, reporting replay, and publication approval. Guarded bulk actions are not autonomous certification: the server first proves eligibility and binds an exact preview checksum, then an identified administrator confirms the immutable decisions.",
        },
        {
          kind: "list",
          title: "Required maintenance whenever AI changes",
          items: [
            "Update this guide and append a dated change order whenever a model, provider, prompt, prompt version, output schema, reasoning level, token limit, cost guard, concurrency, retry rule, input field, image policy, authority boundary, UI trigger, or fallback changes.",
            "Update prompt and schema tests together; never edit a prompt without changing its version and checksum-governed lineage.",
            "Re-run unsupported-number, reference-coverage, source-attribution, hard-blocker, human-review, cost-guard, idempotency, lease/retry, and deterministic-fallback tests.",
            "Verify the production feature flags and non-secret model settings before marking the guide Current. Never document an environment-template placeholder as an implemented AI capability.",
            "Record any paid acceptance run with the exact approval, task/batch scope, model, recorded usage/cost, outcome mix, and whether any human decision or report changed.",
            "Keep planned AI—such as assisted brand classification or Product Pack drafting—explicitly labeled planned until a governed implementation, tests, audit lineage, and administrator surface exist.",
          ],
        },
        {
          kind: "callout",
          tone: "attention",
          title: "Current limitations",
          text: "There is no runtime AI for brand classification, Product Pack generation, Retailer Pack generation, collection planning, retailer payload normalization, quantitative analytics, publication gating, alert decisions, or autonomous web research. Governed prose is intentionally skipped on analyses pinned to human brand/match revisions or Matching v2 gold-set releases, so current certified replays may rely on deterministic copy or previously approved narrative rather than a fresh model call. Matching AI remains pair-scoped and advisory; evidence gaps still require better PDP/label evidence or human judgment.",
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
                "First use Product evidence claims to review each retailer product and Product Pack attribute once across the current AI lineages. Inspect every cited image and visible label excerpt, resolve conflicts by selecting the supported citation, or reject the complete claim; repeated pair proposals are context rather than independent proof. Then inspect pair evidence, attributes, scope, and alternate lenses in Match Certification. Approve or reject a relationship once, reopen only when explicitly flagged, and trigger governed reporting replay after the review set is ready.",
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
      id: "incident-response-recovery",
      group: "operations",
      title: "Production incident response & recovery",
      summary:
        "A severity-based playbook for restoring availability without corrupting queues, evidence, reports, or audit history.",
      audience: "Platform owner · Platform administrator · Engineering",
      readingTime: "12 min",
      lastVerified: productionOperationsLastVerified,
      status: "Current with limitations",
      links: [
        { href: "/admin/operations", label: "Open System Operations" },
        { href: "/admin/report-publishing", label: "Open Report Publishing" },
      ],
      blocks: [
        {
          kind: "callout",
          tone: "attention",
          title: "Protect evidence before restoring speed",
          text: "Never mark work successful, overwrite raw objects, delete queue rows, or replace the current trusted report to make an incident disappear. Pause claims or roll back stateless code, preserve leases and failure evidence, and recover through supported retry/replay paths.",
        },
        {
          kind: "table",
          title: "Incident severity",
          columns: ["Severity", "Use when", "First response", "Target"],
          rows: [
            [
              "SEV-1",
              "The public app or API is unavailable, authoritative data may be at risk, or paid work is running without its approved boundary.",
              "Stop new paid claims, preserve evidence, verify Postgres and bucket state, and restore the last healthy stateless deployment.",
              "Acknowledge immediately; restore safe read access before resuming writes.",
            ],
            [
              "SEV-2",
              "A major workflow, report, queue, or retailer is unavailable while the rest of the platform remains usable.",
              "Isolate the affected service/retailer, retain the current trusted publication, and diagnose leases, cooldowns, gates, and recent deployment changes.",
              "Restore or safely disable the affected workflow without broadening scope.",
            ],
            [
              "SEV-3",
              "A limited defect, stale evidence warning, isolated failure, or presentation issue has a workaround.",
              "Record the defect and evidence, prevent misleading output, and schedule a tested correction.",
              "Correct through the normal release gate.",
            ],
          ],
        },
        {
          kind: "steps",
          title: "Availability incident workflow",
          items: [
            {
              title: "Confirm the failure boundary",
              detail:
                "Open System Operations and test web /health, web /health/ready, API /health/live, and API /health/ready. Distinguish an unavailable process, Postgres dependency failure, slow analytical projection, provider cooldown, and browser-only failure.",
            },
            {
              title: "Freeze risky work",
              detail:
                "If paid or mutating work is unsafe, scale the worker/scheduler to zero or disable the narrow feature flag. Do not change historical rows. In-flight leases remain reclaimable after expiry.",
            },
            {
              title: "Compare release identity",
              detail:
                "Record commit, deployment ID, database migration, Product Pack/Retailer Pack versions, and the last known healthy deployment. A migration mismatch is release-blocking.",
            },
            {
              title: "Restore the smallest component",
              detail:
                "Roll back or restart only the affected stateless service when possible. Keep the prior ready AnalysisResult active; a blocked materialization must not replace it.",
            },
            {
              title: "Verify before resuming",
              detail:
                "Run the zero-credit readiness verifier, exercise one representative Price and Competitive Intelligence read, inspect queue leases/cooldowns, then resume one worker before restoring normal scale.",
            },
            {
              title: "Record the incident",
              detail:
                "Append the timeline, impact, root cause, evidence, spend exposure, remediation, tests, deployment, and follow-up controls to the numbered phase/change record and Platform Docs change-order log.",
            },
          ],
        },
        {
          kind: "steps",
          title: "Database and bucket recovery drill",
          items: [
            {
              title: "Verify a recoverable production backup",
              detail:
                "Confirm the Railway Postgres backup/PITR evidence and record its timestamp. Do not test restoration over production.",
            },
            {
              title: "Restore into an isolated non-production environment",
              detail:
                "Use a new database/service boundary with no production worker, provider, email, or AI credentials. Preserve string identifiers and timezone-aware timestamps.",
            },
            {
              title: "Reconcile control and data planes",
              detail:
                "Verify Alembic head, organizations, definitions, queue history, AnalysisResults, publication state, artifact metadata, and representative private-bucket objects/checksums.",
            },
            {
              title: "Run read-only acceptance",
              detail:
                "Start API/web against the restored database, keep COLLECTION_PROVIDER=fake and paid features disabled, and verify one Price and one Competitive report plus protected admin access.",
            },
            {
              title: "Attest only after evidence passes",
              detail:
                "Set RCI_LAST_DATABASE_BACKUP_VERIFIED_AT after backup evidence is checked and RCI_LAST_RESTORE_DRILL_AT only after the isolated restore succeeds. System Operations flags absent or stale attestations; it does not manufacture proof.",
            },
          ],
        },
        {
          kind: "callout",
          tone: "attention",
          title: "Current recovery posture",
          text: "The 2026-08-29 isolated logical restore passed database, private-object, administrator-boundary, Price, and Competitive acceptance. System Operations displays its operator-attested freshness. Daily and weekly Railway volume backup schedules are active. PITR was enabled in an observed maintenance window on 2026-08-29; it is not retroactive, so the retained named backup remains the recovery layer for time before enablement. A forced WAL segment archived successfully with zero failures.",
        },
      ],
    },
    {
      id: "release-manifest-change-control",
      group: "operations",
      title: "Release manifest, canaries & change control",
      summary:
        "How one release proves its code, migrations, governed configuration, documentation, health, and post-deploy behavior.",
      audience: "Platform owner · Platform administrator · Engineering",
      readingTime: "11 min",
      lastVerified: productionOperationsLastVerified,
      status: "Current",
      links: [
        { href: "/admin/operations", label: "Open System Operations" },
        { href: "/admin/docs", label: "Open Platform Docs" },
      ],
      blocks: [
        {
          kind: "definitions",
          title: "Live release manifest",
          items: [
            {
              term: "Code identity",
              definition:
                "The API exposes the allowlisted application version, Railway commit SHA, deployment ID, environment, and service name. Secrets and arbitrary environment values are never serialized.",
            },
            {
              term: "Database identity",
              definition:
                "The current alembic_version must equal one configured migration head discovered from the deployed repository. A mismatch blocks operational readiness.",
            },
            {
              term: "Governed configuration",
              definition:
                "Every deployed Product Pack and active Retailer Pack is listed by stable ID, semantic version, and checksum so analysis policy can be tied to code and evidence.",
            },
            {
              term: "Operational state",
              definition:
                "Queue depth, running claims, expired leases, recent failures/review outcomes, provider cooldowns, publication blockers, and latest successful work come from live Postgres state.",
            },
            {
              term: "Spend reconciliation",
              definition:
                "Thirty-day Search/PDP credits and persisted AI estimated cost are operational estimates. Missing AI usage remains explicit and MetricsCart/OpenAI billing stays financially authoritative.",
            },
          ],
        },
        {
          kind: "steps",
          title: "Release sequence",
          items: [
            {
              title: "Review scope and paid boundaries",
              detail:
                "Name changed workflows, contracts, migrations, metrics, retailers, Product Packs, AI behavior, secrets, costs, and rollback boundaries. Live provider/AI acceptance requires separate explicit scope and spend approval.",
            },
            {
              title: "Pass documentation coverage",
              detail:
                "CI compares behavioral source/config/schema changes with Platform Docs and requires both the maintained guide update and a numbered phase/change record.",
            },
            {
              title: "Pass the complete release gate",
              detail:
                "Run schemas, Python format/lint/types/tests, migration upgrade/downgrade/upgrade, TypeScript contracts/format/lint/types/tests/build, browser tests, and all four container builds.",
            },
            {
              title: "Deploy in compatible order",
              detail:
                "Apply migration/API first, then lease-safe worker/scheduler services, then web. Do not expose a UI contract before its API is compatible.",
            },
            {
              title: "Run the zero-credit canary",
              detail:
                "Run scripts/verify_release_readiness.py against web and API. It verifies liveness/readiness only, emits a JSON record, and always reports zero paid provider calls.",
            },
            {
              title: "Perform live workflow acceptance",
              detail:
                "Open System Operations and the changed page, confirm release/migration identity, inspect browser errors, and verify one representative read. Run a paid Search/PDP/AI canary only when separately approved.",
            },
          ],
        },
        {
          kind: "table",
          title: "Automatic publication and release blockers",
          columns: ["Condition", "Displayed state", "Required action"],
          rows: [
            [
              "Database migration differs from deployed head",
              "Blocked",
              "Stop promotion; reconcile migration deployment before writes resume.",
            ],
            [
              "Any running durable task has an expired lease",
              "Blocked",
              "Confirm owner/process health and allow governed reclaim; never complete it manually.",
            ],
            [
              "Open validation blocker",
              "Blocked",
              "Resolve or supersede through the evidence workflow before publication.",
            ],
            [
              "Recent queue failure, review outcome, provider cooldown, or stale/missing recovery attestation",
              "Attention",
              "Investigate and disclose; it may not require taking healthy read surfaces offline.",
            ],
            [
              "All runtime checks pass",
              "Healthy",
              "Complete the changed-workflow and live browser acceptance before release sign-off.",
            ],
          ],
        },
        {
          kind: "callout",
          tone: "information",
          title: "Canary spending boundary",
          text: "The built-in release verifier is deliberately zero-credit. A Search-by-ZIP, PDP, or AI canary is a separate, immutable run with named retailers/locations/products, maximum credits or dollars, and explicit owner approval. Passing public health never implies that a provider page is callable.",
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
              "Five current replicas; durable Postgres claims and shared provider limits; provider and OpenAI credentials live here.",
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
                "A hard credit cap, daily/monthly budget, retailer-specific availability gate, disabled feature flag, or missing separate PDP/AI approval may intentionally stop work. A failed retailer no longer blocks retailers that passed. An explicitly configured resilient gate tolerates only its bounded successful-sample quorum and retry-exhausted zero-credit transient whitelist; hard failures and the 404 ceiling still fail closed.",
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
      id: "retailer-integration-registry",
      group: "reference",
      title: "Retailer integration registry",
      summary:
        "The maintained Search, PDP, location, billing, seller, and runtime-contract inventory for every configured retailer.",
      audience: "Platform owner · Platform administrator · Engineering",
      readingTime: "14 min",
      lastVerified: integrationLineageLastVerified,
      status: "Current with limitations",
      links: [
        { href: "/collections/new", label: "Open collection setup" },
        { href: "/data-quality", label: "Open Data Quality" },
      ],
      blocks: [
        {
          kind: "callout",
          tone: "attention",
          title: "Enabled is not the same as universally callable",
          text: "Enabled means the catalogued adapter may be planned and executed. It does not promise that every retailer, category, store, ZIP, or page is currently available from MetricsCart. The immutable run-specific retailer preflight is the authority: each retailer passes, fails, or remains pending independently, and one failed retailer must not contaminate another retailer's plan.",
        },
        {
          kind: "callout",
          tone: "information",
          title: "Quorum never hides a location or a paid failure",
          text: "The deployed resilient gate is opt-in. It may tolerate only a configured number of retry-exhausted zero-credit provider_5xx, timeout, network, or rate_limit samples while requiring its successful-sample quorum. Authentication, request-contract, schema, parse, storage, billable, and unknown failures remain hard blockers, and 404s retain their separate configured ceiling. A recovery may rotate an exact failed scope out of preflight, but that scope remains in the complete frozen collection and its later result remains immutable evidence.",
        },
        {
          kind: "definitions",
          title: "Shared provider contract",
          items: [
            {
              term: "Authentication",
              definition:
                "MetricsCart requests use the server-side METRICSCART_API_KEY as x-api-key. The key must never enter browser JavaScript, report artifacts, logs, downloads, or documentation.",
            },
            {
              term: "Search billing",
              definition:
                "The catalog treats HTTP 2xx and 404 pages as billable charge events. Credit cost varies by retailer. Estimates, approved ceilings, actual attempts, status, and credits remain auditable per task.",
            },
            {
              term: "Shared rate limit",
              definition:
                "The provider documents 3 requests per second / 180 per minute per retailer and endpoint type. Production intentionally defaults Search to 2 per second / 108 per minute and PDP uses a shared account-wide permit plus a retailer permit, all coordinated in Postgres across replicas.",
            },
            {
              term: "Physical-store context",
              definition:
                "The current location master supplies Store_No and normalized five-digit ZIP. Store and ZIP identifiers remain strings, including leading zeros. Target collection locations must be USA rows. ALDI's current authoritative roster uses numeric Store_No values; legacy hyphenated IDs are retained only for history.",
            },
            {
              term: "Eligibility policy reconciliation",
              definition:
                "Location import evaluates active status and provider-safe store identity from the versioned Retailer Catalog. When that policy changes, the administrator first writes and reviews a checksummed dry-run artifact containing the catalog, complete selected location snapshot, counts, reasons, and exact row changes. Apply must consume that exact artifact; it cannot silently create a replacement plan or override its retailer scope. Import and apply share one cross-process whole-operation lock, while apply independently regenerates the plan, rejects a stale snapshot or altered evidence, commits the complete correction atomically, and retains the reviewed-plan checksum in its durable audit. Frozen historical geographies are never rewritten.",
            },
            {
              term: "Service-area context",
              definition:
                "Amazon Same Day is collected and compared by delivery ZIP, not a fabricated physical store. Its Search URL preserves the Same Day/Fresh service-area context.",
            },
          ],
        },
        {
          kind: "table",
          title: "Enabled Search-by-ZIP adapters",
          columns: [
            "Retailer",
            "Retailer ID",
            "Runtime Search path",
            "Credits",
            "Required request context",
          ],
          rows: [
            [
              "Walmart (US)",
              "walmart_us",
              "/mc/walmart/search/zipcode/v2/",
              "1",
              "ZIP · store · page; keyword or URL; Best Match default",
            ],
            [
              "ALDI",
              "aldi_us",
              "/mc/new_aldi/serp/zipcode",
              "2",
              "Keyword · ZIP · numeric store · page",
            ],
            [
              "Amazon Same Day (US)",
              "amazon_us_same_day",
              "/mc/amazon/search/zipcode/",
              "2",
              "Same Day URL · ZIP · page; delivery-area grain",
            ],
            [
              "Albertsons",
              "albertsons_us",
              "/mc/albertsons/serp/zipcode",
              "2",
              "ZIP · store; keyword or URL",
            ],
            [
              "H-E-B",
              "heb_us",
              "/mc/heb/serp/zipcode/",
              "1",
              "Keyword · ZIP · store",
            ],
            [
              "Kroger",
              "kroger_us",
              "/mc/kroger/search/zipcode/",
              "3",
              "Keyword · ZIP · canonical eight-digit store · page; preserve leading zeros",
            ],
            [
              "Safeway",
              "safeway_us",
              "/mc/safeway/serp/zipcode/",
              "2",
              "Keyword · ZIP · store",
            ],
            [
              "Target",
              "target_us",
              "/mc/target/search/zipcode/",
              "4",
              "Keyword · ZIP · store · page; Relevance default",
            ],
            [
              "Giant Eagle",
              "giant_eagle_us",
              "/mc/gianteagle/serp/zipcode/",
              "2",
              "ZIP · store; keyword or URL",
            ],
            [
              "Meijer",
              "meijer_us",
              "/mc/meijer/serp/zipcode",
              "2",
              "ZIP · store · keyword",
            ],
            [
              "Sam's Club",
              "sams_club_us",
              "/mc/samsclub/serp/zipcode",
              "2",
              "Keyword · ZIP · store · page",
            ],
            [
              "ShopRite",
              "shoprite_us",
              "/mc/shoprite/serp/zipcode",
              "1",
              "ZIP · store · shopping type; pickup default",
            ],
            [
              "Trader Joe's",
              "trader_joes_us",
              "/mc/traderjoes/serp/zipcode/",
              "1",
              "Keyword · ZIP · store",
            ],
            [
              "Wegmans",
              "wegmans_us",
              "/mc/wegmans/serp/store/",
              "1",
              "Keyword · ZIP · store",
            ],
            [
              "BJ's Wholesale Club",
              "bjs_us",
              "/mc/bjs/serp/zipcode/",
              "1",
              "Keyword · ZIP · store",
            ],
            [
              "Costco",
              "costco_us",
              "/mc/costco/serp/zipcode/",
              "1",
              "ZIP · store · keyword",
            ],
            [
              "CVS",
              "cvs_us",
              "/mc/cvs/serp/zipcode/",
              "2",
              "Keyword · ZIP · store · page",
            ],
            [
              "Walgreens",
              "walgreens_us",
              "/mc/walgreens/serp/zipcode/",
              "1",
              "Keyword · page · ZIP · store",
            ],
          ],
        },
        {
          kind: "table",
          title: "PDP enrichment registry for enabled Search retailers",
          columns: [
            "Retailer",
            "Runtime PDP path",
            "Credits",
            "Required request context",
          ],
          rows: [
            [
              "Walmart (US)",
              "/mc/walmart/product/zipcode/",
              "2",
              "Product identity · ZIP · store · fulfillment type",
            ],
            [
              "ALDI",
              "/mc/new_aldi/pdp/zipcode/",
              "1",
              "Product identity · ZIP · store · fulfillment type",
            ],
            [
              "Amazon Same Day (US)",
              "/mc/amazon/pdp/zipcode/",
              "2",
              "Product identity; ZIP when available",
            ],
            [
              "Albertsons",
              "/mc/albertsons/pdp/zipcode",
              "3",
              "URL · ZIP · store",
            ],
            [
              "H-E-B",
              "/mc/heb/pdp/zipcode/",
              "1",
              "Product identity · ZIP · store",
            ],
            [
              "Kroger",
              "/kroger/pdp/zipcode/",
              "1",
              "Product identity · request context · fulfillment type; provider-catalog route",
            ],
            [
              "Safeway",
              "/mc/safeway/pdp/zipcode/",
              "3",
              "Product identity · ZIP · store",
            ],
            [
              "Target",
              "/mc/target/pdp/zipcode/",
              "3",
              "URL · ZIP · store · fulfillment type",
            ],
            [
              "Giant Eagle",
              "/mc/gianteagle/pdp/zipcode/",
              "2",
              "Product identity · ZIP · store",
            ],
            [
              "Meijer",
              "/mc/meijer/pdp/zipcode",
              "2",
              "Product identity · ZIP · store",
            ],
            [
              "Sam's Club",
              "/mc/samsclub/pdp/zipcode/",
              "2",
              "URL · ZIP · store · fulfillment type",
            ],
            [
              "ShopRite",
              "/mc/shoprite/pdp/zipcode/",
              "1",
              "Product identity · ZIP · store · shopping type",
            ],
            [
              "Trader Joe's",
              "/mc/traderjoes/pdp/zipcode/",
              "1",
              "Six-digit product ID · ZIP · store",
            ],
            [
              "Wegmans",
              "/mc/wegmans/pdp/zipcode",
              "1",
              "Product identity · ZIP · store",
            ],
            [
              "BJ's Wholesale Club",
              "/mc/bjs/pdp/zipcode/",
              "2",
              "Product identity · ZIP · store",
            ],
            [
              "Costco",
              "/mc/costco/pdp/zipcode",
              "4",
              "Product identity · ZIP · store · fulfillment type",
            ],
            [
              "CVS",
              "/mc/cvs/pdp/zipcode",
              "3",
              "URL · ZIP · store · fulfillment type",
            ],
            [
              "Walgreens",
              "/mc/walgreens/pdp/zipcode",
              "2",
              "Product ID · ZIP · store · pickup fulfillment",
            ],
          ],
        },
        {
          kind: "callout",
          tone: "information",
          title: "PDP collection is selective and cache-first",
          text: "Search remains the store-specific package-price, observed-presence, sponsorship, and collection-time authority. PDP enrichment runs only for distinct admitted analysis products, reuses evidence that is fresh under the current 30-day policy, and normally selects one representative positive-price Search location per product. Another PDP context is justified only by contradictory identity evidence or a governed location/variant diagnostic. Paid-calls-enabled means the contract is eligible for planning—not that every product/location request will succeed.",
        },
        {
          kind: "table",
          title: "What the adapters preserve",
          columns: ["Evidence", "Normalized use", "Authority boundary"],
          rows: [
            [
              "Search product",
              "Name, brand, retailer product ID, identifiers, URL, primary image, rating/review counts, result position, sponsorship",
              "Provider aliases map to canonical fields; raw_extra retains unmapped provider values",
            ],
            [
              "Search price",
              "Current, regular, discounted, currency, and positive-price observation",
              "Only Search may author local shelf price and observed presence",
            ],
            [
              "Search location",
              "Retailer location ID, store number, ZIP, coordinates, country",
              "Current geography is reconciled to the location master; immutable historical snapshots keep their original IDs",
            ],
            [
              "PDP identity",
              "Name, brand, descriptions, categories, specifications, physical properties, identifiers, URL, imagery/video",
              "May complete or corroborate identity and attributes; cannot overwrite Search price or location",
            ],
            [
              "PDP commerce",
              "Seller, offers, price fields, pickup/shipping context, availability, rating/review summaries",
              "Useful for first-party governance and diagnostics; local reporting price still comes from Search",
            ],
          ],
        },
        {
          kind: "definitions",
          title: "First-party seller governance",
          items: [
            {
              term: "Known first party",
              definition:
                "Walmart, Target, and Amazon apply active Retailer Pack first-party policies with exact normalized seller aliases. Walmart accepts Walmart or Walmart.com; Target accepts Target or Target.com; Amazon uses its configured Amazon-owned retail aliases.",
            },
            {
              term: "Known third party",
              definition:
                "A nonmatching known seller is excluded as marketplace noise before paid AI review, certification, and reporting. Seller text is never accepted through loose substring matching.",
            },
            {
              term: "Missing seller",
              definition:
                "Where the active policy permits missing seller evidence, the listing remains eligible but explicitly seller-unverified. Missing never becomes affirmative first-party proof.",
            },
            {
              term: "Retailer without an active seller policy",
              definition:
                "The listing is not seller-governed, not silently classified first party. New marketplace-prone retailers require an evidence-backed Retailer Pack policy before strict 1P claims are made.",
            },
          ],
        },
        {
          kind: "list",
          title: "Operational proof is scope-bound",
          items: [
            "Historical acceptance, a successful playground CURL, or one HTTP 200 proves only that exact retailer, request shape, product or keyword, store/ZIP, and time context.",
            "HTTP 404 normally means the retailer page was unavailable in that request context and may still be billable; it is not automatically a bad location-master row.",
            "Schema drift fails closed after the raw response is preserved. It does not become an empty product page or a false zero.",
            "A failed retailer gate does not stop independently valid retailers unless the approved definition requires all-retailer completeness.",
            "After a gate passes, a terminal bulk-task failure becomes warning-only only when it is zero-credit and in the explicit transient whitelist and at least one useful task succeeded; hard and billable non-404 failures remain fatal, while billable 404s keep their separate threshold and warning behavior.",
            "Walmart Mexico is catalogued but not enabled. Whole Foods Market currently has normalization/Retailer Pack support but no live Search adapter in this registry.",
          ],
        },
        {
          kind: "callout",
          tone: "success",
          title: "Required maintenance whenever a retailer contract changes",
          text: "Update the Search catalog, PDP catalog or runtime override, Retailer Pack, fixtures, adapter tests, paid-credit estimate, location policy, this registry, and the change-order log together. Validate the exact request shape with a bounded preflight only when approved; never infer a production contract from an old sample file.",
        },
        {
          kind: "callout",
          tone: "attention",
          title:
            "Unresolved-only composite continuation is staged, not deployed",
          text: "Migration 0052 and its administrator API are implemented and locally test-verified but are not yet authoritative production behavior. After deployment and PostgreSQL verification, a bound terminal recovery may gain one checksum-bound child that selects no usable success or retained billable 404, always selects integrity blockers, and selects only enough zero-credit gaps to satisfy the existing 95% conclusive-coverage, minimum-success, and retained-404-rate contract. A retailer whose remaining requests cannot mathematically satisfy readiness is not launched and instead requires an explicit governed unavailable decision. The child uses only remaining credits in the original immutable batch, caps lineage depth at 32, rejects unapproved pagination descendants and non-lineage overlap, and requires all ancestors during materialization. No continuation may project or revive Kroger's ineligible historical aliases; that audit-bound scope projection remains separate follow-on work.",
        },
      ],
    },
    {
      id: "source-metric-lineage",
      group: "reference",
      title: "Source-to-metric lineage",
      summary:
        "How raw Search, locations, PDP, brands, Product Packs, matches, and local geography become each trusted metric and drill-down.",
      audience:
        "Platform owner · Platform administrator · Analyst · Engineering",
      readingTime: "15 min",
      lastVerified: integrationLineageLastVerified,
      status: "Current",
      links: [
        { href: "/price-monitoring", label: "Open Price Intelligence" },
        { href: "/analyses", label: "Open Competitive Intelligence" },
        { href: "/data-quality", label: "Open Data Quality" },
      ],
      blocks: [
        {
          kind: "callout",
          tone: "information",
          title: "Every number has a grain, denominator, and authority",
          text: "A trusted metric is not just a formula. It names the atomic evidence, admissibility gates, comparison geography, price basis, denominator, exclusions, and drill-down path. Product-location rows, distinct stores, product relationships, and delivery ZIPs are different grains and must never be relabeled as one another.",
        },
        {
          kind: "table",
          title: "Authority chain",
          columns: [
            "Stage",
            "Authoritative input",
            "What it contributes",
            "What it cannot do",
          ],
          rows: [
            [
              "Raw collection",
              "Immutable MetricsCart Search response",
              "Original provider payload, request context, time, HTTP status, checksum, and credit event",
              "Cannot be rewritten after collection",
            ],
            [
              "Search normalization",
              "Versioned retailer catalog and aliases",
              "Canonical product, price, sponsorship, retailer, and product-location observation",
              "Cannot invent a missing required field or treat schema drift as zero results",
            ],
            [
              "Location resolution",
              "Frozen location-master snapshot",
              "Store identity, ZIP, city, state, country, coordinates, physical/service-area behavior",
              "Cannot prove a retailer page was callable or a missing product was out of stock",
            ],
            [
              "Category admission",
              "Pinned Product Pack",
              "In-scope/noise/review decision, category attributes, valid units, match tiers and comparison bases",
              "Cannot mutate an older result when pack rules change",
            ],
            [
              "Identity enrichment",
              "Fresh retained PDP evidence",
              "Names, descriptions, brand/seller, identifiers, package/specification facts, images, and source-bound evidence",
              "Cannot replace local Search price, observed presence, sponsorship, or collection time",
            ],
            [
              "Brand and seller governance",
              "Brand foundation, Brand Workbench, and Retailer Pack",
              "Canonical brand, aliases, private/regional/national role, first-party eligibility and explicit unknowns",
              "Cannot override a hard product-specification conflict",
            ],
            [
              "Relationship governance",
              "Deterministic matcher plus final Matching v2 certification",
              "Comparable/not-comparable decision, tier, eligible price basis, evidence, local applicability and immutable lineage",
              "Price similarity cannot create semantic comparability; AI advice alone is not certification",
            ],
            [
              "Analytics",
              "Canonical admitted observations plus governed relationships and geography",
              "Counts, medians, rates, gaps, cohorts, ladders, footprint outcomes, assortment and quality results",
              "AI and browser components do not calculate authoritative metrics",
            ],
            [
              "Publication",
              "Immutable AnalysisResult plus staged read models",
              "Fast, context-specific projections that passed semantic trust gates",
              "A partial or failed build cannot replace the current trusted report",
            ],
          ],
        },
        {
          kind: "table",
          title: "The four grains administrators must distinguish",
          columns: ["Grain", "Example", "Where it is used", "Counting rule"],
          rows: [
            [
              "Product × retailer location",
              "One exact milk SKU observed at one Walmart store",
              "Price Intelligence; detailed price evidence; pair outcomes",
              "Latest admitted positive-price Search observation in the immutable run",
            ],
            [
              "Distinct benchmark store",
              "One Walmart store with one or more valid local ALDI comparisons",
              "Retailer and cohort comparable-store coverage",
              "Multiple products at one store count once",
            ],
            [
              "Governed product relationship",
              "One Walmart product certified comparable to one competitor product",
              "Included-product drawers, cohort membership, match summary and audit",
              "Count the immutable certified relationship once; distribution applicability is separate",
            ],
            [
              "Competitor location or service area",
              "One physical ALDI store within radius, or one Amazon delivery ZIP",
              "Contributing competitor footprint and local offer selection",
              "Physical competitors count distinct stores; service-area retailers count distinct delivery ZIPs",
            ],
          ],
        },
        {
          kind: "table",
          title: "Price Intelligence lineage",
          columns: [
            "Reported measure",
            "Formula or rule",
            "Source and gate",
            "Important interpretation",
          ],
          rows: [
            [
              "Observed location",
              "Distinct eligible retailer stores where the exact product has price > 0",
              "Search positive price + product admission + frozen location",
              "Observed/in-stock in this application; not PDP stock",
            ],
            [
              "Not observed",
              "Eligible planned stores minus observed exact-product stores",
              "Successful Search coverage + frozen planned geography",
              "A review signal, not proof of out-of-stock or non-carriage",
            ],
            [
              "Distribution",
              "Observed exact-product locations ÷ eligible retailer locations",
              "Distinct store grain",
              "A product seen in fewer stores may be regionally distributed, not unavailable where carried",
            ],
            [
              "Shelf/package price",
              "Positive Search price for the offered package",
              "Search price authority",
              "PDP price may diagnose identity but never substitutes for this value",
            ],
            [
              "Unit price",
              "Search package price ÷ unambiguous Product Pack quantity",
              "Search price + governed package fact",
              "Unavailable when the denominator or conversion is unknown or conflicting",
            ],
            [
              "Median price",
              "Median of admitted exact-product product-location prices",
              "Positive Search observations in the selected retailer/geography",
              "The UI must label package or normalized unit explicitly",
            ],
            [
              "Price range",
              "Minimum through maximum admitted exact-product price",
              "Same rows as the median",
              "Provides context for regional dispersion and outlier review",
            ],
            [
              "Sponsored share",
              "Observed rows with is_sponsored=true ÷ observed rows with sponsorship evidence",
              "Search is_sponsored authority",
              "Sponsorship is not promotion or rollback",
            ],
            [
              "IQR price exception",
              "Outside Q1 − 1.5×IQR or Q3 + 1.5×IQR; modal-tolerance fallback when IQR is zero",
              "Exact-product local Search prices + Product Pack tolerance",
              "An exception is a review priority, not automatic bad data",
            ],
          ],
        },
        {
          kind: "table",
          title: "Competitive Intelligence lineage",
          columns: [
            "Reported measure",
            "Formula or rule",
            "Source and gate",
            "Important interpretation",
          ],
          rows: [
            [
              "Eligible comparable relationship",
              "Final certified comparable pair admitted by the selected Product Pack profile and price basis",
              "Matching v2 certification + Product Pack",
              "Exact-spec and compatible-spec are governed lenses, not UI synonyms",
            ],
            [
              "Local comparable offer",
              "Eligible competitor product observed at the same delivery ZIP or physical store within selected 1, 3, or 5 miles",
              "Search observations + certified relationship + frozen coordinates",
              "Changing radius changes local evidence, never the product identity or certification",
            ],
            [
              "Comparable benchmark stores",
              "Distinct benchmark stores with at least one valid local competitor product comparison",
              "Local pair outcomes deduplicated by benchmark store",
              "Multiple products at one store count once",
            ],
            [
              "Comparable store coverage",
              "Comparable benchmark stores ÷ distinct benchmark stores carrying an in-scope benchmark product",
              "Distinct benchmark-store grain",
              "This is not product-location volume",
            ],
            [
              "Contributing competitor footprint",
              "Distinct physical competitor stores supplying a scored comparison; service-area retailers use distinct delivery ZIPs",
              "Selected-radius local evidence",
              "Do not compare a delivery ZIP count as though it were a physical-store count",
            ],
            [
              "Lower-price share",
              "Scored pairs where the named retailer is lower ÷ all scored pairs",
              "Same relationship, basis, radius, period and admissible price rows",
              "Display the benchmark-lower, competitor-lower, and parity partition together",
            ],
            [
              "Paired median gap",
              "Median of competitor price minus benchmark price across the same scored pairs",
              "Pair-outcome grain",
              "Positive means Walmart is lower; negative means the competitor is lower",
            ],
            [
              "Product leadership",
              "At each benchmark store, compare the benchmark product with the controlling lowest eligible local competitor offer",
              "Certified relationship + local Search evidence",
              "Leader, tied, at-risk, losing, and unscored are mutually exclusive",
            ],
            [
              "Price ladder",
              "Order governed comparable product prices within match group × geography × snapshot",
              "Matched local positive Search prices",
              "Unrelated category products may not be presented as substitutes",
            ],
            [
              "Cohort scorecard",
              "Roll up certified relationships sharing Product Pack-governed attributes and one price basis",
              "Cohort membership + pair outcomes",
              "Included-product drawers must reconcile to the relationships that produced the row",
            ],
            [
              "Whitespace / exclusivity",
              "Admitted local product with no governed eligible equivalent in the corresponding footprint",
              "Assortment observations + relationship ledger + geography",
              "A missing Search row alone does not prove whitespace",
            ],
          ],
        },
        {
          kind: "steps",
          title: "How to audit a displayed number",
          items: [
            {
              title: "1. Freeze the visible context",
              detail:
                "Record analysis ID, retailer, Product Pack profile, package/unit price basis, 1/3/5-mile radius, state/city selection, and snapshot. A metric without its context is not reproducible.",
            },
            {
              title: "2. Read its definition and grain",
              detail:
                "Confirm whether the value counts product-locations, distinct benchmark stores, distinct competitor stores or delivery ZIPs, relationships, products, or scored pairs.",
            },
            {
              title: "3. Follow the drill-down",
              detail:
                "Use included products, relationship evidence, store comparisons, location drawers, or Data Quality to reach the exact governed members. Drawer counts must reconcile to the headline after applying the same context.",
            },
            {
              title: "4. Reconcile the denominator and exclusions",
              detail:
                "Check non-observation, missing price, unit-conversion failure, seller exclusion, Product Pack noise, no certified relationship, no local competitor within radius, final insufficient evidence, and schema or freshness limitations separately.",
            },
            {
              title: "5. Verify source lineage",
              detail:
                "Trace an atomic member to normalized Search evidence, request/store context, raw checksum, location snapshot, PDP/brand evidence where used, certification decision, and publication checksum. A renderer may format but not recompute it.",
            },
          ],
        },
        {
          kind: "callout",
          tone: "attention",
          title: "Unknown, zero, and unavailable are different",
          text: "Zero means the governed denominator exists and the measured count is zero. Unavailable means the required evidence or denominator does not exist. Unknown means evidence exists but cannot support a safe classification. Unscored means the product/store remained in scope but no valid comparison outcome could be calculated. The UI, downloads, narrative, and alerts must preserve these distinctions.",
        },
        {
          kind: "callout",
          tone: "success",
          title: "Required maintenance whenever a metric changes",
          text: "A source, alias, formula, grain, denominator, exclusion, Product Pack basis, radius policy, label, drill-down, or semantic gate change must update this lineage guide, the metric dictionary, JSON contracts, deterministic tests, golden fixtures, presentation tests, and the change-order log in the same release. AI does not calculate or repair authoritative values.",
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
              term: "Comparable store coverage",
              definition:
                "Distinct benchmark stores with at least one valid local competitor product comparison divided by distinct benchmark stores carrying an in-scope benchmark product. Multiple products at one store count once. Physical competitors report distinct contributing stores; service-area competitors report distinct delivery ZIPs.",
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
                "The worker stages one compact Price Intelligence catalog per governed scoreable retailer, the three default Price Architecture matrices, and one Competitive Portfolio for every configured comparison basis at 1, 3, and 5 miles. The publication plan always uses canonical retailer IDs from the report's governed retailer scope; display labels such as ALDI are never used as service keys. A retailer explicitly classified unavailable remains in audit provenance but receives no catalog or scorecard. Retailer catalogs build one at a time to protect interactive API readiness. Completed scopes survive an automatic retry, so successful work is not repeated unnecessarily.",
            },
            {
              title: "4. Run the semantic trust gate",
              detail:
                "The gate reconciles the complete retailer × comparison-basis × 1/3/5-mile context matrix, stable product and relationship identities, exact evidence-funnel transitions, product-to-relationship rollups, price units, outcome partitions, denominators, rates, weighted gaps, product order, assortment agreement, geography policy, and monotonic radius behavior. Warnings disclose honest evidence limitations; errors block publication.",
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
            "The active Vitamin Brand Foundation resolves and verifies 1,246 of 1,440 distinct queue listings (86.53%). The remaining 194 unresolved brands stay explicitly unknown; the platform does not infer brand authority from weak or ambiguous text.",
            "Vitamins & Supplements reporting is published from the immutable 480-relationship Matching v2 release. The 388 rejected and 1,448 insufficient-evidence cases remain outside price reporting. Competitive Portfolio 1.4.0 is deployed with a complete 322-product source-catalog evidence funnel: 320 products are governed in scope and two topical skin oils are visible governed exclusions. The on-demand product disposition ledger and Product Pack-controlled five-mile default are production-verified. AI remains advisory and no report relationship changes automatically.",
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
              "2026-08-30",
              "Implemented and release-tested; production deployment and blocked-job retry pending",
              "Report publication now keys Price Intelligence catalog materialization by canonical governed retailer IDs rather than presentation labels.",
              "The publication planner reads retailer-scope IDs, fails closed when canonical scope is missing or inconsistent, and excludes explicitly unavailable competitors while retaining the benchmark and all scoreable retailers. This corrects the Banana materialization failure where display label ALDI was passed to the aldi_us-keyed service. Eight focused scope tests and 26 publication, Price, and worker tests pass. The existing trusted Banana report remains active; no source collection, provider call, AI call, match decision, metric, or predecessor report changed. The blocked successor will be retried only after the API hotfix is deployed and healthy.",
            ],
            [
              "2026-08-30",
              "Implemented and locally test-verified; PostgreSQL CI, deployment, and any provider call pending",
              "Terminal composite evidence gained checksum-bound unresolved-only continuation plans under the existing immutable recovery batch.",
              "Migration 0052 adds a bounded non-branching parent/child lineage. The administrator preview resolves every terminal ancestor, never selects a usable success or retained billable 404, always selects contract/quarantine blockers, and selects only enough zero-credit gaps to satisfy the inherited 95% conclusive-coverage, minimum-success, and retained-404-rate contract. Full selection checksums remain stable while item detail is paginated at 500 rows. Approval is idempotent, server-actor controlled, reserves only remaining batch credits, caps lineage depth at 32, forbids unapproved pagination descendants, and serializes PostgreSQL races. Materialization requires all ancestors and permits canonical overlap only within that lineage, retaining cumulative strongest evidence and every redundant result. Location evidence comes from the immutable definition-bound geography while preserving the pre-0052 checksum projection; both existing production root plans recompute exactly. Lineage and artifacts write in bounded 1,000-row batches and reconcile exact returned keys, artifacts, and checksums before analysis queues. The exact Banana projection is 65 tasks / at most 650 credits: 63 ALDI readiness gaps, two Amazon contract blockers, and zero Walmart retries because Walmart's 1.62% gap rate is already a disclosed warning under 95% readiness. No provider call, production write, deployment, metric, report, or source mutation was made. Kroger's audit-bound 1,369-row scope projection remains a separate follow-on (schema revision 0053 if required).",
            ],
            [
              "2026-08-30",
              "Deployed and production-registered; governed continuation and replacement publication pending",
              "Terminal Search evidence gained checksum-bound failure-only recovery and immutable composite input lineage under one aggregate authorization.",
              "Migration 0051 adds an offline immutable spend authorization consumed by one recovery batch, exact and legacy-adoption plans, retailer-unavailability approvals, canonical task selections, component manifests, and one selected lineage row per provider request. CI rehearsed upgrade, downgrade, and upgrade on a pristine database before integration tests created protected audit lineage; production downgrade remains fail-closed once that lineage exists. Production authorization 09350e6f-ee09-4bae-9056-d53a7fc6be0e and batch 922b5ba9-95fc-4321-9074-2a28f27b4f49 bind the exact seven-run Banana/Milk/Egg inventory at 67,908 actual credits ($135.816) under the owner's 100,000-credit ceiling ($200 at the server-controlled $0.002/credit). Banana Walmart and Egg ALDI terminal recoveries are bound through legacy-adoption plans without new calls. Egg Kroger and Meijer have explicit unavailable/no-scorecard approvals. Blocked Banana composite ce40a391-83df-44e0-8306-bed4e328d947 queued no analysis and remains immutable audit history. Exact reservations use credits-per-call times maximum attempts, forbid unapproved pagination descendants and overlapping active selections, preserve successful and billable-404 evidence, and launch idempotently without a gate. Raw collection readiness remains separate from report semantics; unavailable competitors stay visible in source/readiness but are excluded from every scorecard and assortment computation. Contract/quarantine evidence still blocks. Kroger's audit-bound 1,369-row projection remains separate follow-on work; Meijer remains unavailable rather than a zero scorecard. No source data, raw evidence, certification history, or predecessor report was deleted.",
            ],
            [
              "2026-08-30",
              "Deployed and production-verified",
              "Location eligibility gained a generic catalog-driven dry-run/apply reconciliation, and Kroger's provider-safe policy now requires its canonical eight-digit store IDs.",
              "The command defaults to read-only, requires its exact checksummed reviewed-plan artifact plus an identified operator and reason for apply, and refuses scope overrides or stale evidence. Import and apply share one cross-process whole-operation lock. Release commit 8259a0a deployed as API aa589a13-05ee-411a-9710-b077fda463d7 with migration 0050. Reviewed plan 7b07bc6d... over snapshot d94369... disabled exactly 1,298 seven-digit Kroger aliases and left 1,369 canonical eight-digit IDs; durable audit 6901fd05-6390-4052-a331-88f5c16ef773 records the change, and the immediate second dry run returned zero changes. Frozen historical tasks remain immutable.",
            ],
            [
              "2026-08-30",
              "Deployed and production-verified; live execution underway",
              "Full national Banana, Milk, and Egg API Search recollections run under a combined owner-approved $200 Search-only ceiling; workers use rolling slot refill, and an opt-in resilient Walmart availability gate passed before releasing its bulk tasks.",
              "The three primary runs estimate 77,663 credits ($155.326). Resilient recovery b11c9efa-c118-49b0-b6b6-a5045ba06940 launched at exactly 4,683 credits; the conservative batch estimate was 87,029 credits ($174.058) and the actual-plus-open projection was 62,638 ($125.276). Its five-sample gate required four successes, allowed at most one retry-exhausted zero-credit transient, rotated ZIP 60430 / store 5404 out of preflight only, included ZIP 32224 / store 1172, passed, and retained the known-bad scope in the full collection. Commit c6af7b6139738dc65e2ea2328a3d039c863f0406 and CI 33326968373 passed 17 Playwright tests, real-Postgres migration round-trip, and all four containers. Railway deployed migration 0049 plus compatible API, web, scheduler, and five of five uniquely identified workers; health/readiness passed. Shared limits, 429 ramp recovery, leases, cancellation, hard caps, immutable tasks/raw evidence, PDP boundaries, and AI boundaries remain intact. Final run totals, failures, credits, artifact completeness, and downstream readiness remain pending terminal runs.",
            ],
            [
              "2026-08-29",
              "PITR and database credential maintenance production-verified",
              "Railway Postgres PITR was enabled, the database role credential was rotated, and API, worker, and scheduler were bound explicitly to the Postgres service reference.",
              "All durable queues were idle before maintenance. Railway reports PITR enabled, recovery-bucket wiring, and live availability; PostgreSQL archived a forced WAL segment with zero failures. A fresh database connection, all four web/API health checks, and System Operations passed after redeployment with zero provider or AI calls. OpenAI, MetricsCart, and administrator-password rotation remain intentionally deferred by the owner.",
            ],
            [
              "2026-08-29",
              "App/bucket credentials rotated and production-verified",
              "App-owned internal, administrator-bridge, and session-signing secrets plus Railway bucket credentials were rotated without exposing their values.",
              "API, web, and worker were redeployed with synchronized values. Existing administrator sessions were intentionally invalidated; the administrator password is unchanged. Web/API readiness, protected web-to-API admin access, and a product-specific private-object evidence read passed. OpenAI, MetricsCart, administrator-password, and Postgres replacement remain coordinated owner/maintenance actions; PITR remains disabled until that stateful window.",
            ],
            [
              "2026-08-29",
              "Deployed and production-verified",
              "Successful report activation now recoverably retires superseded blocked predecessors, and the default legacy Price read reuses the publication-bound compact catalog.",
              "The obsolete blocked Vitamin predecessor was recoverably archived with an explicit audit; active blocked reports/jobs are zero and System Operations is healthy. Its 246-product default Price payload returned in 0.91 seconds, while a product-specific evidence read continued to use the detailed path. CI run 33281048900 and Railway API/web deployments passed. No provider, PDP, AI, collection, matching, metric, or geography behavior changed.",
            ],
            [
              "2026-08-29",
              "Isolated restore passed; production attestations ready",
              "The first governed Railway recovery drill restored production into a fail-closed non-production environment and reconciled the complete trust boundary.",
              "A checksummed 422 MB PostgreSQL custom dump restored in 67 seconds. Migration 0048 and 19 trust-critical table counts matched production exactly; three private bucket objects matched immutable size and SHA-256 metadata; protected admin access, a 649-product Milk paged Price catalog, and Ground Beef three-mile scorecards passed. Daily and weekly Railway volume backup schedules are now active. No MetricsCart, OpenAI, email, worker, scheduler, PDP, matching, or report mutation ran. PITR remains disabled pending an observed maintenance window and is not implied by the attestations.",
            ],
            [
              "2026-08-29",
              "Production truth-label correction",
              "System Operations stopped inferring the worker collection provider from the API service's environment.",
              "The live API service does not own COLLECTION_PROVIDER, while the worker is independently configured for metricscart. An absent API-local value now displays as Not exposed to API instead of the API code default fake. Queue, spend, provider, AI, Search, PDP, matching, and publication behavior are unchanged; a future service heartbeat is required before the console can claim worker runtime configuration directly.",
            ],
            [
              "2026-08-29",
              "Implemented and release-tested",
              "System Operations, incident/recovery playbooks, live release manifests, zero-credit canaries, and documentation coverage became one governed production-readiness workflow.",
              "The protected System Operations page reads non-secret Railway release identity, current Alembic head, deployed Product Pack/Retailer Pack checksums, durable queue state, expired leases, provider cooldowns, active publication state, thirty-day Search/PDP credits, recorded AI estimated cost, and operator-attested backup/restore freshness. A migration mismatch, expired lease, or open validation blocker fails closed. The zero-credit verifier checks web/API liveness and readiness without calling MetricsCart or OpenAI. CI now requires behavioral changes to update both Platform Docs and a numbered phase record. Backup/restore timestamps remain explicit operator attestations; no automatic Railway restore or paid provider canary is claimed.",
            ],
            [
              "2026-08-29",
              "Implemented and release-tested",
              "Platform Docs gained a catalog-backed Retailer Integration Registry and complete source-to-metric lineage guide.",
              "The registry records all 18 enabled Search adapters, corresponding PDP runtime paths, per-call credits, required location/request context, provider limits, selective 30-day cache-first enrichment, seller governance, and the distinction between adapter enablement and run-specific callability. The lineage guide traces immutable Search, location, PDP, brand, seller, Product Pack, certification, geography, deterministic analytics, and publication evidence into Price and Competitive Intelligence metrics. Automated tests compare every enabled Search/PDP path with the maintained guide and protect distinct product-location, benchmark-store, competitor-store, relationship, and delivery-ZIP grains. This documentation-only change makes no MetricsCart, PDP, OpenAI, certification, metric, source-data, or report-publication change.",
            ],
            [
              "2026-08-29",
              "Implemented, production-config verified, and release-tested",
              "Platform Docs gained one maintained, end-to-end AI integration and operating-boundary guide.",
              "The guide inventories governed insight drafting, governed narrative drafting, administrator-requested Matching v2 review, conditional product-image vision, and the engineering-only narrative bake-off. It names current prompt versions, production models, non-secret token/cost/concurrency controls, data sent to OpenAI, durable task/audit behavior, deterministic and human authority boundaries, explicit non-AI workflows, limitations, and the required maintenance checklist. Production worker flags/models were read without exposing credentials. This documentation-only change makes no OpenAI, MetricsCart, PDP, certification, metric, report-materialization, or source-data change.",
            ],
            [
              "2026-08-28",
              "Deployed, backfilled, and production-verified",
              "Retailer and Cohort Scorecards use distinct-store comparison coverage instead of product-location volume as the primary coverage KPI.",
              "Competitive Portfolio 1.6.0 deduplicates benchmark and competitor locations, preserves observed-but-unscored cohort stores in the denominator, labels Amazon-style service areas as delivery ZIPs, and keeps product-location evidence only for price-result lineage. All 48 configured portfolio documents across the six active reports were rebuilt from retained evidence through a worker-safe sequential process and passed their complete basis-by-1/3/5-mile semantic gates. Live Milk validation reconciled ALDI at 2,273 of 4,574 distinct Walmart stores (49.69%) and 1,877 contributing ALDI stores at three miles; the scorecard API returned in 0.23 seconds, the five-mile control changed to 2,687 of 4,574 stores, service-area coverage remained same-ZIP, readiness stayed green during the worker rebuild, and the browser console was clean. Commit 2c8f81a and GitHub Actions run 33188271627 passed the full release gate; Railway API deployment 7ba061f7-514a-4126-b26f-49a48e693351 and web deployment 03fbec8b-ed3e-4f35-ac41-2cdef68d4acf succeeded. No Search price, PDP evidence, certified relationship, AI decision, or lower-price outcome changed.",
            ],
            [
              "2026-08-28",
              "Deployed and production-verified",
              "Fixed-volume Cohort Scorecards lead with the shopper-visible package basis instead of a gallon equivalent.",
              "The ALDI 64 fl oz whole-organic Milk cohort now presents Walmart $5.96 and ALDI $3.85 per 64 fl oz package, with $0.0931 and $0.0602 per fl oz as secondary context. Its paired median difference displays as ALDI $2.07 per 64 fl oz package lower. Live validation found exactly one matching cohort row, all eight governed relationships in the drawer, a 376 ms drawer open, and zero browser warnings or errors. Mixed-volume fluid cohorts lead with per-fluid-ounce values. Canonical USD/gallon values remain unchanged in audit/export lineage, and all non-volume metrics retain their prior presentation. The change is a pure deterministic browser projection over already-loaded cohort values: it adds no API request, database read, materialization, provider call, or AI call. CI run 33182901876 passed the full release gate and Railway web deployment 057b530e-74b5-44a3-b4f1-4ff422ee0e94 succeeded.",
            ],
            [
              "2026-08-27",
              "Deployed and production-verified; schema backfill performance-gated",
              "Cohort medians state their normalized unit, product-location grain, package equivalent, and brand-neutral scope, with stronger publication gates.",
              "The reported ALDI 64 fl oz whole-organic cohort reconciles exactly to 7,218 certified scored product-locations: Walmart $11.92/gallon, ALDI $7.70/gallon, and a -$4.14/gallon paired median difference—approximately $5.96 versus $3.85 per 64 fl oz. Live validation found exactly one cohort row, eight governed relationships, eight distinct Walmart products, and two distinct ALDI products. UI and drawer labels no longer imply shelf-package medians, all_brand is presented as brand-neutral, and brand summaries count distinct products. Portfolio schema 1.5 and the semantic release gate reject duplicate cohorts, mixed bases, missing medians, and broken rollups for new publications. A cross-publication preflight found zero such defects in all 48 current documents and 1,032 cohort rows. A synchronous historical schema refresh was stopped after it impaired readiness; the API was recoverably restarted and returned ready. Existing schema 1.4 documents were not overwritten and remain authoritative until the backfill can run without affecting API health. No Search price, certification, match attribute, radius rule, or price formula changes.",
            ],
            [
              "2026-08-27",
              "Deployed and production-verified",
              "Competitive comparison-basis changes use demand-loaded, tab-specific scorecard projections with bounded recovery.",
              "Retailer, cohort, and assortment tabs request only the evidence they render; other report tabs make no portfolio request. Included-product relationships load only after the user opens one retailer drawer. A 20-second browser bound and Retry scorecards action replace the indefinite Building state. The live Vitamin scorecard basis switch completed in 2.36 seconds; its projected payload is 8.6 KB rather than the prior 1.29 MB complete document. Target evidence loaded on demand, all 60 Vitamin cohorts and the 649-product Milk catalog rendered, and both browser consoles were clean. CI run 33137061424 and Railway API/web commit c396153 passed. The immutable full portfolio, certified relationships, radius metrics, semantic audit, Search/PDP evidence, and report lineage are unchanged.",
            ],
            [
              "2026-08-27",
              "Deployed, backfilled, and production-verified",
              "Price Intelligence catalogs moved into durable trust-gated publication with server-side paging and filters.",
              "Every configured retailer gains a checksummed compact catalog staged and atomically activated with the report. Home requests 40 products at a time and filters by search, brand, brand type, and PDP seller without hydrating the entire catalog; full product/location/PDP evidence loads only after product selection. Production backfill proved that three concurrent cold catalogs can degrade readiness, so the governed worker and operational backfill run one at a time. Migration 0048_price_catalog is reversible. The zero-provider-call backfill installed all 36 required catalogs across six active reports, including every configured Egg and Vitamin retailer. Warm paged reads returned in 0.44–0.51 seconds; Walmart Milk Home returned HTTP 200 in 0.65 seconds with a 0.22-second response start. Live validation confirmed Egg 40-of-172 paging and expansion, Milk 40-of-649 paging and regional-brand filtering, lazy full-product evidence, and a clean browser console. A production-only prop-wiring defect that initially hid pagination after 40 products was corrected in commit 3ea1fe0. CI runs 33133624891, 33133947107, and 33135131201 passed. No Search, PDP, AI, certification, metric, source authority, report lineage, or archived-report behavior changed.",
            ],
            [
              "2026-08-27",
              "Implemented and incident-verified",
              "Price Intelligence cold projections no longer block API health and unrelated reads.",
              "A large cold Price Intelligence catalog projection previously ran CPU-heavy product-location preparation and schema validation on the FastAPI event-loop thread. The process remained marked running while health checks and small analysis reads timed out, causing the web application to report that the API was unavailable. The affected API instance was recoverably replaced, restoring web readiness. Product-offer normalization, Parquet record conversion, canonical population construction, full catalog projection, evidence export projection, and map projection now run in worker threads while deterministic output and caches remain unchanged. Concurrent requests for one cold catalog join a single shared task, and a browser timeout no longer cancels that build before it can populate the cache. Readiness stayed HTTP 200 throughout the production stress test and warm Milk catalogs returned in 0.46–0.78 seconds. The largest first build can still exceed the web timeout after an API deployment; durable publication-time catalog materialization is the next required performance phase. Regression coverage proves the event loop remains responsive and disconnected callers do not start duplicate projections. No Search, PDP, AI, certification, metric, report evidence, database, or audit-lineage data changed.",
            ],
            [
              "2026-08-27",
              "Production incident remediated and interaction-verified",
              "Competitive and Price Intelligence browser responsiveness is now a release-critical production gate.",
              "Large report projections and context counts are stable across tab changes; duplicate portfolio requests are removed; same-origin navigation has visible pending feedback. Catalog-only Price Intelligence responses omit unused full PDP and location-gap detail while product workspaces retain complete evidence, and catalog rows render progressively in groups of 40. The largest current catalog API response fell from 2,541,246 to 747,734 bytes and its page from 3,307,221 to 927,606 bytes. All nine Competitive Intelligence tabs, the Competitive View and Store Radius drawers, the included-products drawer, the largest Price Intelligence catalog, and a full product workspace were exercised live without console errors. Health and readiness plus the primary route libraries returned HTTP 200. No Search, PDP, AI, certification, metric, report evidence, or audit lineage changed.",
            ],
            [
              "2026-08-27",
              "Deployed, imported, and production-verified",
              "The current ALDI location roster moves to MetricsCart's new numeric Store IDs with authoritative replacement safeguards.",
              "The checksummed source contains 2,687 unique active USA Store IDs and MetricsCart location IDs across 41 states or districts and 2,550 normalized ZIPs. The catalog now admits numeric ALDI Store IDs and rejects legacy district-style IDs. Import f7182e06-1a40-498d-b6d8-4b5b4e651cab loaded all 2,687 rows with zero skips; post-import reconciliation found 2,687 eligible numeric IDs, zero eligible legacy IDs, and all 2,627 former IDs preserved as superseded. The canonical fixture grows by 60 ALDI locations to 157,866 total rows. Commit 9a73da8, all four Railway services, and CI run 33107649907 passed. No Search, PDP, or AI call was made, and prior 404 remediation is not claimed until a separate controlled provider preflight passes.",
            ],
            [
              "2026-08-27",
              "Production incident remediated and verified",
              "Web analytical reads no longer report a false API outage when a healthy cold request exceeds five seconds.",
              "The API and database remained healthy; production logs showed valid analytical reads occasionally completing after roughly seven seconds while the web server canceled every GET at five seconds. The bounded server-read window is now 20 seconds. Web health returned HTTP 200 with API dependency ok, the report library returned all six active reports, and ten warm internal list reads completed in 89–168 ms. No data, metric, report, provider call, or AI state changed.",
            ],
            [
              "2026-08-27",
              "Deployed, rematerialized, and production-verified",
              "Decision-quality certification now covers every active Competitive Intelligence publication.",
              "Vitamins, Milk, Strawberries, Eggs, Bananas, and Ground Beef expose all 204 required retailer × basis × radius contexts across 48 documents with zero blocking semantic errors. The gate verifies nested catalog-to-local-evidence funnels, coverage math, stable identity across radius, monotonic physical-store evidence, and constant delivery-ZIP service-area evidence. Shared repairs bind selective observation reads to the immutable governed artifact generation and keep unobserved certified relationships in the complete ledger without inflating observed funnels. Strawberries and Ground Beef are ready; Vitamins, Milk, Eggs, and Bananas are shareable with their explicit evidence caveats. The complete local suite passed 778 Python and 74 TypeScript tests plus all 91 normative contracts; GitHub Actions runs 33040753435, 33041986464, and 33042654180 passed. No provider, PDP, AI, certification, source-evidence, or audit-lineage change occurred.",
            ],
            [
              "2026-08-26",
              "Deployed, rematerialized, and production-verified",
              "Vitamin reporting gained a decision-quality context matrix and stricter semantic publication gate.",
              "All 54 retailer × basis × radius contexts are explicit: 28 scored, 17 local-evidence limited, and nine without a selected-basis relationship. The gate now blocks identity replacement, product-to-relationship outcome drift, incorrect funnel transitions, denominator drift, mixed price bases, and non-monotonic radius evidence. Production rematerialized the six retained Vitamin documents with zero provider calls and the public audit passes with zero blocking errors and 65 disclosed warnings. Competitive Intelligence Decision Readiness visibly distinguishes scored, limited, and governed-zero contexts. Commit 9be8a04 and GitHub Actions run 33035290829 passed the full release gate. No Search, PDP, AI, certification, source-evidence, or historical-report change occurred.",
            ],
            [
              "2026-08-26",
              "Deployed, rematerialized, and production-verified",
              "Vitamin Competitive Intelligence gained complete catalog-to-score evidence lineage and Product Pack-controlled default radius.",
              "Every retailer scorecard now separates the 322-product source catalog, 320-product governed in-scope catalog, observed Walmart products, certified identities, selected price-basis products, locally scored products, and final scored product-locations. A mutually exclusive six-state ledger includes the two governed topical-oil exclusions and downloads as CSV without inflating all six pre-materialized documents. Competitive Portfolio 1.4.0 blocks missing or internally inconsistent funnels and radius drift before publication. The UI no longer hard-codes three miles; radius-based Product Packs supply the initial 1/3/5-mile context. Six documents passed the production semantic gate, the live Target ledger reconciled 322 unique IDs, every reporting workspace rendered without a load error, and CI run 33021321217 passed all 15 browser tests. No Search, PDP, or AI call occurred and no certification, source, or historical report was mutated.",
            ],
            [
              "2026-08-26",
              "Deployed, rematerialized, and production-verified",
              "Vitamin scorecard unit-price eligibility and Cohort Scorecard drill-down lineage were repaired at their shared evidence boundaries.",
              "Competitive Portfolio 1.3.0 filters cohort calculations to the cohort's certified relationship IDs, persists those relationship summaries, and makes the browser drawer consume that same radius-native payload. The release audit blocks count or outcome-rollup drift. The shared Product Location projector now completes only missing Product Pack attributes from normalized PDP evidence before deriving missing metrics. Conservative written-unit plural handling recovers explicit counts such as 180 Gummies and 50 Tablets; a stated day supply is usable only with explicit one-unit-daily directions, while multi-unit dosage text is excluded from package count. Search remains authoritative for package price, availability, sponsorship, and store location. Production rebuilt all six exact/compatible 1-, 3-, and 5-mile documents with zero cohort lineage or outcome-rollup mismatches. At compatible specification / five miles, scored product-locations are Meijer 32, Sam's Club 16, BJ's 13, Walgreens 3, and Costco 1. The formerly empty Target vitamin-E cohort drawer now reconciles to all six certified relationships. GitHub Actions 33016471925 and Railway API/web/worker deployments passed. Certified matches and retained source evidence are unchanged; no provider or AI call was made.",
            ],
            [
              "2026-08-26",
              "Production reporting ready and trust-gated",
              "Vitamins & Supplements was replayed from an immutable Matching v2 release containing only the 480 certified relationships.",
              "The replay retained all 480 certified identities, excluded all 388 rejected and 1,448 insufficient-evidence relationships, and produced exactly 526 confirmed relationship-by-price-basis views: 48 relationships support package and normalized-unit price, 430 support normalized-unit price only, and two remain in identity and assortment lineage without unsupported price math. Six portfolio documents cover exact and compatible specification at 1, 3, and 5 miles. The semantic publication gate passed with zero errors and 68 explicit evidence-limit warnings. Result 5ea5b275-21f2-489e-b0f1-045ba43a14d0 is ready under publication checksum 93cd61595ee1267b776cd8c6ae874d463de182877b38e3241709546c46e20268. The source contains 23,716 retained Search rows; no MetricsCart or OpenAI call was made.",
            ],
            [
              "2026-08-26",
              "Production deployed and automation complete",
              "Vitamin evidence and match review gained governed queue-wide automation, and the ordinary release-profile blocker was corrected.",
              "Production reconciled 1,415 safe attribute claims across 837 products, completed 1,938 evidence-aware Luna reviews with zero failures, and first committed 372 defensible decisions: two comparable and 370 not comparable due to known hard-blocker conflicts. Product Pack 1.3.1 then corrected ordinary-release and package-count semantics. A fresh 1,920-case Luna pass completed with zero failures for $13.4568006; the checksum-bound gate committed 472 additional comparables and withheld one low-confidence case, 1,165 insufficient-evidence cases, and 282 AI-only rejections. The queue now contains 480 approved, 388 rejected, and 1,448 system-deferred cases. No approved case is release-blocked or lacks observed Search evidence. Reporting was not replayed.",
            ],
            [
              "2026-08-26",
              "Deployed and production-verified",
              "Product evidence claims gained guarded one-action reconciliation for the complete safe-consensus population.",
              "The deterministic policy admitted and committed 1,415 one-value claims across 837 products that fill an unknown attribute, retain exact image and visible-text citations, and meet a 95% minimum confidence floor. It retained 465 conflicting, value-changing, or weaker claims as exceptions. The preview bound the queue, lineage, policy, claim membership, selected values, and proposals to checksum cb206cd1e3fd82eafafa33960a3a638113875f5a58079b5da9e73e60beaf1b88; commit inserted the population atomically without changing a match or report. CI run 32974817009 and Railway deployment passed.",
            ],
            [
              "2026-08-26",
              "Production deployed and verified",
              "Matching v2 gained a product-level Product evidence claims workspace for governed PDP/image reconciliation.",
              "Eligible AI observations are consolidated by retailer listing and Product Pack attribute across the selected batch scope. Each administrator task retains every distinct cited image, visible label excerpt, proposed value, affected relationship, counterpart retailer, and observed-footprint count. Repetition across product pairs is audit context rather than independent proof; multiple proposed values fail closed as a conflict. Verification selects one exact source proposal, rejection applies to the complete claim, and both require rationale plus a current checksum. The append-only decision may update derived governed evidence only. It cannot mutate raw evidence, certify a relationship, start analysis, or publish reporting. Commit c916634 and GitHub Actions run 32969567204 passed 756 Python tests, 72 web unit tests, 15 browser tests, contracts, migrations, static checks, production builds, and all four container builds. Railway deployed the API and web successfully. The read-only production audit reconciled 3,953 eligible pair observations into exactly 1,880 product-attribute claims across 941 products: 1,753 awaiting review and 127 conflicts, with zero automatic verifications or rejections.",
            ],
            [
              "2026-08-26",
              "Production AI review complete; evidence reconciliation and certification pending",
              "The brand-enhanced Vitamin queue completed a bounded full-population gpt-5.6-luna review under an owner-approved $50 cap.",
              "Two immutable batches processed all 2,316 cases with zero failures for $16.7772558. A preflight bounded batch one at $46.878656 under an all-images/all-output-token assumption; after its actual $9.8828092 cost reconciled, the remaining 816 cases had a $25.529446 conservative exposure and completed for $6.8944466. Worker capacity temporarily scaled from one to 16 replicas and returned to one after completion; durable leases prevented duplicate claims. Results are six comparable, 549 not comparable, and 1,761 insufficient evidence. The trust audit found no comparable recommendation with an incompatible governed attribute, but only 25 cases currently pass bulk-certification policy. Image review produced 12,853 proposals: 8,899 corroborations, 3,431 missing-value completions, 247 refinements, 275 conflicts, and one invalid proposal. The 3,953 eligible proposals collapse to 1,880 distinct claims: 1,753 single-value consensus claims and 127 conflicts. Nothing was auto-verified, certified, released, or published.",
            ],
            [
              "2026-08-25",
              "Production deployed; successor import and trust audit passed",
              "Matching v2 gained independent checksum-bound carry-forward for human attribute-evidence decisions.",
              "Commit 0f5fb16 and GitHub Actions run 32927089584 passed Python, TypeScript, 15 browser tests, migrations, contracts, and all four container builds before Railway deployment. Production successor 2026.08.25-spring-valley-brand-shadow-10 contains all 2,316 immutable cases. It carried 28 exact source-bound administrator evidence decisions, each with explicit predecessor lineage, and safely omitted one image-derived brand decision superseded by stronger governed foundation evidence. All 2,316 certification recomputations succeeded with zero reconciliation conflicts or duplicate proposal checksums; the decisions are reused across 72 cases and 118 product-evidence applications. Governed brand verification covers 1,246 of 1,440 distinct listings (86.53%). The queue has zero final match decisions and remains non-authoritative until Match Certification, gold-set release, and governed replay. No MetricsCart or OpenAI call was made.",
            ],
            [
              "2026-08-25",
              "Production deployed and differential audit passed",
              "Attribute evidence reconciliation now distinguishes completion, corroboration, refinement, and conflict instead of treating every non-empty value as resolved.",
              "Commit 7f731ba deployed successfully to Railway and GitHub Actions run 32918348483 passed Python, TypeScript, 15 browser tests, migrations, contracts, and all four container builds. The read-only production audit reconciled 67 proposals and 65 distinct claims: 31 missing-value completions, 29 corroborations, two refinements, and five conflicts. All 29 administrator decisions retained their checksum binding (28 verified and one rejected); the 29 corroborations require no action, while nine previously hidden lower-authority completions/refinements/corrections are now reviewable. Governed and human-verified sources remain locked. No MetricsCart or OpenAI call was made.",
            ],
            [
              "2026-08-25",
              "Production deployed and API reconciliation verified",
              "Match Certification gained a queue-wide Attribute Evidence Proposals workspace grouped by immutable AI retry lineage.",
              "The protected proposal index groups the original batch and every lineage-linked retry, reports all, eligible, retained-ineligible, undecided, verified, and rejected counts, and supports retailer, lineage, eligibility, and decision filters. Production reconciles the bounded pilot as 25 cases, 67 proposals, 65 distinct claims, 29 eligible, and 38 retained ineligible. Each review card shows the exact cited image, visible label text, proposed typed value, confidence, listing identity, counterpart, and observed-store count. Existing checksum-bound verify/reject decisions are reused; AI remains advisory, ineligible proposals remain visible for audit, certification remains separate, and no report changes automatically. Commit e7338ec deployed successfully to Railway.",
            ],
            [
              "2026-08-25",
              "Production deployed and full differential audit passed",
              "Matching v2 now recomputes one checksum-bound deterministic certification view after governed PDP/image evidence reconciliation.",
              "Queue display, paid AI input, evidence-triggered AI re-analysis, individual certification, bulk preview/commit, and gold-set release now share the same derived evidence path. The generic engine reruns under the named active Product Pack profile, recalculates tier and eligible package/unit bases, and fails closed on policy/profile errors or conflicting verified evidence. Bulk policy 1.7.0 binds this derived view into preview and action checksums; unchanged AI input is not charged again. Declared unknown values cannot resolve evidence. All 2,316 vitamin cases recomputed successfully with zero errors and zero invalid checksums; the result remained 2,310 unresolved, five equivalent-product candidates, and one exact-specification candidate because no verified evidence decisions exist. GitHub Actions run 32897486492 and the Railway API/scheduler deployments passed. No MetricsCart or OpenAI call was made for the audit.",
            ],
            [
              "2026-08-25",
              "Production guard implemented; full release validation and deployment pending",
              "Matching v2 vision review now emits only source-attributable, Product-Pack-typed evidence for a genuinely unresolved listing-side attribute.",
              "The audit of 105 older Luna proposals found only two image-sourced claims and 103 structured restatements. The corrected 25-case pilot ultimately completed 25 of 25 for $0.2225386 and produced 67 image-sourced proposals with exact URLs, visible text, at least 0.90 confidence, and no cross-case claim conflicts. An initial heuristic found eight rewrites on rows already marked as matches; the stricter listing-side audit correctly treats conflicts between two known values as comparison evidence, not missing evidence. Prompt/schema 1.3.0 now binds each image URL to its exact listing and only attributes missing or declared unknown on that side; the deployed API makes 38 legacy rewrites ineligible and retains only 29 genuinely unresolved claims. No proposal was verified, no relationship was certified, and reporting did not change. The next bounded scope is 883 distinct-evidence cases covering all 1,020 unresolved product identities, not all 2,316 pair cases. Human verification, derived recomputation, certification, and publication remain separate gates; normalized-unit pricing still cannot create a match.",
            ],
            [
              "2026-08-25",
              "Production deployed and bounded validation completed",
              "The Matching v2 Luna response schema was aligned to the supported OpenAI Structured Outputs subset without weakening comparison-basis governance.",
              "An immutable 18-case batch spanning all nine vitamin competitors failed before inference because uniqueItems is not supported in a strict response schema and recorded $0.00. Commit 788fedd removed the provider keyword while preserving application rejection of duplicate, unknown, or excessive bases; GitHub Actions run 32891810158 and all four Railway deployments passed. Lineage-linked retry 8e862ad6-d981-43dd-b893-fa574d33f44d completed 18 of 18 on gpt-5.6-luna for $0.1312886: 10 insufficient-evidence, two not-comparable, and six comparable proposals. The audit exposed five tier-disagreement cases that were technically bulk-eligible under warning-only policy. No relationship was certified and reporting did not change. Policy 1.6.0 now constrains the request schema to the deterministic tier and eligible price bases, repeats those checks after generation, and makes missing, blocked, or disagreeing engine tiers hard certification exclusions. Live task 7ab6ea7f-23a2-4a8f-9dae-1a6e1c063766 validated the new boundary for $0.0023444: an edge with no tier or eligible price basis returned insufficient evidence, null tier, and no basis after structured-evidence image fallback. The 51,140-byte immutable bounded-run audit is stored under matching-v2/validations with SHA-256 091c153c04ca39d3b2e91fb2062f4bd2a63c2712ee7d0c99dc374d3fdc0288d9.",
            ],
            [
              "2026-08-25",
              "Production deployed and verified",
              "Vitamin matching separates product compatibility from package and normalized-unit price bases and moves new AI reviews to gpt-5.6-luna.",
              "Product Pack 1.3.0 requires known positive package counts before normalized-unit analysis. Prompt 1.1.0 first evaluates ingredient/formula, strength, form, release, and audience without price, then identifies package price, normalized unit price, or both. The API rejects a comparable draft whose proposed basis is absent or unsupported and binds valid bases into human bulk certification. Luna pricing is pinned at the current public $0.20/M input and $1.20/M output rates. Deterministic evidence remains authoritative; normalized unit pricing never creates a match and AI never auto-certifies. GitHub Actions run 32889170545 passed every release gate; Railway API deployment a2c6274f-655c-4aa8-9528-076ca0714e87 and worker deployment 4ffc7aad-ef19-4c5e-a819-973fac2b56b1 succeeded, and both live processes report gpt-5.6-luna. No paid AI or MetricsCart call was launched during deployment.",
            ],
            [
              "2026-08-24",
              "Implemented and regression-tested; deployment and replacement shadow pending",
              "Matching v2 gained distinct-product evidence reuse and a minimum-coverage AI review scope; Vitamins & Supplements advanced to Product Pack 1.2.4.",
              "A verified image attribute can be reused for the identical listing throughout one immutable queue only when the current policy checksum and source-bound proposal still agree; contradictory values fail closed. Administrators can prepare a deterministic set-cover scope that reviews distinct missing product evidence instead of every pair. Plural/ingredient-led supplement scope, comma-formatted strengths, Billion-CFU labels, and additional non-oral noise are repaired without enabling automatic approvals. No paid API or AI call was made.",
            ],
            [
              "2026-08-24",
              "Implemented and regression-tested; production counter repair required",
              "A failed Product Details task no longer terminates the durable worker loop.",
              "A manually requeued zero-cost transient job retained immutable attempt evidence but had its job counter reset, so the database uniqueness guard rejected a second attempt-1 snapshot. The worker now logs an isolated record failure and continues processing other leases; the affected durable lease remains recoverable. Production recovery must restore each affected job counter from its existing snapshot ledger before retrying. No snapshot is overwritten or deleted, no billable 404 is retried, and the credit ceiling remains unchanged.",
            ],
            [
              "2026-08-24",
              "Implemented and test-verified; production recovery in progress",
              "Product Details gained an account-wide provider limiter in addition to retailer limits.",
              "The 2,553-product Spring Valley enrichment produced synchronized zero-cost 429s across five retailer PDP lanes when ten replicas respected only the documented per-retailer limits. Every PDP request now acquires a shared two-per-second / 120-per-minute account permit and its three-per-second / 180-per-minute retailer permit. A 429 pauses both credential-scoped Postgres rows. Completed 200/404 evidence, immutable raw responses, leases, idempotency, and the 7,500-credit hard ceiling are unchanged; only nonbillable transient failures may be requeued after all old workers stop.",
            ],
            [
              "2026-08-24",
              "Implemented, release-verified, and deployed",
              "Product Details workers gained rolling concurrency without weakening durable queue controls.",
              "A 2,553-product Spring Valley enrichment exposed batch-tail latency: a worker waited for every claimed request before refilling, so one slow retailer idled capacity. The worker now retains unfinished leased tasks, waits only for the next completion, and refills the freed slots from the retailer-balanced SKIP LOCKED queue. Graceful shutdown finishes already-leased calls before closing the transport. The shared per-retailer limiter, cooldowns, leases, retries, cancellation, immutable raw evidence, idempotency, and 7,500-credit hard ceiling remain unchanged. Eighty-two Product Details and worker tests pass with three expected database-dependent skips; mypy and Ruff pass. The live run remains immutable and no duplicate provider call or AI task is created by this change.",
            ],
            [
              "2026-08-24",
              "Implemented during approved vitamin coverage recovery",
              "Durable collection claims now prioritize eligible retailer preflight tasks before released bulk work.",
              "The owner-approved Spring Valley Fishers panel launched as run 016e05c8-119b-4580-be1d-e7609fdd3621 with 850 Search calls, a hard 1,615-credit ($3.23) ceiling, and PDP disabled. Retryable Costco 429 and Meijer 500 preflights exposed starvation behind already-released work. The generic SKIP LOCKED claim order now places eligible preflights first without bypassing retailer gates, leases, retries, cancellation, idempotency, or the run budget.",
            ],
            [
              "2026-08-24",
              "Implemented and locally verified; paid collection not launched",
              "Radius collection planning gained a deterministic nearest-N location cap per competitor retailer.",
              "The optional maximum_locations_per_retailer_per_primary control selects the nearest N eligible stores independently for every competitor around each Walmart location; omitting it preserves all-stores-within-radius behavior. The production location-master planner identified Walmart 5767 in Fishers, Indiana as a one-anchor panel covering all eight physical competitors within five miles, with Amazon Same Day using ZIP 46038. N=1 bounds the proposed 85-keyword first stage to 850 Search calls and 1,615 credits ($3.23); exact-title recovery for 199 unobserved Walmart anchors adds at most 199 calls and credits ($0.398). No paid call has been launched.",
            ],
            [
              "2026-08-24",
              "Retained-evidence gate failed; paid recovery not launched",
              "The fourth Spring Valley shadow was completed retailer by retailer after the combined build exceeded one API replica's memory limit.",
              "The nine read-only builds produced 240 cases, ten plausible positive proposals, and zero automatic approvals. Recall still failed: 88–119 observed anchors lacked a candidate per retailer, competitor critical-attribute completion ranged from 10.7% to 55.9%, and 199 Walmart catalog anchors remained unobserved. No queue was imported and no Search, PDP, or AI spend occurred. The next safe action is a disclosed multi-market Search recovery followed by 30-day-cache-aware PDP enrichment.",
            ],
            [
              "2026-08-24",
              "Implemented; fourth retained-evidence shadow pending",
              "Spring Valley query context changed from a retrieval requirement to a preference after the third shadow failed recall.",
              "The third read-only shadow produced 116 cases and zero automatic approvals, and corrected retailer-breadcrumb brand contamination. It was not imported because exact shared-keyword gating left 106–122 observed Walmart anchors without candidates per retailer. Product Pack 1.2.3 now prefers shared query context while permitting cross-query structured/lexical retrieval, retains zero deterministic vitamin auto-approval, and excludes wipes, transdermal patches, and drink mixes from oral supplement candidates. No paid Search, PDP, or AI call was made; production remains unchanged.",
            ],
            [
              "2026-08-24",
              "Implemented and locally verified; third retained-evidence shadow pending deployment",
              "Spring Valley retrieval now uses bounded request-keyword context and PDP brand evidence without relaxing certification.",
              "The second read-only shadow used 2,187 retained PDP snapshots and produced 239 cases, but it failed recall and semantic precision gates and was not imported. Product Pack 1.2.2 records the exact Search keyword as retrieval-only context, requires shared context when both listings provide it, distinguishes additional high-risk vitamin formulations, and temporarily disables automatic vitamin certification. PDP brand resolution now excludes retailer breadcrumbs and descriptions, preventing a Nature Made item under a Meijer category path from becoming Meijer private label. Query context cannot override hard conflicts or certify a match. No paid Search, PDP, or AI call was made, and the quarantined production queue remains unchanged.",
            ],
            [
              "2026-08-24",
              "Implemented; second retained-evidence shadow pending",
              "The first Spring Valley coverage shadow was blocked, then retailer-brand and formula evidence were repaired without importing its queue.",
              "The read-only shadow used 2,187 retained PDP snapshots and produced 11,429 unresolved cases, proving broad retailer recall but unacceptable review volume. No case was imported. Product Pack 1.2.1 adds governed formula-family extraction, explicit Standard-release and General-audience absence policies, a 0.10 lexical floor, a 24-case retailer cap, and three candidates per brand lane. Versioned Retailer Packs add exact retailer-scoped private-label coverage for Amazon, BJ's, Costco, CVS, Meijer, Sam's Club, and Walgreens; existing Kroger and Target brands continue from the shared foundation. Brand classification cannot override ingredient, strength, form, release, or audience conflicts. No paid Search, PDP, or AI call was made.",
            ],
            [
              "2026-08-24",
              "Implemented and test-verified; first shadow blocked by precision gate",
              "Spring Valley matching gained an all-retailer coverage ledger and generic structured high-recall retrieval.",
              "Every one of the 322 governed Walmart anchors is now accounted for against each of the nine configured competitors as not observed, candidate found, or observed without a retained candidate. Product Pack 1.2.0 separates catalog-wide identity discovery from later geographic price applicability, preserves numeric strength evidence, and retains diverse competitor brand lanes before filling ranked candidate capacity. The same generic engine applies to every retailer; Target is not special-cased. Deterministic auto-approval is limited to verified exact-item or complete exact-specification evidence, while unknown hard blockers remain review-only. The existing 203-case queue remains quarantined and production reporting is unchanged. No MetricsCart, PDP, or OpenAI call was made; paid recovery Search requires a separate exact-call and spend approval after the retained-evidence shadow audit.",
            ],
            [
              "2026-08-24",
              "Implemented and validation pending deployment",
              "Matching v2 gained governed PDP/image attribute-evidence reconciliation before certification.",
              "Only exact-image, visible-text, confidence-qualified, Product-Pack-normalizable AI proposals can enter the reconciliation lane. Reviewer verify/reject decisions are immutable, checksum-bound, reversible by superseding events, and applied only to a derived certification view. Raw evidence remains unchanged; ambiguous images, structured AI proposals, conflicting verified values, and finalized cases fail closed. Individual and bulk certification consume the same reconciled view.",
            ],
            [
              "2026-08-24",
              "AI evidence review complete; human certification pending",
              "Every clean Spring Valley candidate received a new advisory review under the fail-closed Product Pack.",
              "All 203 latest AI tasks succeeded under gpt-5.6-terra for $16.4078975 recorded usage. The recommendation mix is 81 not comparable, 114 insufficient evidence, six equivalent product, and two exact specification; no prohibited comparable-substitute tier was proposed. All drafts require human review. The audit caught an AI rejection whose structured ingredient contradicted both title and image evidence. Bulk policy 1.4.0 therefore requires a known deterministic hard-blocker conflict for batch rejection and keeps AI-only or internally contradictory evidence in individual review. The server also blocks all insufficient-evidence cases and all eight positive proposals while deterministic hard-blocker evidence remains unresolved. A title-level audience audit found no adult, children, senior, prenatal, men, or women conflict among the positive proposals. Zero cases were automatically certified and all historical billing failures remain immutable zero-cost retry evidence.",
            ],
            [
              "2026-08-24",
              "Deployed, trust-gated, and clean successor imported",
              "Spring Valley vitamin certification is reset after a systematic life-stage and ingredient-policy defect.",
              "An audit found adult-to-children recommendations and certified relationships because life stage and active ingredient were configured as soft evidence; only 19 of 315 comparable AI proposals had complete critical evidence. Product Pack 1.1.2 makes ingredient/formulation, strength, strength unit, dosage form, release profile, and audience fail-closed hard blockers, removes audience and dosage identity terms from retrieval stop words, requires complete equivalent evidence, and prohibits broad comparable-substitute certification. Candidate discovery may retain a bounded lexical pair with missing critical evidence for PDP/vision review, but the same unknown remains a certification release blocker; known critical conflicts are excluded. Two non-imported dry runs exposed first an empty fail-closed funnel and then a 2,045-case low-similarity funnel; the governed similarity floor was raised from 0.05 to 0.15 after the evidence audit showed it removes 49 of 50 obvious audience-conflict pairs. The generic certification boundary now enforces Product-Pack-permitted tiers for individual review, adjudication, bulk acceptance, and gold-set export. All 300 existing vitamin decisions are excluded from carry-forward and reporting and remain only as immutable quarantined audit history. Clean successor 2026.08.24-spring-valley-7 was generated solely from retained Search/PDP evidence and imported with carry-forward disabled. Its checksum-bound 203 cases are all pending and unresolved; it has zero inherited decisions, AI drafts, active AI tasks, known hard conflicts, known seller-ineligible products, or zero-observation products. No MetricsCart or OpenAI call was made. Any paid review requires a new disclosed case-count and spend approval.",
            ],
            [
              "2026-08-23",
              "Deployed, production-verified, and actively processing",
              "Matching v2 AI review distinguishes successful drafts from terminal failures and tolerates provider image-download wording changes.",
              "The latest-batch panel no longer labels terminal failures as completed AI reviews: it separately reports drafts ready and failed tasks. Vision review now falls back to structured evidence for both documented OpenAI image-download error phrasings instead of failing the case. Production diagnosis of the Spring Valley queue found 1,185 tasks rejected for insufficient OpenAI credits and one image-download failure, zero successful drafts, zero certifiable recommendations, and zero recorded AI spend. After the owner restored credits, immutable retry batch b99c87dc-501b-4146-a819-807f0953e738 queued all 1,186 preserved failures under gpt-5.6-terra; the first completed task succeeded. Historical Matching v2 usage projects approximately $39 for the batch, while actual usage remains recorded per task. Commit 9867a60 and CI run 32680954184 are live.",
            ],
            [
              "2026-08-23",
              "Deployed and production-verified",
              "Product Details contracts gained fixed request parameters and retailer-fair parallel queue claiming.",
              "A controlled Walgreens diagnostic proved that the historical SFS request context and extra Search URL produced HTTP 400 while the same observed product, store, and ZIP returned HTTP 200 with a product-ID-only pickup request. The catalog now fixes provider-required parameters and selects the supported identity after observation values; durable queue serialization preserves both behaviors without retailer branches. Queue claims round-robin retailers within priority and the default claim concurrency rises from one to 18; the shared Postgres retailer/type limiter, credit ceiling, SKIP LOCKED claims, leases, retries, cancellation, and idempotency remain authoritative. Corrected run 09e1979f-36fd-45b4-8576-5138f1504ca8 completed 371/371 Walgreens products with HTTP 200 for 742 credits. Aggregate Spring Valley PDP spend including the diagnostic is 5,322 credits ($10.644), below the $15 ceiling. GitHub Actions runs 32671013676, 32671203338, and 32671662219 passed. No AI call was made.",
            ],
            [
              "2026-08-23",
              "Deployed, audited, and imported for certification",
              "Live Search collections gained a checksum-verified bridge into exhaustive Matching v2 certification.",
              "The bridge reads immutable successful Search pages, retains product-location evidence per retailer, selects the latest successful collection-linked PDP payload per product, and runs the generic Product Pack classifier and Matching v2 evaluator. Diagnostics containing zero, 40,162, and 2,243 cases were blocked before import because they were empty or still admitted an unreviewable candidate set. Product Pack 1.0.5 removes the false full-title active-ingredient value, exposes structured PDP specification fields to declared raw-field extractors, and bounds deterministic identity-oriented retrieval to five candidates per Spring Valley product and retailer. Production queue 2026.08.23-spring-valley-4 contains 1,186 pending cases covering 111 Spring Valley anchors and 605 competitor products across nine competitors; database audit found zero missing observed-location cases, zero non-Spring Valley anchors, and zero known third-party sellers. It remains non-authoritative until certification. CI run 32674158407 passed. No new MetricsCart or OpenAI call was made.",
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
            "Update the Retailer Integration Registry whenever a Search/PDP path, credit, required parameter, location rule, seller policy, runtime override, or enabled status changes.",
            "Update Source-to-Metric Lineage whenever a source authority, normalized field, grain, denominator, formula, exclusion, comparison radius, label, or drill-down changes.",
            "Review System Operations after every deployment and incident; update recovery attestations only after evidence is verified.",
            "Run the zero-credit release verifier for every production deployment; keep paid provider/AI canaries separately approved and recorded.",
            "Append a change-order row; do not silently replace history.",
          ],
        },
      ],
    },
  ],
};
