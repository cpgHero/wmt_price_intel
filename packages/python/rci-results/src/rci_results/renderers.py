"""Pure renderers that present stored AnalysisResult values without recomputing metrics."""

# ruff: noqa: E501 - Embedded CSS/JavaScript is intentionally kept readable in final form.

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from email.message import EmailMessage
from html import escape
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import xlsxwriter  # type: ignore[import-untyped]

from rci_results.blueprints import ReportBlueprint, ReportBlueprintLoader, ReportProjector
from rci_results.contracts import ReportViewValidator, canonical_result_bytes
from rci_results.models import ArtifactPayload, ArtifactType, JsonObject

RENDERER_VERSION = "2.15.1"

_SECTION_EYEBROWS = {
    "executive_summary": "Leadership answer",
    "kpi_strip": "Decision scorecard",
    "coverage": "Market coverage",
    "price_position": "Package-price lens",
    "segment_analysis": "Normalized-value lens",
    "geographic_sensitivity": "Proximity validation",
    "product_table": "Assortment implications",
    "assortment": "Assortment intelligence",
    "recommendations": "Decision agenda",
    "data_quality": "Quality controls",
    "methodology": "Methodology",
}


def _rows(result: JsonObject, key: str) -> list[JsonObject]:
    value = result.get(key, [])
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _mapping(result: JsonObject, key: str) -> JsonObject:
    value = result.get(key, {})
    return value if isinstance(value, dict) else {}


