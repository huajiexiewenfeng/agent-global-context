"""Versioned, deterministic, in-memory Task Capsule construction."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping

from agc_runtime._unicode_confusables import RAW_CONFUSABLE_CLOSURE
from agc_runtime.capture_contracts import CAPTURE_SCHEMA_VERSION, RevisionRef


CAPSULE_SCHEMA_VERSION = "capsule-v1"
CAPSULE_POLICY_SCHEMA_VERSION = "capsule-policy-v1"
SOURCE_HASH_SCHEMA_VERSION = "source-fingerprint-v1"
_PROJECT_SCOPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


def _contract_error() -> ValueError:
    return ValueError("capture_capsule_contract_invalid")


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise _contract_error() from error


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _security_skeleton(value: str) -> str:
    try:
        compatibility = unicodedata.normalize("NFKC", value).casefold()
        decomposed = unicodedata.normalize("NFKD", compatibility)
    except (AttributeError, TypeError, UnicodeError) as error:
        raise _contract_error() from error
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) not in {"Mn", "Mc", "Me"}
    )
    return re.sub(r"\s+", " ", without_marks).strip()


_CONFUSABLE_SCRIPT_NAMES = frozenset({"Latin", "Cyrillic", "Greek"})


def _confusable_skeleton(value: str) -> str:
    """Return the vendored Unicode 17 UTS #39-derived security view."""

    try:
        mapped = "".join(
            RAW_CONFUSABLE_CLOSURE.get(
                ord(character),
                unicodedata.normalize("NFD", character),
            )
            for character in value
        )
        compatibility = unicodedata.normalize("NFKC", mapped.casefold())
        decomposed = unicodedata.normalize("NFKD", compatibility)
    except (AttributeError, TypeError, UnicodeError) as error:
        raise _contract_error() from error
    return "".join(
        character
        for character in decomposed
        if unicodedata.category(character) not in {"Mn", "Mc", "Me"}
    )


def _letter_script(character: str) -> str:
    name = unicodedata.name(character, "")
    markers = (
        ("LATIN", "Latin"),
        ("CYRILLIC", "Cyrillic"),
        ("GREEK", "Greek"),
        ("CJK", "Han"),
        ("IDEOGRAPH", "Han"),
        ("HIRAGANA", "Hiragana"),
        ("KATAKANA", "Katakana"),
        ("HANGUL", "Hangul"),
        ("HEBREW", "Hebrew"),
        ("ARABIC", "Arabic"),
        ("DEVANAGARI", "Devanagari"),
    )
    return next(
        (script for marker, script in markers if marker in name),
        f"Other:{name.split(' ', 1)[0]}",
    )


def _contains_mixed_script_atom(value: str) -> bool:
    try:
        compatibility = unicodedata.normalize("NFKC", value)
    except (AttributeError, TypeError, UnicodeError) as error:
        raise _contract_error() from error
    scripts: set[str] = set()
    for character in compatibility:
        category = unicodedata.category(character)
        if category.startswith("L"):
            script = _letter_script(character)
            if script in _CONFUSABLE_SCRIPT_NAMES:
                scripts.add(script)
                if len(scripts) > 1:
                    return True
            else:
                scripts.clear()
        elif not category.startswith("M"):
            scripts.clear()
    return False


def _sensitive_candidate_views(value: str) -> tuple[str, ...]:
    try:
        surface_variants = (
            value,
            value.lower(),
            value.upper(),
            value.casefold(),
        )
        security_inputs = (
            *surface_variants,
            *(unicodedata.normalize("NFKC", variant) for variant in surface_variants),
        )
    except (AttributeError, TypeError, UnicodeError) as error:
        raise _contract_error() from error
    return tuple(
        re.sub(r"\s+", " ", candidate).strip()
        for candidate in map(_confusable_skeleton, security_inputs)
    )


def _sensitive_candidates(value: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                candidate
                for candidate in _sensitive_candidate_views(value)
                if candidate
            }
        )
    )


