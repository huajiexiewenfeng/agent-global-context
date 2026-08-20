"""Strict content-hidden contracts for semantic Capture extractors."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, TYPE_CHECKING

from agc_runtime.capture_contracts import SanitizedError, TokenUsage
from agc_runtime.capture_safety import ObservationDraft

if TYPE_CHECKING:
    from agc_runtime.capture_budget import TokenReservation
    from agc_runtime.capture_capsule import TaskCapsule


EXTRACTOR_SCHEMA_VERSION = "capture-extractor-v1"
EXTRACTOR_VERSION = "1.0"
TAXONOMY_VERSION = "agc-taxonomy-v1"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_BOUNDARY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVITY = frozenset({"normal", "personal", "sensitive", "secret"})


def _contract_error() -> ValueError:
    return ValueError("capture_extractor_contract_invalid")


def _guard_json(value: Any) -> None:
    try:
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise _contract_error() from error


def _exact_mapping(value: Any, fields: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise _contract_error()
    _guard_json(value)
    return value


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise _contract_error()
    return value


def _optional_boundary(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _BOUNDARY.fullmatch(value) is None:
        raise _contract_error()
    return value


@dataclass(frozen=True)
class ExtractorDescriptor:
    extractor_id: str
    extractor_version: str
    extractor_schema_version: str
    taxonomy_version: str

    def __post_init__(self) -> None:
        try:
            for value in (
                self.extractor_id,
                self.extractor_version,
                self.extractor_schema_version,
                self.taxonomy_version,
            ):
                _identifier(value)
            if self.extractor_schema_version != EXTRACTOR_SCHEMA_VERSION:
                raise _contract_error()
        except (AttributeError, TypeError, UnicodeError, ValueError) as error:
            raise _contract_error() from error

    @classmethod
    def from_mapping(cls, value: Any) -> "ExtractorDescriptor":
        try:
            mapping = _exact_mapping(
                value,
                frozenset(
                    {
                        "extractor_id",
                        "extractor_version",
                        "extractor_schema_version",
                        "taxonomy_version",
                    }
                ),
            )
            descriptor = cls(
                _identifier(mapping["extractor_id"]),
                _identifier(mapping["extractor_version"]),
                _identifier(mapping["extractor_schema_version"]),
                _identifier(mapping["taxonomy_version"]),
            )
            if descriptor.extractor_schema_version != EXTRACTOR_SCHEMA_VERSION:
                raise _contract_error()
            return descriptor
        except (AttributeError, KeyError, TypeError, UnicodeError, ValueError) as error:
            raise _contract_error() from error

    def to_mapping(self) -> dict[str, str]:
        return {
            "extractor_id": self.extractor_id,
            "extractor_version": self.extractor_version,
            "extractor_schema_version": self.extractor_schema_version,
            "taxonomy_version": self.taxonomy_version,
        }


@dataclass(frozen=True)
class CapabilityProbe:
    available: bool
    executable_identity: str
    executable_version: str = field(repr=False)
    model_boundary: str | None = field(default=None, repr=False)
    provider_boundary: str | None = field(default=None, repr=False)
    auth_available: bool = False
    sandbox_read_only: bool = False
    usage_available: bool = False
    error: SanitizedError | None = None

    def __post_init__(self) -> None:
        try:
            if (
                type(self.available) is not bool
                or not isinstance(self.executable_identity, str)
                or (
                    self.executable_identity
                    and _SHA256.fullmatch(self.executable_identity) is None
                )
                or not isinstance(self.executable_version, str)
                or (
                    self.executable_version
                    and _IDENTIFIER.fullmatch(self.executable_version) is None
                )
                or not all(
                    type(item) is bool
                    for item in (
                        self.auth_available,
                        self.sandbox_read_only,
                        self.usage_available,
                    )
                )
            ):
                raise _contract_error()
            _optional_boundary(self.model_boundary)
            _optional_boundary(self.provider_boundary)
            _guard_json(self.to_mapping())
            if self.error is not None:
                SanitizedError.from_mapping(self.error.to_mapping())
            if self.available:
                if (
                    self.error is not None
                    or not self.executable_identity
                    or not self.executable_version
                    or self.model_boundary is None
                    or self.provider_boundary is None
                    or not self.auth_available
                    or not self.sandbox_read_only
                ):
                    raise _contract_error()
            elif self.error is None:
                raise _contract_error()
        except (AttributeError, TypeError, UnicodeError, ValueError) as error:
            raise _contract_error() from error

    @classmethod
    def from_mapping(cls, value: Any) -> "CapabilityProbe":
        try:
            mapping = _exact_mapping(
                value,
                frozenset(
                    {
                        "available",
                        "executable_identity",
                        "executable_version",
                        "model_boundary",
                        "provider_boundary",
                        "auth_available",
                        "sandbox_read_only",
                        "usage_available",
                        "error",
                    }
                ),
            )
            available = mapping["available"]
            identity = mapping["executable_identity"]
            version = mapping["executable_version"]
            model = mapping["model_boundary"]
            provider = mapping["provider_boundary"]
            auth = mapping["auth_available"]
            sandbox = mapping["sandbox_read_only"]
            usage = mapping["usage_available"]
            if (
                type(available) is not bool
                or not isinstance(identity, str)
                or (identity and _SHA256.fullmatch(identity) is None)
                or not isinstance(version, str)
                or (version and _IDENTIFIER.fullmatch(version) is None)
                or not all(type(item) is bool for item in (auth, sandbox, usage))
            ):
                raise _contract_error()
            _optional_boundary(model)
            _optional_boundary(provider)
            error_value = mapping["error"]
            error = (
                None
                if error_value is None
                else SanitizedError.from_mapping(error_value)
            )
            if available:
                if (
                    error is not None
                    or not identity
                    or not version
                    or model is None
                    or provider is None
                    or not auth
                    or not sandbox
                ):
                    raise _contract_error()
            elif error is None:
                raise _contract_error()
            return cls(
                available,
                identity,
                version,
                model,
                provider,
                auth,
                sandbox,
                usage,
                error,
            )
        except (AttributeError, KeyError, TypeError, UnicodeError, ValueError) as error:
            raise _contract_error() from error

    def to_mapping(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "executable_identity": self.executable_identity,
            "executable_version": self.executable_version,
            "model_boundary": self.model_boundary,
            "provider_boundary": self.provider_boundary,
            "auth_available": self.auth_available,
            "sandbox_read_only": self.sandbox_read_only,
            "usage_available": self.usage_available,
            "error": self.error.to_mapping() if self.error is not None else None,
        }


@dataclass(frozen=True)
class CollectedObservationDraft:
    statement: str = field(repr=False)
    assertion_subject: str = field(repr=False)
    assertion_mode: str
    modality: str
    primary_category: str
    kind: str
    scopes: tuple[str, ...] = field(repr=False)
    project_scope: str | None = field(repr=False)
    confidence: str
    sensitivity: str
    signal_type: str
    evidence: tuple[str, ...] = field(repr=False)
    priority: int
    locator: str = field(repr=False)

    def __post_init__(self) -> None:
        try:
            if not isinstance(self.scopes, tuple) or not isinstance(self.evidence, tuple):
                raise _contract_error()
            mapping = self.to_mapping()
            _guard_json(mapping)
            draft = ObservationDraft.from_mapping(mapping)
            if draft.to_mapping() != mapping:
                raise _contract_error()
            if draft.sensitivity not in _SENSITIVITY:
                raise _contract_error()
        except (AttributeError, KeyError, TypeError, UnicodeError, ValueError) as error:
            raise _contract_error() from error

    @classmethod
    def from_mapping(cls, value: Any) -> "CollectedObservationDraft":
        try:
            _guard_json(value)
            draft = ObservationDraft.from_mapping(value)
            if draft.sensitivity not in _SENSITIVITY:
                raise _contract_error()
            return cls(
                draft.statement,
                draft.assertion_subject,
                draft.assertion_mode,
                draft.modality,
                draft.primary_category,
                draft.kind,
                draft.scopes,
                draft.project_scope,
                draft.confidence,
                draft.sensitivity,
                draft.signal_type,
                draft.evidence,
                draft.priority,
                draft.locator,
            )
        except (AttributeError, KeyError, TypeError, UnicodeError, ValueError) as error:
            raise _contract_error() from error

    def to_mapping(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "assertion": {
                "subject": self.assertion_subject,
                "mode": self.assertion_mode,
                "modality": self.modality,
            },
            "primary_category": self.primary_category,
            "kind": self.kind,
            "scopes": list(self.scopes),
            "project_scope": self.project_scope,
            "confidence": self.confidence,
            "sensitivity": self.sensitivity,
            "signal_type": self.signal_type,
            "evidence": list(self.evidence),
            "priority": self.priority,
            "locator": self.locator,
        }


@dataclass(frozen=True)
class ExtractionResult:
    succeeded: bool
    drafts: tuple[CollectedObservationDraft, ...] = field(repr=False)
    usage: TokenUsage | None = None
    error: SanitizedError | None = None

    def __post_init__(self) -> None:
        try:
            if (
                type(self.succeeded) is not bool
                or not isinstance(self.drafts, tuple)
                or len(self.drafts) > 8
                or any(
                    not isinstance(draft, CollectedObservationDraft)
                    for draft in self.drafts
                )
            ):
                raise _contract_error()
            for draft in self.drafts:
                CollectedObservationDraft.from_mapping(draft.to_mapping())
            if self.usage is not None:
                TokenUsage.from_mapping(self.usage.to_mapping())
            if self.error is not None:
                SanitizedError.from_mapping(self.error.to_mapping())
            _guard_json(self.to_mapping())
            if self.succeeded:
                if self.error is not None:
                    raise _contract_error()
            elif self.drafts or self.usage is not None or self.error is None:
                raise _contract_error()
        except (AttributeError, KeyError, TypeError, UnicodeError, ValueError) as error:
            raise _contract_error() from error

    @classmethod
    def from_mapping(cls, value: Any) -> "ExtractionResult":
        try:
            mapping = _exact_mapping(
                value,
                frozenset({"succeeded", "drafts", "usage", "error"}),
            )
            succeeded = mapping["succeeded"]
            drafts_value = mapping["drafts"]
            if type(succeeded) is not bool or not isinstance(drafts_value, list):
                raise _contract_error()
            drafts = tuple(
                CollectedObservationDraft.from_mapping(item) for item in drafts_value
            )
            if len(drafts) > 8:
                raise _contract_error()
            usage_value = mapping["usage"]
            usage = None if usage_value is None else TokenUsage.from_mapping(usage_value)
            error_value = mapping["error"]
            error = None if error_value is None else SanitizedError.from_mapping(error_value)
            if succeeded:
                if error is not None:
                    raise _contract_error()
            elif drafts or usage is not None or error is None:
                raise _contract_error()
            return cls(succeeded, drafts, usage, error)
        except (AttributeError, KeyError, TypeError, UnicodeError, ValueError) as error:
            raise _contract_error() from error

    def to_mapping(self) -> dict[str, Any]:
        return {
            "succeeded": self.succeeded,
            "drafts": [draft.to_mapping() for draft in self.drafts],
            "usage": self.usage.to_mapping() if self.usage is not None else None,
            "error": self.error.to_mapping() if self.error is not None else None,
        }


class SemanticExtractor(Protocol):
    def describe(self) -> ExtractorDescriptor: ...

    def probe_capabilities(self) -> CapabilityProbe: ...

    def extract(
        self,
        capsule: "TaskCapsule",
        reservation: "TokenReservation",
    ) -> ExtractionResult: ...


__all__ = [
    "EXTRACTOR_SCHEMA_VERSION",
    "EXTRACTOR_VERSION",
    "TAXONOMY_VERSION",
    "CapabilityProbe",
    "CollectedObservationDraft",
    "ExtractionResult",
    "ExtractorDescriptor",
    "SemanticExtractor",
]
