"""Pure renderers that present stored AnalysisResult values without recomputing metrics."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from email.message import EmailMessage
from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import xlsxwriter  # type: ignore[import-untyped]

from rci_results.contracts import canonical_result_bytes
from rci_results.models import ArtifactPayload, JsonObject


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


class LeadershipHtmlRenderer:
    def render(self, result: JsonObject) -> bytes:
        product_pack = _mapping(result, "product_pack")
        pack_name = escape(_display(product_pack.get("name") or product_pack.get("id")))
        analysis_id = escape(_display(result.get("analysis_id")))
        generated_at = escape(_display(result.get("generated_at")))
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
<style>
:root{{--ink:#17221d;--muted:#627067;--paper:#f4f2eb;--card:#fff;--accent:#17613e;--line:#d9ddd7}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 Arial,sans-serif}}
main{{max-width:1180px;margin:auto;padding:48px 28px}}
header{{border-bottom:1px solid var(--line);padding-bottom:28px}}
.eyebrow,article span{{color:var(--accent);font-size:12px;font-weight:700}}
.eyebrow,article span{{letter-spacing:.12em;text-transform:uppercase}}
h1{{font-size:clamp(38px,7vw,72px);letter-spacing:-.055em;line-height:.94}}
h1{{margin:10px 0 18px;max-width:12ch}}
h2{{margin-top:42px}}.meta{{color:var(--muted)}}
.findings{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}}
article,section{{background:var(--card);border:1px solid var(--line);border-radius:16px}}
article,section{{padding:20px;margin-top:18px}}article p{{font-size:18px;margin:10px 0}}
.table-wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border-bottom:1px solid var(--line);padding:10px;text-align:left;vertical-align:top}}
th{{color:var(--muted)}}li{{margin:10px 0}}
</style></head><body><main><header><div class="eyebrow">Leadership intelligence brief</div>
<h1>{pack_name}</h1>
<div class="meta">Analysis {analysis_id} · Generated {generated_at}</div>
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
</main></body></html>"""
        return document.encode("utf-8")


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
            {"bold": True, "font_color": "#ffffff", "bg_color": "#17613e"}
        )
        if not rows:
            worksheet.write(0, 0, "No records supplied")
            return
        columns = list(dict.fromkeys(key for row in rows for key in row))
        for column_index, column in enumerate(columns):
            worksheet.write(0, column_index, column, header_format)
        for row_index, row in enumerate(rows, start=1):
            for column_index, column in enumerate(columns):
                value = row.get(column)
                if isinstance(value, list | dict):
                    value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                worksheet.write(row_index, column_index, value)
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, len(rows), len(columns) - 1)
        worksheet.set_column(0, len(columns) - 1, 22)

    def render(self, result: JsonObject) -> bytes:
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        workbook.set_properties({"created": _generated_at(result)})
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
        workbook.close()
        return output.getvalue()


class LeadershipEmailRenderer:
    def render(self, result: JsonObject) -> bytes:
        product_pack = _mapping(result, "product_pack")
        subject_name = _display(product_pack.get("name") or product_pack.get("id"))
        message = EmailMessage()
        message["Subject"] = f"Retail competitive intelligence: {subject_name}"
        message["To"] = "Leadership distribution list"
        message["From"] = "Retail Competitive Intelligence"
        lines = [
            f"Analysis: {_display(result.get('analysis_id'))}",
            f"Generated: {_display(result.get('generated_at'))}",
            "",
            "Key findings",
        ]
        lines.extend(f"- {_display(row.get('text'))}" for row in _rows(result, "findings"))
        lines.extend(("", "Recommended actions"))
        lines.extend(
            f"- {_display(row.get('priority'))}: {_display(row.get('text'))}"
            for row in _rows(result, "recommendations")
        )
        lines.extend(
            ("", "The attached report contains the canonical stored metrics and evidence.")
        )
        message.set_content("\n".join(lines))
        return message.as_bytes()


class ArtifactRenderer:
    def __init__(self) -> None:
        self._html = LeadershipHtmlRenderer()
        self._xlsx = ExcelAuditRenderer()
        self._email = LeadershipEmailRenderer()

    def render(self, result: JsonObject, artifact_type: str) -> ArtifactPayload:
        analysis_id = str(result["analysis_id"])
        if artifact_type == "html":
            return ArtifactPayload(
                "html", f"{analysis_id}.html", "text/html; charset=utf-8", self._html.render(result)
            )
        if artifact_type == "xlsx":
            return ArtifactPayload(
                "xlsx",
                f"{analysis_id}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                self._xlsx.render(result),
            )
        if artifact_type == "leadership_email":
            return ArtifactPayload(
                "leadership_email",
                f"{analysis_id}.eml",
                "message/rfc822",
                self._email.render(result),
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
        )
