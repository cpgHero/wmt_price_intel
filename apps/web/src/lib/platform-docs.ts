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

const lastVerified = "August 16, 2026";

export const platformDocumentation: PlatformDocumentation = {
  title: "Platform Owner & Administrator Guide",
  version: "1.1.0",
  lastVerified,
  baseline:
    "Production implementation through guarded bulk AI match certification Phase 13.7",
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
            "The location master owns store identity, ZIP, city, state, country, latitude, and longitude.",
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
          text: "The existing governed matcher remains authoritative for current reports. Matching v2 is a shadow and certification system until a Product Pack passes its release gates and is explicitly cut over. A certification decision does not silently rewrite a published report.",
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
              "Match Workbench",
              "Inspect and revise currently governed report relationships.",
              "Creates a revision; reanalysis occurs only when explicitly triggered.",
            ],
            [
              "Match Certification",
              "Approve or reject Matching v2 evidence for release certification.",
              "One decision is final until flagged; it does not make v2 authoritative by itself.",
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
                "Retailer adapters call MetricsCart under shared per-retailer/type limits and cooldowns. Raw responses are written once to the private bucket as immutable, checksummed objects. HTTP 200 and 404 calls may be billable; costs remain auditable.",
            },
            {
              title: "7. Normalize without losing identifiers",
              detail:
                "Adapters map retailer payloads into shared contracts. Store IDs, retailer product IDs, ASINs, provider IDs, and leading-zero ZIPs stay strings. Errors become provider-error records rather than disappearing.",
            },
            {
              title: "8. Build the canonical product-location population",
              detail:
                "Keep in-scope positive-USD Search observations with usable locations. Deduplicate to the latest retailer × product × location × collection row, retain sponsorship evidence, disclose conflicts, and enrich geography from the location master.",
            },
            {
              title: "9. Exclude noise and known marketplace sellers",
              detail:
                "Product Pack qualification returns include, exclude, or review with reason codes. Retailer seller policy removes known non-first-party marketplace sellers; permitted blank sellers remain explicitly unverified.",
            },
            {
              title: "10. Enrich distinct admitted products",
              detail:
                "Reuse fresh PDP cache, then collect at most one representative observed location per distinct in-scope product unless contradictory evidence or a governed price-regime diagnostic requires another sample. PDP enhances identity—not local price.",
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
              link: { href: "/workspace/matches", label: "Match Workbench" },
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
                "Schema, quality, readiness, golden, reconciliation, and presentation checks must pass before a result is served. Raw evidence, derived artifacts, policies, and renderer versions remain traceable and immutable.",
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
            "Use a representative location where Search observed the product with a positive price.",
            "Add a targeted location sample only for contradictory identity evidence or a separately governed diagnostic; a price difference alone never changes Search price authority.",
            "Reuse immutable cached payloads and run zero-credit re-normalization when the normalizer improves.",
            "Retain useful identity, descriptions, identifiers, package facts, media, fulfillment, reviews, demand, and relationships; leave oversized provider-native bodies in raw evidence until a governed use exists.",
          ],
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
      links: [
        { href: "/workspace/matches", label: "Match Workbench" },
        { href: "/admin/matching-v2", label: "Match Certification" },
      ],
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
                "Product Pack policy marks each attribute matched, conflicting, unknown, or ignored and calculates evidence coverage separately from similarity.",
            },
            {
              title: "Resolve local applicability",
              detail:
                "A relationship applies only where the products are observed within the governed ZIP, radius, or service-area context. This supports four regional Walmart milk listings compared with one ALDI listing without averaging or double counting them globally.",
            },
            {
              title: "Review current authoritative relationships",
              detail:
                "Match Workbench is the editing surface for report relationships. Confirm, reject, undo, or manually pair products; changes create revisions and wait for explicit reanalysis.",
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
          text: "A user may request bounded AI drafts for up to 25 selected certification cases. Each request is a durable Postgres batch with queue-wide queued, reviewing, ready, and needs-attention counts; the latest batch shows completed items, timestamps, estimated remaining time, and recorded cost. The worker processes two cases concurrently by default. Structured evidence is always supplied; images are used only when critical structured evidence is missing or conflicting. The draft remains advisory. Vision proposals cite the source image and never treat an unseen claim as false.",
        },
        {
          kind: "callout",
          tone: "success",
          title: "Guarded bulk acceptance",
          text: "An administrator may assess up to 50 completed affirmative AI recommendations from the current filtered page. The server includes only pending exact-item, exact-specification, or equivalent-product recommendations when AI and the deterministic engine agree on tier, critical evidence coverage is 100%, there are no AI or Product Pack hard-blocker conflicts, every AI-proposed attribute is at least 85% confident, immutable evidence references exist, and no listing has a known third-party seller exclusion. The preview names every exclusion and binds the eligible case checksums, AI task/output checksums, queue version, and policy version into one confirmation checksum. One explicit administrator confirmation writes an immutable bulk-action audit record plus the same final human submission used by individual approval. No report reanalysis runs automatically; decisions remain final until flagged. Comparable-substitute and custom tiers always require individual review.",
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
                "Aggregates the canonical product-location observations within one retailer. Home selects a product; Product Overview combines identity, presence, price, sponsorship, and map evidence; Price Architecture explains the price distribution; Store Review focuses unusual prices and non-observations.",
            },
            {
              term: "Competitive Intelligence",
              definition:
                "Adds governed product relationships and location correspondence. It reports product leadership, retailer scorecards, price/cohort results, geography, assortment, match detail, and methodology using the same underlying observations.",
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
          text: "Product History remains unavailable until comparable snapshots are certified. Primary app pages are the current reporting surface; export, shareable HTML, email, and workbook parity will be reintroduced after the main tabs and workflows are finalized.",
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
                "Inspect pair evidence, images, attributes, scope, and alternate lenses. Save revisions, then choose whether they apply only here or to future collections. Trigger reanalysis explicitly when the review set is ready.",
              link: { href: "/workspace/matches", label: "Match Workbench" },
            },
            {
              title: "Certify v2 independently",
              detail:
                "Work the queue in descending observed-location exposure. Approve or reject once; use Needs evidence/Flag only when a final decision needs to be reopened. For completed affirmative AI drafts, use guarded bulk acceptance only after reading the eligible set and exclusion reasons; the administrator—not AI—confirms the final decisions.",
              link: {
                href: "/admin/matching-v2",
                label: "Match Certification",
              },
            },
            {
              title: "Validate the decision surface",
              detail:
                "Drill from scorecards, products, cohorts, assortment, and geography to the underlying relationship and store evidence. Totals must reconcile before the result is promoted or shared.",
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
                "A hard credit cap, daily/monthly budget, ALDI availability preflight, disabled feature flag, or missing separate PDP/AI approval may intentionally stop work.",
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
            "Reviewer identity is manually entered inside the protected admin session; individual accounts, verified identity, and RBAC are not yet implemented.",
            "Target marketplace seller rules are defined but not active until live seller values are certified.",
            "Product History is not presented until comparable cross-run snapshots, version compatibility, and continuity are certified.",
            "Exports, shareable HTML, leadership email, and workbook surfaces will be synchronized after the primary application experience is finalized.",
            "Population/county/demographic geography selectors await a governed data source and validation contract.",
            "Amazon Same Day remains a ZIP/delivery-market comparison rather than a fabricated physical-store model.",
            "A Search non-observation is inconclusive; it is not proof that a store does not carry a product or is out of stock.",
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
