"""Pure renderers that present stored AnalysisResult values without recomputing metrics."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from email.message import EmailMessage
from html import escape
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import xlsxwriter  # type: ignore[import-untyped]

from rci_results.blueprints import ReportBlueprint, ReportBlueprintLoader, ReportProjector
from rci_results.contracts import canonical_result_bytes
from rci_results.models import ArtifactPayload, ArtifactType, JsonObject

RENDERER_VERSION = "2.8.0"

_SECTION_EYEBROWS = {
    "executive_summary": "Leadership answer",
    "kpi_strip": "Decision scorecard",
    "coverage": "Market coverage",
    "price_position": "Package-price lens",
    "segment_analysis": "Normalized-value lens",
    "geographic_sensitivity": "Proximity validation",
    "product_table": "Assortment implications",
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
border-top:4px solid #9b6100;box-shadow:none;display:grid;gap:12px;grid-template-columns:70px 1fr;
margin:0;padding:14px}.product-decision.protect{border-top-color:var(--accent)}
.product-decision.parity{border-top-color:var(--muted)}.product-decision img,
.product-decision .product-placeholder{height:70px;width:70px}.product-decision h3{font-size:14px;
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
    columns = list(dict.fromkeys(key for row in rows for key in row))
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
    columns = list(dict.fromkeys(key for row in rows for key in row))
    header = "".join(f"<th>{escape(column.replace('_', ' ').title())}</th>" for column in columns)
    body = "".join(
        "<tr>"
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
    columns = list(dict.fromkeys(key for row in rows for key in row))
    header = "".join(f"<th>{escape(column.replace('_', ' ').title())}</th>" for column in columns)
    body = "".join(
        "<tr>"
        + "".join(f"<td>{escape(_display(row.get(column)))}</td>" for column in columns)
        + "</tr>"
        for row in rows
    )
    return (
        '<div class="table-wrap comparison-table"><table><thead><tr>'
        f"{header}</tr></thead><tbody>{body}</tbody></table></div>"
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
            "<aside><b>What to do</b>"
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


def _product_decisions(context: JsonObject, *, limit: int) -> str:
    decisions = _rows(context, "product_decisions")[:limit]
    if not decisions:
        return ""
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
            f"{competitor} is typically ${abs(gap):,.2f} cheaper"
            if gap < 0
            else f"Walmart is typically ${abs(gap):,.2f} cheaper"
            if gap > 0
            else "Typical prices are tied"
        )
        status = {
            "attention": "Needs attention",
            "protect": "Position to protect",
            "parity": "Price parity",
        }.get(priority, "Price position")
        image_url = row.get("benchmark_image_url")
        image = (
            f'<img src="{escape(str(image_url), quote=True)}" alt="">'
            if image_url
            else "<div class=product-placeholder>P</div>"
        )
        raw_locations = row.get("top_locations", [])
        location_html = ""
        if isinstance(raw_locations, list):
            labels = []
            for location in raw_locations[:3]:
                if not isinstance(location, dict):
                    continue
                label = f"ZIP {_display(location.get('zipcode'))}"
                if location.get("store"):
                    label += f" · store {_display(location.get('store'))}"
                labels.append(f"<li>{escape(label)}</li>")
            if labels:
                location_html = f"<ul class=product-locations>{''.join(labels)}</ul>"
        cards.append(
            f"<article class='product-decision {escape(priority)}'>{image}<div>"
            f"<span>{escape(status)}</span>"
            f"<h3>{escape(_display(row.get('benchmark_product_name')))}</h3>"
            f"<p>vs. {escape(_display(row.get('competitor_product_name')))} at "
            f"{escape(competitor)}</p><strong>{escape(position)}</strong>"
            f"<p>Seen across {geographies:,} comparable "
            f"{'location' if geographies == 1 else 'locations'}.</p>{location_html}</div></article>"
        )
    return (
        "<div class=product-decision-intro><h3>Products that need attention—and positions "
        "to protect</h3><p>Ranked exact product matches. PDP data improves identity and imagery; "
        "search evidence remains authoritative for price and location.</p></div>"
        f"<div class=product-decisions>{''.join(cards)}</div>"
    )


def _percent(value: object) -> float | None:
    try:
        parsed = float(str(value).replace("%", "").replace(",", ""))
    except ValueError:
        return None
    return max(0.0, min(parsed, 100.0))


def _comparison_chart(rows: list[JsonObject]) -> str:
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
    chart_rows = "".join(
        f"<div class=chart-row><div class=chart-label><strong>"
        f"{escape(_display(row.get('segment') or row.get('competitor')))}</strong>"
        f"<span>{escape(_display(row.get('competitor')))} · {matches:,} matches · "
        f"{escape(_display(row.get('matched geographies')))} geographies · "
        f"gap {escape(_display(row.get('competitor - benchmark gap')))}</span></div>"
        f"<div class=paired><div><i><b class=benchmark style='width:{benchmark or 1}%'></b>"
        f"</i><span>{'—' if benchmark is None else f'{benchmark:.1f}%'}</span></div>"
        f"<div><i><b class=competitor style='width:{competitor or 1}%'></b></i>"
        f"<span>{'—' if competitor is None else f'{competitor:.1f}%'}</span></div></div></div>"
        for matches, row, benchmark, competitor in candidates[:8]
    )
    if not chart_rows:
        return ""
    return (
        "<figure class=comparison-chart><figcaption><strong>Lower-price share</strong>"
        "<span>Strict comparable-package outcomes with market coverage and signed gap</span>"
        "</figcaption>"
        f"<div class=chart-body>{chart_rows}</div><p class=chart-note>Directional share "
        "among matched observations; see the supporting table for definitions and caveats."
        "</p></figure>"
    )


def _primary_comparison_rows(view: JsonObject) -> list[JsonObject]:
    sections = _rows(view, "sections")
    selected = next(
        (
            _rows(section, "records")
            for section in sections
            if section.get("kind") == "price_position" and _rows(section, "records")
        ),
        [],
    )
    if not selected:
        selected = next(
            (
                _rows(section, "records")
                for section in sections
                if section.get("kind") == "segment_analysis" and _rows(section, "records")
            ),
            [],
        )
    overall = [
        row for row in selected if str(row.get("segment", "")).casefold() == "all comparable items"
    ]
    return overall or selected


def _map_figure(context: JsonObject) -> str:
    points = []
    for point in _rows(context, "map_points"):
        try:
            latitude = float(point["latitude"])
            longitude = float(point["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (24 <= latitude <= 50 and -125 <= longitude <= -66):
            continue
        points.append((point, latitude, longitude))
    if not points:
        return ""
    products = sorted(
        {
            str(point.get("benchmark_product_id")): str(
                point.get("benchmark_product_name") or point.get("label") or "Product"
            )
            for point, _latitude, _longitude in points
            if point.get("benchmark_product_id")
        }.items(),
        key=lambda item: item[1],
    )
    options = "".join(
        f"<option value='{escape(product_id, quote=True)}'>{escape(name)}</option>"
        for product_id, name in products
    )
    outline_coordinates = (
        (-124.7, 48.4),
        (-123, 46),
        (-124, 42),
        (-122, 38),
        (-117, 32.5),
        (-111, 31.4),
        (-106.5, 31.8),
        (-103, 29.7),
        (-97, 25.8),
        (-90, 29),
        (-83, 25.5),
        (-80, 27),
        (-80, 32),
        (-75, 35),
        (-75, 39),
        (-67, 45),
        (-71, 47),
        (-83, 47),
        (-95, 49),
        (-105, 49),
        (-116, 49),
        (-124.7, 48.4),
    )
    outline = " ".join(
        f"{'M' if index == 0 else 'L'}{((longitude + 125) / 59) * 900 + 30:.1f},"
        f"{((50 - latitude) / 26) * 460 + 30:.1f}"
        for index, (longitude, latitude) in enumerate(outline_coordinates)
    )
    circles = "".join(
        "<circle class='geo-point "
        + escape(str(point.get("outcome") or "parity"), quote=True)
        + "' data-product='"
        + escape(str(point.get("benchmark_product_id") or ""), quote=True)
        + f"' cx='{((longitude + 125) / 59) * 900 + 30:.1f}'"
        + f" cy='{((50 - latitude) / 26) * 460 + 30:.1f}' r='4.5'><title>"
        + escape(
            " · ".join(
                str(value)
                for value in (
                    point.get("benchmark_product_name") or point.get("label"),
                    f"ZIP {point['zipcode']}" if point.get("zipcode") else None,
                    point.get("value_label"),
                )
                if value
            )
        )
        + "</title></circle>"
        for point, latitude, longitude in points[:3000]
    )
    return (
        "<div class=map-controls><label>Benchmark product<select "
        "onchange=\"for(const p of document.querySelectorAll('.geo-point'))"
        "p.style.display=!this.value||p.dataset.product===this.value?'':'none'\">"
        f"<option value=''>All mapped benchmark products</option>{options}</select></label>"
        "<div class=map-legend>Dark = benchmark lower · Blue = competitor lower · "
        "Gold = parity</div></div><figure class=geo-map>"
        f"<svg viewBox='0 0 960 520' role=img aria-label='Benchmark product price map'>"
        f"<path class=outline d='{outline} Z'/>{circles}</svg><figcaption>"
        "Exact comparison evidence only. PDP enrichment supplies product reference detail; "
        "it does not drive mapped price outcomes.</figcaption></figure>"
    )


def _product_highlights(context: JsonObject) -> str:
    products = _rows(context, "product_highlights")[:8]
    if not products:
        return ""
    cards = "".join(
        "<article class=product-card>"
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


class LeadershipHtmlRenderer:
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
        pack_name = escape(_display(product_pack.get("name") or product_pack.get("id")))
        result_checksum = escape(_result_checksum(result))
        decision_rows = _primary_comparison_rows(view)
        section_html = "".join(
            self._section(section, presentation_context, decision_rows)
            for section in _rows(view, "sections")
        )
        document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{pack_name} analysis</title>
<style>{_leadership_styles()}</style></head><body><main data-result-checksum="{result_checksum}">
<header><div class="brand">CPG<b>Hero</b></div>
<div class="eyebrow">Leadership intelligence brief</div>
<h1>{pack_name}</h1><p class="deck">Where the price war is being won, where it is being lost,
and which targeted moves matter most.</p><div class="meta">
Analysis {escape(_display(result.get("analysis_id")))} ·
Generated {escape(_display_generated_at(result))}</div>
</header>{section_html}<footer>CPGHero Retail Competitive Intelligence · Immutable result
<code>{result_checksum}</code></footer></main></body></html>"""
        return document.encode("utf-8")

    @staticmethod
    def _section(
        section: JsonObject,
        presentation_context: JsonObject,
        decision_rows: list[JsonObject],
    ) -> str:
        section_kind = str(section.get("kind", ""))
        title = escape(
            "Competitive Scorecard"
            if section_kind == "kpi_strip"
            else _display(section.get("title"))
        )
        kind = escape(_SECTION_EYEBROWS.get(section_kind, section_kind.replace("_", " ").title()))
        narrative = section.get("narrative")
        narrative_html = _narrative_html(narrative) if isinstance(narrative, dict) else ""
        metrics: list[JsonObject] = []
        metric_html = "".join(
            f"<div class=metric><span>{escape(_display(metric.get('name')))}</span>"
            f"<strong>{escape(_metric_display(metric.get('value'), metric.get('unit')))}</strong>"
            "</div>"
            for metric in metrics
        )
        metric_grid = f"<div class=metrics>{metric_html}</div>" if metric_html else ""
        records = _rows(section, "records")
        if section_kind == "kpi_strip":
            detail = _comparison_chart(decision_rows)
        elif section_kind == "coverage":
            detail = (
                f"{_map_figure(presentation_context)}"
                f"{_collapsed_table('View source coverage detail', records)}"
            )
        elif section_kind in {
            "price_position",
            "segment_analysis",
            "geographic_sensitivity",
        }:
            chart = _comparison_chart(records)
            detail = f"{chart}{_collapsed_table('View supporting detail', records)}"
        elif section_kind == "product_table":
            detail = (
                f"{_product_decisions(presentation_context, limit=16)}"
                f"{_product_highlights(presentation_context)}"
                f"{_collapsed_table('View evidence-backed detail', records)}"
            )
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
            detail = _product_decisions(presentation_context, limit=6)
        elif section_kind in {"recommendations", "data_quality"}:
            detail = ""
        else:
            detail = _collapsed_table("View evidence-backed detail", records)
        empty = (
            f"<p class=empty>{escape(_display(section.get('empty_state')))}</p>"
            if section.get("empty")
            else ""
        )
        return (
            f"<section id={escape(_display(section.get('id')))}><div class=kind>{kind}</div>"
            f"<h2>{title}</h2>{narrative_html}{metric_grid}{detail}{empty}</section>"
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
            row_format = alternate_format if row_index % 2 == 0 else body_format
            for column_index, column in enumerate(columns):
                value = row.get(column)
                if isinstance(value, list | dict):
                    value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                rendered = "" if value is None else str(value)
                widths[column_index] = min(56, max(widths[column_index], len(rendered) + 2))
                worksheet.write(row_index, column_index, value, row_format)
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, len(rows), len(columns) - 1)
        for column_index, width in enumerate(widths):
            worksheet.set_column(column_index, column_index, max(12, width))

    def render(
        self,
        result: JsonObject,
        blueprint: ReportBlueprint | None = None,
        product_pack: JsonObject | None = None,
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
            projector = ReportProjector()
            profile = blueprint.artifact_profile("xlsx")
            for worksheet in profile.get("worksheet_definitions", []):
                self._write_rows(
                    workbook,
                    str(worksheet["name"]),
                    projector.worksheet_rows(result, str(worksheet["source"]), product_pack),
                )
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
        benchmark = (
            _display(
                view.get("benchmark_retailer")
                if view is not None
                else result.get("benchmark_retailer")
            )
            .replace("_", " ")
            .title()
        )
        competitors = ", ".join(
            _display(value).replace("_", " ").title()
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
            for section in _rows(view, "sections"):
                lines.extend(("", _display(section.get("title")), ""))
                narrative = section.get("narrative")
                if isinstance(narrative, dict) and narrative.get("body"):
                    lines.append(_display(narrative["body"]))
                metrics = _rows(section, "metrics")
                if metrics and not (isinstance(narrative, dict) and narrative.get("body")):
                    lines.extend(
                        f"- {_display(metric.get('name'))}: "
                        f"{_metric_display(metric.get('value'), metric.get('unit'))}"
                        for metric in metrics[:6]
                    )
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
        self._html = LeadershipHtmlRenderer()
        self._xlsx = ExcelAuditRenderer()
        self._email = LeadershipEmailRenderer()
        inferred_root = repository_root or Path.cwd()
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

    @property
    def version(self) -> str:
        return RENDERER_VERSION

    def report_view(
        self,
        result: JsonObject,
        *,
        artifact_type: ArtifactType | None = None,
        presentation_context: JsonObject | None = None,
    ) -> JsonObject:
        if str(result.get("schema_version")) != "2.0.0":
            raise ValueError("report views require AnalysisResult V2")
        if self._blueprints is None:
            raise RuntimeError("report blueprint catalog is not configured")
        blueprint, product_pack = self._blueprints.load_for_result(result)
        view = self._projector.project(
            result,
            blueprint,
            product_pack,
            artifact_type=artifact_type,
        )
        if presentation_context:
            view.update(presentation_context)
        return view

    def _context(
        self,
        result: JsonObject,
        artifact_type: ArtifactType,
    ) -> tuple[ReportBlueprint, JsonObject, JsonObject] | None:
        if str(result.get("schema_version")) != "2.0.0":
            return None
        if self._blueprints is None:
            raise RuntimeError("report blueprint catalog is not configured")
        blueprint, product_pack = self._blueprints.load_for_result(result)
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

    def render(
        self,
        result: JsonObject,
        artifact_type: str,
        *,
        presentation_context: JsonObject | None = None,
    ) -> ArtifactPayload:
        analysis_id = str(result["analysis_id"])
        if artifact_type == "html":
            context = self._context(result, "html")
            return ArtifactPayload(
                "html",
                f"{analysis_id}.html",
                "text/html; charset=utf-8",
                self._html.render(
                    result,
                    context[2] if context else None,
                    presentation_context=presentation_context,
                ),
                self.version,
            )
        if artifact_type == "xlsx":
            context = self._context(result, "xlsx")
            return ArtifactPayload(
                "xlsx",
                f"{analysis_id}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                self._xlsx.render(
                    result,
                    context[0] if context else None,
                    context[1] if context else None,
                ),
                self.version,
            )
        if artifact_type == "leadership_email":
            context = self._context(result, "leadership_email")
            html_context = self._context(result, "html")
            view = context[2] if context else None
            return ArtifactPayload(
                "leadership_email",
                f"{analysis_id}.eml",
                "message/rfc822",
                self._email.render(
                    result,
                    view,
                    report_html=self._html.render(
                        result,
                        html_context[2] if html_context else None,
                        presentation_context=presentation_context,
                    ),
                ),
                self.version,
            )
        if artifact_type == "audit_zip":
            return self._audit_package(result, presentation_context=presentation_context)
        raise ValueError(f"unsupported artifact type {artifact_type!r}")

    def _audit_package(
        self,
        result: JsonObject,
        *,
        presentation_context: JsonObject | None = None,
    ) -> ArtifactPayload:
        children = [
            self.render(result, "html", presentation_context=presentation_context),
            self.render(result, "xlsx"),
            self.render(
                result,
                "leadership_email",
                presentation_context=presentation_context,
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