def _display(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, list | dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _result_checksum(result: JsonObject) -> str:
    provenance = _mapping(result, "provenance")
    persisted = provenance.get("final_result_checksum_sha256")
    if isinstance(persisted, str) and len(persisted) == 64:
        return persisted
    return hashlib.sha256(canonical_result_bytes(result)).hexdigest()


def _compact_interactive_view(view: JsonObject) -> None:
    """Keep interactive report payloads decision-complete without audit-list bloat.

    Immutable AnalysisResult and publication artifacts retain the complete
    location scopes and PDP evidence. The browser read model needs only the
    product identity and aggregate counts; detailed match/location evidence is
    available through its governed drill-through APIs.
    """

    candidates = view.get("match_candidates")
    if isinstance(candidates, list):
        view["match_candidates"] = [
            {
                key: value
                for key, value in row.items()
                if key
                not in {
                    "benchmark_location_scope_keys",
                    "excluded_benchmark_location_scope_keys",
                }
            }
            if isinstance(row, dict)
            else row
            for row in candidates
        ]

    relationships = view.get("match_relationships")
    if isinstance(relationships, list):
        view["match_relationships"] = [
            {
                key: value
                for key, value in row.items()
                if key
                not in {
                    "benchmark_location_scope_keys",
                    "excluded_benchmark_location_scope_keys",
                }
            }
            if isinstance(row, dict)
            else row
            for row in relationships
        ]

    assortment = view.get("assortment_analysis")
    if not isinstance(assortment, dict):
        return
    retailers = assortment.get("retailers")
    if not isinstance(retailers, list):
        return
    compact_retailers: list[object] = []
    allowed_product_fields = {
        "product_id",
        "canonical_product_id",
        "name",
        "brand",
        "brand_type",
        "brand_origin",
        "brand_status",
        "image_url",
        "url",
        "seller",
        "observed_locations",
        "observed_zipcodes",
        "observed_brand",
    }
    for retailer in retailers:
        if not isinstance(retailer, dict):
            compact_retailers.append(retailer)
            continue
        compact = dict(retailer)
        products = retailer.get("products")
        if isinstance(products, list):
            compact_products: list[JsonObject] = []
            for product in products:
                if not isinstance(product, dict):
                    continue
                compact_product = {
                    key: value for key, value in product.items() if key in allowed_product_fields
                }
                attributes = product.get("attributes")
                observed_brand = attributes.get("brand") if isinstance(attributes, dict) else None
                if not isinstance(observed_brand, str) or not observed_brand.strip():
                    variants = product.get("attribute_variants")
                    if isinstance(variants, list):
                        observed_brand = next(
                            (
                                variant.get("brand")
                                for variant in variants
                                if isinstance(variant, dict)
                                and isinstance(variant.get("brand"), str)
                                and str(variant.get("brand")).strip()
                            ),
                            None,
                        )
                compact_product["observed_brand"] = (
                    observed_brand.strip()
                    if isinstance(observed_brand, str) and observed_brand.strip()
                    else product.get("brand")
                )
                compact_products.append(compact_product)
            compact["products"] = compact_products
        compact_retailers.append(compact)
    assortment["retailers"] = compact_retailers


def _metric_display(value: object, unit: object) -> str:
    normalized_unit = unit if isinstance(unit, str) else ""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return _display(value)
    if normalized_unit == "rate":
        return f"{value:.1%}"
    if normalized_unit.startswith("USD"):
        amount = f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"
        suffix_parts = normalized_unit.removeprefix("USD").split("_")
        suffix_parts = [part for part in suffix_parts if part]
        if suffix_parts and suffix_parts[0] == "per":
            suffix_parts.pop(0)
        suffix = " ".join(suffix_parts)
        return f"{amount} / {suffix}" if suffix else amount
    formatted = f"{value:,}" if isinstance(value, int) else f"{value:,.2f}"
    return f"{formatted} {normalized_unit}".rstrip()


def _safe_external_url(value: object) -> str | None:
    rendered = str(value or "").strip()
    return rendered if rendered.startswith(("https://", "http://")) else None


def _integer(value: object) -> int:
    try:
        return int(float(str(value or 0).replace(",", "")))
    except ValueError:
        return 0


def _topology_state_paths(topology: JsonObject) -> str:
    """Decode the same us-atlas TopoJSON used by the web workspace."""

    raw_arcs = topology.get("arcs", [])
    transform = _mapping(topology, "transform")
    scale = transform.get("scale", [1, 1])
    translate = transform.get("translate", [0, 0])
    if not (
        isinstance(raw_arcs, list)
        and isinstance(scale, list)
        and len(scale) == 2
        and isinstance(translate, list)
        and len(translate) == 2
    ):
        return ""

    decoded: list[list[tuple[float, float]]] = []
    for raw_arc in raw_arcs:
        if not isinstance(raw_arc, list):
            decoded.append([])
            continue
        x = y = 0.0
        points: list[tuple[float, float]] = []
        for raw_point in raw_arc:
            if not isinstance(raw_point, list) or len(raw_point) < 2:
                continue
            x += float(raw_point[0])
            y += float(raw_point[1])
            points.append(
                (
                    x * float(scale[0]) + float(translate[0]),
                    y * float(scale[1]) + float(translate[1]),
                )
            )
        decoded.append(points)

    def arc_points(index: int) -> list[tuple[float, float]]:
        points = decoded[index if index >= 0 else ~index]
        return points if index >= 0 else list(reversed(points))

    def ring_path(indices: object) -> str:
        if not isinstance(indices, list):
            return ""
        points: list[tuple[float, float]] = []
        for index in indices:
            if not isinstance(index, int):
                continue
            part = arc_points(index)
            points.extend(part if not points else part[1:])
        if not points:
            return ""
        commands = []
        for position, (longitude, latitude) in enumerate(points):
            x = ((longitude + 125) / 59) * 900 + 30
            y = ((50 - latitude) / 26) * 460 + 30
            commands.append(f"{'M' if position == 0 else 'L'}{x:.1f},{y:.1f}")
        return " ".join(commands) + " Z"

    objects = _mapping(topology, "objects")
    states = _mapping(objects, "states")
    geometries = states.get("geometries", [])
    if not isinstance(geometries, list):
        return ""
    paths: list[str] = []
    for geometry in geometries:
        if not isinstance(geometry, dict):
            continue
        coordinates = geometry.get("arcs", [])
        polygons = [coordinates] if geometry.get("type") == "Polygon" else coordinates
        if not isinstance(polygons, list):
            continue
        path = " ".join(
            ring_path(ring)
            for polygon in polygons
            if isinstance(polygon, list)
            for ring in polygon
            if isinstance(ring, list)
        )
        if path:
            paths.append(f"<path d='{path}'/>")
    return "".join(paths)


def _leadership_styles() -> str:
    return """
:root{color-scheme:light dark;--ink:rgba(10,10,12,.95);--muted:rgba(10,10,12,.62);
--paper:#f6f7fb;--card:#fff;--surface:#eef0f6;--accent:#0082c8;--highlight:#58d2f8;
--line:rgba(0,0,0,.14);--shadow:0 12px 30px rgba(0,0,0,.1)}
@media (prefers-color-scheme:dark){:root{--ink:rgba(255,255,255,.92);
--muted:rgba(255,255,255,.62);--paper:#0b0b0d;--card:#1a1a1d;--surface:#222228;
--accent:#58d2f8;--line:rgba(255,255,255,.1);--shadow:0 12px 30px rgba(0,0,0,.4)}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:1180px;margin:auto;padding:48px 28px 64px}
header{background:linear-gradient(135deg,rgba(0,130,200,.12),transparent 58%);
border-bottom:1px solid var(--line);border-radius:22px;padding:34px}
.brand{font-size:17px;font-weight:850;letter-spacing:-.04em}.brand b{color:var(--accent)}
.eyebrow,.kind{color:var(--accent);font-size:12px;font-weight:800;letter-spacing:.12em;
text-transform:uppercase}h1{font-size:clamp(38px,7vw,72px);font-weight:800;letter-spacing:-.055em;
line-height:.94;margin:12px 0 18px;max-width:13ch}h2{margin:0 0 12px;letter-spacing:-.025em}
.meta,.empty,small{color:var(--muted)}.deck{color:var(--muted);font-size:18px;max-width:720px}
.checksum{background:rgba(88,210,248,.12);
border:1px solid rgba(88,210,248,.35);border-radius:999px;color:var(--accent);display:inline-block;
font:11px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;margin-top:16px;padding:7px 10px}
.findings,.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.decision-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
article,section{background:var(--card);border:1px solid var(--line);border-radius:16px;
box-shadow:var(--shadow);padding:22px;margin-top:18px}article p{font-size:17px;margin:10px 0}
article span{color:var(--accent);font-size:12px;font-weight:800;letter-spacing:.1em;
text-transform:uppercase}
.narrative{background:rgba(88,210,248,.08);border-left:3px solid var(--accent);
border-radius:0 12px 12px 0;margin:14px 0 20px;max-width:900px;padding:18px 20px}
.narrative .narrative-subtitle{font-size:17px;font-weight:650;margin:0;line-height:1.55}
.narrative ul{display:grid;gap:9px;margin:14px 0 0;padding-left:20px}.narrative li{margin:0}
.narrative aside{background:var(--card);border:1px solid var(--line);border-radius:10px;
display:grid;gap:4px;margin-top:16px;padding:12px}.narrative aside b{color:var(--accent);
font-size:11px;letter-spacing:.09em;text-transform:uppercase}.narrative aside span{font-size:14px}
.metric{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px}
.metric strong{display:block;font-size:24px;margin-top:12px}.table-wrap{overflow:auto}
.comparison-chart{background:var(--surface);border:1px solid var(--line);border-radius:14px;
margin:18px 0;padding:18px}.comparison-chart figcaption strong,
.comparison-chart figcaption span,.chart-label strong,.chart-label span{display:block}
.comparison-chart figcaption span,.chart-label span,
.chart-note{color:var(--muted);font-size:12px}.chart-body{display:grid;gap:15px;margin-top:16px}
.chart-row{align-items:center;display:grid;gap:18px;grid-template-columns:minmax(170px,.8fr)
minmax(260px,2fr)}.chart-label strong{font-size:13px}.paired{display:grid;gap:5px}.paired>div{
align-items:center;display:grid;gap:8px;grid-template-columns:1fr 52px}
.paired i{background:var(--card);border-radius:999px;display:block;height:9px;overflow:hidden}
.paired b{border-radius:inherit;display:block;
height:100%}.paired b.benchmark{background:var(--ink)}.paired b.competitor{background:var(--accent)}
.paired>div>span{font-size:11px;text-align:right}.chart-note{border-top:1px solid var(--line);
margin:14px 0 0;padding-top:12px}.product-intro p{color:var(--muted);font-size:13px}
.map-controls{align-items:end;display:flex;gap:14px;justify-content:space-between;margin:16px 0}
.map-controls label{color:var(--muted);display:grid;font-size:11px;font-weight:800;gap:6px;
letter-spacing:.08em;text-transform:uppercase}.map-controls select{background:var(--surface);
border:1px solid var(--line);border-radius:9px;color:var(--ink);min-height:40px;padding:0 10px}
.map-legend{color:var(--muted);font-size:11px}.geo-map{margin:0}.geo-map svg{
background:var(--surface);
border:1px solid var(--line);border-radius:14px;display:block;width:100%}.geo-map .outline{
fill:var(--card);stroke:var(--muted);stroke-width:1.5}.geo-map circle{fill:#9b6100;opacity:.76;
stroke:var(--card);stroke-width:2}.geo-map circle.benchmark_lower{fill:var(--ink)}
.geo-map circle.competitor_lower{fill:var(--accent)}.geo-map figcaption{color:var(--muted);
font-size:12px;margin-top:8px}
.product-grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}
.product-card{align-items:center;background:var(--surface);box-shadow:none;display:grid;gap:14px;
grid-template-columns:72px 1fr;margin:0;padding:12px}.product-card img,
.product-placeholder{background:var(--card);
border-radius:9px;height:72px;object-fit:contain;width:72px}.product-placeholder{align-items:center;
color:var(--accent);display:flex;font-size:28px;justify-content:center}
.product-card h3{font-size:14px;
line-height:1.35;margin:5px 0}.product-card p{color:var(--muted);font-size:12px;margin:0}
.product-decision-intro{border-top:1px solid var(--line);margin-top:22px;padding-top:20px}
.product-decision-intro h3{font-size:18px;margin:0}.product-decision-intro p{color:var(--muted);
font-size:13px;margin:5px 0 14px}.product-decisions{display:grid;gap:12px;
grid-template-columns:repeat(auto-fit,minmax(310px,1fr))}.product-decision{background:var(--surface);
border-left:4px solid #9b6100;box-shadow:none;display:grid;gap:14px;grid-template-columns:118px 1fr;
margin:0;padding:14px}.product-decision.protect{border-left-color:var(--accent)}
.product-decision.parity{border-left-color:var(--muted)}.product-decision img,
.product-decision .product-placeholder{height:76px;width:112px}.product-pair{display:grid;gap:6px}
.product-pair-image{position:relative}.product-pair-image span{background:var(--ink);
border-radius:99px;color:white;font-size:8px;font-weight:800;left:5px;padding:3px 5px;
position:absolute;top:5px;z-index:1}.product-prices{display:flex;flex-wrap:wrap;gap:6px;
margin:8px 0}.product-prices b{background:var(--card);border:1px solid var(--line);
border-radius:7px;font-size:10px;padding:5px 7px}.product-decision h3{font-size:14px;
line-height:1.35;margin:5px 0}.product-decision p{color:var(--muted);font-size:11px;margin:4px 0}
.product-decision strong{display:block;font-size:13px;margin-top:8px}
.product-locations{display:flex;flex-wrap:wrap;gap:4px;list-style:none;margin:9px 0 0;padding:0}
.product-locations li{background:var(--card);border:1px solid var(--line);border-radius:999px;
color:var(--muted);font-size:10px;margin:0;padding:3px 6px}
.decision-card{background:var(--surface);box-shadow:none}.decision-card h3{font-size:17px;
line-height:1.35;margin:12px 0 0}.decision-card p{color:var(--muted);font-size:14px}
.evidence{border-top:1px solid var(--line);margin-top:20px;padding-top:14px}
.evidence summary{color:var(--accent);cursor:pointer;font-weight:750}
.evidence .table-wrap{margin-top:12px}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid var(--line);
padding:10px;text-align:left;vertical-align:top}th{color:var(--muted);font-size:11px;letter-spacing:.06em;
text-transform:uppercase}tbody tr:nth-child(even){background:var(--surface)}li{margin:10px 0}
.comparison-table{margin-top:18px}.comparison-table td:first-child{font-weight:750}
footer{border-top:1px solid var(--line);color:var(--muted);font-size:12px;margin-top:34px;
padding-top:18px}footer code{overflow-wrap:anywhere}
@media(max-width:700px){main{padding:24px 14px 44px}header{padding:24px 20px}section{padding:18px}
h1{font-size:42px}.chart-row{grid-template-columns:1fr}.map-controls{align-items:stretch;
flex-direction:column}}
"""


def _aligned_report_styles() -> str:
    return """
.report-nav{align-items:center;background:color-mix(in srgb,var(--card) 94%,transparent);
border:1px solid var(--line);border-radius:14px;display:flex;gap:4px;margin:18px 0 4px;
overflow-x:auto;padding:6px;position:sticky;top:8px;z-index:20;backdrop-filter:blur(16px)}
.report-nav a{border-radius:9px;color:var(--muted);font-size:12px;font-weight:750;
padding:8px 11px;text-decoration:none;white-space:nowrap}.report-nav a:hover,.report-nav a:focus{
background:var(--surface);color:var(--ink);outline:none}.report-group{background:transparent;border:0;
box-shadow:none;margin:28px 0 0;padding:0}.report-group>h2{font-size:26px;margin:0 0 4px}
.report-group>.group-note{color:var(--muted);margin:0 0 10px}.report-section{box-shadow:var(--shadow)}
.readiness{align-items:center;border-left:4px solid var(--accent);display:flex;gap:24px;
justify-content:space-between;margin-top:18px}.readiness.review_required{border-left-color:#9b6100}
.readiness.limited{border-left-color:var(--muted)}.readiness h2{font-size:20px;margin:3px 0}
.readiness p{color:var(--muted);margin:0}.readiness dl{display:grid;gap:8px;
grid-template-columns:repeat(3,minmax(80px,1fr));margin:0}.readiness dl div{background:var(--surface);
border-radius:10px;display:grid;padding:8px 12px}.readiness dt{color:var(--muted);font-size:9px;
font-weight:800;letter-spacing:.06em;text-transform:uppercase}.readiness dd{font-size:20px;font-weight:800;margin:0}
.comparison-basis td:first-child small{color:var(--muted);display:block;font-size:9px}
.product-decisions{grid-template-columns:repeat(auto-fit,minmax(390px,1fr))}
.product-decision{background:var(--card);border:1px solid var(--line);border-left:5px solid #9b6100;
border-radius:18px;display:grid;gap:18px;grid-template-columns:142px minmax(0,1fr);margin:0;
min-height:330px;padding:18px}.product-decision.protect{border-left-color:var(--accent)}
.product-decision.parity{border-left-color:var(--muted)}.product-pair{align-content:start;
display:grid;gap:9px;justify-items:center}.product-pair:after{color:var(--muted);content:'VS';
font-size:9px;font-weight:850;grid-row:2;letter-spacing:.12em}.product-pair-image{grid-row:auto;
height:112px;width:132px}.product-pair-image:first-child{grid-row:1}.product-pair-image:last-child{grid-row:3}
.product-pair-image span{background:rgba(10,10,12,.88);max-width:calc(100% - 10px);overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}.product-decision h3{font-size:15px;margin:4px 0}
.product-decision .benchmark-name{font-weight:760}.product-evidence{border-top:1px solid var(--line);
grid-column:1/-1;padding-top:12px}.product-evidence summary{color:var(--accent);cursor:pointer;font-weight:800}
.product-evidence-note{color:var(--muted);font-size:11px}.segment-matrix{border:1px solid var(--line);
border-radius:14px;overflow:auto}.segment-row{align-items:center;border-top:1px solid var(--line);
display:grid;gap:14px;grid-template-columns:minmax(240px,2fr) minmax(130px,.8fr)
minmax(120px,.7fr) minmax(110px,.7fr);min-width:760px;padding:12px 14px}.segment-row.head{
background:var(--surface);border:0;color:var(--muted);font-size:10px;font-weight:800;
letter-spacing:.06em;text-transform:uppercase}.segment-row strong,.segment-row span{display:block}
.segment-row small{color:var(--muted)}.leader{border-radius:999px;display:inline-block!important;
font-size:10px;font-weight:800;padding:4px 7px}.leader.benchmark{background:rgba(0,130,200,.12);
color:var(--accent)}.leader.competitor{background:rgba(155,97,0,.12);color:#9b6100}
.quality-explainer{background:linear-gradient(135deg,rgba(0,130,200,.1),transparent);
border:1px solid rgba(0,130,200,.25);border-radius:14px;padding:16px}.quality-explainer span{
color:var(--accent);font-size:10px;font-weight:850;letter-spacing:.08em;text-transform:uppercase}
.quality-explainer p{color:var(--muted);margin:6px 0 0}.quality-issues{display:flex;flex-wrap:wrap;
gap:7px;margin:14px 0}.quality-issues span{background:var(--surface);border:1px solid var(--line);
border-radius:999px;color:var(--muted);font-size:11px;padding:6px 9px}.quality-issues b{color:var(--ink)}
.quality-product{align-items:center;display:flex;gap:8px;min-width:250px}.quality-product img{background:white;
border:1px solid var(--line);border-radius:8px;height:44px;object-fit:contain;padding:2px;width:44px}
.quality-product span{display:grid}.quality-product small{font-size:10px}.quality-issue{background:rgba(155,97,0,.12);
border-radius:999px;color:#9b6100;display:inline-block;font-size:10px;font-weight:800;padding:4px 7px}
.map-controls{align-items:end;display:grid;grid-template-columns:minmax(260px,1.4fr)
minmax(180px,.7fr) minmax(280px,1.3fr)}.map-controls label span{display:block;margin-bottom:6px}
.map-stage{display:grid;gap:16px;grid-template-columns:minmax(0,3fr) minmax(230px,.85fr)}
.geo-map svg{background:linear-gradient(180deg,#edf7fb,#f8fbfc)}
.geo-map svg>rect{fill:transparent}
@media(prefers-color-scheme:dark){.geo-map svg{background:linear-gradient(180deg,#14242d,#11171c)}}
.geo-map .state-layer path{fill:color-mix(in srgb,var(--card) 86%,var(--surface));
stroke:color-mix(in srgb,var(--muted) 42%,transparent);stroke-linejoin:round;stroke-width:.85}
.geo-map .map-point-layer circle{cursor:pointer;opacity:.82;transition:opacity 120ms ease}
.geo-map .map-point-layer circle:hover,.geo-map .map-point-layer circle:focus{opacity:1;outline:none;
stroke-width:3}.map-rail{align-content:start;display:grid;gap:10px}.map-rail>div{background:var(--surface);
border:1px solid var(--line);border-radius:12px;display:grid;gap:4px;padding:12px}.map-rail .selected{
background:#053d4c;color:white}.map-rail span{color:var(--muted);font-size:10px}.map-rail .selected span{
color:rgba(255,255,255,.65)}.map-rail strong{font-size:19px}.map-rail .selected strong{font-size:13px}
.map-legend{display:flex;flex-wrap:wrap;gap:10px}.map-legend span:before{border-radius:50%;content:'';
display:inline-block;height:8px;margin-right:5px;width:8px}.map-legend .benchmark_lower:before{background:var(--ink)}
.map-legend .competitor_lower:before{background:var(--accent)}.map-legend .parity:before{background:#9b6100}
.key-points{display:grid}.key-point{align-items:start;border-bottom:1px solid var(--line);display:grid;
gap:16px;grid-template-columns:40px 1fr;padding:16px 0}.key-point>span{color:var(--accent);font-size:11px;
font-weight:850;letter-spacing:.08em}.key-point h3{font-size:15px;margin:0}.key-point p{color:var(--muted);
font-size:13px;margin:5px 0 0}.source-link{color:var(--accent);font-weight:800;text-decoration:none}
.retailer-scope{align-items:center;background:var(--card);border:1px solid var(--line);border-radius:14px;
display:flex;gap:16px;justify-content:space-between;margin:18px 0;padding:14px 16px}.retailer-scope div{
display:grid;gap:3px}.retailer-scope strong{font-size:14px}.retailer-scope span{color:var(--muted);
font-size:11px}.retailer-scope label{color:var(--muted);display:grid;font-size:10px;font-weight:800;
gap:5px;letter-spacing:.08em;text-transform:uppercase}.retailer-scope select{background:var(--surface);
border:1px solid var(--line);border-radius:9px;color:var(--ink);min-height:40px;min-width:240px;padding:0 10px}
.retailer-scorecard table{min-width:920px}.retailer-scorecard td:first-child small{color:var(--muted);
display:block;font-size:10px;margin-top:3px}.score-share{display:grid;gap:4px;grid-template-columns:120px 110px}
.score-share span{font-size:10px}.score-share span:nth-of-type(2){grid-column:1}.score-share i{background:var(--surface);
border-radius:999px;display:block;height:7px;overflow:hidden}.score-share i b{border-radius:inherit;display:block;
height:100%}.score-share i b.benchmark{background:var(--ink)}.score-share i b.competitor{background:var(--accent)}
.score-share i b.parity{background:#9b6100}.retailer-scorecard td>small{display:block;margin-top:5px;max-width:24ch}
.score-status{background:rgba(98,98,105,.12);border-radius:999px;color:var(--muted);display:inline-block;
font-size:10px;font-weight:800;padding:5px 8px}.score-status.ready{background:rgba(0,130,200,.12);color:var(--accent)}
[data-competitor-id][hidden]{display:none!important}.retailer-scope-note{background:rgba(88,210,248,.08);
border-left:3px solid var(--accent);color:var(--muted);display:none;font-size:12px;margin:12px 0;
padding:10px 12px}.retailer-scope-note.visible{display:block}
.assortment-score{display:grid;gap:14px}.assortment-score>article{border:1px solid var(--line);
border-radius:16px;padding:16px}.assortment-score header{align-items:center;display:flex;justify-content:space-between}
.assortment-score header span{background:var(--surface);border-radius:999px;color:var(--muted);font-size:10px;
font-weight:800;padding:6px 9px}.assortment-kpis{display:grid;gap:8px;grid-template-columns:repeat(5,1fr);
margin:14px 0}.assortment-kpis div{background:var(--surface);border-radius:11px;display:grid;gap:3px;padding:10px}
.assortment-kpis small,.assortment-products small{color:var(--muted);font-size:9px}.assortment-kpis b{font-size:21px}
.assortment-insights{display:grid;gap:12px;grid-template-columns:1fr 1fr}.assortment-insights section{border-top:1px solid var(--line);padding-top:12px}
.assortment-insights li{color:var(--muted);font-size:12px;line-height:1.45;margin:6px 0}
.assortment-products{display:grid;gap:8px;grid-template-columns:1fr 1fr}.assortment-products>section{background:var(--surface);border-radius:12px;padding:12px}
.assortment-product{align-items:center;border-top:1px solid var(--line);display:grid;gap:8px;grid-template-columns:42px 1fr;padding:8px 0}
.assortment-product img,.assortment-product .placeholder{background:white;border-radius:7px;height:42px;object-fit:contain;width:42px}
.assortment-product .placeholder{align-items:center;display:flex;justify-content:center}.assortment-product strong{display:block;font-size:11px}
@media(max-width:900px){.map-stage,.map-controls{grid-template-columns:1fr}.map-rail{grid-template-columns:
repeat(3,1fr)}.map-rail .selected{grid-column:span 3}.assortment-kpis{grid-template-columns:repeat(2,1fr)}}
@media(max-width:700px){.report-nav{top:4px}.product-decisions{grid-template-columns:1fr}
.product-decision{grid-template-columns:1fr}.product-pair{align-items:center;grid-template-columns:1fr auto 1fr}
.product-pair-image:first-child,.product-pair-image:last-child,.product-pair:after{grid-row:1}.product-pair-image{
width:100%}.map-rail{grid-template-columns:1fr 1fr}.map-rail .selected{grid-column:span 2}
.retailer-scope{align-items:stretch;flex-direction:column}.retailer-scope select{min-width:0;width:100%}
.assortment-insights,.assortment-products{grid-template-columns:1fr}}
"""


def _generated_at(result: JsonObject) -> datetime:
    value = str(result.get("generated_at", "1980-01-01T00:00:00+00:00"))
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _display_generated_at(result: JsonObject) -> str:
    generated_at = _generated_at(result)
    clock = generated_at.strftime("%I:%M %p").lstrip("0")
    return f"{generated_at.strftime('%B')} {generated_at.day}, {generated_at.year} at {clock} UTC"


def _zip_entry(filename: str) -> ZipInfo:
    entry = ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
    entry.compress_type = ZIP_DEFLATED
    entry.create_system = 3
    entry.external_attr = 0o600 << 16
    return entry


def _table(title: str, rows: list[JsonObject]) -> str:
    if not rows:
        return f"<section><h2>{escape(title)}</h2><p>No records supplied.</p></section>"
    columns = list(dict.fromkeys(key for row in rows for key in row if not key.startswith("_")))
    header = "".join(f"<th>{escape(column.replace('_', ' ').title())}</th>" for column in columns)
    body = "".join(
        "<tr>"
        + "".join(f"<td>{escape(_display(row.get(column)))}</td>" for column in columns)
        + "</tr>"
        for row in rows
    )
    return (
        f"<section><h2>{escape(title)}</h2><div class=table-wrap><table>"
        f"<thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div></section>"
    )


def _collapsed_table(title: str, rows: list[JsonObject]) -> str:
    if not rows:
        return ""
    columns = list(dict.fromkeys(key for row in rows for key in row if not key.startswith("_")))
    header = "".join(f"<th>{escape(column.replace('_', ' ').title())}</th>" for column in columns)
    body = "".join(
        f"<tr{_competitor_scope_attribute(row)}>"
        + "".join(f"<td>{escape(_display(row.get(column)))}</td>" for column in columns)
        + "</tr>"
        for row in rows
    )
    return (
        f"<details class=evidence><summary>{escape(title)}</summary><div class=table-wrap>"
        f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div></details>"
    )


def _inline_table(rows: list[JsonObject]) -> str:
    if not rows:
        return ""
    columns = list(dict.fromkeys(key for row in rows for key in row if not key.startswith("_")))
    header = "".join(f"<th>{escape(column.replace('_', ' ').title())}</th>" for column in columns)
    body = "".join(
        f"<tr{_competitor_scope_attribute(row)}>"
        + "".join(f"<td>{escape(_display(row.get(column)))}</td>" for column in columns)
        + "</tr>"
        for row in rows
    )
    return (
        '<div class="table-wrap comparison-table"><table><thead><tr>'
        f"{header}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _competitor_scope_attribute(row: JsonObject) -> str:
    competitor_id = row.get("_competitor_id") or row.get("competitor_id")
    if not competitor_id:
        return ""
    return f" data-competitor-id='{escape(str(competitor_id), quote=True)}'"


def _portfolio_overflow_attribute(
    row: JsonObject,
    positions: dict[int, int],
    limit: int,
) -> str:
    return " data-portfolio-overflow=true" if positions.get(id(row), 0) >= limit else ""


def _scorecard_rate(value: object) -> str:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return f"{float(value):.1%}"
    return "—"


def _retailer_scorecard_html(view: JsonObject) -> str:
    rows = _rows(view, "retailer_scorecards")
    if not rows:
        return ""
    benchmark = _display(view.get("benchmark_retailer") or "Reference retailer")
    body = "".join(
        "<tr"
        + _competitor_scope_attribute(row)
        + "><td><strong>"
        + escape(_display(row.get("competitor")))
        + "</strong><small>"
        + escape(_display(row.get("comparison_lens")))
        + "</small></td><td>"
        + f"{_integer(row.get('matches')):,}"
        + "</td><td>"
        + (
            f"{_integer(row.get('matched_geographies')):,}"
            if row.get("matched_geographies") is not None
            else "—"
        )
        + "</td><td><div class=score-share><span>"
        + escape(benchmark)
        + " <b>"
        + _scorecard_rate(row.get("benchmark_lower_rate"))
        + "</b></span><i><b class=benchmark style='width:"
        + f"{max(1.0, float(row.get('benchmark_lower_rate') or 0) * 100):.1f}%"
        + "'></b></i><span>"
        + escape(_display(row.get("competitor")))
        + " <b>"
        + _scorecard_rate(row.get("competitor_lower_rate"))
        + "</b></span><i><b class=competitor style='width:"
        + f"{max(1.0, float(row.get('competitor_lower_rate') or 0) * 100):.1f}%"
        + "'></b></i><span>Parity <b>"
        + _scorecard_rate(row.get("parity_rate"))
        + "</b></span><i><b class=parity style='width:"
        + f"{max(1.0, float(row.get('parity_rate') or 0) * 100):.1f}%"
        + "'></b></i></div></td><td>"
        + escape(_display(row.get("price_position")))
        + "</td><td><span class='score-status "
        + escape(str(row.get("status") or "limited_evidence"), quote=True)
        + "'>"
        + ("Ready" if row.get("status") == "ready" else "Limited evidence")
        + "</span><small>"
        + escape(_display(row.get("readiness_reason")))
        + "</small></td></tr>"
        for row in sorted(
            rows,
            key=lambda row: (_integer(row.get("matches")), _display(row.get("competitor"))),
            reverse=True,
        )
    )
    return (
        "<section class='report-section retailer-scorecard'><div class=kind>Competitive set</div>"
        "<h2>Retailer scorecard</h2><p class=group-note>One preferred comparison basis per "
        f"competitor. Each row names its configured comparison basis and unit. Lower-price shares "
        f"include {escape(benchmark)}, the competitor, and parity; the price-position statement "
        "uses the paired median of observation-level competitor-minus-reference differences.</p>"
        "<div class=table-wrap><table><thead><tr><th>Competitor</th><th>Matched observations"
        "</th><th>Matched ZIP markets</th><th>Lower-price share</th><th>Paired median price position"
        f"</th><th>Evidence</th></tr></thead><tbody>{body}</tbody></table></div></section>"
    )


def _report_readiness_html(view: JsonObject) -> str:
    readiness = _mapping(view, "report_readiness")
    governance = _mapping(view, "match_governance")
    status = str(readiness.get("status") or "limited")
    labels = {
        "ready": "Ready for decision use",
        "review_required": "Match review required",
        "limited": "Use with stated limitations",
    }
    reasons = [*_rows(readiness, "blocking_reasons"), *_rows(readiness, "warnings")]
    note = (
        _display(reasons[0].get("message"))
        if reasons
        else (
            f"{_integer(readiness.get('suppressed_decisions')):,} product decisions were "
            "withheld by deterministic evidence guardrails."
        )
    )
    return (
        f"<section class='report-section readiness {escape(status, quote=True)}'>"
        "<div><div class=kind>Decision readiness</div>"
        f"<h2>{escape(labels.get(status, labels['limited']))}</h2>"
        f"<p>{escape(note)}</p></div><dl><div><dt>Confirmed</dt><dd>"
        f"{_integer(governance.get('confirmed')):,}</dd></div><div><dt>Suggested</dt><dd>"
        f"{_integer(governance.get('suggested')):,}</dd></div><div><dt>Ambiguous</dt><dd>"
        f"{_integer(governance.get('ambiguous')):,}</dd></div></dl></section>"
    )


def _comparison_basis_html(view: JsonObject) -> str:
    rows = _rows(view, "comparison_bases")
    if not rows:
        return ""
    body = "".join(
        "<tr><td><strong>"
        + escape(_display(row.get("label")))
        + "</strong><small>"
        + escape(_display(row.get("profile_id")))
        + "</small></td><td>"
        + escape(_display(row.get("comparison_metric")).replace("_", " "))
        + "</td><td>"
        + escape(_display(row.get("package_basis")).replace("_", " "))
        + "</td><td>"
        + escape(_display(row.get("geography")).replace("_", " "))
        + "</td><td>"
        + escape(_display(row.get("scorecard_role", "configured")).replace("_", " "))
        + "</td></tr>"
        for row in rows
    )
    return (
        "<section class='report-section comparison-basis'><div class=kind>Comparison contract"
        "</div><h2>Price and segment lenses</h2><p class=group-note>Every result below states "
        "whether it compares exact package price, normalized unit price, or a configured "
        "proximity sensitivity.</p><div class=table-wrap><table><thead><tr><th>Lens</th>"
        "<th>Metric</th><th>Package basis</th><th>Geography</th><th>Scorecard role</th></tr>"
        f"</thead><tbody>{body}</tbody></table></div></section>"
    )


def _match_governance_html(view: JsonObject) -> str:
    relationships = _rows(view, "match_relationships")
    governance = _mapping(view, "match_governance")
    rows = [
        {
            "relationship_id": row.get("relationship_id") or row.get("id"),
            "status": row.get("status"),
            "competitor": row.get("competitor") or row.get("competitor_retailer_id"),
            "primary_product": row.get("benchmark_product_name") or row.get("benchmark_product_id"),
            "competitor_product": row.get("competitor_product_name")
            or row.get("competitor_product_id"),
            "eligible_lenses": row.get("eligible_profile_ids") or row.get("profile_ids"),
        }
        for row in relationships
    ]
    revision = governance.get("match_revision_id") or "No saved revision"
    return (
        "<section class=report-section><div class=kind>Governed one-to-one matching</div>"
        "<h2>Product relationship review</h2><p class=group-note>Relationship decisions are "
        "staged separately from the current publication. Use the application to confirm, reject, "
        f"or reset a pair. Current match revision: {escape(_display(revision))}.</p>"
        + _collapsed_table("View product relationships", rows)
        + "</section>"
    )


def _export_manifest_html(view: JsonObject) -> str:
    publication = _mapping(view, "publication")
    row = {
        "analysis_id": view.get("analysis_id"),
        "publication_version": publication.get("version"),
        "publication_status": publication.get("status"),
        "result_checksum": view.get("result_checksum"),
        "report_schema_version": view.get("schema_version"),
        "renderer_version": RENDERER_VERSION,
    }
    return (
        "<section class=report-section><div class=kind>Delivery integrity</div>"
        "<h2>Export manifest</h2><p class=group-note>The app, HTML report, leadership email, "
        "and workbook are projections of the same immutable AnalysisResult.</p>"
        + _collapsed_table("View export identifiers", [row])
        + "</section>"
    )


def _narrative_html(value: object) -> str:
    if isinstance(value, dict) and (
        value.get("subtitle") or value.get("bullets") or value.get("implication")
    ):
        subtitle = (
            f"<p class=narrative-subtitle>{escape(_display(value.get('subtitle')))}</p>"
            if value.get("subtitle")
            else ""
        )
        raw_bullets = value.get("bullets", [])
        bullets = (
            "<ul>"
            + "".join(
                f"<li>{escape(str(bullet))}</li>"
                for bullet in raw_bullets
                if isinstance(bullet, str) and bullet.strip()
            )
            + "</ul>"
            if isinstance(raw_bullets, list) and raw_bullets
            else ""
        )
        implication = (
            "<aside><b>Key point</b>"
            f"<span>{escape(_display(value.get('implication')))}</span></aside>"
            if value.get("implication")
            else ""
        )
        return f"<div class=narrative>{subtitle}{bullets}{implication}</div>"
    body = value.get("body") if isinstance(value, dict) else value
    paragraphs = [paragraph.strip() for paragraph in str(body or "").split("\n\n")]
    rendered = "".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs if paragraph)
    return f"<div class=narrative>{rendered}</div>" if rendered else ""


def _retailer_label(value: object) -> str:
    retailer_id = str(value)
    return {
        "walmart_us": "Walmart",
        "aldi_us": "ALDI",
        "amazon_us": "Amazon Same Day",
    }.get(retailer_id, retailer_id.replace("_us", "").replace("_", " ").title())


def _product_decisions(
    context: JsonObject,
    *,
    limit: int,
    title: str,
    benchmark_label: str,
    include_evidence: bool = False,
) -> str:
    all_decisions = _rows(context, "product_decisions")
    if not all_decisions:
        return ""
    decision_positions = {id(row): index for index, row in enumerate(all_decisions)}
    decisions = list(all_decisions[:limit])
    selected = {id(row) for row in decisions}
    competitor_counts: dict[str, int] = {}
    for row in all_decisions:
        competitor_id = str(row.get("competitor") or "competitor")
        count = competitor_counts.get(competitor_id, 0)
        if count < limit and id(row) not in selected:
            decisions.append(row)
            selected.add(id(row))
        competitor_counts[competitor_id] = count + 1
    cards: list[str] = []
    for row in decisions:
        priority = str(row.get("priority", "parity"))
        competitor = _retailer_label(row.get("competitor"))
        try:
            gap = float(row.get("median_gap", 0))
            geographies = int(row.get("geographies", 0))
        except (TypeError, ValueError):
            gap = 0
            geographies = 0
        position = (
            f"{competitor} is ${abs(gap):,.2f} lower at the median match"
            if gap < 0
            else f"{benchmark_label} is ${abs(gap):,.2f} lower at the median match"
            if gap > 0
            else "Median matched prices are tied"
        )
        status = {
            "attention": "Needs attention",
            "protect": "Position to protect",
            "parity": "Price parity",
        }.get(priority, "Price position")
        images = []
        for label, image_url in (
            (benchmark_label, row.get("benchmark_image_url")),
            (competitor, row.get("competitor_image_url")),
        ):
            image = (
                f'<img src="{escape(str(image_url), quote=True)}" alt="">'
                if image_url
                else "<div class=product-placeholder>P</div>"
            )
            images.append(
                f"<div class=product-pair-image><span>{escape(label)}</span>{image}</div>"
            )
        try:
            benchmark_price = float(row.get("median_benchmark_price", 0))
            competitor_price = float(row.get("median_competitor_price", 0))
        except (TypeError, ValueError):
            benchmark_price = competitor_price = 0
        summary = row.get("evidence_summary", {})
        store_count = (
            int(summary.get("benchmark_store_observations", 0)) if isinstance(summary, dict) else 0
        )
        zip_count = (
            _integer(summary.get("matched_zip_markets"))
            if isinstance(summary, dict)
            else geographies
        ) or geographies
        scope = (
            f"{store_count:,} observed benchmark stores across {zip_count:,} matched ZIP markets."
            if store_count
            else f"{zip_count:,} matched ZIP markets in the analytical comparison."
        )
        evidence_html = ""
        product_evidence = context.get("product_evidence", {})
        evidence = (
            product_evidence.get(str(row.get("id"))) if isinstance(product_evidence, dict) else None
        )
        if include_evidence and isinstance(evidence, dict):
            evidence_rows = _rows(evidence, "rows")
            shown = evidence_rows[:100]
            evidence_html = (
                "<details class=product-evidence><summary>View exact store evidence</summary>"
                f"<p class=product-evidence-note>{escape(_display(evidence.get('comparison_grain')))}. "
                f"Showing {len(shown):,} of {len(evidence_rows):,} retained rows; the app provides "
                "the complete downloadable CSV.</p>"
                f"{_inline_table(shown)}</details>"
            )
        overflow_attribute = (
            " data-portfolio-overflow=true" if decision_positions[id(row)] >= limit else ""
        )
        cards.append(
            f"<article class='product-decision {escape(priority)}' "
            f"data-competitor-id='{escape(str(row.get('competitor') or ''), quote=True)}'"
            f"{overflow_attribute}>"
            f"<div class=product-pair>{''.join(images)}</div><div>"
            f"<span>{escape(status)}</span>"
            f"<h3 class=benchmark-name>{escape(_display(row.get('benchmark_product_name')))}</h3>"
            f"<h3>{escape(_display(row.get('competitor_product_name')))}</h3>"
            f"<div class=product-prices><b>{escape(benchmark_label)} ${benchmark_price:,.2f}</b>"
            f"<b>{escape(competitor)} ${competitor_price:,.2f}</b></div>"
            f"<strong>{escape(position)}</strong><p>{escape(scope)}</p></div>{evidence_html}</article>"
        )
    return (
        f"<div class=product-decision-intro><h3>{escape(title)}</h3>"
        "<p>Each card names the exact product pair and median matched prices. PDP data supplies "
        "identity and imagery; search evidence remains authoritative for price and location."
        "</p></div>"
        f"<div class=product-decisions>{''.join(cards)}</div>"
    )


def _percent(value: object) -> float | None:
    try:
        parsed = float(str(value).replace("%", "").replace(",", ""))
    except ValueError:
        return None
    return max(0.0, min(parsed, 100.0))


def _comparison_chart(rows: list[JsonObject], *, benchmark_label: str) -> str:
    candidates = []
    for row in rows:
        benchmark = _percent(row.get("benchmark lower"))
        competitor = _percent(row.get("competitor lower"))
        if benchmark is None and competitor is None:
            continue
        try:
            matches = int(str(row.get("matches", 0)).replace(",", ""))
        except ValueError:
            matches = 0
        candidates.append((matches, row, benchmark, competitor))
    candidates.sort(key=lambda value: value[0], reverse=True)
    candidate_positions = {id(item[1]): index for index, item in enumerate(candidates)}
    rendered_candidates = list(candidates[:8])
    selected = {id(item[1]) for item in rendered_candidates}
    competitor_counts: dict[str, int] = {}
    for item in candidates:
        competitor_id = str(item[1].get("_competitor_id") or item[1].get("competitor"))
        count = competitor_counts.get(competitor_id, 0)
        if count < 8 and id(item[1]) not in selected:
            rendered_candidates.append(item)
            selected.add(id(item[1]))
        competitor_counts[competitor_id] = count + 1
    chart_rows = "".join(
        f"<div class=chart-row{_competitor_scope_attribute(row)}"
        f"{_portfolio_overflow_attribute(row, candidate_positions, 8)}>"
        "<div class=chart-label><strong>"
        f"{escape(_display(row.get('segment') or row.get('competitor')))}</strong>"
        f"<span>{escape(_display(row.get('competitor')))} · {matches:,} matches · "
        f"{escape(_display(row.get('matched geographies')))} geographies · "
        f"paired median difference "
        f"{escape(_display(row.get('paired median gap') if row.get('paired median gap') is not None else row.get('competitor - benchmark gap')))}</span></div>"
        f"<div class=paired><div><i><b class=benchmark style='width:{benchmark or 1}%'></b>"
        f"</i><span>{'—' if benchmark is None else f'{benchmark:.1f}%'}</span></div>"
        f"<div><i><b class=competitor style='width:{competitor or 1}%'></b></i>"
        f"<span>{'—' if competitor is None else f'{competitor:.1f}%'}</span></div></div></div>"
        for matches, row, benchmark, competitor in rendered_candidates
    )
    if not chart_rows:
        return ""
    return (
        "<figure class=comparison-chart><figcaption><strong>Lower-price share</strong>"
        "<span>Strict comparable-package outcomes with market coverage and "
        "paired median price difference · dark bar "
        f"{escape(benchmark_label)} · blue bar competitor</span></figcaption>"
        f"<div class=chart-body>{chart_rows}</div><p class=chart-note>Directional share "
        "among matched observations; see the supporting table for definitions and caveats."
        "</p></figure>"
    )


def _map_figure(
    context: JsonObject,
    *,
    state_paths: str,
    coverage_rows: list[JsonObject],
    benchmark_label: str,
) -> str:
    points: list[JsonObject] = []
    for point in _rows(context, "map_points"):
        try:
            latitude = float(point["latitude"])
            longitude = float(point["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if 24 <= latitude <= 50 and -125 <= longitude <= -66:
            points.append(point)
    if not points:
        return ""
    products = sorted(
        {
            str(point.get("benchmark_product_id")): str(
                point.get("benchmark_product_name") or point.get("label") or "Product"
            )
            for point in points
            if point.get("benchmark_product_id")
        }.items(),
        key=lambda item: item[1],
    )
    options = "".join(
        f"<option value='{escape(product_id, quote=True)}'>{escape(name)}</option>"
        for product_id, name in products
    )
    coverage = sorted(
        coverage_rows,
        key=lambda row: _integer(row.get("matched geographies")),
        reverse=True,
    )
    coverage_positions = {id(row): index for index, row in enumerate(coverage)}
    coverage_html = "".join(
        f"<div{_competitor_scope_attribute(row)}"
        f"{_portfolio_overflow_attribute(row, coverage_positions, 3)}>"
        f"<span>{escape(_display(row.get('competitor')))}</span>"
        f"<strong>{_integer(row.get('matched geographies')):,} matched ZIP markets</strong></div>"
        for row in coverage
        if _integer(row.get("matched geographies"))
    )
    points_json = json.dumps(points, ensure_ascii=False, separators=(",", ":")).replace(
        "<", "\\u003c"
    )
    script = """
<script>(()=>{const data=JSON.parse(document.getElementById('map-data').textContent);
const benchmarkName=__BENCHMARK_NAME__;const product=document.getElementById('map-product');const outcome=document.getElementById('map-outcome');
const layer=document.getElementById('map-point-layer');const ns='http://www.w3.org/2000/svg';
const fmt=n=>Number(n||0).toLocaleString('en-US');const project=p=>({x:((Number(p.longitude)+125)/59)*900+30,y:((50-Number(p.latitude))/26)*460+30});
function render(){const selectedCompetitor=document.getElementById('report-competitor')?.value||'all';const selectedRetailer=window.rciRetailerScope?.competitors?.find(row=>row.id===selectedCompetitor);const retailerMatches=window.rciRetailerMatches||((value,row)=>String(value)===String(row?.id));const filtered=data.filter(p=>(selectedCompetitor==='all'||retailerMatches(p.competitor,selectedRetailer))&&(product.value==='all'||String(p.benchmark_product_id)===product.value)&&(outcome.value==='all'||(p.outcome||'parity')===outcome.value));
const counts={benchmark_lower:0,competitor_lower:0,parity:0};const clusters=new Map();
for(const p of filtered){const keyOutcome=p.outcome||'parity';counts[keyOutcome]=(counts[keyOutcome]||0)+Number(p.matches||1);const q=project(p);const key=`${Math.round(q.x/14)}:${Math.round(q.y/14)}:${keyOutcome}`;const current=clusters.get(key);if(current)current.count+=Number(p.matches||1);else clusters.set(key,{point:p,count:Number(p.matches||1),...q});}
layer.replaceChildren();for(const {point:p,count,x,y} of clusters.values()){const c=document.createElementNS(ns,'circle');c.setAttribute('cx',x);c.setAttribute('cy',y);c.setAttribute('r',Math.min(11,4+Math.sqrt(count)));c.setAttribute('class',p.outcome||'parity');c.setAttribute('tabindex','0');c.setAttribute('role','button');const label=[p.benchmark_product_name||p.label,p.zipcode?`ZIP ${p.zipcode}`:'',p.competitor?`vs. ${p.competitor}`:'',p.value_label||'',count>1?`${count} nearby observations`:''].filter(Boolean).join(' · ');const title=document.createElementNS(ns,'title');title.textContent=label;c.append(title);const show=()=>{document.getElementById('map-detail-name').textContent=p.benchmark_product_name||p.label||'Selected product';document.getElementById('map-detail-scope').textContent=`ZIP ${p.zipcode||'—'} · vs. ${p.competitor||'competitor'}`;document.getElementById('map-detail-value').textContent=p.value_label||'Price evidence';};c.addEventListener('click',show);c.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();show();}});layer.append(c);}
document.getElementById('map-current').textContent=product.value==='all'?`All mapped ${benchmarkName} products`:product.options[product.selectedIndex].text;document.getElementById('map-observations').textContent=fmt(filtered.length);for(const key of ['benchmark_lower','competitor_lower','parity']){for(const node of document.querySelectorAll(`[data-map-count="${key}"]`))node.textContent=fmt(counts[key]||0);}}
product.addEventListener('change',render);outcome.addEventListener('change',render);document.addEventListener('rci:competitor-change',render);render();})();</script>
"""
    script = script.replace("__BENCHMARK_NAME__", json.dumps(benchmark_label))
    return (
        f"<div class=map-controls><label><span>{escape(benchmark_label)} product</span>"
        f"<select id=map-product><option value=all>All mapped {escape(benchmark_label)} products</option>{options}"
        "</select></label><label><span>Price outcome</span><select id=map-outcome>"
        "<option value=all>All outcomes</option><option value=competitor_lower>Competitor lower"
        f"</option><option value=benchmark_lower>{escape(benchmark_label)} lower</option><option value=parity>"
        "Price parity</option></select></label><div class=map-legend>"
        f"<span class=benchmark_lower>{escape(benchmark_label)} lower · <b data-map-count=benchmark_lower>0</b></span>"
        "<span class=competitor_lower>Competitor lower · <b data-map-count=competitor_lower>0</b></span>"
        "<span class=parity>Parity · <b data-map-count=parity>0</b></span></div></div>"
        "<div class=map-stage><figure class=geo-map><svg viewBox='0 0 960 520' role=img "
        "aria-label='Analysis-linked geographic price outcomes'><rect width=960 height=520 rx=22>"
        "</rect>"
        f"<g class=state-layer>{state_paths}</g><g class=map-point-layer id=map-point-layer></g>"
        "</svg><figcaption>Circle size reflects nearby matched observations. Select a point for "
        "its product, ZIP, retailer, and price difference.</figcaption></figure><aside class=map-rail>"
        "<div class=selected><span>Current view</span><strong id=map-current>All mapped benchmark "
        f"{escape(benchmark_label)} products</strong></div><div><span>Mapped observations</span><strong id=map-observations>0"
        "</strong></div><div><span>Competitor lower</span><strong data-map-count=competitor_lower>0"
        f"</strong></div><div><span>{escape(benchmark_label)} lower</span><strong data-map-count=benchmark_lower>0"
        "</strong></div><div class=selected><span>Selected evidence</span><strong id=map-detail-name>"
        "Select a point</strong><span id=map-detail-scope>ZIP and retailer detail</span><b "
        f"id=map-detail-value>Price evidence</b></div>{coverage_html}</aside></div>"
        f"<script type=application/json id=map-data>{points_json}</script>{script}"
    )


def _product_highlights(context: JsonObject) -> str:
    all_products = _rows(context, "product_highlights")
    if not all_products:
        return ""
    product_positions = {id(row): index for index, row in enumerate(all_products)}
    products = list(all_products[:8])
    selected = {id(row) for row in products}
    retailer_counts: dict[str, int] = {}
    for row in all_products:
        retailer = str(row.get("retailer") or "retailer")
        count = retailer_counts.get(retailer, 0)
        if count < 8 and id(row) not in selected:
            products.append(row)
            selected.add(id(row))
        retailer_counts[retailer] = count + 1
    cards = "".join(
        "<article class=product-card data-retailer-id='"
        + escape(str(product.get("retailer") or ""), quote=True)
        + "'"
        + _portfolio_overflow_attribute(product, product_positions, 8)
        + ">"
        + (
            f"<img src='{escape(str(product['image_url']), quote=True)}' alt='' loading=lazy>"
            if product.get("image_url")
            else "<div class=product-placeholder aria-hidden=true>•</div>"
        )
        + "<div><span>"
        + escape(_display(product.get("retailer")))
        + "</span><h3>"
        + escape(_display(product.get("name")))
        + "</h3>"
        + (f"<p>{escape(_display(product.get('brand')))}</p>" if product.get("brand") else "")
        + "</div></article>"
        for product in products
    )
    return (
        "<div class=product-intro><h3>Products to know</h3><p>PDP-enriched identity and "
        "imagery; search observations remain authoritative for price.</p></div>"
        f"<div class=product-grid>{cards}</div>"
    )


def _assortment_analysis(context: JsonObject, *, benchmark_label: str) -> str:
    assortment = _mapping(context, "assortment_analysis")
    comparisons = _rows(assortment, "comparisons")
    retailers = {str(row.get("retailer")): row for row in _rows(assortment, "retailers")}
    benchmark = retailers.get(str(assortment.get("benchmark_retailer")), {})
    if not comparisons:
        return ""

    def product_list(title: str, products: list[JsonObject]) -> str:
        rows = "".join(
            "<div class=assortment-product>"
            + (
                f"<img src='{escape(str(row['image_url']), quote=True)}' alt='' loading=lazy>"
                if row.get("image_url")
                else "<div class=placeholder>•</div>"
            )
            + "<div><strong>"
            + escape(_display(row.get("name")))
            + "</strong><small>"
            + f"{_integer(row.get('observed_locations')):,} locations · "
            + f"{_integer(row.get('observed_zipcodes')):,} ZIPs"
            + "</small></div></div>"
            for row in products[:8]
        )
        return f"<section><h4>{escape(title)}</h4>{rows or '<p class=empty>None observed.</p>'}</section>"

    cards = []
    for row in comparisons:
        competitor_id = str(row.get("competitor") or "")
        competitor = _retailer_label(competitor_id)
        competitor_summary = retailers.get(competitor_id, {})
        geography = _mapping(row, "geography")
        kpis = (
            (benchmark_label + " products", benchmark.get("distinct_products")),
            (competitor + " products", competitor_summary.get("distinct_products")),
            ("Product relationships", row.get("product_relationships")),
            (benchmark_label + "-only", row.get("benchmark_only_products")),
            (competitor + " whitespace", row.get("competitor_whitespace_products")),
        )
        kpi_html = "".join(
            f"<div><small>{escape(label)}</small><b>{_integer(value):,}</b></div>"
            for label, value in kpis
        )
        key_points = "".join(
            f"<li>{escape(str(point))}</li>" for point in row.get("key_points", [])
        )
        geographic_points = (
            f"<li>{benchmark_label} has broader observed variety in "
            f"{_integer(geography.get('benchmark_broader_zipcodes')):,} shared ZIPs.</li>"
            f"<li>{competitor} has broader observed variety in "
            f"{_integer(geography.get('competitor_broader_zipcodes')):,} shared ZIPs.</li>"
            f"<li>{_integer(geography.get('parity_zipcodes')):,} shared ZIPs have the same "
            "distinct-product count.</li>"
        )
        cards.append(
            f"<article data-competitor-id='{escape(competitor_id, quote=True)}'><header>"
            f"<div><div class=kind>{escape(benchmark_label)} vs. {escape(competitor)}</div>"
            "<h3>Product relationship and whitespace scorecard</h3></div>"
            f"<span>{_integer(geography.get('shared_zipcodes')):,} shared ZIPs</span></header>"
            f"<div class=assortment-kpis>{kpi_html}</div>"
            "<div class=assortment-insights><section><h4>Key points</h4>"
            f"<ul>{key_points}</ul></section><section><h4>Store-market breadth</h4>"
            f"<ul>{geographic_points}</ul></section></div><div class=assortment-products>"
            + product_list(
                f"{benchmark_label}-only products",
                _rows(row, "top_benchmark_only"),
            )
            + product_list(
                f"{competitor} whitespace",
                _rows(row, "top_competitor_whitespace"),
            )
            + "</div></article>"
        )
    return (
        "<section class=report-section><div class=kind>Assortment intelligence</div>"
        f"<h2>Where {escape(benchmark_label)} overlaps—and where each retailer stands alone</h2>"
        "<p class=group-note>Search supplies store presence and observed product counts. Product "
        "Pack rules govern matches; PDP supplies identity and imagery where available.</p>"
        f"<div class=assortment-score>{''.join(cards)}</div></section>"
    )


def _segment_matrix(rows: list[JsonObject], *, benchmark_label: str) -> str:
    ranked: list[tuple[int, JsonObject, float | None, float | None]] = []
    for row in rows:
        benchmark = _percent(row.get("benchmark lower"))
        competitor = _percent(row.get("competitor lower"))
        if benchmark is None and competitor is None:
            continue
        ranked.append((_integer(row.get("matches")), row, benchmark, competitor))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked:
        return ""
    ranked_positions = {id(item[1]): index for index, item in enumerate(ranked)}
    rendered_ranked = list(ranked[:16])
    selected = {id(item[1]) for item in rendered_ranked}
    competitor_counts: dict[str, int] = {}
    for item in ranked:
        competitor_id = str(item[1].get("_competitor_id") or item[1].get("competitor"))
        count = competitor_counts.get(competitor_id, 0)
        if count < 16 and id(item[1]) not in selected:
            rendered_ranked.append(item)
            selected.add(id(item[1]))
        competitor_counts[competitor_id] = count + 1
    body = "".join(
        "<div class=segment-row"
        + _competitor_scope_attribute(row)
        + _portfolio_overflow_attribute(row, ranked_positions, 16)
        + "><div><strong>"
        + escape(_display(row.get("segment") or "Comparable items"))
        + "</strong><small>"
        + escape(_display(row.get("competitor")))
        + "</small></div><div><span class='leader "
        + ("benchmark" if (benchmark or 0) >= (competitor or 0) else "competitor")
        + "'>"
        + escape(
            benchmark_label
            if (benchmark or 0) >= (competitor or 0)
            else _display(row.get("competitor"))
        )
        + "</span><strong>"
        + f"{max(benchmark or 0, competitor or 0):.1f}%"
        + "</strong></div><div><strong>"
        + f"{matches:,}"
        + "</strong><small>matched observations</small></div><strong>"
        + escape(
            _display(
                row.get("paired median gap")
                if row.get("paired median gap") is not None
                else row.get("competitor - benchmark gap")
            )
        )
        + "</strong></div>"
        for matches, row, benchmark, competitor in rendered_ranked
    )
    return (
        "<div class=segment-matrix><div class='segment-row head'><span>Comparable product "
        "segment</span><span>Lower-price leader</span><span>Matched evidence</span>"
        f"<span>Paired median difference</span></div>{body}</div>"
    )


def _quality_evidence(context: JsonObject) -> str:
    rows = _rows(context, "quality_observations")
    if not rows:
        return (
            "<p class=empty>No source search observations were retained for this publication.</p>"
        )
    issue_counts: dict[str, int] = {}
    for row in rows:
        issue = str(row.get("issue") or "Quality observation")
        issue_counts[issue] = issue_counts.get(issue, 0) + 1
    issues = "".join(
        f"<span><b>{count:,}</b> {escape(issue)}</span>" for issue, count in issue_counts.items()
    )
    body: list[str] = []
    for row in rows:
        image_url = _safe_external_url(row.get("image_url"))
        source_url = _safe_external_url(row.get("source_url"))
        image = (
            f"<img src='{escape(image_url, quote=True)}' alt='' loading=lazy>" if image_url else ""
        )
        source = (
            f"<a class=source-link href='{escape(source_url, quote=True)}' target=_blank "
            "rel='noreferrer'>Open result</a>"
            if source_url
            else "—"
        )
        price = row.get("price")
        rendered_price = (
            f"${float(price):,.2f}" if isinstance(price, int | float) else _display(price)
        )
        body.append(
            "<tr data-retailer-id='"
            + escape(str(row.get("retailer") or ""), quote=True)
            + "'><td><span class=quality-issue>"
            + escape(_display(row.get("issue")))
            + "</span></td><td>"
            + escape(_retailer_label(row.get("retailer")))
            + "</td><td><div class=quality-product>"
            + image
            + "<span><b>"
            + escape(_display(row.get("product")))
            + "</b><small>"
            + escape(_display(row.get("product_id")))
            + "</small></span></div></td><td>"
            + escape(rendered_price)
            + "</td><td>"
            + escape(_display(row.get("zipcode")))
            + "</td><td>"
            + escape(_display(row.get("store")))
            + "</td><td>"
            + escape(_display(row.get("reason")))
            + "</td><td>"
            + source
            + "</td></tr>"
        )
    table = (
        "<div class='table-wrap comparison-table'><table><thead><tr><th>Issue</th><th>Retailer"
        "</th><th>Search product</th><th>Price</th><th>ZIP</th><th>Store</th><th>Reason"
        "</th><th>Source</th></tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
    )
    return (
        "<div class=quality-explainer><span>What this section contains</span><strong>Source "
        "search records behind the quality counts</strong><p>This is a representative, "
        "deterministic sample of rejected or incomplete search observations—not PDP data. "
        "Product, retailer, ZIP, store, source price, and exclusion reason stay together for "
        f"review.</p></div><div class=quality-issues data-portfolio-summary=true>{issues}</div>"
        f"{table}<p class=chart-note>"
        f"Showing {len(rows):,} representative source observations. Authoritative issue totals "
        "remain in the governed narrative above.</p>"
    )


def _key_point_list(rows: list[JsonObject]) -> str:
    unique: list[JsonObject] = []
    seen: set[str] = set()
    for row in rows:
        identity = json.dumps(
            [
                row.get("summary"),
                row.get("action"),
                row.get("title"),
                row.get("text"),
                row.get("rationale"),
            ],
            ensure_ascii=False,
        )
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(row)
    rendered = "".join(
        "<article class=key-point><span>"
        + escape(f"{index:02d}")
        + "</span><div><h3>"
        + escape(
            _display(
                row.get("summary")
                or row.get("action")
                or row.get("title")
                or row.get("text")
                or "Decision signal"
            )
        )
        + "</h3>"
        + (
            f"<p>{escape(_display(detail))}</p>"
            if (detail := row.get("detail") or row.get("rationale") or row.get("description"))
            else ""
        )
        + "</div></article>"
        for index, row in enumerate(unique[:8], start=1)
    )
    return f"<div class=key-points>{rendered}</div>" if rendered else ""


class LeadershipHtmlRenderer:
    def __init__(self, *, state_paths: str = "") -> None:
        self._state_paths = state_paths

    def render(
        self,
        result: JsonObject,
        view: JsonObject | None = None,
        *,
        presentation_context: JsonObject | None = None,
    ) -> bytes:
        if view is not None:
            return self._render_blueprint(result, view, presentation_context or {})
        product_pack = _mapping(result, "product_pack")
        pack_name = escape(_display(product_pack.get("name") or product_pack.get("id")))
        analysis_id = escape(_display(result.get("analysis_id")))
        generated_at = escape(_display_generated_at(result))
        result_checksum = escape(_result_checksum(result))
        findings = _rows(result, "findings")
        recommendations = _rows(result, "recommendations")
        narrative = "".join(
            f"<article><span>{escape(_display(row.get('severity', 'finding')))}</span>"
            f"<p>{escape(_display(row.get('text')))}</p></article>"
            for row in findings
        )
        actions = "".join(
            f"<li><strong>{escape(_display(row.get('priority')))}</strong> "
            f"{escape(_display(row.get('text')))}</li>"
            for row in recommendations
        )
        document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{pack_name} analysis</title>
<style>{_leadership_styles()}</style></head><body><main data-result-checksum="{result_checksum}">
<header><div class="brand">CPG<b>Hero</b></div>
<div class="eyebrow">Leadership intelligence brief</div>
<h1>{pack_name}</h1>
<div class="meta">Analysis {analysis_id} · Generated {generated_at}</div>
<div class="checksum">Result checksum · {result_checksum}</div>
</header><h2>What matters</h2>
<div class="findings">{narrative or "<p>No findings supplied.</p>"}</div>
<section><h2>Recommended actions</h2>
<ol>{actions or "<li>No recommendations supplied.</li>"}</ol></section>
{_table("Competitive position", _rows(result, "comparisons"))}
{_table("Geographic coverage", _rows(result, "coverage"))}
{_table("Segments", _rows(result, "segments"))}
{_table("Validation", [_mapping(result, "validation")])}
{_table("Data quality", [_mapping(result, "data_quality")])}
{_table("Provenance", [_mapping(result, "provenance")])}
<footer>CPGHero Retail Competitive Intelligence · Immutable result
<code>{result_checksum}</code></footer>
</main></body></html>"""
        return document.encode("utf-8")

    def _render_blueprint(
        self,
        result: JsonObject,
        view: JsonObject,
        presentation_context: JsonObject,
    ) -> bytes:
        product_pack = _mapping(view, "product_pack")
        report_context = {**view, **presentation_context}
        pack_name = escape(_display(product_pack.get("name") or product_pack.get("id")))
        result_checksum = escape(_result_checksum(result))
        benchmark_label = str(view.get("benchmark_retailer") or "Benchmark")
        sections = {str(section.get("id")): section for section in _rows(view, "sections")}
        groups = _rows(view, "groups")
        if not groups:
            groups = [
                {
                    "id": "summary",
                    "label": "Report",
                    "section_ids": list(sections),
                }
            ]
        special_groups = {"match-review", "exports"}
        populated_groups = [
            group
            for group in groups
            if group.get("id") in special_groups
            or any(str(section_id) in sections for section_id in group.get("section_ids", []))
        ]
        nav = "".join(
            f"<a href='#{escape(str(group.get('id')), quote=True)}'>"
            f"{escape(_display(group.get('label')))}</a>"
            for group in populated_groups
        )
        section_html = "".join(
            self._group(
                group,
                sections,
                report_context,
                benchmark_label=benchmark_label,
            )
            for group in populated_groups
        )
        retailer_scope = _mapping(view, "retailer_scope")
        competitor_options = _rows(retailer_scope, "competitors")
        scope_control = ""
        scope_script = ""
        if competitor_options:
            options = "".join(
                f"<option value='{escape(str(row.get('id')), quote=True)}'>"
                f"{escape(_display(row.get('name')))}</option>"
                for row in competitor_options
            )
            scope_control = (
                "<div class=retailer-scope><div><strong>Competitive view</strong><span>Use one "
                "publication for the full competitive set, then focus every evidence surface on "
                "one retailer.</span></div><label>Competitor<select id=report-competitor>"
                f"<option value=all>All competitors ({len(competitor_options)})</option>{options}"
                "</select></label></div><p class=retailer-scope-note id=retailer-scope-note>"
                "Retailer-only view: portfolio narrative is hidden so it cannot be mistaken for "
                "retailer-specific commentary. Scorecards and visible evidence reflect the "
                "selected retailer.</p>"
            )
            scope_data = json.dumps(retailer_scope, ensure_ascii=False, separators=(",", ":"))
            scope_script = """
<script>(()=>{const select=document.getElementById('report-competitor');if(!select)return;
const scope=__RETAILER_SCOPE__;const token=value=>String(value||'').toLowerCase().replace(/\\(us\\)/g,'').replace(/[^a-z0-9]/g,'');
const matches=(value,retailer)=>Boolean(retailer)&&(token(value)===token(retailer.id)||token(value)===token(retailer.name));window.rciRetailerMatches=matches;window.rciRetailerScope=scope;
const note=document.getElementById('retailer-scope-note');function apply(){const selected=select.value;const retailer=scope.competitors.find(row=>row.id===selected);
for(const node of document.querySelectorAll('[data-competitor-id]')){node.hidden=selected==='all'?node.dataset.portfolioOverflow==='true':!matches(node.dataset.competitorId,retailer);}
for(const node of document.querySelectorAll('[data-retailer-id]')){node.hidden=selected==='all'?node.dataset.portfolioOverflow==='true':!(matches(node.dataset.retailerId,scope.benchmark)||matches(node.dataset.retailerId,retailer));}
for(const node of document.querySelectorAll('[data-portfolio-narrative]')){node.hidden=selected!=='all';}
for(const node of document.querySelectorAll('[data-retailer-title]')){node.hidden=selected==='all';if(retailer)node.textContent=`${retailer.name}: ${node.dataset.retailerTitle}`;}
for(const node of document.querySelectorAll('[data-portfolio-summary]')){node.hidden=selected!=='all';}
note?.classList.toggle('visible',selected!=='all');document.dispatchEvent(new CustomEvent('rci:competitor-change',{detail:{competitor:selected}}));}
select.addEventListener('change',apply);apply();})();</script>
"""
            scope_script = scope_script.replace("__RETAILER_SCOPE__", scope_data)
        document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{pack_name} analysis</title>
<style>{_leadership_styles()}{_aligned_report_styles()}</style></head><body><main data-result-checksum="{result_checksum}">
<header><div class="brand">CPG<b>Hero</b></div>
<div class="eyebrow">Leadership intelligence brief</div>
<h1>{pack_name}</h1><p class="deck">Where the price war is being won, where it is being lost,
and which targeted moves matter most.</p><div class="meta">
Analysis {escape(_display(result.get("analysis_id")))} ·
Generated {escape(_display_generated_at(result))}</div><div class=checksum>Deterministic metrics ·
Evidence linked · Result checksum {result_checksum[:12]}…</div>
</header>{scope_control}{_report_readiness_html(report_context)}<nav class=report-nav aria-label='Report sections'>{nav}</nav>{section_html}{scope_script}<footer>CPGHero Retail Competitive Intelligence · Immutable result
<code>{result_checksum}</code></footer></main></body></html>"""
        return document.encode("utf-8")

    def _group(
        self,
        group: JsonObject,
        sections: dict[str, JsonObject],
        presentation_context: JsonObject,
        *,
        benchmark_label: str,
    ) -> str:
        group_id = str(group.get("id") or "report")
        group_sections = [
            sections[str(section_id)]
            for section_id in group.get("section_ids", [])
            if str(section_id) in sections
        ]
        content: list[str] = []
        if group_id == "overview":
            scorecard = _retailer_scorecard_html(presentation_context)
            if scorecard:
                content.append(scorecard)
        if group_id == "price-segments":
            basis = _comparison_basis_html(presentation_context)
            if basis:
                content.append(basis)
        if group_id == "geography" and _rows(presentation_context, "map_points"):
            coverage = next(
                (
                    _rows(section, "records")
                    for section in group_sections
                    if section.get("kind") == "coverage"
                ),
                [],
            )
            content.append(
                "<section class=report-section><div class=kind>Market coverage</div>"
                f"<h2>Where {escape(benchmark_label)} products win and lose</h2>"
                "<p class=group-note>Filter the "
                "map by product or outcome. State boundaries provide geographic context; every "
                "point is tied to retained search-price evidence.</p>"
                + _map_figure(
                    presentation_context,
                    state_paths=self._state_paths,
                    coverage_rows=coverage,
                    benchmark_label=benchmark_label,
                )
                + "</section>"
            )
        if group_id == "products":
            highlights = _product_highlights(presentation_context)
            if highlights:
                content.append(f"<section class=report-section>{highlights}</section>")
            decisions = _product_decisions(
                presentation_context,
                limit=16,
                title="Product-level price evidence",
                benchmark_label=benchmark_label,
                include_evidence=True,
            )
            if decisions:
                content.append(f"<section class=report-section>{decisions}</section>")
        if group_id == "assortment":
            assortment = _assortment_analysis(
                presentation_context,
                benchmark_label=benchmark_label,
            )
            if assortment:
                content.append(assortment)
        if group_id == "match-review":
            content.append(_match_governance_html(presentation_context))
        if group_id == "exports":
            content.append(_export_manifest_html(presentation_context))
        for section in group_sections:
            if section.get("kind") in {"kpi_strip", "assortment"}:
                continue
            content.append(
                self._section(
                    section,
                    presentation_context,
                    benchmark_label=benchmark_label,
                )
            )
        return (
            f"<section class=report-group id='{escape(group_id, quote=True)}'>"
            f"<h2>{escape(_display(group.get('label')))}</h2>"
            f"<p class=group-note>App and shareable-report view</p>{''.join(content)}</section>"
        )

    def _section(
        self,
        section: JsonObject,
        presentation_context: JsonObject,
        *,
        benchmark_label: str,
    ) -> str:
        section_kind = str(section.get("kind", ""))
        title = escape(_display(section.get("title")))
        kind = escape(_SECTION_EYEBROWS.get(section_kind, section_kind.replace("_", " ").title()))
        narrative = section.get("narrative")
        narrative_html = _narrative_html(narrative) if isinstance(narrative, dict) else ""
        title_html = f"<h2>{title}</h2>"
        if narrative_html and section_kind not in {"data_quality", "methodology"}:
            narrative_html = narrative_html.replace(
                "<div class=narrative>",
                "<div class=narrative data-portfolio-narrative=true>",
                1,
            )
            title_html = (
                f"<h2 data-portfolio-narrative=true>{title}</h2>"
                f"<h2 data-retailer-title='{kind}' hidden></h2>"
            )
        metrics: list[JsonObject] = []
        metric_html = "".join(
            f"<div class=metric><span>{escape(_display(metric.get('name')))}</span>"
            f"<strong>{escape(_metric_display(metric.get('value'), metric.get('unit')))}</strong>"
            "</div>"
            for metric in metrics
        )
        metric_grid = f"<div class=metrics>{metric_html}</div>" if metric_html else ""
        records = _rows(section, "records")
        if section_kind == "coverage":
            detail = _collapsed_table("View source coverage detail", records)
        elif section_kind == "price_position":
            chart = _comparison_chart(records, benchmark_label=benchmark_label)
            detail = f"{chart}{_collapsed_table('View supporting detail', records)}"
        elif section_kind == "segment_analysis":
            detail = (
                f"{_segment_matrix(records, benchmark_label=benchmark_label)}"
                f"{_collapsed_table('View evidence-backed detail', records)}"
            )
        elif section_kind in {"geographic_sensitivity", "product_table"}:
            detail = _collapsed_table("View evidence-backed detail", records)
        elif section.get("visualization") == "ranked_cards" and not narrative_html:
            repeated_detail = (
                len({str(row.get("summary") or row.get("rationale") or "") for row in records[:5]})
                == 1
                and len(records[:5]) > 1
            )
            cards = "".join(
                LeadershipHtmlRenderer._record_card(
                    row,
                    index,
                    include_detail=not repeated_detail,
                )
                for index, row in enumerate(records[:5])
            )
            detail = f"<div class=decision-cards>{cards}</div>" if cards else ""
        elif section_kind == "executive_summary":
            detail = _product_decisions(
                presentation_context,
                limit=6,
                title="Products changing the competitive picture",
                benchmark_label=benchmark_label,
            )
        elif section_kind == "data_quality":
            detail = _quality_evidence(presentation_context)
        elif section_kind == "recommendations":
            detail = _collapsed_table("View supporting detail", records)
        else:
            detail = _collapsed_table("View evidence-backed detail", records)
        empty = (
            f"<p class=empty>{escape(_display(section.get('empty_state')))}</p>"
            if section.get("empty")
            else ""
        )
        return (
            f"<section class=report-section id={escape(_display(section.get('id')))}><div class=kind>{kind}</div>"
            f"{title_html}{narrative_html}{metric_grid}{detail}{empty}</section>"
        )

    @staticmethod
    def _record_card(row: JsonObject, index: int, *, include_detail: bool = True) -> str:
        rank = row.get("priority") or row.get("severity") or index + 1
        headline = (
            row.get("title")
            or row.get("action")
            or row.get("summary")
            or row.get("text")
            or "Decision signal"
        )
        detail = (
            row.get("summary")
            if row.get("title") and row.get("summary") != row.get("title")
            else row.get("detail") or row.get("rationale") or row.get("description")
        )
        detail_html = (
            f"<p>{escape(_display(detail))}</p>" if include_detail and detail is not None else ""
        )
        return (
            f"<article class=decision-card><span>{escape(_display(rank))}</span>"
            f"<h3>{escape(_display(headline))}</h3>{detail_html}</article>"
        )


class ExcelAuditRenderer:
    _SECTIONS = (
        ("Coverage", "coverage"),
        ("Segments", "segments"),
        ("Comparisons", "comparisons"),
        ("Findings", "findings"),
        ("Recommendations", "recommendations"),
    )

    @staticmethod
    def _write_rows(workbook: object, name: str, rows: list[JsonObject]) -> None:
        worksheet = workbook.add_worksheet(name)  # type: ignore[attr-defined]
        header_format = workbook.add_format(  # type: ignore[attr-defined]
            {
                "bold": True,
                "font_color": "#58D2F8",
                "bg_color": "#0F0F11",
                "border": 0,
                "text_wrap": True,
                "valign": "vcenter",
            }
        )
        body_format = workbook.add_format(  # type: ignore[attr-defined]
            {"font_color": "#0A0A0C", "valign": "top", "text_wrap": True}
        )
        alternate_format = workbook.add_format(  # type: ignore[attr-defined]
            {
                "font_color": "#0A0A0C",
                "bg_color": "#F6F7FB",
                "valign": "top",
                "text_wrap": True,
            }
        )
        numeric_formats = {
            (False, "integer"): workbook.add_format(  # type: ignore[attr-defined]
                {
                    "font_color": "#0A0A0C",
                    "valign": "top",
                    "num_format": "#,##0",
                }
            ),
            (True, "integer"): workbook.add_format(  # type: ignore[attr-defined]
                {
                    "font_color": "#0A0A0C",
                    "bg_color": "#F6F7FB",
                    "valign": "top",
                    "num_format": "#,##0",
                }
            ),
            (False, "rate"): workbook.add_format(  # type: ignore[attr-defined]
                {
                    "font_color": "#0A0A0C",
                    "valign": "top",
                    "num_format": "0.0%",
                }
            ),
            (True, "rate"): workbook.add_format(  # type: ignore[attr-defined]
                {
                    "font_color": "#0A0A0C",
                    "bg_color": "#F6F7FB",
                    "valign": "top",
                    "num_format": "0.0%",
                }
            ),
            (False, "currency"): workbook.add_format(  # type: ignore[attr-defined]
                {
                    "font_color": "#0A0A0C",
                    "valign": "top",
                    "num_format": "$#,##0.00;[Red]-$#,##0.00",
                }
            ),
            (True, "currency"): workbook.add_format(  # type: ignore[attr-defined]
                {
                    "font_color": "#0A0A0C",
                    "bg_color": "#F6F7FB",
                    "valign": "top",
                    "num_format": "$#,##0.00;[Red]-$#,##0.00",
                }
            ),
        }
        empty_format = workbook.add_format(  # type: ignore[attr-defined]
            {"font_color": "#626269", "italic": True}
        )
        worksheet.hide_gridlines(2)
        worksheet.set_tab_color("#58D2F8")
        if not rows:
            worksheet.write(0, 0, "No records supplied", empty_format)
            worksheet.set_column(0, 0, 28)
            return
        columns = list(dict.fromkeys(key for row in rows for key in row))
        widths = [len(column.replace("_", " ")) + 2 for column in columns]
        worksheet.set_row(0, 28)
        for column_index, column in enumerate(columns):
            worksheet.write(0, column_index, column.replace("_", " ").title(), header_format)
        for row_index, row in enumerate(rows, start=1):
            alternate = row_index % 2 == 0
            row_format = alternate_format if alternate else body_format
            for column_index, column in enumerate(columns):
                value = row.get(column)
                if isinstance(value, list | dict):
                    value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                cell_format = row_format
                if isinstance(value, int | float) and not isinstance(value, bool):
                    if column.endswith(("_rate", "_share")):
                        cell_format = numeric_formats[(alternate, "rate")]
                    elif any(token in column for token in ("price", "_gap")):
                        cell_format = numeric_formats[(alternate, "currency")]
                    elif any(
                        token in column
                        for token in ("matches", "observations", "geographies", "markets")
                    ):
                        cell_format = numeric_formats[(alternate, "integer")]
                rendered = "" if value is None else str(value)
                widths[column_index] = min(56, max(widths[column_index], len(rendered) + 2))
                worksheet.write(row_index, column_index, value, cell_format)
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, len(rows), len(columns) - 1)
        for column_index, width in enumerate(widths):
            worksheet.set_column(column_index, column_index, max(12, width))

    def render(
        self,
        result: JsonObject,
        blueprint: ReportBlueprint | None = None,
        product_pack: JsonObject | None = None,
        projector: ReportProjector | None = None,
        report_view: JsonObject | None = None,
    ) -> bytes:
        output = BytesIO()
        workbook = xlsxwriter.Workbook(
            output,
            {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
        )
        workbook.set_properties(
            {
                "author": "CPGHero Retail Competitive Intelligence",
                "company": "CPGHero",
                "comments": "Generated from immutable deterministic AnalysisResult metrics.",
                "created": _generated_at(result),
                "title": f"Retail Competitive Intelligence — {_display(result.get('analysis_id'))}",
            }
        )
        if blueprint is not None and product_pack is not None:
            resolved_projector = projector or ReportProjector()
            profile = blueprint.artifact_profile("xlsx")
            written_names: set[str] = set()
            for worksheet in profile.get("worksheet_definitions", []):
                worksheet_name = str(worksheet["name"])
                self._write_rows(
                    workbook,
                    worksheet_name,
                    resolved_projector.worksheet_rows(
                        result, str(worksheet["source"]), product_pack
                    ),
                )
                written_names.add(worksheet_name)
            if report_view is not None:
                aligned_sheets = (
                    ("Report Readiness", [_mapping(report_view, "report_readiness")]),
                    ("Comparison Bases", _rows(report_view, "comparison_bases")),
                    ("Product Decisions", _rows(report_view, "product_decisions")),
                    (
                        "Suppressed Decisions",
                        _rows(report_view, "suppressed_product_decisions"),
                    ),
                    ("Match Relationships", _rows(report_view, "match_relationships")),
                    ("Match Governance", [_mapping(report_view, "match_governance")]),
                )
                for sheet_name, rows in aligned_sheets:
                    if sheet_name not in written_names:
                        self._write_rows(workbook, sheet_name, rows)
            self._write_rows(
                workbook,
                "Artifact Manifest",
                [
                    {
                        "analysis_id": result.get("analysis_id"),
                        "result_checksum_sha256": _result_checksum(result),
                        "schema_version": result.get("schema_version"),
                        "product_pack_id": product_pack.get("id"),
                        "product_pack_version": product_pack.get("version"),
                        "report_blueprint_id": blueprint.id,
                        "report_blueprint_version": blueprint.version,
                    }
                ],
            )
            workbook.close()
            return output.getvalue()
        self._write_rows(
            workbook,
            "Executive Summary",
            [
                {
                    "analysis_id": result.get("analysis_id"),
                    "collection_run_id": result.get("collection_run_id"),
                    "generated_at": result.get("generated_at"),
                    "benchmark_retailer": result.get("benchmark_retailer"),
                    "competitors": result.get("competitors", []),
                    "product_pack": result.get("product_pack", {}),
                    "source_summary": result.get("source_summary", {}),
                }
            ],
        )
        for sheet_name, key in self._SECTIONS:
            self._write_rows(workbook, sheet_name, _rows(result, key))
        for sheet_name, key in (
            ("Data Quality", "data_quality"),
            ("Validation", "validation"),
            ("Provenance", "provenance"),
        ):
            self._write_rows(workbook, sheet_name, [_mapping(result, key)])
        self._write_rows(
            workbook,
            "Artifact Manifest",
            [
                {
                    "analysis_id": result.get("analysis_id"),
                    "result_checksum_sha256": _result_checksum(result),
                    "schema_version": result.get("schema_version"),
                    "product_pack_id": _mapping(result, "product_pack").get("id"),
                    "product_pack_version": _mapping(result, "product_pack").get("version"),
                }
            ],
        )
        workbook.close()
        return output.getvalue()


class LeadershipEmailRenderer:
    def render(
        self,
        result: JsonObject,
        view: JsonObject | None = None,
        *,
        report_html: bytes | None = None,
    ) -> bytes:
        product_pack = _mapping(result, "product_pack")
        view_product_pack = _mapping(view, "product_pack") if view is not None else {}
        subject_name = _display(
            view_product_pack.get("name") or product_pack.get("name") or product_pack.get("id")
        )
        message = EmailMessage()
        benchmark = _display(
            view.get("benchmark_retailer") if view is not None else result.get("benchmark_retailer")
        ).replace("_", " ")
        competitors = ", ".join(
            _display(value).replace("_", " ")
            for value in (
                view.get("competitors", []) if view is not None else result.get("competitors", [])
            )
        )
        message["Subject"] = (
            f"{subject_name} Competitive Intelligence: {benchmark} vs. {competitors}"
        )
        message["To"] = "Leadership distribution list"
        message["From"] = "CPGHero Retail Competitive Intelligence"
        message["X-RCI-Result-Checksum"] = _result_checksum(result)
        lines = [
            "CPGHero Retail Competitive Intelligence",
            "Decision-ready brief from immutable, evidence-linked metrics",
            "",
            "Leadership team,",
            "",
            f"Analysis: {_display(result.get('analysis_id'))}",
            f"Generated: {_display(result.get('generated_at'))}",
            f"Result checksum: {_result_checksum(result)}",
        ]
        if view is not None:
            readiness = _mapping(view, "report_readiness")
            governance = _mapping(view, "match_governance")
            lines.extend(
                (
                    "",
                    "Report integrity",
                    "",
                    f"- Decision readiness: {_display(readiness.get('status')).replace('_', ' ').title()}",
                    f"- Match revision: {_display(governance.get('match_revision_id') or 'No saved revision')}",
                    f"- Relationships: {_integer(governance.get('confirmed')):,} confirmed; "
                    f"{_integer(governance.get('suggested')):,} suggested; "
                    f"{_integer(governance.get('ambiguous')):,} ambiguous.",
                    f"- Product decisions withheld by evidence guardrails: "
                    f"{_integer(readiness.get('suppressed_decisions')):,}.",
                )
            )
            scorecards = sorted(
                _rows(view, "retailer_scorecards"),
                key=lambda row: _integer(row.get("matches")),
                reverse=True,
            )
            if scorecards:
                lines.extend(("", "Retailer scorecard", ""))
                for row in scorecards[:5]:
                    reference_rate = row.get("benchmark_lower_rate")
                    competitor_rate = row.get("competitor_lower_rate")
                    reference_position = (
                        f"{benchmark} lower {_scorecard_rate(reference_rate)}"
                        if reference_rate is not None
                        else f"{benchmark} lower-price share unavailable"
                    )
                    competitor_position = (
                        f"{_display(row.get('competitor'))} lower "
                        f"{_scorecard_rate(competitor_rate)}"
                        if competitor_rate is not None
                        else f"{_display(row.get('competitor'))} lower-price share unavailable"
                    )
                    lines.append(
                        f"- {_display(row.get('competitor'))}: "
                        f"{_integer(row.get('matches')):,} matched observations; "
                        f"{reference_position}; {competitor_position}; "
                        f"{_display(row.get('price_position'))}."
                    )
                if len(scorecards) > 5:
                    lines.append(
                        f"- {len(scorecards) - 5} additional retailer scorecards are included "
                        "in the attached report and workbook."
                    )
            for section in _rows(view, "sections"):
                section_lines: list[str] = []
                narrative = section.get("narrative")
                if isinstance(narrative, dict) and narrative.get("body"):
                    section_lines.append(_display(narrative["body"]))
                elif isinstance(narrative, dict):
                    if narrative.get("subtitle"):
                        section_lines.append(_display(narrative.get("subtitle")))
                    raw_bullets = narrative.get("bullets", [])
                    if isinstance(raw_bullets, list):
                        section_lines.extend(
                            f"- {bullet}"
                            for bullet in raw_bullets
                            if isinstance(bullet, str) and bullet.strip()
                        )
                    if narrative.get("implication"):
                        section_lines.append(f"Key point: {_display(narrative.get('implication'))}")
                metrics = _rows(section, "metrics")
                if metrics and not section_lines:
                    section_lines.extend(
                        f"- {_display(metric.get('name'))}: "
                        f"{_metric_display(metric.get('value'), metric.get('unit'))}"
                        for metric in metrics[:6]
                    )
                if section_lines:
                    lines.extend(("", _display(section.get("title")), "", *section_lines))
        else:
            lines.extend(("", "Key findings", ""))
            lines.extend(
                f"- {_display(row.get('summary') or row.get('text'))}"
                for row in _rows(result, "findings")
            )
            lines.extend(("", "Recommended actions", ""))
            lines.extend(
                f"- {_display(row.get('priority'))}: "
                f"{_display(row.get('action') or row.get('text'))}"
                for row in _rows(result, "recommendations")
            )
        lines.extend(
            (
                "",
                "The attached report contains the canonical stored metrics, evidence, and "
                "methodology.",
                "",
                "Thank you,",
                "",
                "Brian",
            )
        )
        message.set_content("\n".join(lines))
        if report_html is not None:
            message.add_attachment(
                report_html,
                maintype="text",
                subtype="html",
                filename=f"{result['analysis_id']}-report.html",
            )
            message.set_boundary(f"rci-{_result_checksum(result)[:24]}")
        return message.as_bytes()


class ArtifactRenderer:
    def __init__(self, repository_root: Path | None = None) -> None:
        inferred_root = repository_root or Path.cwd()
        state_paths = ""
        topology_path = inferred_root / "config" / "us-states-10m.json"
        if topology_path.is_file():
            try:
                topology = json.loads(topology_path.read_text(encoding="utf-8"))
                if isinstance(topology, dict):
                    state_paths = _topology_state_paths(topology)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                state_paths = ""
        self._html = LeadershipHtmlRenderer(state_paths=state_paths)
        self._xlsx = ExcelAuditRenderer()
        self._email = LeadershipEmailRenderer()
        retailer_names: dict[str, str] = {}
        retailer_catalog = inferred_root / "config/retailer-catalog.json"
        if retailer_catalog.is_file():
            catalog = json.loads(retailer_catalog.read_text(encoding="utf-8"))
            catalog_rows = [
                *_rows(catalog, "retailers"),
                *_rows(catalog, "normalization_only_retailers"),
            ]
            retailer_names = {
                str(row["id"]): str(row["display_name"])
                for row in catalog_rows
                if row.get("id") and row.get("display_name")
            }
        self._blueprints = (
            ReportBlueprintLoader(inferred_root)
            if (inferred_root / "report-blueprints").is_dir()
            else None
        )
        self._projector = ReportProjector(retailer_names)
        self._report_view_validator = (
            ReportViewValidator(inferred_root)
            if (inferred_root / "schemas/report-view.schema.json").is_file()
            else None
        )

    @property
    def version(self) -> str:
        return RENDERER_VERSION

    def runtime_bundle(
        self,
        result: JsonObject,
        product_pack: JsonObject,
        report_blueprint: JsonObject,
    ) -> tuple[ReportBlueprint, JsonObject]:
        """Validate database-backed presentation documents against the result references."""

        if self._blueprints is None:
            raise RuntimeError("report blueprint validation is not configured")
        return self._blueprints.load_for_documents(result, report_blueprint, product_pack)

    def report_view(
        self,
        result: JsonObject,
        *,
        artifact_type: ArtifactType | None = None,
        presentation_context: JsonObject | None = None,
        runtime_bundle: tuple[ReportBlueprint, JsonObject] | None = None,
    ) -> JsonObject:
        if str(result.get("schema_version")) != "2.0.0":
            raise ValueError("report views require AnalysisResult V2")
        if self._blueprints is None:
            raise RuntimeError("report blueprint catalog is not configured")
        blueprint, product_pack = runtime_bundle or self._blueprints.load_for_result(result)
        view = self._projector.project(
            result,
            blueprint,
            product_pack,
            artifact_type=artifact_type,
        )
        if presentation_context:
            view.update(presentation_context)
        view["retailer_scorecards"] = self._projector.reconcile_scorecards_with_product_evidence(
            _rows(view, "retailer_scorecards"),
            product_decisions=_rows(view, "product_decisions"),
            product_evidence=_mapping(view, "product_evidence"),
            benchmark_name=_display(view.get("benchmark_retailer") or "Reference retailer"),
            match_relationships=_rows(view, "match_relationships"),
            certification_coverage=_mapping(view, "certification_coverage"),
        )
        self._apply_report_integrity(view, result)
        # Reconciliation and integrity checks run against the complete immutable
        # evidence projection. Only the browser-facing copy drops audit-sized
        # location lists after those server-side decisions are complete.
        _compact_interactive_view(view)
        view["result_checksum"] = _result_checksum(result)
        view["publication"] = None
        return (
            self._report_view_validator.validate(view)
            if self._report_view_validator is not None
            else view
        )

    @staticmethod
    def _apply_report_integrity(view: JsonObject, result: JsonObject) -> None:
        relationships = _rows(view, "match_relationships")
        ambiguous_groups = _rows(view, "ambiguous_match_groups")
        suppressed = _rows(view, "suppressed_product_decisions")
        decisions = _rows(view, "product_decisions")
        statuses = Counter(str(row.get("status")) for row in relationships)
        source = _mapping(result, "source")
        revision_id = source.get("match_revision_id")
        view["match_governance"] = {
            "mode": "governed" if revision_id else "ungoverned",
            "match_revision_id": revision_id,
            "applied_policy_revision_id": None,
            "staged_revision_id": None,
            "suggested": statuses["suggested"],
            "confirmed": statuses["confirmed"],
            "rejected": statuses["rejected"],
            "ambiguous": len(ambiguous_groups),
        }
        blocking_reasons: list[JsonObject] = []
        warnings: list[JsonObject] = []
        certification = _mapping(source, "matching_v2_certification_coverage")
        if certification:
            source_candidates = int(
                certification.get("source_candidate_count")
                or certification.get("queue_case_count")
                or 0
            )
            selected_candidates = int(
                certification.get("selected_candidate_count")
                or certification.get("queue_case_count")
                or 0
            )
            queue_cases = int(certification.get("queue_case_count") or 0)
            certified_labels = int(certification.get("certified_label_count") or 0)
            certified_comparable = int(certification.get("certified_comparable_count") or 0)
            unresolved = int(certification.get("unresolved_excluded_count") or 0)
            if certification.get("selection_complete") is False:
                blocking_reasons.append(
                    {
                        "code": "matching_v2_candidate_selection_incomplete",
                        "message": (
                            f"The certification queue contains {selected_candidates:,} of "
                            f"{source_candidates:,} source candidates. A sampled validation "
                            "queue cannot support complete operational reporting."
                        ),
                    }
                )
            if unresolved > 0:
                blocking_reasons.append(
                    {
                        "code": "matching_v2_certification_incomplete",
                        "message": (
                            f"{unresolved:,} of {queue_cases:,} candidate relationships remain "
                            "unresolved and are excluded from this report."
                        ),
                    }
                )
            if certified_labels + unresolved != queue_cases:
                blocking_reasons.append(
                    {
                        "code": "matching_v2_certification_does_not_reconcile",
                        "message": (
                            "Certified and unresolved Matching v2 case counts do not reconcile "
                            "to the review queue."
                        ),
                    }
                )
            missing_observations = max(0, certified_comparable - len(relationships))
            if missing_observations:
                warnings.append(
                    {
                        "code": "certified_relationships_without_price_observations",
                        "message": (
                            f"{missing_observations:,} certified comparable relationships did "
                            "not produce an admissible price observation under the configured "
                            "geography and comparison profiles."
                        ),
                    }
                )
        validation = _mapping(result, "validation")
        validation_status = str(validation.get("status") or "")
        if validation_status and validation_status != "ready_to_share":
            blocking_reasons.append(
                {
                    "code": "analysis_validation_not_ready",
                    "message": (
                        "The underlying AnalysisResult is marked "
                        f"{validation_status.replace('_', ' ')} and is not ready for "
                        "decision use."
                    ),
                }
            )
        if ambiguous_groups:
            blocking_reasons.append(
                {
                    "code": "ambiguous_product_relationships",
                    "message": (
                        f"{len(ambiguous_groups):,} automatic candidate groups require "
                        "one-to-one review."
                    ),
                }
            )
        if suppressed:
            # A decision that is already withheld solely because its observed gap
            # exceeds the Product Pack review threshold is safely contained. Keep
            # that condition visible as a warning; reserve report-wide blocking for
            # unresolved comparability defects that could contaminate other views.
            material_terms = ("package", "unit", "incompatible", "unresolved")
            material_suppressed = [
                row
                for row in suppressed
                if any(
                    term in str(reason).casefold()
                    for reason in row.get("suppression_reasons", [])
                    for term in material_terms
                )
            ]
            target = blocking_reasons if material_suppressed else warnings
            target.append(
                {
                    "code": (
                        "material_product_decisions_suppressed"
                        if material_suppressed
                        else "sparse_product_decisions_suppressed"
                    ),
                    "message": (
                        f"{len(suppressed):,} product decisions were withheld; "
                        + (
                            f"{len(material_suppressed):,} require package, unit, or gap review."
                            if material_suppressed
                            else "the available store or geography evidence was below the configured minimum."
                        )
                    ),
                }
            )
        scorecards = _rows(view, "retailer_scorecards")
        for scorecard in scorecards:
            rates = [
                scorecard.get("benchmark_lower_rate"),
                scorecard.get("competitor_lower_rate"),
                scorecard.get("parity_rate"),
            ]
            numeric_rates = [
                float(value)
                for value in rates
                if isinstance(value, int | float) and not isinstance(value, bool)
            ]
            if len(numeric_rates) == 3 and abs(sum(numeric_rates) - 1.0) > 0.001:
                blocking_reasons.append(
                    {
                        "code": "price_outcomes_do_not_reconcile",
                        "message": (
                            f"Price outcomes do not reconcile for {scorecard.get('competitor')}."
                        ),
                        "competitor_id": str(scorecard.get("competitor_id")),
                        "profile_id": str(scorecard.get("profile_id")),
                    }
                )
        if decisions and not relationships:
            warnings.append(
                {
                    "code": "legacy_relationship_projection",
                    "message": "Product decisions predate relationship-governance metadata.",
                }
            )
        has_ready_scorecard = any(row.get("status") == "ready" for row in scorecards)
        competitor_ids = {str(value) for value in result.get("competitors", [])}
        reported_competitors = {
            str(row.get("competitor_id"))
            for row in scorecards
            if row.get("evidence_state") == "reported"
        }
        missing_competitors = sorted(competitor_ids - reported_competitors)
        if missing_competitors:
            warnings.append(
                {
                    "code": "competitors_without_reported_price_evidence",
                    "message": (
                        f"{len(missing_competitors):,} configured competitor retailers have no "
                        "reported price evidence under any governed comparison basis."
                    ),
                }
            )
        status = (
            "review_required"
            if blocking_reasons
            else "ready"
            if has_ready_scorecard and not missing_competitors
            else "limited"
        )
        view["report_readiness"] = {
            "status": status,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
            "suppressed_decisions": len(suppressed),
        }

    def _context(
        self,
        result: JsonObject,
        artifact_type: ArtifactType,
        runtime_bundle: tuple[ReportBlueprint, JsonObject] | None = None,
    ) -> tuple[ReportBlueprint, JsonObject, JsonObject] | None:
        if str(result.get("schema_version")) != "2.0.0":
            return None
        if self._blueprints is None:
            raise RuntimeError("report blueprint catalog is not configured")
        blueprint, product_pack = runtime_bundle or self._blueprints.load_for_result(result)
        return (
            blueprint,
            product_pack,
            self._projector.project(
                result,
                blueprint,
                product_pack,
                artifact_type=artifact_type,
            ),
        )

    def _artifact_view(
        self,
        result: JsonObject,
        context: tuple[ReportBlueprint, JsonObject, JsonObject] | None,
        presentation_context: JsonObject | None,
    ) -> JsonObject | None:
        """Build a renderer view while retaining presentation-only evidence payloads."""

        if context is None:
            return None
        view = dict(context[2])
        if presentation_context:
            view.update(presentation_context)
        self._apply_report_integrity(view, result)
        view["result_checksum"] = _result_checksum(result)
        view.setdefault("publication", None)
        return view

    def render(
        self,
        result: JsonObject,
        artifact_type: str,
        *,
        presentation_context: JsonObject | None = None,
        runtime_bundle: tuple[ReportBlueprint, JsonObject] | None = None,
    ) -> ArtifactPayload:
        analysis_id = str(result["analysis_id"])
        if artifact_type == "html":
            context = self._context(result, "html", runtime_bundle)
            view = self._artifact_view(result, context, presentation_context)
            return ArtifactPayload(
                "html",
                f"{analysis_id}.html",
                "text/html; charset=utf-8",
                self._html.render(
                    result,
                    view,
                    presentation_context=view,
                ),
                self.version,
            )
        if artifact_type == "xlsx":
            context = self._context(result, "xlsx", runtime_bundle)
            view = self._artifact_view(result, context, presentation_context)
            return ArtifactPayload(
                "xlsx",
                f"{analysis_id}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                self._xlsx.render(
                    result,
                    context[0] if context else None,
                    context[1] if context else None,
                    self._projector,
                    view,
                ),
                self.version,
            )
        if artifact_type == "leadership_email":
            context = self._context(result, "leadership_email", runtime_bundle)
            html_context = self._context(result, "html", runtime_bundle)
            view = self._artifact_view(result, context, presentation_context)
            html_view = self._artifact_view(result, html_context, presentation_context)
            return ArtifactPayload(
                "leadership_email",
                f"{analysis_id}.eml",
                "message/rfc822",
                self._email.render(
                    result,
                    view,
                    report_html=self._html.render(
                        result,
                        html_view,
                        presentation_context=html_view,
                    ),
                ),
                self.version,
            )
        if artifact_type == "audit_zip":
            return self._audit_package(
                result,
                presentation_context=presentation_context,
                runtime_bundle=runtime_bundle,
            )
        raise ValueError(f"unsupported artifact type {artifact_type!r}")

    def _audit_package(
        self,
        result: JsonObject,
        *,
        presentation_context: JsonObject | None = None,
        runtime_bundle: tuple[ReportBlueprint, JsonObject] | None = None,
    ) -> ArtifactPayload:
        children = [
            self.render(
                result,
                "html",
                presentation_context=presentation_context,
                runtime_bundle=runtime_bundle,
            ),
            self.render(
                result,
                "xlsx",
                presentation_context=presentation_context,
                runtime_bundle=runtime_bundle,
            ),
            self.render(
                result,
                "leadership_email",
                presentation_context=presentation_context,
                runtime_bundle=runtime_bundle,
            ),
        ]
        result_body = canonical_result_bytes(result)
        manifest = {
            "analysis_id": result["analysis_id"],
            "renderer_version": self.version,
            "result_checksum_sha256": _result_checksum(result),
            "files": [
                {
                    "filename": "analysis-result.json",
                    "sha256": hashlib.sha256(result_body).hexdigest(),
                    "bytes": len(result_body),
                },
                *[
                    {
                        "filename": child.filename,
                        "sha256": hashlib.sha256(child.body).hexdigest(),
                        "bytes": len(child.body),
                    }
                    for child in children
                ],
            ],
        }
        output = BytesIO()
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(_zip_entry("analysis-result.json"), result_body)
            for child in children:
                archive.writestr(_zip_entry(child.filename), child.body)
            archive.writestr(
                _zip_entry("manifest.json"),
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            )
        analysis_id = str(result["analysis_id"])
        return ArtifactPayload(
            "audit_zip",
            f"{analysis_id}-audit.zip",
            "application/zip",
            output.getvalue(),
            self.version,
        )
