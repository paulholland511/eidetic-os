"""Detect local LLM endpoints (LM Studio, Ollama, any OpenAI-compatible server).

Used by ``atlas init`` to auto-discover a running embeddings/chat backend so the
user doesn't have to hand-configure host/port/model.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

# (label, base_url, models_path) for common local servers.
_CANDIDATES: tuple[tuple[str, str, str], ...] = (
    ("LM Studio (default)", "http://localhost:1234", "/v1/models"),
    ("OpenAI-compatible :5555", "http://localhost:5555", "/v1/models"),
    ("Ollama", "http://localhost:11434", "/api/tags"),
)


@dataclass(frozen=True)
class Endpoint:
    """A reachable LLM endpoint discovered on the local machine."""

    label: str
    base_url: str  # e.g. http://localhost:1234
    host: str
    port: int
    models: tuple[str, ...]


def _parse_models(payload: object) -> tuple[str, ...]:
    """Pull model ids out of an OpenAI (/v1/models) or Ollama (/api/tags) body."""
    if not isinstance(payload, dict):
        return ()
    out: list[str] = []
    for item in payload.get("data", []) or []:  # OpenAI shape
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            out.append(item["id"])
    for item in payload.get("models", []) or []:  # Ollama shape
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            out.append(item["name"])
    return tuple(out)


def detect_endpoints(timeout: float = 1.5) -> list[Endpoint]:
    """Probe the well-known local ports and return whatever responds."""
    found: list[Endpoint] = []
    for label, base, path in _CANDIDATES:
        try:
            resp = requests.get(f"{base}{path}", timeout=timeout)
        except requests.RequestException:
            continue
        if resp.status_code >= 400:
            continue
        try:
            models = _parse_models(resp.json())
        except ValueError:
            models = ()
        host = base.split("://", 1)[-1].split(":", 1)[0]
        port = int(base.rsplit(":", 1)[-1])
        found.append(Endpoint(label=label, base_url=base, host=host, port=port, models=models))
    return found
