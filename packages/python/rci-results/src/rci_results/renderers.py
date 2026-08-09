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

RENDERER_VERSION = "2.2.0"


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
header{border-bottom:1px solid var(--line);padding-bottom:28px}
.brand{font-size:17px;font-weight:850;letter-spacing:-.04em}.brand b{color:var(--accent)}
.eyebrow,.kind{color:var(--accent);font-size:12px;font-weight:800;letter-spacing:.12em;
text-transform:uppercase}h1{font-size:clamp(38px,7vw,72px);font-weight:800;letter-spacing:-.055em;
line-height:.94;margin:12px 0 18px;max-width:13ch}h2{margin:0 0 12px;letter-spacing:-.025em}
.meta,.empty,small{color:var(--muted)}.checksum{background:rgba(88,210,248,.12);
border:1px solid rgba(88,210,248,.35);border-radius:999px;color:var(--accent);display:inline-block;
font:11px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;margin-top:16px;padding:7px 10px}
.findings,.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.decision-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
article,section{background:var(--card);border:1px solid var(--line);border-radius:16px;
box-shadow:var(--shadow);padding:22px;margin-top:18px}article p{font-size:17px;margin:10px 0}
article span{color:var(--accent);font-size:12px;font-weight:800;letter-spacing:.1em;
text-transform:uppercase}
.metric{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px}
.metric strong{display:block;font-size:24px;margin-top:16px}.table-wrap{overflow:auto}
.decision-card{background:var(--surface);box-shadow:none}.decision-card h3{font-size:17px;
line-height:1.35;margin:12px 0 0}.decision-card p{color:var(--muted);font-size:14px}
.evidence{border-top:1px solid var(--line);margin-top:20px;padding-top:14px}
.evidence summary{color:var(--accent);cursor:pointer;font-weight:750}
.evidence .table-wrap{margin-top:12px}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid var(--line);
padding:10px;text-align:left;vertical-align:top}th{color:var(--muted);font-size:11px;letter-spacing:.06em;
text-transform:uppercase}tbody tr:nth-child(even){background:var(--surface)}li{margin:10px 0}
footer{border-top:1px solid var(--line);color:var(--muted);font-size:12px;margin-top:34px;
padding-top:18px}footer code{overflow-wrap:anywhere}
"""


def _generated_at(result: JsonObject) -> datetime:
    value = str(result.get("generated_at", "1980-01-01T00:00:00+00:00"))
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


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


def _narrative_html(value: object) -> str:
    paragraphs = [paragraph.strip() for paragraph in str(value).split("\n\n")]
    return "".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs if paragraph)


class LeadershipHtmlRenderer:
    def render(self, result: JsonObject, view: JsonObject | None = None) -> bytes:
        if view is not None:
            return self._render_blueprint(result, view)
        product_pack = _mapping(result, "product_pack")
        pack_name = escape(_display(product_pack.get("name") or product_pack.get("id")))
        analysis_id = escape(_display(result.get("analysis_id")))
        generated_at = escape(_display(result.get("generated_at")))
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

    def _render_blueprint(self, result: JsonObject, view: JsonObject) -> bytes:
        product_pack = _mapping(view, "product_pack")
        pack_name = escape(_display(product_pack.get("name") or product_pack.get("id")))
        result_checksum = escape(_result_checksum(result))
        section_html = "".join(self._section(section) for section in _rows(view, "sections"))
        document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{pack_name} analysis</title>
<style>{_leadership_styles()}</style></head><body><main data-result-checksum="{result_checksum}">
<header><div class="brand">CPG<b>Hero</b></div>
<div class="eyebrow">Leadership intelligence brief</div>
<h1>{pack_name}</h1><div class="meta">
Analysis {escape(_display(result.get("analysis_id")))} ·
Generated {escape(_display(result.get("generated_at")))}</div>
<div class="checksum">Result checksum · {result_checksum}</div>
</header>{section_html}<footer>CPGHero Retail Competitive Intelligence · Immutable result
<code>{result_checksum}</code></footer></main></body></html>"""
        return document.encode("utf-8")

    @staticmethod
    def _section(section: JsonObject) -> str:
        title = escape(_display(section.get("title")))
        kind = escape(_display(section.get("kind")))
        narrative = section.get("narrative")
        narrative_html = (
            _narrative_html(narrative.get("body")) if isinstance(narrative, dict) else ""
        )
        metrics = _rows(section, "metrics")[:6]
        metric_html = "".join(
            f"<div class=metric><span>{escape(_display(metric.get('name')))}</span>"
            f"<strong>{escape(_metric_display(metric.get('value'), metric.get('unit')))}</strong>"
            f"<small>{escape(_display(metric.get('method')))}</small></div>"
            for metric in metrics
        )
        metric_grid = f"<div class=metrics>{metric_html}</div>" if metric_html else ""
        records = _rows(section, "records")
        if section.get("visualization") == "ranked_cards":
            cards = "".join(
                LeadershipHtmlRenderer._record_card(row, index)
                for index, row in enumerate(records[:5])
            )
            detail = f"<div class=decision-cards>{cards}</div>" if cards else ""
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
    def _record_card(row: JsonObject, index: int) -> str:
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
        detail_html = f"<p>{escape(_display(detail))}</p>" if detail is not None else ""
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
    def render(self, result: JsonObject, view: JsonObject | None = None) -> bytes:
        product_pack = _mapping(result, "product_pack")
        view_product_pack = _mapping(view, "product_pack") if view is not None else {}
        subject_name = _display(
            view_product_pack.get("name") or product_pack.get("name") or product_pack.get("id")
        )
        message = EmailMessage()
        benchmark = _display(result.get("benchmark_retailer")).replace("_", " ").title()
        competitors = ", ".join(
            _display(value).replace("_", " ").title() for value in result.get("competitors", [])
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
                if metrics:
                    lines.extend(
                        f"- {_display(metric.get('name'))}: "
                        f"{_metric_display(metric.get('value'), metric.get('unit'))}"
                        for metric in metrics[:6]
                    )
            lines.extend(("", "Prioritized actions", ""))
            lines.extend(
                f"{_display(row.get('priority'))}. {_display(row.get('action'))} "
                f"{_display(row.get('rationale'))}"
                for row in _rows(result, "recommendations")
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
        return message.as_bytes()


class ArtifactRenderer:
    def __init__(self, repository_root: Path | None = None) -> None:
        self._html = LeadershipHtmlRenderer()
        self._xlsx = ExcelAuditRenderer()
        self._email = LeadershipEmailRenderer()
        inferred_root = repository_root or Path.cwd()
        self._blueprints = (
            ReportBlueprintLoader(inferred_root)
            if (inferred_root / "report-blueprints").is_dir()
            else None
        )
        self._projector = ReportProjector()

    @property
    def version(self) -> str:
        return RENDERER_VERSION

    def report_view(
        self,
        result: JsonObject,
        *,
        artifact_type: ArtifactType | None = None,
    ) -> JsonObject:
        if str(result.get("schema_version")) != "2.0.0":
            raise ValueError("report views require AnalysisResult V2")
        if self._blueprints is None:
            raise RuntimeError("report blueprint catalog is not configured")
        blueprint, product_pack = self._blueprints.load_for_result(result)
        return self._projector.project(
            result,
            blueprint,
            product_pack,
            artifact_type=artifact_type,
        )

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

    def render(self, result: JsonObject, artifact_type: str) -> ArtifactPayload:
        analysis_id = str(result["analysis_id"])
        if artifact_type == "html":
            context = self._context(result, "html")
            return ArtifactPayload(
                "html",
                f"{analysis_id}.html",
                "text/html; charset=utf-8",
                self._html.render(result, context[2] if context else None),
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
            return ArtifactPayload(
                "leadership_email",
                f"{analysis_id}.eml",
                "message/rfc822",
                self._email.render(result, context[2] if context else None),
                self.version,
            )
        if artifact_type == "audit_zip":
            return self._audit_package(result)
        raise ValueError(f"unsupported artifact type {artifact_type!r}")

    def _audit_package(self, result: JsonObject) -> ArtifactPayload:
        children = [
            self.render(result, "html"),
            self.render(result, "xlsx"),
            self.render(result, "leadership_email"),
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
