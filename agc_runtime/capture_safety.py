"""Deterministic in-memory safety gates for semantic Capture."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, TYPE_CHECKING

from agc_runtime.capture_capsule import (
    _confusable_skeleton,
    _contains_mixed_script_atom,
    _security_skeleton,
    _sensitive_candidates,
)

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
    r"\b(?:sk-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9_]{10,}|github_pat_[A-Za-z0-9_]{10,}|"
    r"AKIA[A-Z0-9]{12,}|AIza[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b",
    re.IGNORECASE,
)
_JWT = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\b",
    re.IGNORECASE,
)
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
    r"[,/:;\n，：；、\u2013\u2014]|"
    r"(?i:\b(?:and|or|also|plus|but|while|whereas|although)\b)|(?:以及|并且|而且|或者|和)"
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
_STRUCTURAL_CHARACTER = re.compile(r"[(){}\[\]`~@=\\|<>]")
_CODE_KEYWORD = re.compile(
    r"(?i)\b(?:lambda|await|import|from|def|class|yield|return|exec|eval)\b"
)
_PLAIN_COMMAND_SHAPE = re.compile(
    r"(?i)\bpython(?:3(?:\.\d+)?)?\s+[A-Za-z0-9_./-]+\.py\b"
)
_QUOTED_ASSERTION = re.compile(
    r"(?i)(?:^\s*>|\baccording\s+to\b|"
    r"\b(?:said|says|reported?|reports?|claimed|claims|quoted?)\b|"
    r"[\"“”].*\b(?:i|user)\b)"
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
    security_view = _confusable_skeleton(text)
    label_views = _sensitive_candidates(text)
    pattern_views = tuple(
        dict.fromkeys((security_view, _security_skeleton(text), *label_views))
    )
    patterns = (
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
    )
    if (
        labels and any(label in view for label in labels for view in label_views)
    ) or any(
        pattern.search(view) is not None
        for pattern in patterns
        for view in pattern_views
    ):
        return "[REDACTED]", 1
    count = 0

    def replace(pattern: re.Pattern[str], value: str) -> str:
        nonlocal count
        value, replacements = pattern.subn("[REDACTED]", value)
        count += replacements
        return value

    cleaned = text
    for pattern in patterns:
        cleaned = replace(pattern, cleaned)
    return cleaned, count


def _contains_sensitive_label(text: str, labels: tuple[str, ...]) -> bool:
    if not labels:
        return False
    return any(
        label in view
        for label in labels
        for view in _sensitive_candidates(text)
    )


_PLAIN_PUNCTUATION = frozenset(".,!?:;/'\"()-_，。！？：；、–—")


def _is_plain_language_unit(text: str) -> bool:
    if (
        not text
        or _STRUCTURAL_CHARACTER.search(text)
        or _CODE_KEYWORD.search(text)
        or _PLAIN_COMMAND_SHAPE.search(text)
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


def _strip_prohibited_content(
    text: str,
    *,
    enforce_assistant_allowlist: bool = True,
) -> tuple[str, bool]:
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
        or (
            enforce_assistant_allowlist
            and not _assistant_prefixed_text_is_safe(text)
        )
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


_ASSISTANT_PREFIX = re.compile(
    r"(?i)^\s*(?P<prefix>decision|result|constraint|method|next(?:\s+step)?)\s*:\s*(?P<body>\S.*)$"
)
_SIMPLE_ASSISTANT_RESULT = re.compile(
    r"(?i)^(?:tests? pass(?:ed)?|verification (?:passes|passed)|"
    r"build (?:passes|passed)|the safe hash is stable)$"
)


def _assistant_body_is_safe(prefix: str, body: str) -> bool:
    canonical_prefix = _security_skeleton(prefix)
    if canonical_prefix.startswith("next"):
        canonical_prefix = "next"
    complete = f"{prefix}: {body}"
    if _assistant_user_proposition(complete) is not None:
        return True
    result_body = _normalize_text(body).rstrip(".!?。！？").strip()
    if canonical_prefix == "result":
        return _SIMPLE_ASSISTANT_RESULT.fullmatch(_security_skeleton(result_body)) is not None
    allowed_actions = _ASSISTANT_PREFIX_ACTIONS.get(canonical_prefix)
    if allowed_actions is None:
        return False
    tokens = result_body.split(" ")
    return _action_phrase_skeleton(
        tokens,
        allowed_actions=allowed_actions,
        allow_in_phrase=canonical_prefix == "constraint",
    ) is not None


def _assistant_prefixed_text_is_safe(text: str) -> bool:
    for raw_unit in re.split(r"\n+|(?<=[.!?。！？])\s+", text):
        unit = _normalize_text(raw_unit)
        if not unit:
            continue
        prefixed = _ASSISTANT_PREFIX.fullmatch(unit)
        if prefixed is not None and not _assistant_body_is_safe(
            prefixed.group("prefix"), prefixed.group("body")
        ):
            return False
    return True


def _one_plain_clause(text: str, *, subject_pattern: re.Pattern[str]) -> str | None:
    normalized = _normalize_text(text)
    if (
        not _is_plain_language_unit(normalized)
        or _MULTI_CLAIM.search(normalized)
    ):
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

_PatternSpec = tuple[str, str, re.Pattern[str]]
_Proposition = tuple[str, str, str]

_USER_PROPOSITION_PATTERNS: tuple[_PatternSpec, ...] = (
    ("preference", "negative", re.compile(r"(?i)^(?:i|we)\s+(?:do\s+not|don't)\s+prefer\s+(?P<object>.+)$")),
    ("preference", "negative", re.compile(r"(?i)^(?:i|we)\s+never\s+prefer\s+(?P<object>.+)$")),
    ("preference", "down_toned", re.compile(r"(?i)^(?:i|we)\s+(?:hardly(?:\s+ever)?|rarely|seldom)\s+prefer\s+(?P<object>.+)$")),
    ("preference", "positive", re.compile(r"(?i)^(?:i|we)\s+prefer\s+(?P<object>.+)$")),
    ("preference", "positive", re.compile(r"(?i)^(?:my|our)\s+(?:preference|priority)\s+(?:is|remains)\s+(?P<object>.+)$")),
    ("avoidance", "down_toned", re.compile(r"(?i)^(?:i|we)\s+(?:hardly(?:\s+ever)?|rarely|seldom)\s+avoid\s+(?P<object>.+)$")),
    ("avoidance", "positive", re.compile(r"(?i)^(?:i|we)\s+avoid\s+(?P<object>.+)$")),
    ("goal", "positive", re.compile(r"(?i)^(?:i|we)\s+(?:aim|plan|intend|want)\s+to\s+(?P<object>.+)$")),
    ("goal", "positive", re.compile(r"(?i)^(?:my|our)\s+(?:long[- ]term\s+)?goal\s+(?:is|remains)\s+to\s+(?P<object>.+)$")),
    ("constraint", "negative", re.compile(r"(?i)^(?:i|we)\s+(?:must\s+not|cannot|can't)\s+(?P<object>.+)$")),
    ("constraint", "positive", re.compile(r"(?i)^(?:i|we)\s+(?:must|need\s+to|require)\s+(?P<object>.+)$")),
    ("ability", "positive", re.compile(r"(?i)^(?:i\s+(?:can\s+reliably|am\s+able\s+to)|we\s+(?:can\s+reliably|are\s+able\s+to))\s+(?P<object>.+)$")),
    ("method", "positive", re.compile(r"(?i)^(?:i|we)\s+(?:use|follow|reuse)\s+(?P<object>.+)$")),
    ("trajectory", "positive", re.compile(r"(?i)^(?:i|we)\s+(?:learned\s+to|have\s+learned\s+to|am\s+learning\s+to|are\s+learning\s+to)\s+(?P<object>.+)$")),
    ("trajectory", "positive", re.compile(r"(?i)^(?:my|our)\s+(?:long[- ]term\s+)?(?:research\s+direction|trajectory|learning\s+direction)(?:\s+now)?\s+prioritizes\s+(?P<object>.+)$")),
    ("principle", "positive", re.compile(r"(?i)^(?:my|our)\s+principle\s+(?:is|remains)\s+(?P<object>.+)$")),
    ("identity", "positive", re.compile(r"(?i)^(?:i|we)\s+identify\s+as\s+(?P<object>.+)$")),
    ("identity", "positive", re.compile(r"(?i)^(?:my|our)\s+background\s+is\s+(?P<object>.+)$")),
)

_STATEMENT_PROPOSITION_PATTERNS: tuple[_PatternSpec, ...] = (
    ("preference", "negative", re.compile(r"(?i)^the\s+user\s+does\s+not\s+prefer\s+(?P<object>.+)$")),
    ("preference", "negative", re.compile(r"(?i)^the\s+user\s+never\s+prefers\s+(?P<object>.+)$")),
    ("preference", "down_toned", re.compile(r"(?i)^the\s+user\s+(?:hardly(?:\s+ever)?|rarely|seldom)\s+prefers\s+(?P<object>.+)$")),
    ("preference", "positive", re.compile(r"(?i)^the\s+user\s+prefers\s+(?P<object>.+)$")),
    ("preference", "positive", re.compile(r"(?i)^the\s+user's\s+(?:preference|priority)\s+(?:is|remains)\s+(?P<object>.+)$")),
    ("avoidance", "down_toned", re.compile(r"(?i)^the\s+user\s+(?:hardly(?:\s+ever)?|rarely|seldom)\s+avoids\s+(?P<object>.+)$")),
    ("avoidance", "positive", re.compile(r"(?i)^the\s+user\s+avoids\s+(?P<object>.+)$")),
    ("goal", "positive", re.compile(r"(?i)^the\s+user\s+(?:aims|plans|intends|wants)\s+to\s+(?P<object>.+)$")),
    ("goal", "positive", re.compile(r"(?i)^the\s+user's\s+(?:long[- ]term\s+)?goal\s+(?:is|remains)\s+to\s+(?P<object>.+)$")),
    ("constraint", "negative", re.compile(r"(?i)^the\s+user\s+(?:must\s+not|cannot|can't)\s+(?P<object>.+)$")),
    ("constraint", "positive", re.compile(r"(?i)^the\s+user\s+(?:must|needs\s+to|requires)\s+(?P<object>.+)$")),
    ("ability", "positive", re.compile(r"(?i)^the\s+user\s+(?:can\s+reliably|is\s+able\s+to|demonstrated\s+ability\s+to)\s+(?P<object>.+)$")),
    ("method", "positive", re.compile(r"(?i)^the\s+user\s+(?:uses|follows|reuses)\s+(?P<object>.+)$")),
    ("trajectory", "positive", re.compile(r"(?i)^the\s+user\s+(?:learned\s+to|has\s+learned\s+to|is\s+learning\s+to)\s+(?P<object>.+)$")),
    ("trajectory", "positive", re.compile(r"(?i)^the\s+user's\s+(?:long[- ]term\s+)?(?:research\s+direction|trajectory|learning\s+direction)(?:\s+now)?\s+prioritizes\s+(?P<object>.+)$")),
    ("principle", "positive", re.compile(r"(?i)^the\s+user's\s+principle\s+(?:is|remains)\s+(?P<object>.+)$")),
    ("identity", "positive", re.compile(r"(?i)^the\s+user\s+identifies\s+as\s+(?P<object>.+)$")),
    ("identity", "positive", re.compile(r"(?i)^the\s+user's\s+background\s+is\s+(?P<object>.+)$")),
)

_YOU_PROPOSITION_PATTERNS: tuple[_PatternSpec, ...] = (
    ("preference", "negative", re.compile(r"(?i)^you\s+(?:do\s+not|don't|never)\s+prefer\s+(?P<object>.+)$")),
    ("preference", "down_toned", re.compile(r"(?i)^you\s+(?:hardly(?:\s+ever)?|rarely|seldom)\s+prefer\s+(?P<object>.+)$")),
    ("preference", "positive", re.compile(r"(?i)^you\s+prefer\s+(?P<object>.+)$")),
    ("avoidance", "positive", re.compile(r"(?i)^you\s+avoid\s+(?P<object>.+)$")),
    ("goal", "positive", re.compile(r"(?i)^you\s+(?:aim|plan|intend|want)\s+to\s+(?P<object>.+)$")),
    ("constraint", "negative", re.compile(r"(?i)^you\s+(?:must\s+not|cannot|can't)\s+(?P<object>.+)$")),
    ("constraint", "positive", re.compile(r"(?i)^you\s+(?:must|need\s+to|require)\s+(?P<object>.+)$")),
    ("ability", "positive", re.compile(r"(?i)^you\s+(?:can\s+reliably|are\s+able\s+to|demonstrated\s+ability\s+to)\s+(?P<object>.+)$")),
    ("method", "positive", re.compile(r"(?i)^you\s+(?:use|follow|reuse)\s+(?P<object>.+)$")),
    ("trajectory", "positive", re.compile(r"(?i)^you\s+(?:learned\s+to|have\s+learned\s+to|are\s+learning\s+to)\s+(?P<object>.+)$")),
    ("identity", "positive", re.compile(r"(?i)^you\s+identify\s+as\s+(?P<object>.+)$")),
)

_CHINESE_USER_PROPOSITION_PATTERNS: tuple[_PatternSpec, ...] = (
    (
        "constraint",
        "positive",
        re.compile(
            r"^我需要的是(?P<object>[^,，。！？?]+)[,，][^。！？?]+[,，]不是[^。！？?]+[。.]?$"
        ),
    ),
    (
        "constraint",
        "positive",
        re.compile(r"^我需要的是(?P<object>[^,，。！？?]+)[,，]不是[^。！？?]+[。.]?$"),
    ),
    ("constraint", "positive", re.compile(r"^我需要(?P<object>[^。！？?]+)[。.]?$")),
    ("constraint", "positive", re.compile(r"^我必须(?P<object>[^。！？?]+)[。.]?$")),
    ("goal", "positive", re.compile(r"^我希望(?P<object>[^。！？?]+)[。.]?$")),
    ("goal", "positive", re.compile(r"^我的(?:长期)?目标是(?P<object>[^。！？?]+)[。.]?$")),
    ("preference", "positive", re.compile(r"^我(?:偏好|喜欢)(?P<object>[^。！？?]+)[。.]?$")),
    ("preference", "negative", re.compile(r"^我不喜欢(?P<object>[^。！？?]+)[。.]?$")),
    ("avoidance", "positive", re.compile(r"^我避免(?P<object>[^。！？?]+)[。.]?$")),
    ("method", "positive", re.compile(r"^我(?:使用|采用|遵循)(?P<object>[^。！？?]+)[。.]?$")),
    ("principle", "positive", re.compile(r"^我的原则是(?P<object>[^。！？?]+)[。.]?$")),
)

_CHINESE_STATEMENT_PROPOSITION_PATTERNS: tuple[_PatternSpec, ...] = (
    ("constraint", "positive", re.compile(r"^用户需要(?P<object>[^。！？?]+)[。.]?$")),
    ("constraint", "positive", re.compile(r"^用户必须(?P<object>[^。！？?]+)[。.]?$")),
    ("goal", "positive", re.compile(r"^用户希望(?P<object>[^。！？?]+)[。.]?$")),
    ("goal", "positive", re.compile(r"^用户的(?:长期)?目标是(?P<object>[^。！？?]+)[。.]?$")),
    ("preference", "positive", re.compile(r"^用户(?:偏好|喜欢)(?P<object>[^。！？?]+)[。.]?$")),
    ("preference", "negative", re.compile(r"^用户不喜欢(?P<object>[^。！？?]+)[。.]?$")),
    ("avoidance", "positive", re.compile(r"^用户避免(?P<object>[^。！？?]+)[。.]?$")),
    ("method", "positive", re.compile(r"^用户(?:使用|采用|遵循)(?P<object>[^。！？?]+)[。.]?$")),
    ("principle", "positive", re.compile(r"^用户的原则是(?P<object>[^。！？?]+)[。.]?$")),
)

_ACTION_OBJECT_CLASSES = frozenset({"goal", "constraint", "ability"})
_ACTION_VERBS = frozenset(
    {
        "adopt", "apply", "avoid", "choose", "follow", "keep", "learn",
        "perform", "prioritize", "render", "reuse", "review", "run", "store",
        "update", "use", "validate",
    }
)
_DOMAIN_MODIFIERS = frozenset(
    {
        "async", "backend", "brief", "clear", "code", "concise", "data",
        "detailed", "deterministic", "direct", "documented", "error",
        "established", "failing", "frontend", "generated", "plain",
        "practical", "privacy", "product", "project", "release", "remote",
        "research", "review", "rust", "safe", "security", "short",
        "software", "stable", "status", "structured", "team", "test",
        "written",
    }
)
_COMMON_NOUN_HEADS = frozenset(
    {
        "answers", "architect", "communication", "controls", "conventions",
        "coverage", "credentials", "data", "direction", "engineer", "examples",
        "explanations", "feedback", "gate", "hashes", "hooks", "language",
        "manager", "meetings", "memory", "messages", "method", "methods",
        "notes", "output", "package", "packages", "practice", "privacy", "process",
        "replies", "responses", "review", "scientist", "storage", "summaries",
        "tests", "tooling", "verification", "workflow", "workflows", "work",
    }
)
_PREDICATIVE_ADJECTIVES = frozenset(
    {"brief", "concise", "deterministic", "first", "readable", "safe", "secure", "short"}
)
_REJECTED_ATOM_SKELETONS = frozenset(
    {
        "a", "according", "allegedly", "also", "although", "am", "an", "and",
        "are", "as", "based", "be", "because", "been", "being", "believe",
        "believed", "believes", "break", "breaks", "broke", "broken", "but",
        "can", "cannot", "claim", "claimed", "claims", "could", "did", "do",
        "does", "fail", "failed", "fails", "for", "from", "had", "has", "have",
        "if", "in", "intend", "intends", "is", "may", "maybe", "might", "must",
        "need", "needs", "of", "on", "or", "per", "perhaps", "plan", "plans",
        "plus", "possibly", "prefer", "preferred", "prefers", "provided", "quote",
        "quoted", "report", "reported", "reportedly", "reports", "require",
        "requires", "said", "say", "says", "should", "sit", "sits", "the", "to",
        "under", "unless", "view", "views", "want", "wants", "was", "were", "when",
        "whenever", "whereas", "while", "with", "would",
        "after", "he", "her", "him", "it", "lest", "occur", "occurs", "she",
        "that", "them", "these", "they", "this", "those", "until", "whichever",
        "which", "who", "whoever", "whom", "whose", "whether",
        "adopt", "adopts", "adopted", "apply", "applies", "applied", "avoid",
        "avoids", "avoided", "choose", "chooses", "chose", "follow", "follows",
        "followed", "keep", "keeps", "kept", "learn", "learns", "learned",
        "perform", "performs", "performed", "prioritize", "prioritizes", "prioritized",
        "render", "renders", "rendered", "reuse", "reuses", "reused", "reviews",
        "reviewed", "run", "runs", "ran", "store", "stores", "stored",
        "update", "updates", "updated", "use", "uses", "used", "validate",
        "validates", "validated",
    }
)
_ASSISTANT_PREFIX_ACTIONS = {
    "decision": frozenset({"adopt", "choose", "keep", "use"}),
    "method": frozenset({"apply", "follow", "reuse", "use"}),
    "next": frozenset({"apply", "review", "run", "update", "validate"}),
    "constraint": frozenset({"keep", "store", "use"}),
}
def _nominal_token_is_valid(token: str) -> bool:
    compatibility = unicodedata.normalize("NFKC", token)
    return bool(compatibility) and not (
        compatibility.startswith("-")
        or compatibility.endswith("-")
        or "--" in compatibility
        or any(
            character != "-"
            and unicodedata.category(character)[0] not in {"L", "M", "N"}
            for character in compatibility
        )
    )


def _safe_atom_skeleton(token: str) -> str | None:
    if not _nominal_token_is_valid(token):
        return None
    skeleton = _security_skeleton(token)
    if (
        not skeleton
        or " " in skeleton
        or _contains_mixed_script_atom(token)
        or skeleton in _REJECTED_ATOM_SKELETONS
        or skeleton.endswith("ly")
    ):
        return None
    return skeleton


def _modifier_skeleton(token: str) -> str | None:
    skeleton = _safe_atom_skeleton(token)
    if skeleton is None:
        return None
    if "-" in skeleton:
        pieces = skeleton.split("-")
        if not all(piece and _modifier_skeleton(piece) is not None for piece in pieces):
            return None
        return skeleton
    if skeleton in _DOMAIN_MODIFIERS:
        return skeleton
    return None


def _noun_head_skeleton(token: str) -> str | None:
    skeleton = _safe_atom_skeleton(token)
    if skeleton in _COMMON_NOUN_HEADS:
        return skeleton
    return None


def _predicative_adjective_skeleton(token: str) -> str | None:
    skeleton = _safe_atom_skeleton(token)
    if skeleton in _PREDICATIVE_ADJECTIVES:
        return skeleton
    return None


def _nominal_atoms_skeleton(
    tokens: list[str],
    *,
    predicate_class: str | None = None,
) -> tuple[str, ...] | None:
    if len(tokens) not in {1, 2}:
        return None
    if len(tokens) == 1:
        atom = _safe_atom_skeleton(tokens[0])
        return (atom,) if atom is not None else None
    modifier = _modifier_skeleton(tokens[0])
    head = _noun_head_skeleton(tokens[1])
    if modifier is not None and head is not None:
        return modifier, head
    if predicate_class in {"preference", "principle"}:
        nominal = _noun_head_skeleton(tokens[0])
        adjective = _predicative_adjective_skeleton(tokens[1])
        if nominal is not None and adjective is not None:
            return nominal, adjective
    return None


def _action_phrase_skeleton(
    tokens: list[str],
    *,
    allowed_actions: frozenset[str] = _ACTION_VERBS,
    allow_in_phrase: bool = True,
) -> tuple[str, ...] | None:
    skeletons = [_security_skeleton(token) for token in tokens]
    if not skeletons or skeletons[0] not in allowed_actions:
        return None
    if allow_in_phrase and len(tokens) in {4, 5} and skeletons[-2] == "in":
        direct = _nominal_atoms_skeleton(tokens[1:-2])
        location = _nominal_atoms_skeleton(tokens[-1:])
        if direct is None or location is None:
            return None
        return (skeletons[0], *direct, "in", *location)
    if skeletons[0] == "keep" and len(tokens) == 3:
        nominal = _noun_head_skeleton(tokens[1])
        adjective = _predicative_adjective_skeleton(tokens[2])
        if nominal is not None and adjective is not None:
            return skeletons[0], nominal, adjective
    complement = _nominal_atoms_skeleton(tokens[1:])
    return (skeletons[0], *complement) if complement is not None else None


def _simple_nominal_phrase(value: str, predicate_class: str) -> str | None:
    surface = re.sub(r"\s+", " ", value).strip()
    tokens = surface.split(" ") if surface else []
    if not tokens or not all(_nominal_token_is_valid(token) for token in tokens):
        return None
    folded = [_security_skeleton(token) for token in tokens]
    action_object = predicate_class in _ACTION_OBJECT_CLASSES or (
        predicate_class == "trajectory" and folded[0] in _ACTION_VERBS
    )
    if action_object:
        action = _action_phrase_skeleton(tokens)
        return " ".join(action) if action is not None else None
    nominal = _nominal_atoms_skeleton(tokens, predicate_class=predicate_class)
    return " ".join(nominal) if nominal is not None else None


def _class_from_patterns(
    text: str,
    patterns: tuple[_PatternSpec, ...],
    *,
    subject_pattern: re.Pattern[str],
) -> _Proposition | None:
    clause = _one_plain_clause(text, subject_pattern=subject_pattern)
    if clause is None:
        return None
    matches: list[_Proposition] = []
    for predicate_class, polarity, pattern in patterns:
        match = pattern.fullmatch(clause)
        if match is None:
            continue
        normalized_object = _simple_nominal_phrase(match.group("object"), predicate_class)
        if normalized_object is not None:
            matches.append((predicate_class, polarity, normalized_object))
    return matches[0] if len(matches) == 1 else None


def _simple_chinese_object(value: str) -> str | None:
    surface = unicodedata.normalize("NFKC", value)
    surface = re.sub(r"\s+", " ", surface).strip().casefold()
    if (
        not 1 <= len(surface) <= 80
        or _HYPOTHETICAL.search(surface)
        or _QUOTED_ASSERTION.search(surface)
        or _MULTI_CLAIM.search(surface)
        or any(
            not (
                character.isspace()
                or unicodedata.category(character)[0] in {"L", "M", "N"}
                or character in "-_"
            )
            for character in surface
        )
    ):
        return None
    return surface


def _class_from_chinese_patterns(
    text: str,
    patterns: tuple[_PatternSpec, ...],
) -> _Proposition | None:
    clause = _normalize_text(text)
    if (
        not clause
        or clause.endswith(("?", "？"))
        or _HYPOTHETICAL.search(clause)
        or _QUOTED_ASSERTION.search(clause)
    ):
        return None
    matches: list[_Proposition] = []
    for predicate_class, polarity, pattern in patterns:
        match = pattern.fullmatch(clause)
        if match is None:
            continue
        normalized_object = _simple_chinese_object(match.group("object"))
        if normalized_object is not None:
            matches.append((predicate_class, polarity, normalized_object))
    return matches[0] if len(matches) == 1 else None


def _user_proposition(text: str) -> _Proposition | None:
    english = _class_from_patterns(
        text,
        _USER_PROPOSITION_PATTERNS,
        subject_pattern=_USER_EVIDENCE_SUBJECT,
    )
    chinese = _class_from_chinese_patterns(text, _CHINESE_USER_PROPOSITION_PATTERNS)
    return english if chinese is None else chinese if english is None else None


def _statement_proposition(text: str) -> _Proposition | None:
    english = _class_from_patterns(
        text,
        _STATEMENT_PROPOSITION_PATTERNS,
        subject_pattern=_PERSISTED_USER_SUBJECT,
    )
    chinese = _class_from_chinese_patterns(
        text,
        _CHINESE_STATEMENT_PROPOSITION_PATTERNS,
    )
    return english if chinese is None else chinese if english is None else None


def _assistant_user_proposition(text: str) -> _Proposition | None:
    prefixed = _ASSISTANT_PREFIX.fullmatch(_normalize_text(text))
    if prefixed is None:
        return None
    body = prefixed.group("body")
    if re.match(r"(?i)^you\b", body):
        patterns = _YOU_PROPOSITION_PATTERNS
    elif re.match(r"(?i)^the\s+user(?:'s|’s)?\b", body):
        patterns = _STATEMENT_PROPOSITION_PATTERNS
    else:
        return None
    return _class_from_patterns(
        body,
        patterns,
        subject_pattern=_ASSISTANT_USER_SUBJECT,
    )


def _user_declarative_predicate_class(text: str) -> str | None:
    proposition = _user_proposition(text)
    return proposition[0] if proposition is not None else None


def _statement_predicate_class(text: str) -> str | None:
    proposition = _statement_proposition(text)
    return proposition[0] if proposition is not None else None


def _assistant_user_predicate_class(text: str) -> str | None:
    proposition = _assistant_user_proposition(text)
    return proposition[0] if proposition is not None else None


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
    if (
        prefixed is None
        or not _is_plain_language_unit(prefixed.group("body"))
        or not _assistant_body_is_safe(prefixed.group("prefix"), prefixed.group("body"))
    ):
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
    stripped, changed = _strip_prohibited_content(
        combined,
        enforce_assistant_allowlist=False,
    )
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
    proposition: _Proposition,
) -> bool:
    predicate_class = proposition[0]
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
            and _user_proposition(evidence) == proposition
        )
        assistant_provenance = provenance.intersection(
            {"decision_result", "reusable_method", "next_step"}
        )
        assistant_supported = bool(assistant_provenance.intersection(allowed))
        assistant_supported = (
            assistant_supported
            and _assistant_user_proposition(evidence) == proposition
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
    proposition = _statement_proposition(draft.statement)
    if proposition is None:
        return False
    if not _provenance_supports_mode(draft, evidence_provenance, proposition):
        return False
    return True


def _canonicalize_direct_chinese_statement(
    draft: ObservationDraft,
    capsule: "TaskCapsule",
) -> ObservationDraft:
    if draft.assertion_mode != "direct" or len(draft.evidence) != 1:
        return draft
    evidence = draft.evidence[0]
    if evidence not in capsule.user_signals:
        return draft
    source = _class_from_chinese_patterns(
        evidence,
        _CHINESE_USER_PROPOSITION_PATTERNS,
    )
    if source is None:
        return draft
    statement = _class_from_chinese_patterns(
        draft.statement,
        _CHINESE_STATEMENT_PROPOSITION_PATTERNS,
    )
    predicate_prefixes = {
        ("constraint", "positive"): ("用户需要", "用户必须"),
        ("goal", "positive"): ("用户希望", "用户的目标是", "用户的长期目标是"),
        ("preference", "positive"): ("用户偏好", "用户喜欢"),
        ("preference", "negative"): ("用户不喜欢",),
        ("avoidance", "positive"): ("用户避免",),
        ("method", "positive"): ("用户使用", "用户采用", "用户遵循"),
        ("principle", "positive"): ("用户的原则是",),
    }
    normalized_statement = _normalize_text(draft.statement)
    prefix_match = (
        not normalized_statement.endswith(("?", "？"))
        and _HYPOTHETICAL.search(normalized_statement) is None
        and _QUOTED_ASSERTION.search(normalized_statement) is None
        and normalized_statement.startswith(predicate_prefixes.get(source[:2], ()))
    )
    if not prefix_match and (statement is None or source[:2] != statement[:2]):
        return draft
    predicate_class, polarity, object_value = source
    prefixes = {
        ("constraint", "positive"): "用户需要",
        ("goal", "positive"): "用户希望",
        ("preference", "positive"): "用户偏好",
        ("preference", "negative"): "用户不喜欢",
        ("avoidance", "positive"): "用户避免",
        ("method", "positive"): "用户使用",
        ("principle", "positive"): "用户的原则是",
    }
    prefix = prefixes.get((predicate_class, polarity))
    if prefix is None:
        return draft
    return replace(draft, statement=f"{prefix}{object_value}")


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
        draft = _canonicalize_direct_chinese_statement(draft, capsule)
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