@dataclass(frozen=True)
class CapsulePolicy:
    schema_version: int = CAPTURE_SCHEMA_VERSION
    policy_schema_version: str = CAPSULE_POLICY_SCHEMA_VERSION
    project_scope: str | None = field(default=None, repr=False)
    target_token_limit: int = 1200
    hard_token_limit: int = 3000
    max_signal_codepoints: int = 800
    max_title_codepoints: int = 160
    sensitive_labels: tuple[str, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        valid_scope = self.project_scope is None or (
            isinstance(self.project_scope, str)
            and _PROJECT_SCOPE.fullmatch(self.project_scope) is not None
            and not self.project_scope.lower().startswith("file:")
            and re.match(r"^[A-Za-z]:/", self.project_scope) is None
        )
        labels_valid = (
            isinstance(self.sensitive_labels, tuple)
            and len(self.sensitive_labels) <= 32
            and all(
                isinstance(label, str)
                and 1 <= len(label) <= 64
                and "\n" not in label
                and "\r" not in label
                and not any(
                    unicodedata.category(character).startswith("C") for character in label
                )
                for label in self.sensitive_labels
            )
        )
        if (
            type(self.schema_version) is not int
            or self.schema_version != CAPTURE_SCHEMA_VERSION
            or self.policy_schema_version != CAPSULE_POLICY_SCHEMA_VERSION
            or not valid_scope
            or type(self.target_token_limit) is not int
            or not 256 <= self.target_token_limit <= 3000
            or type(self.hard_token_limit) is not int
            or not self.target_token_limit <= self.hard_token_limit <= 3000
            or type(self.max_signal_codepoints) is not int
            or not 64 <= self.max_signal_codepoints <= 4000
            or type(self.max_title_codepoints) is not int
            or not 32 <= self.max_title_codepoints <= 300
            or not labels_valid
        ):
            raise _contract_error()
        label_candidate_views = tuple(
            _sensitive_candidate_views(label) for label in self.sensitive_labels
        )
        if any(not all(views) for views in label_candidate_views):
            raise _contract_error()
        canonical_labels = tuple(
            sorted(
                {
                    candidate
                    for views in label_candidate_views
                    for candidate in views
                }
            )
        )
        object.__setattr__(self, "sensitive_labels", canonical_labels)


@dataclass(frozen=True)
class TaskCapsule:
    schema_version: int = CAPTURE_SCHEMA_VERSION
    adapter_id: str = field(default="", repr=False)
    adapter_version: str = field(default="", repr=False)
    source_schema_version: str = field(default="", repr=False)
    source_root_id: str = field(default="", repr=False)
    task_id: str = field(default="", repr=False)
    revision_id: str = field(default="", repr=False)
    rollout_anchor_id: str = field(default="", repr=False)
    identity_quality: str = field(default="", repr=False)
    completed_at: str = field(default="", repr=False)
    project_scope: str | None = field(default=None, repr=False)
    task_title: str | None = field(default=None, repr=False)
    user_signals: tuple[str, ...] = field(default=(), repr=False)
    decisions_results: tuple[str, ...] = field(default=(), repr=False)
    reusable_methods: tuple[str, ...] = field(default=(), repr=False)
    next_steps: tuple[str, ...] = field(default=(), repr=False)
    file_locators: tuple[str, ...] = field(default=(), repr=False)
    _sensitive_labels: tuple[str, ...] = field(default=(), repr=False, compare=False)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "source_schema_version": self.source_schema_version,
            "source_root_id": self.source_root_id,
            "task_id": self.task_id,
            "revision_id": self.revision_id,
            "rollout_anchor_id": self.rollout_anchor_id,
            "identity_quality": self.identity_quality,
            "completed_at": self.completed_at,
            "project_scope": self.project_scope,
            "task_title": self.task_title,
            "user_signals": list(self.user_signals),
            "decisions_results": list(self.decisions_results),
            "reusable_methods": list(self.reusable_methods),
            "next_steps": list(self.next_steps),
            "file_locators": list(self.file_locators),
        }


@dataclass(frozen=True)
class CapsuleCounts:
    input_record_count: int
    allowlisted_count: int
    selected_count: int
    dropped_class_count: int
    dropped_safety_count: int
    scrubbed_secret_count: int
    truncated_count: int
    omitted_count: int


@dataclass(frozen=True)
class CapsuleResult:
    capsule: TaskCapsule = field(repr=False)
    source_fingerprint: str
    source_hash_schema_version: str
    capsule_hash: str
    capsule_schema_version: str
    source_schema_versions: tuple[str, ...]
    estimated_tokens: int
    counts: CapsuleCounts


