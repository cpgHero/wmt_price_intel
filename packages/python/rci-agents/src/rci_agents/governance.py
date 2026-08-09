"""Hard validation and deterministic metric-citation rendering for model output."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from rci_agents.models import JsonObject, PromptTemplate, ProviderResponse
from rci_contracts import validate_instance

_PLACEHOLDER = re.compile(
    r"\{\{metric:([A-Za-z0-9_.-]+)\|"
    r"(integer|decimal_1|decimal_2|percent_1|percent_2|currency_2)\}\}"
)
_STORYLINE_PLACEHOLDER = re.compile(r"\{\{storyline:([A-Za-z0-9_.-]+)\|headline\}\}")
_NUMERIC_LITERAL = re.compile(
    r"(?<![A-Za-z0-9_.])(?:-\$?|\$-?)?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?"
)
_PERCENT_DESCRIPTOR = re.compile(
    r"(?:pct|percent|percentage)\s*:\s*"
    r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?",
    flags=re.IGNORECASE,
)
_MACHINE_PROSE = re.compile(
    r"\b[a-z][a-z0-9]*_us(?:_[a-z0-9]+)*\b|"
    r"\b(?:lean pct|fat pct|weight lb|organic|grass fed|premium tier)\s*:",
    flags=re.IGNORECASE,
)


class AgentGovernanceError(ValueError):
    """Raised when model output crosses the configured authority boundary."""


class NarrativeQualityCritic:
    """Reject structurally thin or semantically ungrounded leadership prose."""

    def validate(
        self,
        rows: list[JsonObject],
        requested: dict[str, JsonObject],
    ) -> None:
        covered_topics: set[str] = set()
        required_topics: set[str] = set()
        for raw in rows:
            section_id = str(raw["id"])
            request = requested[section_id]
            topics = {str(value) for value in raw.get("topic_refs", [])}
            required = {str(value) for value in request.get("required_topics", [])}
            if not required.issubset(topics):
                raise AgentGovernanceError(
                    f"narrative {section_id!r} omits required topics {sorted(required - topics)}"
                )
            storylines = {str(value) for value in raw.get("storyline_refs", [])}
            allowed_storylines = {str(value) for value in request.get("storyline_refs", [])}
            if not storylines or not storylines.issubset(allowed_storylines):
                raise AgentGovernanceError(
                    f"narrative {section_id!r} has missing or undeclared storylines"
                )
            body = str(raw.get("body_template", "")).strip()
            if len(body) < 48:
                raise AgentGovernanceError(
                    f"narrative {section_id!r} is too thin for leadership use"
                )
            self.validate_prose(body)
            covered_topics.update(topics)
            required_topics.update(required)
        if not required_topics.issubset(covered_topics):
            raise AgentGovernanceError(
                "narrative does not cover the complete requested leadership brief"
            )

    @staticmethod
    def validate_prose(*values: str) -> None:
        for value in values:
            prose = _STORYLINE_PLACEHOLDER.sub("", _PLACEHOLDER.sub("", value))
            match = _MACHINE_PROSE.search(prose)
            if match:
                raise AgentGovernanceError(
                    f"leadership prose exposes machine-oriented label {match.group(0)!r}"
                )


def trusted_numeric_literals(source: JsonObject) -> set[str]:
    """Return numeric product descriptors explicitly present in governed source copy."""

    trusted: set[str] = set()
    for field in ("title", "summary", "business_impact"):
        text = str(source.get(field, ""))
        trusted.update(_NUMERIC_LITERAL.findall(text))
        for match in _PERCENT_DESCRIPTOR.finditer(text):
            integer, decimal = match.groups()
            trusted.add(f"{integer}{f'.{decimal}' if decimal else ''}%")
    return trusted


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def checksum(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class MetricCitationRenderer:
    def __init__(self, metrics: list[JsonObject]) -> None:
        self._metrics = {str(metric["metric_id"]): metric for metric in metrics}

    def render(
        self,
        template: str,
        *,
        allowed_metric_refs: set[str],
        trusted_numeric_literals: set[str] | None = None,
        allowed_storyline_refs: set[str] | None = None,
        storylines: dict[str, JsonObject] | None = None,
    ) -> tuple[str, list[JsonObject]]:
        trusted_numbers = trusted_numeric_literals or set()
        without_placeholders = _STORYLINE_PLACEHOLDER.sub(
            "",
            _PLACEHOLDER.sub("", template),
        )
        unsupported = [
            value
            for value in _NUMERIC_LITERAL.findall(without_placeholders)
            if value not in trusted_numbers
        ]
        if unsupported:
            raise AgentGovernanceError(
                f"model output contains unsupported numeric literals {unsupported}"
            )
        claims: list[JsonObject] = []

        def substitute(match: re.Match[str]) -> str:
            metric_ref, format_name = match.groups()
            if metric_ref not in allowed_metric_refs:
                raise AgentGovernanceError(
                    f"numeric placeholder references undeclared metric {metric_ref!r}"
                )
            metric = self._metrics.get(metric_ref)
            if metric is None:
                raise AgentGovernanceError(
                    f"numeric placeholder references unknown metric {metric_ref!r}"
                )
            rendered = self._format(metric, format_name)
            claims.append(
                {
                    "metric_ref": metric_ref,
                    "rendered_value": rendered,
                    "format": format_name,
                }
            )
            return rendered

        rendered = _PLACEHOLDER.sub(substitute, template)
        trusted_storyline_numbers: list[str] = []

        def substitute_storyline(match: re.Match[str]) -> str:
            storyline_ref = match.group(1)
            if storyline_ref not in (allowed_storyline_refs or set()):
                raise AgentGovernanceError(
                    f"narrative placeholder references undeclared storyline {storyline_ref!r}"
                )
            storyline = (storylines or {}).get(storyline_ref)
            if storyline is None:
                raise AgentGovernanceError(
                    f"narrative placeholder references unknown storyline {storyline_ref!r}"
                )
            headline = str(storyline.get("headline", "")).strip()
            if not headline:
                raise AgentGovernanceError(
                    f"narrative placeholder references an empty storyline {storyline_ref!r}"
                )
            trusted_storyline_numbers.extend(_NUMERIC_LITERAL.findall(headline))
            return headline

        rendered = _STORYLINE_PLACEHOLDER.sub(substitute_storyline, rendered)
        remaining = _NUMERIC_LITERAL.findall(rendered)
        claim_values = [
            *[str(claim["rendered_value"]) for claim in claims],
            *trusted_storyline_numbers,
        ]
        for value in remaining:
            if value in trusted_numbers:
                continue
            if value not in claim_values:
                raise AgentGovernanceError(f"unresolved numeric claim {value!r}")
            claim_values.remove(value)
        return rendered, claims

    @staticmethod
    def _format(metric: JsonObject, format_name: str) -> str:
        value = float(metric["value"])
        unit = str(metric["unit"])
        if format_name == "integer":
            if abs(value - round(value)) > 1e-9:
                raise AgentGovernanceError("integer format requires a whole-number metric")
            return f"{round(value):,}"
        if format_name == "decimal_1":
            return f"{value:,.1f}"
        if format_name == "decimal_2":
            return f"{value:,.2f}"
        if format_name in {"percent_1", "percent_2"}:
            if unit != "rate":
                raise AgentGovernanceError("percent format requires a rate metric")
            precision = 1 if format_name == "percent_1" else 2
            return f"{value * 100:,.{precision}f}%"
        if format_name == "currency_2":
            if not unit.startswith("USD"):
                raise AgentGovernanceError("currency format requires a USD metric")
            sign = "-" if value < 0 else ""
            return f"{sign}${abs(value):,.2f}"
        raise AgentGovernanceError(f"unsupported metric format {format_name!r}")


class GovernedOutputBuilder:
    def __init__(self, repository_root: Path) -> None:
        self._root = repository_root
        self._critic = NarrativeQualityCritic()

    def insight_result(
        self,
        provider_result: JsonObject,
        deterministic_insights: list[JsonObject],
        metrics: list[JsonObject],
    ) -> JsonObject:
        candidates = {str(value["id"]): value for value in deterministic_insights}
        rows = provider_result.get("insights")
        if not isinstance(rows, list) or not rows:
            raise AgentGovernanceError("insight output must contain at least one insight")
        renderer = MetricCitationRenderer(metrics)
        selected: list[JsonObject] = []
        seen: set[str] = set()
        for raw in rows:
            if not isinstance(raw, dict):
                raise AgentGovernanceError("insight output rows must be objects")
            insight_id = str(raw.get("id", ""))
            source = candidates.get(insight_id)
            if source is None or insight_id in seen:
                raise AgentGovernanceError(
                    f"model selected unknown or duplicate insight {insight_id!r}"
                )
            seen.add(insight_id)
            metric_refs = {str(value) for value in source["metric_refs"]}
            trusted_numbers = trusted_numeric_literals(source)
            title, title_claims = renderer.render(
                str(raw.get("title", "")),
                allowed_metric_refs=metric_refs,
                trusted_numeric_literals=trusted_numbers,
            )
            summary, summary_claims = renderer.render(
                str(raw.get("summary", "")),
                allowed_metric_refs=metric_refs,
                trusted_numeric_literals=trusted_numbers,
            )
            impact, impact_claims = renderer.render(
                str(raw.get("business_impact", "")),
                allowed_metric_refs=metric_refs,
                trusted_numeric_literals=trusted_numbers,
            )
            if not title or not summary or not impact:
                raise AgentGovernanceError("AI insight text fields cannot be empty")
            self._critic.validate_prose(title, summary, impact)
            selected.append(
                {
                    "id": insight_id,
                    "title": title,
                    "summary": summary,
                    "severity": source["severity"],
                    "business_impact": impact,
                    "metric_refs": list(source["metric_refs"]),
                    "evidence_refs": list(source["evidence_refs"]),
                    "confidence": source["confidence"],
                    "numeric_claims": [*title_claims, *summary_claims, *impact_claims],
                }
            )
        return {"insights": selected}

    def narrative_result(
        self,
        provider_result: JsonObject,
        requested_sections: list[JsonObject],
        metrics: list[JsonObject],
        evidence_ids: set[str],
        storylines: list[JsonObject],
    ) -> JsonObject:
        requested = {str(section["id"]): section for section in requested_sections}
        rows = provider_result.get("sections")
        if not isinstance(rows, list) or not rows:
            raise AgentGovernanceError("narrative output must contain sections")
        if (
            len(rows) != len(requested)
            or not all(isinstance(row, dict) for row in rows)
            or {str(row.get("id")) for row in rows if isinstance(row, dict)} != set(requested)
        ):
            raise AgentGovernanceError("narrative output must return every requested section once")
        typed_rows = [dict(row) for row in rows if isinstance(row, dict)]
        self._critic.validate(typed_rows, requested)
        metric_index = {str(metric["metric_id"]): metric for metric in metrics}
        storyline_index = {str(storyline["id"]): storyline for storyline in storylines}
        renderer = MetricCitationRenderer(metrics)
        sections: list[JsonObject] = []
        for raw in rows:
            assert isinstance(raw, dict)
            section_id = str(raw["id"])
            metric_refs = [str(value) for value in raw.get("metric_refs", [])]
            topic_refs = [str(value) for value in raw.get("topic_refs", [])]
            storyline_refs = [str(value) for value in raw.get("storyline_refs", [])]
            allowed_metrics = {
                str(value) for value in requested[section_id].get("allowed_metric_refs", [])
            }
            allowed_evidence = {
                str(value) for value in requested[section_id].get("allowed_evidence_refs", [])
            }
            if not set(metric_refs).issubset(allowed_metrics):
                raise AgentGovernanceError(
                    f"narrative {section_id!r} cites metrics outside its governed brief"
                )
            if not metric_refs or set(metric_refs) - set(metric_index):
                raise AgentGovernanceError(
                    f"narrative {section_id!r} references unknown or empty metrics"
                )
            metric_evidence = {
                str(evidence)
                for metric_ref in metric_refs
                for evidence in metric_index[metric_ref]["evidence_refs"]
            }
            referenced_evidence = sorted(metric_evidence & allowed_evidence & evidence_ids)
            if not referenced_evidence:
                raise AgentGovernanceError(
                    f"narrative {section_id!r} metrics have no governed evidence"
                )
            body, claims = renderer.render(
                str(raw.get("body_template", "")),
                allowed_metric_refs=set(metric_refs),
                allowed_storyline_refs=set(storyline_refs),
                storylines=storyline_index,
            )
            if not body:
                raise AgentGovernanceError("AI narrative body cannot be empty")
            self._critic.validate_prose(body)
            sections.append(
                {
                    "id": section_id,
                    "heading": requested[section_id]["heading"],
                    "body": body,
                    "topic_refs": topic_refs,
                    "storyline_refs": storyline_refs,
                    "metric_refs": metric_refs,
                    "evidence_refs": referenced_evidence,
                    "numeric_claims": claims,
                }
            )
        return {"sections": sections}

    def envelope(
        self,
        *,
        task_id: str,
        analysis_id: str,
        prompt: PromptTemplate,
        provider_id: str,
        model_id: str,
        input_checksum: str,
        evidence_refs: list[str],
        result: JsonObject,
        response: ProviderResponse,
    ) -> JsonObject:
        usage: JsonObject = {
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "latency_ms": response.latency_ms,
        }
        if response.estimated_cost_usd is not None:
            usage["estimated_cost_usd"] = response.estimated_cost_usd
        document: JsonObject = {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "analysis_id": analysis_id,
            "role": prompt.role,
            "prompt_template": {
                "id": prompt.id,
                "version": prompt.version,
                "checksum_sha256": prompt.checksum,
            },
            "model": {"provider": provider_id, "model_id": model_id},
            "input_checksum_sha256": input_checksum,
            "output_checksum_sha256": checksum(result),
            "evidence_refs": sorted(set(evidence_refs)),
            "generated_at": datetime.now(UTC).isoformat(),
            "authoritative_metrics_computed": False,
            "usage": usage,
            "result": result,
            "validation": {
                "status": "passed",
                "unsupported_numeric_claims": 0,
                "metric_reference_coverage": 1,
                "issues": [],
            },
        }
        self.validate_envelope(document, expected_input_checksum=input_checksum)
        return document

    def validate_envelope(
        self,
        document: JsonObject,
        *,
        expected_input_checksum: str,
    ) -> None:
        validate_instance(self._root, "agent-output.schema.json", document, label="agent output")
        if document["authoritative_metrics_computed"] is not False:
            raise AgentGovernanceError("model output cannot compute authoritative metrics")
        if str(document["input_checksum_sha256"]) != expected_input_checksum:
            raise AgentGovernanceError("agent output input checksum does not match")
        if str(document["output_checksum_sha256"]) != checksum(document["result"]):
            raise AgentGovernanceError("agent output result checksum does not match")


def apply_governed_outputs(
    deterministic_result: JsonObject,
    *,
    insight_output: JsonObject | None,
    narrative_output: JsonObject | None,
    task_ids: list[str],
) -> JsonObject:
    """Overlay only interpretive fields; authoritative metrics remain byte-identical."""

    result = deepcopy(deterministic_result)
    original_metrics = canonical_bytes(result["metrics"])
    if insight_output is not None:
        result["insights"] = [
            {
                **{key: value for key, value in insight.items() if key != "numeric_claims"},
                "generated_by": "ai_assisted",
            }
            for insight in insight_output["result"]["insights"]
        ]
    if narrative_output is not None:
        result["narratives"] = {
            "generation_mode": "ai_assisted",
            "agent_task_ids": task_ids,
            "sections": [
                {key: value for key, value in section.items() if key != "numeric_claims"}
                for section in narrative_output["result"]["sections"]
            ],
        }
    validation = result["validation"]
    assert isinstance(validation, dict)
    checks = validation["checks"]
    assert isinstance(checks, list)
    checks.append(
        {
            "id": "governed-ai-authority",
            "status": "passed",
            "evidence_refs": sorted(
                {
                    str(ref)
                    for output in (insight_output, narrative_output)
                    if output is not None
                    for ref in output["evidence_refs"]
                }
            ),
        }
    )
    validation["unsupported_numeric_claims"] = 0
    validation["metric_reference_coverage"] = 1
    if canonical_bytes(result["metrics"]) != original_metrics:
        raise AgentGovernanceError("AI assistance attempted to mutate authoritative metrics")
    provenance = result["provenance"]
    assert isinstance(provenance, dict)
    provenance["final_result_checksum_sha256"] = "0" * 64
    provenance["final_result_checksum_sha256"] = checksum(result)
    return result
