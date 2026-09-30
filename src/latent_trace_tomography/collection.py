from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class CompletionRequest:
    prompt_text: str
    max_output_tokens: int
    temperature: float
    seed: int | None = None


@dataclass(frozen=True)
class ProviderCapabilities:
    provider_name: str
    model_alias: str
    supports_seed: bool | None = None
    supports_system_fingerprint: bool | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompletionRecord:
    """Raw collection evidence; telemetry is excluded from primary features."""

    text: str
    provider_name: str
    model_alias: str
    requested_params: dict[str, Any]
    transmitted_params: dict[str, Any]
    timestamp_utc: str
    raw_response: dict[str, Any] | None = None
    response_id: str | None = None
    system_fingerprint: str | None = None
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    latency_ms: float | None = None
    retry_count: int = 0
    seed_accepted: bool | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


class CompletionProvider(Protocol):
    capabilities: ProviderCapabilities

    def complete(self, request: CompletionRequest) -> CompletionRecord: ...


class InternalObserver(Protocol):
    """OSS-only causal measurement, intentionally separate from completion."""

    observer_revision: str

    def intervene(self, case_id: str, intervention_spec: dict[str, Any]) -> dict[str, Any]: ...
