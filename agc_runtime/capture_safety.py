"""Deterministic in-memory safety gates for semantic Capture."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from agc_runtime.capture_capsule import CapsulePolicy, TaskCapsule
    from agc_runtime.capture_contracts import RevisionRef


_ALLOWED_DRAFT_FIELDS = frozenset(
    {
        "statement",
        "assertion",
        "primary_category",
        "kind",
        "scopes",
        "project_scope",
        "confidence",
        "sensitivity",
        "signal_type",
        "evidence",
        "priority",
        "locator",
    }
)
_ASSERTION_MODES = frozenset({"direct", "behavior_observed", "agent_inferred"})
_CATEGORIES = frozenset({"personal_growth", "research", "learning", "project", "work"})
_KINDS = frozenset(
    {"identity", "principle", "preference", "interest", "capability", "goal", "pattern", "context"}
)
_CONFIDENCE = frozenset({"tentative", "observed", "confirmed", "disputed"})
_SIGNAL_TYPES = frozenset(
    {
        "explicit_user_state",
        "decision_or_constraint",
        "verified_outcome",
        "reusable_method",
        "learning_change",
        "research_change",
        "capability_evidence",
        "open_commitment",
    }
)
_SCOPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_LOCATOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/~-]{0,255}$")
_WINDOWS_PATH = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|\\\\)[^\s\"'<>|]+")
_UNIX_PRIVATE_PATH = re.compile(
    r"(?<![:/A-Za-z0-9.])/(?:[A-Za-z0-9._~-]+/)+[A-Za-z0-9._~-]+"
)
_RELATIVE_FILE = re.compile(
    r"(?<![A-Za-z0-9_./-])((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,12})"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?-----END [^-\r\n]*PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)
_BEARER = re.compile(r"(?i)\b(?:authorization\s*:\s*)?bearer\s+[A-Za-z0-9._~+/-]{6,}")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:[a-z0-9]+[_-])*(?:password|passwd|pwd|api[_-]?key|access[_-]?token|"
    r"auth[_-]?token|refresh[_-]?token|client[_-]?secret|secret[_-]?access[_-]?key|"
    r"secret|credential|token)\b\s*[:=]\s*"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\r\n,;]+)"
)
_AUTH_COOKIE = re.compile(
    r"(?i)\b(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*:\s*[^\r\n]+"
)
_CONNECTION = re.compile(
    r"(?i)\b(?:https?|ssh|ftp|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|mssql)://"
    r"[^\s/:@]+:[^\s@]+@[^\s]+"
)
_KNOWN_TOKEN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,}|"
    r"AKIA[A-Z0-9]{12,}|AIza[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\b")
_FENCED = re.compile(r"```.*?```", re.DOTALL)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HYPOTHETICAL = re.compile(
    r"(?i)(?:^|[.!?。！？]\s*)(?:if|suppose|assuming|what if)\b|"
    r"(?:\bmight\b|\bwould\b|\bcould perhaps\b)|(?:如果|假如|假设|可能会)"
)
_PSYCHOLOGICAL = re.compile(
    r"(?i)\b(?:personality|psychological|diagnosis|neurotic|fragile|lazy|anxious|depressed)\b|"
    r"(?:人格|心理诊断|焦虑症|抑郁症|懒惰)"
)
_COMMAND = re.compile(
    r"(?i)^\s*(?:run|execute|invoke|type|enter|install)\s+"
    r"(?:pytest|python|pip|npm|git|cargo|mvn|gradle|\./|[A-Za-z]:\\)"
)
_THIRD_PARTY = re.compile(
    r"(?i)^\s*(?:a|an|the)\s+(?:library|framework|company|team|article|paper|author|third[- ]party)\b"
)
_PROJECT_FACT = re.compile(
    r"(?i)^\s*(?:the\s+)?(?:parser|module|class|function|service|endpoint|database|repository|file|test|build)\b"
)
_MULTI_CLAIM = re.compile(
    r";|\n|(?i:\b(?:and|but)\s+(?:the\s+user|user|they|he|she|i)\b)|(?:并且|而且).*(?:用户|他|她)"
)
_WORD = re.compile(r"[A-Za-z0-9_]{3,}|[\u3400-\u9fff]{2,}")
_STOP_WORDS = frozenset(
    {
        "the", "user", "and", "for", "with", "that", "this", "from", "has", "have",
        "prefer", "prefers", "may",
    }
)


def _safe_error() -> ValueError:
    return ValueError("capture_safety_contract_invalid")


def _normalize_text(value: str) -> str:
    try:
        text = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    except (AttributeError, TypeError, UnicodeError) as error:
        raise _safe_error() from error
    text = _CONTROL.sub("", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    compact: list[str] = []
    for line in lines:
        if line or (compact and compact[-1]):
            compact.append(line)
    return "\n".join(compact).strip()


def _sensitive_label_pattern(labels: tuple[str, ...]) -> re.Pattern[str] | None:
    if not labels:
        return None
    return re.compile(
        r"(?im)\b(?:" + "|".join(re.escape(label) for label in labels) + r")\b\s*[:=]\s*[^\r\n]+"
    )


def _scrub_known_secrets(text: str, labels: tuple[str, ...]) -> tuple[str, int]:
    count = 0

    def replace(pattern: re.Pattern[str], value: str) -> str:
        nonlocal count
        value, replacements = pattern.subn("[REDACTED]", value)
        count += replacements
        return value

    cleaned = text
    for pattern in (
        _PRIVATE_KEY,
        _AUTH_COOKIE,
        _BEARER,
        _CONNECTION,
        _SECRET_ASSIGNMENT,
        _KNOWN_TOKEN,
        _JWT,
    ):
        cleaned = replace(pattern, cleaned)
    label_pattern = _sensitive_label_pattern(labels)
    if label_pattern is not None:
        cleaned = replace(label_pattern, cleaned)
    return cleaned, count


def _strip_prohibited_content(text: str) -> tuple[str, bool]:
    if (
        re.search(r"(?m)^\s*(?:diff --git|@@ |\*\*\* (?:Begin|End) Patch)", text)
        or "Traceback (most recent call last):" in text
    ):
        return "", True
    changed = False
    text, fenced_count = _FENCED.subn(" ", text)
    changed = bool(fenced_count)
    text, windows_count = _WINDOWS_PATH.subn("[PATH]", text)
    text, unix_count = _UNIX_PRIVATE_PATH.subn("[PATH]", text)
    changed = changed or bool(windows_count or unix_count)
    kept: list[str] = []
    code_lines = 0
    for line in text.split("\n"):
        stripped = line.strip()
        prohibited = (
            stripped.startswith(("diff --git", "@@ ", "+++ ", "--- ", "Traceback (", "> "))
            or re.match(r"^(?:File \".*\", line \d+|[A-Za-z]+Error:|\$ |PS [^>]*>)", stripped)
            is not None
            or (len(stripped) > 2000)
            or (stripped.startswith(("{", "[")) and len(stripped) > 400)
        )
        looks_code = (
            stripped.startswith(("def ", "class ", "import ", "from ", "function ", "const ", "let "))
            or stripped.count("{") + stripped.count("}") >= 3
        )
        if prohibited or looks_code:
            changed = True
            code_lines += 1
            continue
        kept.append(line)
    if code_lines and not any(line.strip() for line in kept):
        return "", True
    return _normalize_text("\n".join(kept)), changed


def _extract_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return None
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            item_type = item.get("type")
            if item_type in {None, "text", "input_text", "output_text"}:
                candidate = item.get("text", item.get("content"))
                if isinstance(candidate, str):
                    parts.append(candidate)
    return "\n".join(parts) if parts else None


def _record_message(record: Mapping[str, Any]) -> tuple[str, str, bool] | None:
    record_type = record.get("type")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return None
    role: Any = payload.get("role", record.get("role"))
    content: Any = payload.get("content", payload.get("message", payload.get("text")))
    explicit_final = payload.get("phase") == "final" or payload.get("is_final") is True
    if record_type == "response_item":
        if payload.get("type") not in {None, "message", "input_text", "output_text"}:
            return None
    elif record_type == "event_msg":
        event_type = payload.get("type")
        if event_type == "user_message":
            role = "user"
        elif event_type in {"agent_message", "assistant_message"}:
            role = "assistant"
        else:
            return None
    elif record_type == "user_message":
        role = "user"
    elif record_type == "assistant_message":
        role = "assistant"
    else:
        return None
    if role not in {"user", "assistant"}:
        return None
    text = _extract_text(content)
    if text is None:
        return None
    return role, text, explicit_final


def _record_matches_turn(record: Mapping[str, Any], revision_id: str) -> bool:
    candidates: list[Any] = []
    if "turn_id" in record:
        candidates.append(record.get("turn_id"))
    payload = record.get("payload")
    if isinstance(payload, dict):
        if "turn_id" in payload:
            candidates.append(payload.get("turn_id"))
        turn = payload.get("turn")
        if isinstance(turn, dict) and "id" in turn:
            candidates.append(turn.get("id"))
    return not candidates or all(candidate == revision_id for candidate in candidates)


def _units(text: str, maximum: int) -> tuple[str, ...]:
    raw_units = re.split(r"\n+|(?<=[.!?。！？])\s+", text)
    units: list[str] = []
    for raw in raw_units:
        normalized = _normalize_text(raw)
        if not normalized:
            continue
        while len(normalized) > maximum:
            boundary = normalized.rfind(" ", 0, maximum + 1)
            if boundary < maximum // 2:
                boundary = maximum
            piece = normalized[:boundary].rstrip()
            while piece and unicodedata.combining(piece[-1]):
                piece = piece[:-1]
            if piece:
                units.append(piece)
            normalized = normalized[boundary:].lstrip()
        if normalized:
            units.append(normalized)
    return tuple(units)


def _relative_locators(text: str) -> tuple[str, ...]:
    locators: list[str] = []
    for match in _RELATIVE_FILE.finditer(text):
        value = match.group(1).strip(".,:;!?()[]{}")
        parts = value.split("/")
        if value.startswith(("/", "./")) or ".." in parts or len(parts) > 12:
            continue
        if value not in locators:
            locators.append(value)
    return tuple(locators)


def _assistant_kind(text: str) -> tuple[str, int]:
    lowered = text.casefold()
    if re.search(r"\b(?:next step|next|remaining|todo|follow[- ]?up)\b|(?:下一步|后续|待办)", lowered):
        return "next_step", 3
    if re.search(r"\b(?:method|approach|workflow|procedure|steps?|reuse|reusable)\b|(?:方法|流程|步骤|复用)", lowered):
        return "reusable_method", 2
    if re.search(
        r"\b(?:decision|decided|result|completed|implemented|passed|must|never|constraint|require)\b|"
        r"(?:决定|结果|完成|通过|必须|不得|约束|要求)",
        lowered,
    ):
        return "decision_result", 1
    return "decision_result", 1


@dataclass(frozen=True)
class SafeCapsuleRecord:
    kind: str
    source_index: int
    priority: int
    text: str = field(repr=False)
    locator: str | None = field(default=None, repr=False)

    def hash_mapping(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "priority": self.priority,
            "text": self.text,
            "locator": self.locator,
        }


@dataclass(frozen=True)
class PreCapsuleResult:
    records: tuple[SafeCapsuleRecord, ...] = field(repr=False)
    input_record_count: int
    dropped_class_count: int
    dropped_safety_count: int
    scrubbed_secret_count: int

    @property
    def allowlisted_count(self) -> int:
        return len(self.records)


def pre_capsule_gate(
    records: Iterable[Mapping[str, Any]],
    ref: "RevisionRef",
    policy: "CapsulePolicy",
) -> PreCapsuleResult:
    """Return only scrubbed, allowlisted, target-turn in-memory signals."""

    if isinstance(records, (str, bytes, bytearray)):
        raise _safe_error()
    try:
        materialized = tuple(records)
    except (TypeError, ValueError) as error:
        raise _safe_error() from error
    for record in materialized:
        if not isinstance(record, Mapping) or any(not isinstance(key, str) for key in record):
            raise _safe_error()

    message_candidates: list[tuple[int, str, str, bool]] = []
    title_candidates: list[tuple[int, str]] = []
    dropped_class = 0
    dropped_safety = 0
    scrubbed_count = 0
    for index, record in enumerate(materialized):
        if not _record_matches_turn(record, ref.key.revision_id):
            dropped_class += 1
            continue
        payload = record.get("payload")
        if record.get("type") == "session_meta" and isinstance(payload, dict):
            title = payload.get("title", payload.get("task_title"))
            if isinstance(title, str) and title.strip():
                title_candidates.append((index, title))
            continue
        message = _record_message(record)
        if message is None:
            dropped_class += 1
            continue
        role, text, explicit_final = message
        message_candidates.append((index, role, text, explicit_final))

    explicit_assistant = [item for item in message_candidates if item[1] == "assistant" and item[3]]
    assistant_pool = explicit_assistant or [item for item in message_candidates if item[1] == "assistant"]
    final_assistant_index = assistant_pool[-1][0] if assistant_pool else None
    safe_records: list[SafeCapsuleRecord] = []

    for index, title in title_candidates[:1]:
        normalized = _normalize_text(title)
        scrubbed, secret_count = _scrub_known_secrets(normalized, policy.sensitive_labels)
        scrubbed_count += secret_count
        scrubbed, changed = _strip_prohibited_content(scrubbed)
        if scrubbed:
            safe_records.append(
                SafeCapsuleRecord("task_title", index, 5, scrubbed[: policy.max_title_codepoints])
            )
        else:
            dropped_safety += 1 if normalized or changed else 0

    for index, role, text, _explicit_final in message_candidates:
        if role == "assistant" and index != final_assistant_index:
            dropped_class += 1
            continue
        normalized = _normalize_text(text)
        scrubbed, secret_count = _scrub_known_secrets(normalized, policy.sensitive_labels)
        scrubbed_count += secret_count
        cleaned, changed = _strip_prohibited_content(scrubbed)
        if not cleaned:
            dropped_safety += 1
            continue
        units = _units(cleaned, policy.max_signal_codepoints)
        if not units:
            dropped_safety += 1
            continue
        for offset, unit in enumerate(units):
            source_index = index * 1000 + offset
            if role == "user":
                durable = re.search(
                    r"(?i)\b(?:prefer|goal|must|never|always|constraint|long[- ]term)\b|"
                    r"(?:偏好|目标|必须|不得|始终|长期|约束)",
                    unit,
                )
                safe_records.append(
                    SafeCapsuleRecord("user_signal", source_index, 0 if durable else 1, unit)
                )
            else:
                kind, priority = _assistant_kind(unit)
                safe_records.append(SafeCapsuleRecord(kind, source_index, priority, unit))
            for locator_offset, locator in enumerate(_relative_locators(unit)):
                safe_records.append(
                    SafeCapsuleRecord(
                        "file_locator",
                        source_index * 100 + locator_offset,
                        4,
                        locator,
                        locator=locator,
                    )
                )
        if changed and not units:
            dropped_safety += 1

    safe_records.sort(key=lambda item: (item.source_index, item.kind, item.text))
    return PreCapsuleResult(
        tuple(safe_records),
        len(materialized),
        dropped_class,
        dropped_safety,
        scrubbed_count,
    )


@dataclass(frozen=True)
class ObservationDraft:
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

    @classmethod
    def from_mapping(cls, value: Any) -> "ObservationDraft":
        try:
            if not isinstance(value, Mapping) or set(value) != _ALLOWED_DRAFT_FIELDS:
                raise _safe_error()
            assertion = value["assertion"]
            if not isinstance(assertion, Mapping) or set(assertion) != {"subject", "mode", "modality"}:
                raise _safe_error()
            statement = _normalize_text(value["statement"])
            subject = _normalize_text(assertion["subject"])
            mode = assertion["mode"]
            modality = assertion["modality"]
            category = value["primary_category"]
            kind = value["kind"]
            confidence = value["confidence"]
            sensitivity = value["sensitivity"]
            signal_type = value["signal_type"]
            project_scope = value["project_scope"]
            priority = value["priority"]
            locator = value["locator"]
            scopes_value = value["scopes"]
            evidence_value = value["evidence"]
            if (
                not statement
                or len(statement) > 300
                or subject != "user"
                or mode not in _ASSERTION_MODES
                or modality != "asserted"
                or category not in _CATEGORIES
                or kind not in _KINDS
                or confidence not in _CONFIDENCE
                or not isinstance(sensitivity, str)
                or signal_type not in _SIGNAL_TYPES
                or type(priority) is not int
                or priority not in {1, 2, 3, 4}
                or not isinstance(locator, str)
                or _LOCATOR.fullmatch(locator) is None
            ):
                raise _safe_error()
            if mode == "agent_inferred" and confidence != "tentative":
                raise _safe_error()
            if project_scope is not None and (
                not isinstance(project_scope, str) or _SCOPE.fullmatch(project_scope) is None
            ):
                raise _safe_error()
            if not isinstance(scopes_value, list) or not 1 <= len(scopes_value) <= 8:
                raise _safe_error()
            scopes = tuple(_normalize_text(item) for item in scopes_value)
            if any(_SCOPE.fullmatch(item) is None for item in scopes) or len(set(scopes)) != len(scopes):
                raise _safe_error()
            if not isinstance(evidence_value, list) or not 1 <= len(evidence_value) <= 8:
                raise _safe_error()
            evidence = tuple(_normalize_text(item) for item in evidence_value)
            if any(not item or len(item) > 600 for item in evidence):
                raise _safe_error()
            return cls(
                statement,
                subject,
                mode,
                modality,
                category,
                kind,
                scopes,
                project_scope,
                confidence,
                sensitivity,
                signal_type,
                evidence,
                priority,
                locator,
            )
        except (AttributeError, KeyError, TypeError, UnicodeError, ValueError) as error:
            raise _safe_error() from error


@dataclass(frozen=True)
class PersistenceResult:
    accepted: tuple[ObservationDraft, ...] = field(repr=False)
    filtered_safety_count: int
    filtered_policy_count: int
    duplicate_count: int
    over_limit_count: int


def _capsule_units(capsule: "TaskCapsule") -> tuple[str, ...]:
    values: list[str] = []
    if capsule.task_title:
        values.append(capsule.task_title)
    values.extend(capsule.user_signals)
    values.extend(capsule.decisions_results)
    values.extend(capsule.reusable_methods)
    values.extend(capsule.next_steps)
    values.extend(capsule.file_locators)
    return tuple(values)


def _substantive_words(text: str) -> set[str]:
    return {
        token.casefold()
        for token in _WORD.findall(text)
        if token.casefold() not in _STOP_WORDS
    }


def _draft_is_unsafe(draft: ObservationDraft) -> bool:
    if draft.sensitivity not in {"normal", "personal"}:
        return True
    combined = "\n".join((draft.statement, *draft.evidence))
    scrubbed, count = _scrub_known_secrets(combined, ())
    if count or scrubbed != combined:
        return True
    if _PSYCHOLOGICAL.search(draft.statement):
        return True
    stripped, changed = _strip_prohibited_content(combined)
    return changed or not stripped


def _is_atomic(statement: str) -> bool:
    if _MULTI_CLAIM.search(statement):
        return False
    terminal = re.findall(r"[.!?。！？]", statement.rstrip(".!?。！？"))
    return not terminal


def _is_personally_relevant(draft: ObservationDraft) -> bool:
    if draft.kind in {"identity", "principle", "preference", "interest", "capability", "goal", "pattern"}:
        return True
    if draft.signal_type in {
        "explicit_user_state",
        "decision_or_constraint",
        "reusable_method",
        "learning_change",
        "research_change",
        "capability_evidence",
        "open_commitment",
    }:
        return True
    return draft.primary_category != "project" and draft.kind != "context"


def _draft_is_policy_valid(
    draft: ObservationDraft,
    capsule: "TaskCapsule",
    evidence_units: frozenset[str],
) -> bool:
    if draft.project_scope != capsule.project_scope:
        return False
    if draft.statement.endswith(("?", "？")) or _HYPOTHETICAL.search(draft.statement):
        return False
    if not _is_atomic(draft.statement):
        return False
    if _COMMAND.search(draft.statement) or _THIRD_PARTY.search(draft.statement):
        return False
    if _PROJECT_FACT.search(draft.statement):
        return False
    if not _is_personally_relevant(draft):
        return False
    if any(evidence not in evidence_units for evidence in draft.evidence):
        return False
    evidence_words = _substantive_words(" ".join(draft.evidence))
    statement_words = _substantive_words(draft.statement)
    if statement_words and (
        len(statement_words.intersection(evidence_words)) / len(statement_words) < 0.75
    ):
        return False
    return True


def _canonical_proposition(statement: str) -> str:
    normalized = _normalize_text(statement).casefold().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.rstrip(".!?。！？")


def _rank(draft: ObservationDraft) -> tuple[int, int, int, int, str]:
    mode_rank = {"direct": 0, "behavior_observed": 1, "agent_inferred": 3}[draft.assertion_mode]
    signal_rank = {
        "explicit_user_state": 0,
        "decision_or_constraint": 1,
        "verified_outcome": 1,
        "reusable_method": 1,
        "learning_change": 2,
        "research_change": 2,
        "capability_evidence": 2,
        "open_commitment": 2,
    }[draft.signal_type]
    return (mode_rank, signal_rank, -len(draft.evidence), draft.priority, draft.locator)


def persistence_gate(
    drafts: Iterable[Mapping[str, Any] | ObservationDraft],
    capsule: "TaskCapsule",
) -> PersistenceResult:
    """Validate, rank, deduplicate, and bound in-memory extractor drafts."""

    if isinstance(drafts, (str, bytes, bytearray)):
        return PersistenceResult((), 0, 1, 0, 0)
    try:
        materialized = tuple(drafts)
    except (TypeError, ValueError):
        return PersistenceResult((), 0, 1, 0, 0)
    evidence_units = frozenset(_capsule_units(capsule))
    safety_count = 0
    policy_count = 0
    valid: list[ObservationDraft] = []
    for value in materialized:
        try:
            draft = value if isinstance(value, ObservationDraft) else ObservationDraft.from_mapping(value)
        except (AttributeError, TypeError, ValueError):
            policy_count += 1
            continue
        if _draft_is_unsafe(draft):
            safety_count += 1
            continue
        if not _draft_is_policy_valid(draft, capsule, evidence_units):
            policy_count += 1
            continue
        valid.append(draft)

    groups: dict[str, list[ObservationDraft]] = {}
    for draft in valid:
        groups.setdefault(_canonical_proposition(draft.statement), []).append(draft)
    duplicate_count = sum(len(group) - 1 for group in groups.values())
    deduplicated = [min(group, key=_rank) for group in groups.values()]
    deduplicated.sort(key=_rank)
    accepted = tuple(deduplicated[:8])
    return PersistenceResult(
        accepted,
        safety_count,
        policy_count,
        duplicate_count,
        max(0, len(deduplicated) - 8),
    )


__all__ = [
    "ObservationDraft",
    "PersistenceResult",
    "PreCapsuleResult",
    "SafeCapsuleRecord",
    "persistence_gate",
    "pre_capsule_gate",
]
