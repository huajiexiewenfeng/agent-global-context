"""Content-safe host activation diagnosis and explicit-consent digests."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Mapping

from agc_runtime import __version__


_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "effective_v2_skill_count",
        "legacy_v1_skill_count",
        "mcp_block_count",
        "memory_root_count",
        "runtime_hash_matches",
        "config_hash_matches",
        "recall_gate_passed",
        "extractor_capability",
        "hook_enabled",
        "hook_trusted",
        "hook_latency_passed",
        "scheduler_enabled",
        "frozen_census",
    }
)
_CAPABILITIES = frozenset({"not_assessed", "ready", "invalid", "unavailable"})
_READINESS_KEYS = (
    "installed_inert",
    "scanner_ready",
    "hook_ready",
    "backfill_runner_ready",
    "continuous_runner_ready",
)


def _count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("invalid activation evidence")
    return value


def _optional_bool(value: Any) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raise ValueError("invalid activation evidence")


@dataclass(frozen=True, slots=True)
class ActivationEvidence:
    """Host-only facts without paths, commands, or user content."""

    schema_version: int
    effective_v2_skill_count: int | None
    legacy_v1_skill_count: int | None
    mcp_block_count: int | None
    memory_root_count: int | None
    runtime_hash_matches: bool | None
    config_hash_matches: bool | None
    recall_gate_passed: bool | None
    extractor_capability: str
    hook_enabled: bool | None
    hook_trusted: bool | None
    hook_latency_passed: bool | None
    scheduler_enabled: bool | None
    frozen_census: bool | None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ActivationEvidence":
        try:
            if not isinstance(value, Mapping) or set(value) != _EVIDENCE_FIELDS:
                raise ValueError
            if value["schema_version"] != 1 or isinstance(
                value["schema_version"], bool
            ):
                raise ValueError
            capability = value["extractor_capability"]
            if not isinstance(capability, str) or capability not in _CAPABILITIES:
                raise ValueError
            return cls(
                schema_version=1,
                effective_v2_skill_count=_count(value["effective_v2_skill_count"]),
                legacy_v1_skill_count=_count(value["legacy_v1_skill_count"]),
                mcp_block_count=_count(value["mcp_block_count"]),
                memory_root_count=_count(value["memory_root_count"]),
                runtime_hash_matches=_optional_bool(value["runtime_hash_matches"]),
                config_hash_matches=_optional_bool(value["config_hash_matches"]),
                recall_gate_passed=_optional_bool(value["recall_gate_passed"]),
                extractor_capability=capability,
                hook_enabled=_optional_bool(value["hook_enabled"]),
                hook_trusted=_optional_bool(value["hook_trusted"]),
                hook_latency_passed=_optional_bool(value["hook_latency_passed"]),
                scheduler_enabled=_optional_bool(value["scheduler_enabled"]),
                frozen_census=_optional_bool(value["frozen_census"]),
            )
        except (KeyError, TypeError, ValueError):
            raise ValueError("invalid activation evidence") from None

    @classmethod
    def not_assessed(cls) -> "ActivationEvidence":
        return cls.from_mapping(
            {
                "schema_version": 1,
                "effective_v2_skill_count": None,
                "legacy_v1_skill_count": None,
                "mcp_block_count": None,
                "memory_root_count": None,
                "runtime_hash_matches": None,
                "config_hash_matches": None,
                "recall_gate_passed": None,
                "extractor_capability": "not_assessed",
                "hook_enabled": None,
                "hook_trusted": None,
                "hook_latency_passed": None,
                "scheduler_enabled": None,
                "frozen_census": None,
            }
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            field_name: getattr(self, field_name)
            for field_name in sorted(_EVIDENCE_FIELDS)
        }


@dataclass(frozen=True, slots=True)
class ActivationReport:
    schema_version: int
    route_assessment: str
    conflicts: tuple[str, ...]
    readiness: Mapping[str, bool]
    reasons: tuple[str, ...]
    consent_digest_matches: bool
    evidence: ActivationEvidence
    _authorization_json: str = field(repr=False)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "route_assessment": self.route_assessment,
            "conflicts": list(self.conflicts),
            "readiness": {
                key: bool(self.readiness[key]) for key in _READINESS_KEYS
            },
            "reasons": list(self.reasons),
            "consent_digest_matches": self.consent_digest_matches,
            "evidence": self.evidence.to_mapping(),
        }


def _route_conflicts(evidence: ActivationEvidence) -> tuple[str, ...]:
    conflicts: list[str] = []
    if evidence.effective_v2_skill_count == 0:
        conflicts.append("effective_v2_skill_missing")
    elif evidence.effective_v2_skill_count not in {None, 1}:
        conflicts.append("multiple_effective_v2_skills")
    if evidence.legacy_v1_skill_count not in {None, 0}:
        conflicts.append("legacy_v1_route_present")
    if evidence.mcp_block_count == 0:
        conflicts.append("mcp_block_missing")
    elif evidence.mcp_block_count not in {None, 1}:
        conflicts.append("multiple_mcp_blocks")
    if evidence.memory_root_count == 0:
        conflicts.append("memory_root_missing")
    elif evidence.memory_root_count not in {None, 1}:
        conflicts.append("multiple_memory_roots")
    if evidence.runtime_hash_matches is False:
        conflicts.append("runtime_hash_stale")
    if evidence.config_hash_matches is False:
        conflicts.append("config_hash_stale")
    return tuple(sorted(conflicts))


def _authorization_payload(
    status: Mapping[str, Any], evidence: ActivationEvidence
) -> dict[str, Any]:
    scanner = status.get("scanner", {})
    exclusions = scanner.get("exclusions", {}) if isinstance(scanner, Mapping) else {}
    return {
        "schema_version": 1,
        "runtime": {
            "version": status["runtime"]["version"],
            "sha256": status["runtime"]["sha256"],
        },
        "config_source": {
            "kind": status["config_source"]["kind"],
            "sha256": status["config_source"]["sha256"],
        },
        "memory_root_id": status["memory_root"]["fingerprint"],
        "source_root_ids": sorted(status["source_roots"]["ids"]),
        "extractor_boundary": dict(status["extractor_boundary"]),
        "budgets": dict(status["budgets"]),
        "state": dict(status["state"]),
        "exclusions": {
            "task_id_count": exclusions.get("task_id_count", 0),
            "project_id_count": exclusions.get("project_id_count", 0),
        },
        "host_evidence": evidence.to_mapping(),
    }


def activation_digest_for(report: ActivationReport) -> str:
    return hashlib.sha256(report._authorization_json.encode("utf-8")).hexdigest()


def diagnose_activation(
    status: Mapping[str, Any],
    evidence: ActivationEvidence,
    *,
    consent_digest: str | None = None,
) -> ActivationReport:
    """Diagnose readiness without reading or mutating host configuration."""

    payload = _authorization_payload(status, evidence)
    authorization_json = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    required_digest = hashlib.sha256(authorization_json.encode("utf-8")).hexdigest()
    consent_matches = consent_digest == required_digest
    conflicts = _route_conflicts(evidence)
    counts = (
        evidence.effective_v2_skill_count,
        evidence.legacy_v1_skill_count,
        evidence.mcp_block_count,
        evidence.memory_root_count,
    )
    route_assessment = (
        "conflict"
        if conflicts
        else (
            "not_assessed"
            if any(item is None for item in counts)
            or evidence.runtime_hash_matches is None
            or evidence.config_hash_matches is None
            else "ready"
        )
    )
    state = status["state"]
    memory_root = status["memory_root"]
    source_roots = status["source_roots"]
    budgets = status["budgets"]
    installed_inert = (
        status["runtime"]["version"] == __version__
        and state["enabled"] is False
        and state["mode"] == "off"
        and state["paused"] is False
    )
    scanner_ready = all(
        (
            route_assessment == "ready",
            evidence.recall_gate_passed is True,
            evidence.runtime_hash_matches is True,
            evidence.config_hash_matches is True,
            memory_root["assessment"] == "verified",
            memory_root["matches_host_binding"] is True,
            source_roots["configured_count"] > 0,
            state["enabled"] is True,
            state["paused"] is False,
            state["mode"] in {"scanner_only", "runner"},
            budgets["backfill_window_days"] == 7,
        )
    )
    hook_ready = all(
        (
            scanner_ready,
            evidence.hook_enabled is True,
            evidence.hook_trusted is True,
            evidence.hook_latency_passed is True,
        )
    )
    backfill_runner_ready = all(
        (
            scanner_ready,
            evidence.frozen_census is True,
            evidence.extractor_capability == "ready",
            budgets["backfill_total_tokens"] == 100_000,
        )
    )
    continuous_runner_ready = all(
        (
            backfill_runner_ready,
            state["mode"] == "runner",
            evidence.scheduler_enabled is True,
            budgets["incremental_total_tokens"] is not None,
            consent_matches,
        )
    )
    readiness = {
        "installed_inert": installed_inert,
        "scanner_ready": scanner_ready,
        "hook_ready": hook_ready,
        "backfill_runner_ready": backfill_runner_ready,
        "continuous_runner_ready": continuous_runner_ready,
    }
    reasons: list[str] = list(conflicts)
    if route_assessment == "not_assessed":
        reasons.append("route_not_assessed")
    if not state["enabled"]:
        reasons.append("capture_disabled")
    if state["mode"] == "off":
        reasons.append("capture_mode_off")
    if state["paused"]:
        reasons.append("capture_paused")
    if source_roots["configured_count"] == 0:
        reasons.append("source_roots_unavailable")
    if memory_root["assessment"] != "verified":
        reasons.append("memory_root_binding_not_assessed")
    if evidence.recall_gate_passed is not True:
        reasons.append("recall_gate_not_passed")
    if evidence.extractor_capability == "not_assessed":
        reasons.append("extractor_capability_not_assessed")
    elif evidence.extractor_capability != "ready":
        reasons.append("extractor_capability_not_ready")
    if state["mode"] == "runner" and not consent_matches:
        reasons.append("activation_digest_required")
    return ActivationReport(
        schema_version=1,
        route_assessment=route_assessment,
        conflicts=conflicts,
        readiness=readiness,
        reasons=tuple(dict.fromkeys(reasons)),
        consent_digest_matches=consent_matches,
        evidence=evidence,
        _authorization_json=authorization_json,
    )


__all__ = [
    "ActivationEvidence",
    "ActivationReport",
    "activation_digest_for",
    "diagnose_activation",
]
