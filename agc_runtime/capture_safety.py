"""Deterministic in-memory safety gates for semantic Capture."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, TYPE_CHECKING

from agc_runtime.capture_capsule import _canonical_sensitive_text

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
_SCOPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_PROJECT_SCOPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_LOCATOR = re.compile(
    r"^(?:user|final|result|method|next):[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$"
)
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
_PARTIAL_PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?(?:-----END [^-\r\n]*PRIVATE KEY-----|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_BEARER = re.compile(r"(?i)\b(?:authorization\s*:\s*)?bearer\s+[A-Za-z0-9._~+/-]{6,}")
_SECRET_KEY = (
    r"(?:[a-z0-9]+[_-])*(?:password|passwd|pwd|api[_-]?key|access[_-]?token|"
    r"auth[_-]?token|refresh[_-]?token|client[_-]?secret|secret[_-]?access[_-]?key|"
    r"secret|credential|token)"
)
_YAML_SECRET_BLOCK = re.compile(
    r"(?im)^(?P<indent>[ \t]*)[\"']?" + _SECRET_KEY + r"[\"']?\s*:\s*[|>][^\r\n]*"
    r"(?:\r?\n(?P=indent)[ \t]+[^\r\n]*)+"
)
_XML_SECRET = re.compile(
    r"(?is)<\s*(?:" + _SECRET_KEY + r")\b[^>]*>.*?</\s*(?:" + _SECRET_KEY + r")\s*>"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)[\"']?" + _SECRET_KEY + r"[\"']?\s*[:=]\s*"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\r\n,;]+)"
)
_AUTH_COOKIE = re.compile(
    r"(?i)\b(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*:\s*[^\r\n]+"
)
_CONNECTION = re.compile(
    r"(?i)\b[A-Za-z][A-Za-z0-9+.-]{0,31}://"
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
    r"(?:\bmay\b|\bmight\b|\bwould\b|\bcould\b|\bperhaps\b)|(?:如果|假如|假设|可能会)"
)
_PSYCHOLOGICAL = re.compile(
    r"(?i)\b(?:personality|psychological|diagnosis|neurotic|fragile|lazy|anxious|depressed|"
    r"impulsive|introverted|extroverted|narcissistic)\b|"
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
    r"[,/:;\n，：；、\u2013\u2014]|(?i:\b(?:and|also|plus|but)\b)|(?:以及|并且|而且|和)"
)
_LOG_LINE = re.compile(
    r"(?i)^\s*(?:\d{4}-\d{2}-\d{2}[T ][0-9:.+Z-]+\s+)?"
    r"(?:TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL)\b"
)
_ASSIGNMENT_LINE = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_.-]*\s*(?::=|=)\s*.+$")
_SERIALIZED_LINE = re.compile(
    r"^\s*(?:\{.*[\"'][^\r\n]+[\"']\s*:.*\}|\[.*\]|[\"']?[^:\r\n]{1,64}[\"']?\s*:\s*.+)\s*$"
)
_METHOD_CALL_LINE = re.compile(
    r"^\s*[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\s*\([^\r\n]*\)\s*;?\s*$"
)
_CODE_CALL = re.compile(
    r"(?i)\b(?:await\s+)?[A-Za-z_][A-Za-z0-9_]*"
    r"(?:(?:\.[A-Za-z_][A-Za-z0-9_]*)|(?:\[[^\]\r\n]{1,120}\]))*\s*\([^()\r\n]*\)"
)
_INLINE_ASSIGNMENT = re.compile(
    r"(?m)(?:^|[;:\s])(?:[A-Za-z_][A-Za-z0-9_]*"
    r"(?:(?:\.[A-Za-z_][A-Za-z0-9_]*)|(?:\[[^\]\r\n]{1,120}\]))*)\s*"
    r"(?::=|=(?!=))\s*\S"
)
_JSON_MAPPING_PAYLOAD = re.compile(
    r"(?:\{[^{}\r\n]{0,400}:[^{}\r\n]{0,400}\}|[\"'][^\"'\r\n]{1,120}[\"']\s*:)"
)
_ARRAY_PAYLOAD = re.compile(r"\[[^\[\]\r\n]{0,400}(?:,|:|[\"'])[^\[\]\r\n]{0,400}\]")
_STRUCTURAL_CHARACTER = re.compile(r"[{}\[\]`~@=\\|<>]")
_CODE_KEYWORD = re.compile(
    r"(?i)\b(?:lambda|await|async|import|from|def|class|yield|return|exec|eval)\b"
)
_QUOTED_ASSERTION = re.compile(
    r"(?i)(?:^\s*>|\baccording\s+to\b|"
    r"\b(?:said|says|reported?|reports?|claimed|claims|quoted?)\b|"
    r"[\"“”].*\b(?:i|user)\b)"
)
_NEGATION = re.compile(
    r"(?i)\b(?:no|not|never|cannot|can't|don't|doesn't|didn't|isn't|aren't|wasn't|"
    r"weren't|won't|wouldn't|couldn't|shouldn't|do not|does not|did not|must not)\b|"
    r"(?:不|没有|从不|不得)"
)
_DOWN_TONER = re.compile(r"(?i)\b(?:hardly|hardly ever|rarely|seldom|scarcely|barely)\b|(?:很少|几乎不)")
_WORD = re.compile(r"[A-Za-z0-9_]{3,}|[\u3400-\u9fff]{2,}")
_STOP_WORDS = frozenset(
    {
        "the", "user", "and", "for", "with", "that", "this", "from", "has", "have",
        "prefer", "prefers", "may",
    }
)

def _safe_error() -> ValueError:
    return ValueError("capture_safety_contract_invalid")


def _looks_like_path(value: str) -> bool:
    lowered = value.casefold()
    return (
        lowered.startswith("file:")
        or value.startswith(("/", "\\", "../", "..\\", "./", ".\\"))
        or re.match(r"^[A-Za-z]:[\\/]", value) is not None
        or "/../" in value
        or "\\..\\" in value
    )


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


def _scrub_known_secrets(text: str, labels: tuple[str, ...]) -> tuple[str, int]:
    canonical_text = _canonical_sensitive_text(text)
    if labels and any(label in canonical_text for label in labels):
        return "[REDACTED]", 1
    count = 0

    def replace(pattern: re.Pattern[str], value: str) -> str:
        nonlocal count
        value, replacements = pattern.subn("[REDACTED]", value)
        count += replacements
        return value

    cleaned = text
    for pattern in (
        _PARTIAL_PRIVATE_KEY,
        _PRIVATE_KEY,
        _YAML_SECRET_BLOCK,
        _XML_SECRET,
        _AUTH_COOKIE,
        _BEARER,
        _CONNECTION,
        _SECRET_ASSIGNMENT,
        _KNOWN_TOKEN,
        _JWT,
    ):
        cleaned = replace(pattern, cleaned)
    return cleaned, count


def _contains_sensitive_label(text: str, labels: tuple[str, ...]) -> bool:
    if not labels:
        return False
    canonical_text = _canonical_sensitive_text(text)
    return any(label in canonical_text for label in labels)


_PLAIN_PUNCTUATION = frozenset(".,!?:;/'\"()-_，。！？：；、–—")


def _is_plain_language_unit(text: str) -> bool:
    if (
        not text
        or _STRUCTURAL_CHARACTER.search(text)
        or _CODE_KEYWORD.search(text)
        or _CODE_CALL.search(text)
        or _INLINE_ASSIGNMENT.search(text)
    ):
        return False
    return all(
        character.isspace()
        or unicodedata.category(character)[0] in {"L", "M", "N"}
        or character in _PLAIN_PUNCTUATION
        for character in text
    )


def _strip_prohibited_content(text: str) -> tuple[str, bool]:
    if (
        re.search(r"(?m)^\s*(?:diff --git|@@ |\*\*\* (?:Begin|End) Patch)", text)
        or "Traceback (most recent call last):" in text
        or "```" in text
        or "~~~" in text
        or _JSON_MAPPING_PAYLOAD.search(text)
        or _ARRAY_PAYLOAD.search(text)
        or _CODE_CALL.search(text)
        or _INLINE_ASSIGNMENT.search(text)
        or not _is_plain_language_unit(text)
    ):
        return "", True
    source_lines = text.split("\n")
    log_lines = sum(1 for line in source_lines if _LOG_LINE.search(line))
    serialized_lines = sum(1 for line in source_lines if _SERIALIZED_LINE.search(line))
    assignment_lines = sum(1 for line in source_lines if _ASSIGNMENT_LINE.search(line))
    method_call_lines = sum(1 for line in source_lines if _METHOD_CALL_LINE.search(line))
    if (
        log_lines
        or serialized_lines >= 3
        or assignment_lines >= 3
        or method_call_lines >= 3
        or len(re.findall(r"\{[^{}\r\n]{1,400}:[^{}\r\n]{1,400}\}", text)) >= 3
    ):
        return "", True
    if len(source_lines) >= 8:
        unsafe_lines = sum(
            1
            for line in source_lines
            if _LOG_LINE.search(line)
            or _ASSIGNMENT_LINE.search(line)
            or line.strip().startswith(
                ("def ", "class ", "import ", "from ", "function ", "const ", "let ")
            )
        )
        if unsafe_lines >= max(4, len(source_lines) // 3):
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
        if not isinstance(item, Mapping) or item.get("type") not in {
            "text",
            "input_text",
            "output_text",
        }:
            return None
        candidate = item.get("text")
        if not isinstance(candidate, str):
            return None
        parts.append(candidate)
    return "\n".join(parts) if parts else None


def _is_subagent_tag(value: Any) -> bool:
    if isinstance(value, str):
        return "subagent" in value.casefold()
    if isinstance(value, Mapping):
        return any(_is_subagent_tag(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_is_subagent_tag(item) for item in value)
    return False


def _has_subagent_provenance(record: Mapping[str, Any]) -> bool:
    payload = record.get("payload")
    containers = (record, payload) if isinstance(payload, Mapping) else (record,)
    for container in containers:
        for field_name in ("provenance", "source", "thread_source", "origin", "agent_type"):
            if field_name in container and _is_subagent_tag(container[field_name]):
                return True
    return False


def _record_message(record: Mapping[str, Any]) -> tuple[str, str, bool] | None:
    if _has_subagent_provenance(record):
        return None
    record_type = record.get("type")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return None
    role: Any = payload.get("role", record.get("role"))
    content: Any = payload.get("content", payload.get("message", payload.get("text")))
    explicit_final = payload.get("phase") == "final" or payload.get("is_final") is True
    if record_type == "response_item":
        if payload.get("type") != "message":
            return None
    elif record_type == "event_msg":
        event_type = payload.get("type")
        if event_type == "user_message":
            role = "user"
        elif event_type in {"agent_message", "assistant_message"}:
            role = "assistant"
        else:
            return None
    else:
        return None
    if role not in {"user", "assistant"}:
        return None
    if role == "assistant" and not explicit_final:
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
    return bool(candidates) and all(candidate == revision_id for candidate in candidates)


_USER_DECLARATIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "preference",
        re.compile(
            r"(?i)^(?:(?:i|we)\s+(?:(?:do\s+not|don't|never|hardly(?:\s+ever)?|rarely|seldom)\s+)?prefer\b|"
            r"(?:my|our)\s+(?:preference|priority)\s+(?:is|remains)\b)"
        ),
    ),
    (
        "avoidance",
        re.compile(r"(?i)^(?:i|we)\s+(?:(?:hardly(?:\s+ever)?|rarely|seldom)\s+)?avoid\b"),
    ),
    (
        "goal",
        re.compile(
            r"(?i)^(?:(?:i|we)\s+(?:aim|plan|intend|want)\s+to\b|"
            r"(?:my|our)\s+(?:long[- ]term\s+)?goal\s+(?:is|remains)\b)"
        ),
    ),
    (
        "constraint",
        re.compile(
            r"(?i)^(?:(?:i|we)\s+(?:must(?:\s+not)?|cannot|can't|need\s+to|require)\b|"
            r"(?:my|our)\s+constraint\s+(?:is|requires)\b)"
        ),
    ),
    (
        "ability",
        re.compile(
            r"(?i)^(?:(?:i\s+(?:can\s+reliably|am\s+able\s+to)|"
            r"we\s+(?:can\s+reliably|are\s+able\s+to))\b|"
            r"(?:my|our)\s+ability\s+(?:is|allows)\b)"
        ),
    ),
    (
        "method",
        re.compile(
            r"(?i)^(?:i|we)\s+(?:use|follow|reuse)\b.{0,160}\b"
            r"(?:method|workflow|process|practice|approach)\b"
        ),
    ),
    (
        "trajectory",
        re.compile(
            r"(?i)^(?:(?:i|we)\s+(?:learned\s+to|have\s+learned\s+to|"
            r"am\s+learning\s+to|are\s+learning\s+to|acquired\b.{0,80}\bskill)\b|"
            r"(?:my|our)\s+(?:long[- ]term\s+)?(?:research\s+direction|trajectory|"
            r"learning\s+direction)\b)"
        ),
    ),
    (
        "principle",
        re.compile(r"(?i)^(?:my|our)\s+principle\s+(?:is|remains)\b"),
    ),
    (
        "identity",
        re.compile(r"(?i)^(?:i|we)\s+identify\s+as\b|^(?:my|our)\s+background\s+is\b"),
    ),
)

_STATEMENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "preference",
        re.compile(
            r"(?i)^the\s+user\s+(?:(?:does\s+not|never|hardly(?:\s+ever)?|rarely|seldom)\s+)?prefers\b|"
            r"^the\s+user's\s+(?:preference|priority)\s+(?:is|remains)\b"
        ),
    ),
    ("avoidance", re.compile(r"(?i)^the\s+user\s+(?:(?:hardly(?:\s+ever)?|rarely|seldom)\s+)?avoids\b")),
    (
        "goal",
        re.compile(
            r"(?i)^the\s+user\s+(?:aims|plans|intends|wants)\s+to\b|"
            r"^the\s+user's\s+(?:long[- ]term\s+)?goal\s+(?:is|remains)\b"
        ),
    ),
    (
        "constraint",
        re.compile(
            r"(?i)^the\s+user\s+(?:must(?:\s+not)?|cannot|can't|needs\s+to|requires)\b|"
            r"^the\s+user's\s+constraint\s+(?:is|requires)\b"
        ),
    ),
    (
        "ability",
        re.compile(
            r"(?i)^the\s+user\s+(?:can\s+reliably|is\s+able\s+to|"
            r"demonstrated\s+ability\s+to)\b|^the\s+user's\s+ability\s+(?:is|allows)\b"
        ),
    ),
    (
        "method",
        re.compile(
            r"(?i)^the\s+user\s+(?:uses|follows|reuses)\b.{0,160}\b"
            r"(?:method|workflow|process|practice|approach)\b"
        ),
    ),
    (
        "trajectory",
        re.compile(
            r"(?i)^the\s+user\s+(?:learned\s+to|has\s+learned\s+to|"
            r"is\s+learning\s+to|acquired\b.{0,80}\bskill)\b|"
            r"^the\s+user's\s+(?:long[- ]term\s+)?(?:research\s+direction|trajectory|"
            r"learning\s+direction)\b"
        ),
    ),
    ("principle", re.compile(r"(?i)^the\s+user's\s+principle\s+(?:is|remains)\b")),
    (
        "identity",
        re.compile(
            r"(?i)^the\s+user\s+identifies\s+as\b|^the\s+user's\s+background\s+is\b"
        ),
    ),
)

_YOU_STATEMENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("preference", re.compile(r"(?i)^you\s+(?:(?:do\s+not|never|hardly(?:\s+ever)?|rarely|seldom)\s+)?prefer\b")),
    ("avoidance", re.compile(r"(?i)^you\s+(?:(?:hardly(?:\s+ever)?|rarely|seldom)\s+)?avoid\b")),
    ("goal", re.compile(r"(?i)^you\s+(?:aim|plan|intend|want)\s+to\b")),
    ("constraint", re.compile(r"(?i)^you\s+(?:must(?:\s+not)?|cannot|can't|need\s+to|require)\b")),
    ("ability", re.compile(r"(?i)^you\s+(?:can\s+reliably|are\s+able\s+to|demonstrated\s+ability\s+to)\b")),
    (
        "method",
        re.compile(
            r"(?i)^you\s+(?:use|follow|reuse)\b.{0,160}\b"
            r"(?:method|workflow|process|practice|approach)\b"
        ),
    ),
    (
        "trajectory",
        re.compile(
            r"(?i)^you\s+(?:learned\s+to|have\s+learned\s+to|are\s+learning\s+to|"
            r"acquired\b.{0,80}\bskill)\b"
        ),
    ),
    ("identity", re.compile(r"(?i)^you\s+identify\s+as\b")),
)

_ASSISTANT_PREFIX = re.compile(
    r"(?i)^\s*(?P<prefix>decision|result|constraint|method|next(?:\s+step)?)\s*:\s*(?P<body>\S.*)$"
)


def _one_plain_clause(text: str, *, subject_pattern: re.Pattern[str]) -> str | None:
    normalized = _normalize_text(text)
    if not _is_plain_language_unit(normalized) or _MULTI_CLAIM.search(normalized):
        return None
    stripped = normalized.rstrip()
    if stripped.endswith((".", "。")):
        stripped = stripped[:-1].rstrip()
    if not stripped or re.search(r"[.!?。！？]", stripped):
        return None
    subject = subject_pattern.match(stripped)
    if subject is None:
        return None
    remainder = stripped[subject.end() :]
    if subject_pattern is _USER_EVIDENCE_SUBJECT:
        repeated = re.compile(r"(?i)\b(?:i|my|we|our)\b")
    else:
        repeated = re.compile(r"(?i)\b(?:the\s+user|user's|user’s|i|my|we|our)\b")
    if repeated.search(remainder):
        return None
    return stripped


_USER_EVIDENCE_SUBJECT = re.compile(r"(?i)^(?:i|my|we|our)\b\s*")
_PERSISTED_USER_SUBJECT = re.compile(r"(?i)^(?:the\s+user|the\s+user's|the\s+user’s)\b\s*")
_ASSISTANT_USER_SUBJECT = re.compile(r"(?i)^(?:you|the\s+user|the\s+user's|the\s+user’s)\b\s*")


def _class_from_patterns(
    text: str,
    patterns: tuple[tuple[str, re.Pattern[str]], ...],
    *,
    subject_pattern: re.Pattern[str],
) -> str | None:
    clause = _one_plain_clause(text, subject_pattern=subject_pattern)
    if clause is None:
        return None
    matches = [predicate_class for predicate_class, pattern in patterns if pattern.search(clause)]
    return matches[0] if len(matches) == 1 else None


def _user_declarative_predicate_class(text: str) -> str | None:
    return _class_from_patterns(
        text,
        _USER_DECLARATIVE_PATTERNS,
        subject_pattern=_USER_EVIDENCE_SUBJECT,
    )


def _statement_predicate_class(text: str) -> str | None:
    return _class_from_patterns(
        text,
        _STATEMENT_PATTERNS,
        subject_pattern=_PERSISTED_USER_SUBJECT,
    )


def _assistant_user_predicate_class(text: str) -> str | None:
    prefixed = _ASSISTANT_PREFIX.fullmatch(_normalize_text(text))
    if prefixed is None:
        return None
    body = prefixed.group("body")
    if re.match(r"(?i)^you\b", body):
        patterns = _YOU_STATEMENT_PATTERNS
    elif re.match(r"(?i)^the\s+user(?:'s|’s)?\b", body):
        patterns = _STATEMENT_PATTERNS
    else:
        return None
    return _class_from_patterns(
        body,
        patterns,
        subject_pattern=_ASSISTANT_USER_SUBJECT,
    )


def _polarity_class(text: str) -> str:
    if _DOWN_TONER.search(text):
        return "down_toned"
    if _NEGATION.search(text):
        return "negative"
    return "positive"


def _user_has_high_signal(text: str) -> bool:
    return (
        _user_declarative_predicate_class(text) is not None
        and not _HYPOTHETICAL.search(text)
        and not _QUOTED_ASSERTION.search(text)
    )


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


def _assistant_kind(text: str) -> tuple[str, int] | None:
    prefixed = _ASSISTANT_PREFIX.fullmatch(text)
    if prefixed is None or not _is_plain_language_unit(prefixed.group("body")):
        return None
    prefix = re.sub(r"\s+", " ", prefixed.group("prefix").casefold())
    if prefix.startswith("next"):
        return "next_step", 3
    if prefix == "method":
        return "reusable_method", 2
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
        payload = record.get("payload")
        if record.get("type") == "session_meta" and isinstance(payload, dict):
            title = payload.get("title", payload.get("task_title"))
            if (
                payload.get("session_id") == ref.key.task_id
                and payload.get("id") == ref.rollout_anchor_id
                and isinstance(title, str)
                and title.strip()
            ):
                title_candidates.append((index, title))
            continue
        if not _record_matches_turn(record, ref.key.revision_id):
            dropped_class += 1
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
                if not _user_has_high_signal(unit):
                    dropped_class += 1
                    continue
                safe_records.append(
                    SafeCapsuleRecord("user_signal", source_index, 0, unit)
                )
            else:
                classified = _assistant_kind(unit)
                if classified is None:
                    dropped_class += 1
                    continue
                kind, priority = classified
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
                not isinstance(project_scope, str)
                or _PROJECT_SCOPE.fullmatch(project_scope) is None
                or _looks_like_path(project_scope)
            ):
                raise _safe_error()
            if not isinstance(scopes_value, list) or not 1 <= len(scopes_value) <= 8:
                raise _safe_error()
            scopes = tuple(_normalize_text(item) for item in scopes_value)
            if (
                any(_SCOPE.fullmatch(item) is None or _looks_like_path(item) for item in scopes)
                or len(set(scopes)) != len(scopes)
            ):
                raise _safe_error()
            if not isinstance(evidence_value, list) or not 1 <= len(evidence_value) <= 8:
                raise _safe_error()
            evidence = tuple(dict.fromkeys(_normalize_text(item) for item in evidence_value))
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


def _capsule_evidence(capsule: "TaskCapsule") -> dict[str, frozenset[str]]:
    provenance: dict[str, set[str]] = {}
    for kind, values in (
        ("user_signal", capsule.user_signals),
        ("decision_result", capsule.decisions_results),
        ("reusable_method", capsule.reusable_methods),
        ("next_step", capsule.next_steps),
    ):
        for value in values:
            provenance.setdefault(value, set()).add(kind)
    return {value: frozenset(kinds) for value, kinds in provenance.items()}


def _substantive_words(text: str) -> set[str]:
    return {
        token.casefold()
        for token in _WORD.findall(text)
        if token.casefold() not in _STOP_WORDS
    }


def _draft_is_unsafe(draft: ObservationDraft, capsule: "TaskCapsule") -> bool:
    if draft.sensitivity not in {"normal", "personal"}:
        return True
    combined = "\n".join((draft.statement, *draft.evidence))
    if _contains_sensitive_label(combined, capsule._sensitive_labels):
        return True
    scrubbed, count = _scrub_known_secrets(combined, ())
    if count or scrubbed != combined:
        return True
    if _PSYCHOLOGICAL.search(draft.statement):
        return True
    stripped, changed = _strip_prohibited_content(combined)
    return changed or not stripped


def _is_atomic(statement: str) -> bool:
    return _statement_predicate_class(statement) is not None


def _is_personally_relevant(draft: ObservationDraft) -> bool:
    return (
        _statement_predicate_class(draft.statement) is not None
        and _PSYCHOLOGICAL.search(draft.statement) is None
    )


def _evidence_form_is_assertive(evidence: str) -> bool:
    return not (
        evidence.endswith(("?", "？"))
        or _HYPOTHETICAL.search(evidence)
        or _QUOTED_ASSERTION.search(evidence)
    )


def _provenance_supports_mode(
    draft: ObservationDraft,
    evidence_provenance: dict[str, frozenset[str]],
    predicate_class: str,
) -> bool:
    if draft.assertion_mode == "direct":
        allowed = frozenset({"user_signal"})
    elif draft.assertion_mode == "behavior_observed":
        allowed = frozenset({"decision_result", "reusable_method"})
    else:
        allowed = frozenset({"user_signal", "decision_result", "reusable_method"})
    for evidence in draft.evidence:
        provenance = evidence_provenance[evidence]
        user_supported = (
            "user_signal" in provenance
            and "user_signal" in allowed
            and _user_declarative_predicate_class(evidence) == predicate_class
        )
        assistant_provenance = provenance.intersection(
            {"decision_result", "reusable_method", "next_step"}
        )
        assistant_supported = bool(assistant_provenance.intersection(allowed))
        assistant_supported = (
            assistant_supported
            and _assistant_user_predicate_class(evidence) == predicate_class
        )
        if assistant_provenance and predicate_class in {
            "preference",
            "avoidance",
            "goal",
            "principle",
            "identity",
        }:
            assistant_supported = False
        if "reusable_method" in assistant_provenance and predicate_class != "method":
            assistant_supported = False
        if "decision_result" in assistant_provenance and predicate_class not in {
            "constraint",
            "ability",
            "trajectory",
        }:
            assistant_supported = False
        if not user_supported and not assistant_supported:
            return False
    return True


def _draft_is_policy_valid(
    draft: ObservationDraft,
    capsule: "TaskCapsule",
    evidence_provenance: dict[str, frozenset[str]],
) -> bool:
    if draft.project_scope != capsule.project_scope:
        return False
    if (
        draft.statement.endswith(("?", "？"))
        or _HYPOTHETICAL.search(draft.statement)
    ):
        return False
    if not _is_atomic(draft.statement):
        return False
    if _COMMAND.search(draft.statement) or _THIRD_PARTY.search(draft.statement):
        return False
    if _PROJECT_FACT.search(draft.statement):
        return False
    if not _is_personally_relevant(draft):
        return False
    if any(evidence not in evidence_provenance for evidence in draft.evidence):
        return False
    if not all(_evidence_form_is_assertive(evidence) for evidence in draft.evidence):
        return False
    predicate_class = _statement_predicate_class(draft.statement)
    if predicate_class is None:
        return False
    if not _provenance_supports_mode(draft, evidence_provenance, predicate_class):
        return False
    statement_polarity = _polarity_class(draft.statement)
    if any(_polarity_class(evidence) != statement_polarity for evidence in draft.evidence):
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
    semantic_tier = (
        3
        if draft.assertion_mode == "agent_inferred"
        else {
            "explicit_user_state": 0,
            "decision_or_constraint": 0,
            "verified_outcome": 1,
            "reusable_method": 1,
            "learning_change": 2,
            "research_change": 2,
            "capability_evidence": 1,
            "open_commitment": 2,
        }[draft.signal_type]
    )
    return (semantic_tier, -len(draft.evidence), draft.priority, mode_rank, draft.locator)


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
    evidence_provenance = _capsule_evidence(capsule)
    safety_count = 0
    policy_count = 0
    valid: list[ObservationDraft] = []
    for value in materialized:
        try:
            mapping = value.to_mapping() if isinstance(value, ObservationDraft) else value
            draft = ObservationDraft.from_mapping(mapping)
        except (AttributeError, TypeError, ValueError):
            policy_count += 1
            continue
        if _draft_is_unsafe(draft, capsule):
            safety_count += 1
            continue
        if not _draft_is_policy_valid(draft, capsule, evidence_provenance):
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