def estimate_capsule_tokens(capsule: TaskCapsule) -> int:
    """Return a conservative deterministic local bound, not provider usage."""

    if not isinstance(capsule, TaskCapsule):
        raise _contract_error()
    byte_count = len(_canonical_json(capsule.to_mapping()))
    return max(1, (byte_count + 2) // 3)


def capsule_has_durable_signal(capsule: TaskCapsule) -> bool:
    if not isinstance(capsule, TaskCapsule):
        raise _contract_error()
    return any(
        (
            capsule.user_signals,
            capsule.decisions_results,
            capsule.reusable_methods,
            capsule.next_steps,
        )
    )


def _empty_capsule(ref: RevisionRef, policy: CapsulePolicy) -> TaskCapsule:
    return TaskCapsule(
        schema_version=CAPTURE_SCHEMA_VERSION,
        adapter_id=ref.key.adapter_id,
        adapter_version=ref.adapter_version,
        source_schema_version=ref.source_schema_version,
        source_root_id=ref.key.source_root_id,
        task_id=ref.key.task_id,
        revision_id=ref.key.revision_id,
        rollout_anchor_id=ref.rollout_anchor_id,
        identity_quality=ref.identity_quality,
        completed_at=ref.completed_at,
        project_scope=policy.project_scope,
        _sensitive_labels=policy.sensitive_labels,
    )


def _append(capsule: TaskCapsule, kind: str, text: str) -> TaskCapsule:
    if kind == "task_title":
        return replace(capsule, task_title=text)
    if kind == "user_signal":
        return replace(capsule, user_signals=(*capsule.user_signals, text))
    if kind == "decision_result":
        return replace(capsule, decisions_results=(*capsule.decisions_results, text))
    if kind == "reusable_method":
        return replace(capsule, reusable_methods=(*capsule.reusable_methods, text))
    if kind == "next_step":
        return replace(capsule, next_steps=(*capsule.next_steps, text))
    if kind == "file_locator":
        if text in capsule.file_locators:
            return capsule
        return replace(capsule, file_locators=(*capsule.file_locators, text))
    raise _contract_error()


def _safe_prefix(text: str, length: int) -> str:
    prefix = text[:length].rstrip()
    while prefix and (
        unicodedata.combining(prefix[-1])
        or 0xD800 <= ord(prefix[-1]) <= 0xDBFF
    ):
        prefix = prefix[:-1]
    return prefix.rstrip(" ")


def _fit_text(
    capsule: TaskCapsule,
    kind: str,
    text: str,
    token_limit: int,
) -> str | None:
    low = 0
    high = len(text)
    best = ""
    while low <= high:
        middle = (low + high) // 2
        candidate_text = _safe_prefix(text, middle)
        candidate = _append(capsule, kind, candidate_text) if candidate_text else capsule
        if candidate_text and estimate_capsule_tokens(candidate) <= token_limit:
            best = candidate_text
            low = middle + 1
        else:
            high = middle - 1
    return best or None


def _validate_inputs(ref: RevisionRef, policy: CapsulePolicy) -> tuple[RevisionRef, CapsulePolicy]:
    if not isinstance(ref, RevisionRef) or not isinstance(policy, CapsulePolicy):
        raise _contract_error()
    try:
        validated_ref = RevisionRef.from_mapping(ref.to_mapping())
    except (TypeError, ValueError, UnicodeError) as error:
        raise _contract_error() from error
    return validated_ref, policy


def build_capsule(
    records: Iterable[Mapping[str, Any]],
    ref: RevisionRef,
    policy: CapsulePolicy,
) -> CapsuleResult:
    """Build one privacy-cleaned Task Capsule without a raw-record side channel."""

    ref, policy = _validate_inputs(ref, policy)
    from agc_runtime.capture_safety import pre_capsule_gate

    try:
        gated = pre_capsule_gate(records, ref, policy)
    except (TypeError, ValueError, UnicodeError) as error:
        raise _contract_error() from error

    fingerprint_payload = {
        "hash_schema_version": SOURCE_HASH_SCHEMA_VERSION,
        "source_schema_versions": [ref.source_schema_version],
        "records": [record.hash_mapping() for record in gated.records],
    }
    source_fingerprint = _sha256(fingerprint_payload)

    capsule = _empty_capsule(ref, policy)
    if estimate_capsule_tokens(capsule) > policy.hard_token_limit:
        raise _contract_error()
    ordered = sorted(
        gated.records,
        key=lambda item: (item.priority, item.source_index, item.kind, item.text),
    )
    selected_count = 0
    truncated_count = 0
    omitted_count = 0
    for record in ordered:
        candidate = _append(capsule, record.kind, record.text)
        if candidate == capsule:
            omitted_count += 1
            continue
        if estimate_capsule_tokens(candidate) <= policy.target_token_limit:
            capsule = candidate
            selected_count += 1
            continue
        if record.kind == "file_locator":
            omitted_count += 1
            continue
        fitted = _fit_text(capsule, record.kind, record.text, policy.target_token_limit)
        if fitted is None or len(fitted) < min(16, len(record.text)):
            omitted_count += 1
            continue
        capsule = _append(capsule, record.kind, fitted)
        selected_count += 1
        truncated_count += int(fitted != record.text)

    estimated_tokens = estimate_capsule_tokens(capsule)
    if estimated_tokens > policy.hard_token_limit:
        raise _contract_error()
    capsule_hash = _sha256(
        {
            "capsule_schema_version": CAPSULE_SCHEMA_VERSION,
            "capsule": capsule.to_mapping(),
        }
    )
    return CapsuleResult(
        capsule,
        source_fingerprint,
        SOURCE_HASH_SCHEMA_VERSION,
        capsule_hash,
        CAPSULE_SCHEMA_VERSION,
        (ref.source_schema_version,),
        estimated_tokens,
        CapsuleCounts(
            gated.input_record_count,
            gated.allowlisted_count,
            selected_count,
            gated.dropped_class_count,
            gated.dropped_safety_count,
            gated.scrubbed_secret_count,
            truncated_count,
            omitted_count,
        ),
    )


__all__ = [
    "CAPSULE_POLICY_SCHEMA_VERSION",
    "CAPSULE_SCHEMA_VERSION",
    "SOURCE_HASH_SCHEMA_VERSION",
    "CapsuleCounts",
    "CapsulePolicy",
    "CapsuleResult",
    "TaskCapsule",
    "build_capsule",
    "capsule_has_durable_signal",
    "estimate_capsule_tokens",
]
