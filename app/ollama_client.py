from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import OLLAMA_BASE_URL, OLLAMA_TIMEOUT_SECONDS


class OllamaUnavailable(RuntimeError):
    pass


ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low", "info"],
                    },
                    "title": {"type": "string"},
                    "observations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "analysis": {"type": "string"},
                    "recommendations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "validation_sql": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "risk": {"type": "string"},
                },
                "required": [
                    "severity",
                    "title",
                    "observations",
                    "analysis",
                    "recommendations",
                    "validation_sql",
                    "risk",
                ],
            },
        },
        "missing_information": {
            "type": "array",
            "items": {"type": "string"},
        },
        "next_steps": {"type": "array", "items": {"type": "string"}},
        "disclaimer": {"type": "string"},
    },
    "required": [
        "executive_summary",
        "confidence",
        "findings",
        "missing_information",
        "next_steps",
        "disclaimer",
    ],
}


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(
                timeout=8, trust_env=False
            ) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaUnavailable(
                f"Ollama is not reachable at {self.base_url}."
            ) from exc
        models = []
        for item in payload.get("models", []):
            name = item.get("name") or item.get("model")
            if name:
                models.append(str(name))
        return sorted(set(models), key=str.lower)

    async def analyse(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        request = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": ANALYSIS_SCHEMA,
            "stream": False,
            "options": {"temperature": 0.15},
            "keep_alive": "10m",
        }
        try:
            async with httpx.AsyncClient(
                timeout=OLLAMA_TIMEOUT_SECONDS, trust_env=False
            ) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat", json=request
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise OllamaUnavailable(
                "The local model timed out. Try a smaller model or increase OLLAMA_TIMEOUT_SECONDS."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise OllamaUnavailable(
                f"Ollama rejected the request ({exc.response.status_code}): {detail}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaUnavailable(
                f"Ollama is not reachable at {self.base_url}."
            ) from exc

        content = str(payload.get("message", {}).get("content", "")).strip()
        if not content:
            raise OllamaUnavailable("The local model returned an empty response.")
        result = self._parse_json(content)
        return self._normalise(result)

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.S)
            if not match:
                raise OllamaUnavailable(
                    "The model did not return structured JSON. Try another model."
                )
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise OllamaUnavailable(
                    "The model response was not valid JSON. Try another model."
                ) from exc
        if not isinstance(parsed, dict):
            raise OllamaUnavailable("The model response has an unexpected shape.")
        return parsed

    @staticmethod
    def _normalise(result: dict[str, Any]) -> dict[str, Any]:
        confidence = str(result.get("confidence", "low")).lower()
        if confidence not in {"low", "medium", "high"}:
            confidence = "low"
        findings = result.get("findings")
        if not isinstance(findings, list):
            findings = []
        normalised_findings = []
        for finding in findings[:20]:
            if not isinstance(finding, dict):
                continue
            severity = str(finding.get("severity", "info")).lower()
            if severity not in {"critical", "high", "medium", "low", "info"}:
                severity = "info"

            def strings(key: str) -> list[str]:
                value = finding.get(key, [])
                if isinstance(value, str):
                    return [value]
                if isinstance(value, list):
                    return [str(item) for item in value if str(item).strip()]
                return []

            normalised_findings.append(
                {
                    "severity": severity,
                    "title": str(finding.get("title", "Finding")).strip(),
                    "observations": strings("observations"),
                    "analysis": str(finding.get("analysis", "")).strip(),
                    "recommendations": strings("recommendations"),
                    "validation_sql": strings("validation_sql"),
                    "risk": str(finding.get("risk", "")).strip(),
                }
            )

        def top_strings(key: str) -> list[str]:
            value = result.get(key, [])
            if isinstance(value, str):
                return [value]
            if isinstance(value, list):
                return [str(item) for item in value if str(item).strip()]
            return []

        return {
            "executive_summary": str(
                result.get("executive_summary", "No summary returned.")
            ).strip(),
            "confidence": confidence,
            "findings": normalised_findings,
            "missing_information": top_strings("missing_information"),
            "next_steps": top_strings("next_steps"),
            "disclaimer": str(
                result.get(
                    "disclaimer",
                    "Validate every recommendation before applying it.",
                )
            ).strip(),
        }
