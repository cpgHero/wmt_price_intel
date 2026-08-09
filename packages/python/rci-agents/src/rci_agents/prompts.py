"""Versioned prompt-template loading."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from rci_agents.models import AgentRole, JsonObject, PromptTemplate
from rci_contracts import ContractError, validate_instance


class PromptTemplateLoader:
    def __init__(self, repository_root: Path) -> None:
        self._root = repository_root

    def load(self, prompt_id: str) -> PromptTemplate:
        path = self._root / "agent-prompts" / f"{prompt_id}.json"
        try:
            body = path.read_bytes()
            document: JsonObject = json.loads(body)
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"could not read governed prompt {path}: {exc}") from exc
        validate_instance(
            self._root,
            "agent-prompt.schema.json",
            document,
            label=str(path),
        )
        return PromptTemplate(
            id=str(document["id"]),
            version=str(document["version"]),
            role=cast(AgentRole, str(document["role"])),
            instructions=str(document["instructions"]),
            checksum=hashlib.sha256(body).hexdigest(),
        )
