from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest


SOURCE_ROOT_ID = "7" * 64


@pytest.fixture(scope="module", autouse=True)
def _isolate_deferred_capture_modules():
    starting = set(sys.modules)
    yield
    for name in tuple(sys.modules):
        if name not in starting and name in {
            "agc_runtime.capture_capsule",
            "agc_runtime.capture_safety",
            "agc_runtime.capture_source",
            "agc_runtime.codex_source_adapter",
        }:
            sys.modules.pop(name, None)


def _ref(*, locator: str = "sessions/task.jsonl"):
    from agc_runtime.capture_contracts import CaptureKey, RevisionRef

    return RevisionRef(
        key=CaptureKey("codex", SOURCE_ROOT_ID, "task-main", "turn-target"),
        rollout_anchor_id="rollout-main",
        completed_at="2026-08-19T12:00:00Z",
        locator=locator,
        identity_quality="session_id",
        adapter_version="1.0",
        source_schema_version="codex-v1",
    )


def _record(
    role: str,
    content: str,
    *,
    turn_id: str | None = "turn-target",
    final: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "message",
        "role": role,
        "content": content,
    }
    if turn_id is not None:
        payload["turn_id"] = turn_id
    if final:
        payload["phase"] = "final"
    return {"type": "response_item", "payload": payload}


def _draft(
    statement: str,
    evidence: str,
    *,
    locator: str = "user:0001",
    signal_type: str = "explicit_user_state",
    kind: str = "preference",
    category: str = "personal_growth",
    mode: str = "direct",
    sensitivity: str = "normal",
    priority: int = 1,
) -> dict[str, object]:
    return {
        "statement": statement,
        "assertion": {"subject": "user", "mode": mode, "modality": "asserted"},
        "primary_category": category,
        "kind": kind,
        "scopes": ["global"],
        "project_scope": "project:stable",
        "confidence": "confirmed" if mode == "direct" else "tentative",
        "sensitivity": sensitivity,
        "signal_type": signal_type,
        "evidence": [evidence],
        "priority": priority,
        "locator": locator,
    }


def _safe_result():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    evidence = "I prefer deterministic privacy-safe workflows for future collaboration."
    result = build_capsule(
        (
            _record("user", evidence),
            _record(
                "assistant",
                "Decision: keep the workflow deterministic. Next step: reuse the safety gate.",
                final=True,
            ),
        ),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    return result, evidence


def test_capsule_allowlist_isolates_target_turn_and_redacts_repr():
    from dataclasses import FrozenInstanceError, fields

    from agc_runtime.capture_capsule import CapsulePolicy, TaskCapsule, build_capsule

    records = (
        {
            "type": "session_meta",
            "payload": {
                "id": "rollout-main",
                "session_id": "task-main",
                "source": "cli",
                "title": "Safe task title",
            },
        },
        _record("system", "SYSTEM_SENTINEL must never enter the capsule"),
        _record("developer", "DEVELOPER_SENTINEL must never enter the capsule"),
        {
            "type": "response_item",
            "payload": {"type": "reasoning", "content": "REASONING_SENTINEL"},
        },
        _record("user", "I prefer deterministic privacy-safe workflows."),
        _record("user", "OTHER_TURN_SENTINEL", turn_id="turn-other"),
        _record(
            "assistant",
            "Decision: use the bounded gate. Result: tests pass. Method: keep inputs in memory. "
            "Next step: reuse src/safety.py.",
            final=True,
        ),
        {"type": "tool_result", "payload": {"output": "TOOL_SENTINEL"}},
        {"type": "attachment", "payload": {"body": "ATTACHMENT_SENTINEL"}},
        {
            "type": "event_msg",
            "payload": {"type": "task_complete", "turn_id": "turn-target"},
            "timestamp": "2026-08-19T12:00:00Z",
        },
    )
    result = build_capsule(records, _ref(), CapsulePolicy(project_scope="project:stable"))
    capsule = result.capsule
    serialized = repr(capsule.to_mapping())

    assert isinstance(capsule, TaskCapsule)
    assert capsule.task_title == "Safe task title"
    assert capsule.user_signals == ("I prefer deterministic privacy-safe workflows.",)
    assert capsule.decisions_results
    assert capsule.reusable_methods
    assert capsule.next_steps
    assert capsule.file_locators == ("src/safety.py",)
    for sentinel in (
        "SYSTEM_SENTINEL",
        "DEVELOPER_SENTINEL",
        "REASONING_SENTINEL",
        "OTHER_TURN_SENTINEL",
        "TOOL_SENTINEL",
        "ATTACHMENT_SENTINEL",
    ):
        assert sentinel not in serialized
        assert sentinel not in repr(capsule)
        assert sentinel not in repr(result)
    assert all(not field.repr for field in fields(TaskCapsule) if field.name != "schema_version")
    with pytest.raises(FrozenInstanceError):
        capsule.task_title = "changed"  # type: ignore[misc]


def test_pre_capsule_gate_scrubs_known_secret_corpus_before_hashing():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    secrets = (
        "password=Hunter2-SENTINEL",
        "password=two word password-SENTINEL",
        "Authorization: Bearer bearer-secret-SENTINEL",
        "Authorization: Basic basic-secret-SENTINEL",
        "api_key=sk-live-SENTINEL123456789",
        "OPENAI_API_KEY=openai-env-SENTINEL",
        "AWS_SECRET_ACCESS_KEY=aws-env-SENTINEL",
        "token=generic-token-SENTINEL with spaces",
        "Cookie: session=cookie-SENTINEL",
        "postgresql://alice:db-SENTINEL@localhost/private",
        "https://alice:https-SENTINEL@example.invalid/private",
        "eyJhbGciOiJIUzI1NiJ9.eyJzZWNyZXQiOiJqd3QtU0VOVElORUwifQ.signature-SENTINEL",
        "-----BEGIN PRIVATE KEY-----\nprivate-key-SENTINEL\n-----END PRIVATE KEY-----",
        "Sensitive-Note: labelled-SENTINEL",
    )
    result = build_capsule(
        tuple(
            _record("user", f"I prefer safe workflows; {secret}") for secret in secrets
        ),
        _ref(),
        CapsulePolicy(
            project_scope="project:stable",
            sensitive_labels=("Sensitive-Note",),
        ),
    )
    surfaces = (
        repr(result),
        repr(result.capsule),
        repr(result.capsule.to_mapping()),
        result.source_fingerprint,
        result.capsule_hash,
    )
    for secret in secrets:
        for fragment in (secret, "SENTINEL"):
            assert all(fragment not in surface for surface in surfaces)
    assert result.counts.scrubbed_secret_count >= len(secrets)


def test_source_and_capsule_hashes_are_separate_and_archive_move_stable():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    records = (_record("user", "I prefer stable hashes across archive moves."),)
    policy = CapsulePolicy(project_scope="project:stable")
    active = build_capsule(records, _ref(locator="sessions/task.jsonl"), policy)
    archived = build_capsule(
        records,
        _ref(locator="archived_sessions/2026/task.jsonl"),
        policy,
    )

    assert active.source_fingerprint == archived.source_fingerprint
    assert active.capsule_hash == archived.capsule_hash
    assert active.source_fingerprint != active.capsule_hash
    assert active.source_hash_schema_version != active.capsule_schema_version


def test_filtered_record_insertions_do_not_change_privacy_cleaned_hashes():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    allowed = (
        _record("user", "I prefer stable privacy-cleaned source hashes."),
        _record("assistant", "Result: the safe hash is stable.", final=True),
    )
    with_forbidden = (
        {"type": "tool_result", "payload": {"output": "FORBIDDEN_INSERT_A"}},
        allowed[0],
        {"type": "response_item", "payload": {"type": "reasoning", "content": "FORBIDDEN_INSERT_B"}},
        allowed[1],
    )
    policy = CapsulePolicy(project_scope="project:stable")
    baseline = build_capsule(allowed, _ref(), policy)
    filtered = build_capsule(with_forbidden, _ref(), policy)

    assert baseline.source_fingerprint == filtered.source_fingerprint
    assert baseline.capsule_hash == filtered.capsule_hash


def test_estimator_truncates_deterministically_near_target_and_never_exceeds_hard_limit():
    from agc_runtime.capture_capsule import (
        CapsulePolicy,
        build_capsule,
        estimate_capsule_tokens,
    )

    records = tuple(
        _record(
            "user",
            f"I prefer durable constraint {index:03d} " + ("界" * 180),
        )
        for index in range(80)
    )
    policy = CapsulePolicy(
        project_scope="project:stable",
        target_token_limit=1200,
        hard_token_limit=3000,
    )
    first = build_capsule(records, _ref(), policy)
    second = build_capsule(records, _ref(), policy)

    assert first == second
    assert first.estimated_tokens == estimate_capsule_tokens(first.capsule)
    assert first.estimated_tokens <= 1200
    assert first.estimated_tokens <= 3000
    assert first.counts.truncated_count + first.counts.omitted_count > 0
    assert first.capsule_hash == second.capsule_hash


def test_empty_safe_capsule_is_valid_and_errors_are_content_free():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        ({"type": "tool_result", "payload": {"output": "PRIVATE_ERROR_SENTINEL"}},),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert result.capsule.user_signals == ()
    assert result.capsule.decisions_results == ()
    assert result.counts.selected_count == 0

    with pytest.raises(ValueError) as caught:
        build_capsule(
            ("PRIVATE_ERROR_SENTINEL",),  # type: ignore[arg-type]
            _ref(),
            CapsulePolicy(project_scope="project:stable"),
        )
    assert "PRIVATE_ERROR_SENTINEL" not in str(caught.value)
    assert "PRIVATE_ERROR_SENTINEL" not in repr(caught.value)


def test_policy_rejects_private_path_scope_and_invalid_draft_types_content_safely():
    from agc_runtime.capture_capsule import CapsulePolicy
    from agc_runtime.capture_safety import persistence_gate

    with pytest.raises(ValueError, match="capture_capsule_contract_invalid"):
        CapsulePolicy(project_scope="C:/Users/private/repo")

    result, _evidence = _safe_result()
    gated = persistence_gate(
        (
            {
                "statement": {"PRIVATE_TYPE_SENTINEL": "must not escape"},
                "assertion": {"subject": "user", "mode": "direct", "modality": "asserted"},
                "primary_category": "personal_growth",
                "kind": "preference",
                "scopes": ["global"],
                "project_scope": "project:stable",
                "confidence": "confirmed",
                "sensitivity": "normal",
                "signal_type": "explicit_user_state",
                "evidence": ["evidence"],
                "priority": 1,
                "locator": "user:1",
            },
        ),
        result.capsule,
    )
    assert gated.filtered_policy_count == 1
    assert "PRIVATE_TYPE_SENTINEL" not in repr(gated)


@pytest.mark.parametrize(
    "blocked",
    (
        "diff --git a/private.py b/private.py\n@@ -1 +1 @@\n-CODE_SENTINEL\n+DIFF_SENTINEL",
        "Traceback (most recent call last):\n  File \"private.py\", line 1\nLOG_SENTINEL\nRuntimeError: boom",
        "> QUOTED_SOURCE_SENTINEL\n> raw source dump",
    ),
)
def test_pre_capsule_gate_drops_complete_diff_log_and_quote_blocks(blocked: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", blocked),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert "SENTINEL" not in repr(result.capsule.to_mapping())
    assert result.counts.dropped_safety_count == 1


@pytest.mark.parametrize("count", (0, 1, 8, 11))
def test_persistence_gate_returns_stable_zero_to_eight_without_persistent_objects(count: int):
    from agc_runtime.capture_contracts import CollectedObservation
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    evidence_values = tuple(
        f"I prefer deterministic privacy-safe workflow variant {index}."
        for index in range(count)
    )
    result = build_capsule(
        tuple(_record("user", evidence) for evidence in evidence_values),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    drafts = tuple(
        _draft(
            f"The user prefers deterministic privacy-safe workflow variant {index}.",
            evidence_values[index],
            locator=f"user:{index:04d}",
            priority=(index % 4) + 1,
        )
        for index in range(count)
    )
    gated = persistence_gate(drafts, result.capsule)

    assert len(gated.accepted) == min(count, 8)
    assert gated.over_limit_count == max(0, count - 8)
    assert not any(isinstance(item, CollectedObservation) for item in gated.accepted)
    assert "statement=" not in repr(gated)


def test_persistence_gate_rejects_safety_policy_atomicity_and_ungrounded_drafts():
    from agc_runtime.capture_safety import persistence_gate

    result, evidence = _safe_result()
    valid = _draft("The user prefers deterministic privacy-safe workflows.", evidence)
    drafts = (
        valid,
        _draft("The user password is sk-secret-SENTINEL123456789.", evidence),
        _draft("The user has a hidden diagnosis.", evidence, sensitivity="secret"),
        _draft("Does the user prefer deterministic workflows?", evidence),
        _draft("If needed, the user might prefer deterministic workflows.", evidence),
        _draft(
            "The user prefers deterministic workflows; the user also leads a research team.",
            evidence,
        ),
        _draft("A third-party library uses deterministic parsing.", evidence),
        _draft("Run pytest -q once.", evidence, kind="context", category="project"),
        _draft("The parser stores JSON fields.", evidence, kind="context", category="project"),
        _draft("The user is neurotic and psychologically fragile.", evidence, mode="agent_inferred"),
        _draft("The user prefers an unrelated framework.", "UNSUPPORTED_EVIDENCE"),
        {**valid, "unknown": "REJECTED_TEXT_MUST_NOT_BE_RETAINED"},
    )
    gated = persistence_gate(drafts, result.capsule)

    assert gated.accepted == (gated.accepted[0],)
    assert gated.accepted[0].statement == valid["statement"]
    assert gated.filtered_safety_count == 3
    assert gated.filtered_policy_count == len(drafts) - 4
    assert "SENTINEL" not in repr(gated)
    assert "REJECTED_TEXT_MUST_NOT_BE_RETAINED" not in repr(gated)


def test_persistence_gate_canonicalizes_deduplicates_and_uses_stable_rank():
    from agc_runtime.capture_safety import persistence_gate

    result, evidence = _safe_result()
    duplicate_a = _draft(
        "The user prefers deterministic privacy-safe workflows.",
        evidence,
        locator="user:0002",
        priority=3,
    )
    duplicate_b = _draft(
        "  the USER prefers deterministic privacy-safe workflows.  ",
        evidence,
        locator="user:0001",
        priority=1,
    )
    direct = _draft(
        "The user prefers privacy-safe workflows.",
        evidence,
        locator="user:0003",
        priority=1,
    )
    inferred = _draft(
        "The user prefers deterministic workflows.",
        evidence,
        locator="user:0000",
        mode="agent_inferred",
        priority=1,
    )
    gated = persistence_gate(
        (duplicate_a, inferred, duplicate_b, direct),
        result.capsule,
    )

    assert gated.duplicate_count == 1
    assert len(gated.accepted) == 3
    assert gated.accepted[0].locator == "user:0001"
    assert gated.accepted[-1].assertion_mode == "agent_inferred"


def test_persistence_evidence_requires_a_whole_capsule_signal_and_claim_coverage():
    from agc_runtime.capture_safety import persistence_gate

    result, evidence = _safe_result()
    valid = _draft("The user prefers deterministic privacy-safe workflows.", evidence)
    partial_evidence = _draft(
        "The user prefers deterministic aviation frameworks.",
        "deterministic",
        locator="user:0002",
    )
    weakly_related_claim = _draft(
        "The user prefers deterministic aviation frameworks.",
        evidence,
        locator="user:0003",
    )

    gated = persistence_gate((partial_evidence, weakly_related_claim, valid), result.capsule)

    assert gated.accepted == (gated.accepted[0],)
    assert gated.accepted[0].statement == valid["statement"]
    assert gated.filtered_policy_count == 2


def test_capsule_and_gates_make_no_writes_or_external_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import socket
    import subprocess
    import tempfile

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    memory_root = tmp_path / "synthetic-memory"
    memory_root.mkdir()
    (memory_root / "config.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    before = {
        path.relative_to(memory_root).as_posix(): path.read_bytes()
        for path in memory_root.rglob("*")
        if path.is_file()
    }

    def forbidden(*_args, **_kwargs):
        raise AssertionError("external or persistence boundary invoked")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", forbidden)
    monkeypatch.setattr(tempfile, "TemporaryDirectory", forbidden)

    result, evidence = _safe_result()
    secret_result = build_capsule(
        (_record("user", "I prefer safe workflows; token=FILESYSTEM_SENTINEL"),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    gated = persistence_gate(
        (_draft("The user prefers deterministic privacy-safe workflows.", evidence),),
        result.capsule,
    )
    after = {
        path.relative_to(memory_root).as_posix(): path.read_bytes()
        for path in memory_root.rglob("*")
        if path.is_file()
    }

    assert len(gated.accepted) == 1
    assert "FILESYSTEM_SENTINEL" not in repr(secret_result.capsule.to_mapping())
    assert before == after
    assert tuple(after) == ("config.yaml",)
    assert all(b"FILESYSTEM_SENTINEL" not in content for content in after.values())


def _write_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                '{"timestamp":"2026-08-19T10:00:00Z","type":"session_meta",'
                '"payload":{"id":"rollout-main","session_id":"task-main","source":"cli",'
                '"title":"Capsule task"}}',
                '{"timestamp":"2026-08-19T10:01:00Z","type":"event_msg",'
                '"payload":{"type":"task_started","turn_id":"turn-old"}}',
                '{"timestamp":"2026-08-19T10:01:10Z","type":"response_item",'
                '"payload":{"type":"message","role":"user","content":"OLD_TURN_SENTINEL"}}',
                '{"timestamp":"2026-08-19T10:02:00Z","type":"event_msg",'
                '"payload":{"type":"task_complete","turn_id":"turn-old"}}',
                '{"timestamp":"2026-08-19T11:00:00Z","type":"event_msg",'
                '"payload":{"type":"task_started","turn_id":"turn-target"}}',
                '{"timestamp":"2026-08-19T11:00:10Z","type":"response_item",'
                '"payload":{"type":"message","role":"user",'
                '"content":"I prefer deterministic privacy-safe workflows."}}',
                '{"timestamp":"2026-08-19T11:00:20Z","type":"response_item",'
                '"payload":{"type":"reasoning","content":"REASONING_SENTINEL"}}',
                '{"timestamp":"2026-08-19T11:00:30Z","type":"response_item",'
                '"payload":{"type":"message","role":"assistant","phase":"final",'
                '"content":"Decision: use the safe capsule. Next step: reuse src/safety.py."}}',
                '{"timestamp":"2026-08-19T12:00:00Z","type":"event_msg",'
                '"payload":{"type":"task_complete","turn_id":"turn-target"}}',
            )
        )
        + "\n",
        encoding="utf-8",
    )


def _window():
    from agc_runtime.capture_source import TimeWindow

    return TimeWindow.from_mapping(
        {
            "schema_version": 1,
            "start_at": "2026-08-18T00:00:00Z",
            "end_at": "2026-08-20T00:00:00Z",
        }
    )


def test_codex_load_capsule_reuses_settled_target_loader_and_archive_hashes_are_stable(
    tmp_path: Path,
):
    from agc_runtime.capture_capsule import CapsulePolicy
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    root = tmp_path / "profile"
    active = root / "sessions" / "task.jsonl"
    _write_source(active)
    adapter = CodexSourceAdapter(root)
    ref = next(
        item
        for item in adapter.discover(None, _window()).revisions
        if item.key.revision_id == "turn-target"
    )
    policy = CapsulePolicy(project_scope="project:stable")
    first = adapter.load_capsule(ref, policy)

    archived = root / "archived_sessions" / "task.jsonl"
    archived.parent.mkdir(parents=True)
    shutil.move(active, archived)
    moved_ref = next(
        item
        for item in adapter.discover(None, _window()).revisions
        if item.key.revision_id == "turn-target"
    )
    second = adapter.load_capsule(moved_ref, policy)

    assert first.source_fingerprint == second.source_fingerprint
    assert first.capsule_hash == second.capsule_hash
    assert "OLD_TURN_SENTINEL" not in repr(first.capsule.to_mapping())
    assert "REASONING_SENTINEL" not in repr(first.capsule.to_mapping())
    assert first.capsule.user_signals == (
        "I prefer deterministic privacy-safe workflows.",
    )


def test_codex_load_capsule_fails_closed_with_content_safe_error_on_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agc_runtime.capture_capsule import CapsulePolicy
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    root = tmp_path / "profile"
    source = root / "sessions" / "task.jsonl"
    _write_source(source)
    adapter = CodexSourceAdapter(root)
    ref = next(
        item
        for item in adapter.discover(None, _window()).revisions
        if item.key.revision_id == "turn-target"
    )
    original_scan = adapter._scan_file

    def scan_then_drift(path: Path):
        settled = original_scan(path)
        with source.open("a", encoding="utf-8", newline="") as handle:
            handle.write(
                '{"timestamp":"2026-08-19T12:01:00Z","type":"response_item",'
                '"payload":{"role":"user","content":"DRIFT_PRIVATE_SENTINEL"}}\n'
            )
        return settled

    monkeypatch.setattr(adapter, "_scan_file", scan_then_drift)
    with pytest.raises(ValueError) as caught:
        adapter.load_capsule(ref, CapsulePolicy(project_scope="project:stable"))
    assert "DRIFT_PRIVATE_SENTINEL" not in str(caught.value)
    assert "DRIFT_PRIVATE_SENTINEL" not in repr(caught.value)


@pytest.mark.parametrize(
    ("left_secret", "right_secret"),
    (
        ('{"password":"JSON_SECRET_ALPHA"}', '{"password":"JSON_SECRET_BRAVO"}'),
        ("password: YAML_SECRET_ALPHA", "password: YAML_SECRET_BRAVO"),
        (
            "password: |\n  YAML_BLOCK_SECRET_ALPHA\n  second-alpha-line",
            "password: |\n  YAML_BLOCK_SECRET_BRAVO\n  second-bravo-line",
        ),
        ("<password>XML_SECRET_ALPHA</password>", "<password>XML_SECRET_BRAVO</password>"),
        (
            "-----BEGIN PRIVATE KEY-----\nPARTIAL_PEM_SECRET_ALPHA",
            "-----BEGIN PRIVATE KEY-----\nPARTIAL_PEM_SECRET_BRAVO",
        ),
        (
            "custom+db://alice:URL_SECRET_ALPHA@example.invalid/database",
            "custom+db://alice:URL_SECRET_BRAVO@example.invalid/database",
        ),
    ),
)
def test_structured_secret_changes_have_content_independent_redaction_and_hashes(
    left_secret: str, right_secret: str
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    policy = CapsulePolicy(project_scope="project:stable")
    left = build_capsule(
        (_record("user", f"I prefer safe workflows.\n{left_secret}"),),
        _ref(),
        policy,
    )
    right = build_capsule(
        (_record("user", f"I prefer safe workflows.\n{right_secret}"),),
        _ref(),
        policy,
    )

    assert left.source_fingerprint == right.source_fingerprint
    assert left.capsule_hash == right.capsule_hash
    assert left.counts == right.counts
    assert left.counts.scrubbed_secret_count == 1
    surfaces = repr((left, right, left.capsule.to_mapping(), right.capsule.to_mapping()))
    assert "SECRET_ALPHA" not in surfaces
    assert "SECRET_BRAVO" not in surfaces


@pytest.mark.parametrize(
    "record",
    (
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "turn_id": "turn-target",
                "provenance": "subagent",
                "content": "I prefer SUBAGENT_SENTINEL workflows.",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "role": "user",
                "turn_id": "turn-target",
                "content": "I prefer UNTYPED_SENTINEL workflows.",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": "I prefer NO_TURN_SENTINEL workflows.",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "turn_id": "turn-target",
                "content": "hello thanks continue GREETING_SENTINEL",
            },
        },
    ),
)
def test_allowlist_rejects_untrusted_provenance_type_turn_and_low_signal_user(
    record: dict[str, object]
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (record,),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()
    assert "SENTINEL" not in repr(result.capsule.to_mapping())


def test_allowlist_rejects_generic_assistant_without_explicit_semantic_cue():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (
            _record(
                "assistant",
                "Everything looks nice and ready GENERIC_ASSISTANT_SENTINEL.",
                final=True,
            ),
        ),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.decisions_results == ()
    assert "GENERIC_ASSISTANT_SENTINEL" not in repr(result.capsule.to_mapping())


@pytest.mark.parametrize(
    "body",
    (
        "I prefer this output.\n"
        + "\n".join(f"2026-08-19T12:00:{index:02d}Z INFO LOG_SENTINEL_{index}" for index in range(30)),
        "I prefer this implementation.\n"
        + "\n".join(f"private_value_{index} = CODE_SENTINEL_{index}" for index in range(30)),
    ),
)
def test_allowlist_drops_long_unfenced_log_code_and_assignment_blocks(body: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", body),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()
    assert "SENTINEL" not in repr(result.capsule.to_mapping())
    assert result.counts.dropped_safety_count == 1


def _write_interleaved_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                '{"timestamp":"2026-08-19T10:00:00Z","type":"session_meta",'
                '"payload":{"id":"rollout-main","session_id":"task-main","source":"cli"}}',
                '{"timestamp":"2026-08-19T10:01:00Z","type":"event_msg",'
                '"payload":{"type":"task_started","turn_id":"turn-target"}}',
                '{"timestamp":"2026-08-19T10:01:10Z","type":"response_item",'
                '"payload":{"type":"message","role":"user",'
                '"content":"I prefer deterministic workflows."}}',
                '{"timestamp":"2026-08-19T10:01:20Z","type":"event_msg",'
                '"payload":{"type":"task_started","turn_id":"turn-other"}}',
                '{"timestamp":"2026-08-19T10:01:30Z","type":"response_item",'
                '"payload":{"type":"message","role":"user",'
                '"content":"I prefer OTHER_TURN_INTERLEAVED_SENTINEL workflows."}}',
                '{"timestamp":"2026-08-19T10:01:40Z","type":"event_msg",'
                '"payload":{"type":"task_complete","turn_id":"turn-other"}}',
                '{"timestamp":"2026-08-19T10:02:00Z","type":"event_msg",'
                '"payload":{"type":"task_complete","turn_id":"turn-target"}}',
            )
        )
        + "\n",
        encoding="utf-8",
    )


def test_codex_load_capsule_fails_closed_on_interleaved_turn_ambiguity(tmp_path: Path):
    from agc_runtime.capture_capsule import CapsulePolicy
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    root = tmp_path / "profile"
    _write_interleaved_source(root / "sessions" / "task.jsonl")
    adapter = CodexSourceAdapter(root)
    ref = next(
        item
        for item in adapter.discover(None, _window()).revisions
        if item.key.revision_id == "turn-target"
    )

    with pytest.raises(ValueError) as caught:
        adapter.load_capsule(ref, CapsulePolicy(project_scope="project:stable"))
    assert "OTHER_TURN_INTERLEAVED_SENTINEL" not in str(caught.value)
    assert "OTHER_TURN_INTERLEAVED_SENTINEL" not in repr(caught.value)


def test_direct_observation_drafts_roundtrip_strict_validation_without_value_leaks():
    from dataclasses import replace

    from agc_runtime.capture_safety import ObservationDraft, persistence_gate

    result, evidence = _safe_result()
    valid = ObservationDraft.from_mapping(
        _draft("The user prefers deterministic privacy-safe workflows.", evidence)
    )
    invalid = (
        replace(valid, statement="X" * 301),
        replace(valid, primary_category="PRIVATE_CATEGORY_SENTINEL"),
        replace(valid, assertion_mode="PRIVATE_MODE_SENTINEL"),
    )

    gated = persistence_gate(invalid, result.capsule)

    assert gated.accepted == ()
    assert gated.filtered_policy_count == 3
    assert "PRIVATE" not in repr(gated)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("scopes", ["C:/Users/private"]),
        ("scopes", [r"\\server\share"]),
        ("scopes", ["/etc/passwd"]),
        ("scopes", ["file:///private"]),
        ("scopes", ["../escape"]),
        ("locator", "C:/Users/private"),
        ("locator", r"\\server\share"),
        ("locator", "/etc/passwd"),
        ("locator", "file:///private"),
        ("locator", "../escape"),
        ("locator", "user:CONTENT SENTINEL"),
    ),
)
def test_draft_scopes_and_locators_reject_path_or_content_shapes(field: str, value: object):
    from agc_runtime.capture_safety import persistence_gate

    result, evidence = _safe_result()
    draft = _draft("The user prefers deterministic privacy-safe workflows.", evidence)
    draft[field] = value

    gated = persistence_gate((draft,), result.capsule)

    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1
    assert "private" not in repr(gated).casefold()
    assert "SENTINEL" not in repr(gated)


@pytest.mark.parametrize(
    ("evidence", "statement", "mode"),
    (
        (
            "Do you prefer deterministic workflows?",
            "The user prefers deterministic workflows.",
            "direct",
        ),
        (
            'A colleague said "I prefer deterministic workflows."',
            "The user prefers deterministic workflows.",
            "direct",
        ),
        (
            "If needed, I might prefer deterministic workflows.",
            "The user prefers deterministic workflows.",
            "direct",
        ),
        (
            "I do not prefer remote work.",
            "The user prefers remote work.",
            "direct",
        ),
        (
            "Result: the user prefers deterministic workflows.",
            "The user prefers deterministic workflows.",
            "direct",
        ),
    ),
)
def test_grounding_rejects_question_quote_modality_polarity_and_wrong_provenance(
    evidence: str, statement: str, mode: str
):
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    result, _base_evidence = _safe_result()
    if evidence.startswith("Result:"):
        capsule = replace(result.capsule, user_signals=(), decisions_results=(evidence,))
    else:
        capsule = replace(result.capsule, user_signals=(evidence,), decisions_results=())
    draft = _draft(statement, evidence, mode=mode)

    gated = persistence_gate((draft,), capsule)

    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    "statement",
    (
        "PostgreSQL stores the project data.",
        "React supports component hooks.",
        "The user is impulsive.",
        "The user prefers Rust and remote work.",
    ),
)
def test_personal_relevance_and_atomicity_ignore_claimed_labels(statement: str):
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    result, _evidence = _safe_result()
    capsule = replace(result.capsule, user_signals=(statement,), decisions_results=())
    draft = _draft(
        statement,
        statement,
        kind="preference",
        signal_type="explicit_user_state",
    )

    gated = persistence_gate((draft,), capsule)

    assert gated.accepted == ()
    assert gated.filtered_safety_count + gated.filtered_policy_count == 1


def test_ranking_keeps_verified_outcome_above_direct_research_changes():
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    result, _evidence = _safe_result()
    research_evidence = tuple(
        f"My long-term research direction now prioritizes topic {index}."
        for index in range(8)
    )
    verified_evidence = "Result: the user demonstrated ability to run deterministic verification."
    capsule = replace(
        result.capsule,
        user_signals=research_evidence,
        decisions_results=(verified_evidence,),
        reusable_methods=(),
        next_steps=(),
    )
    research = tuple(
        _draft(
            f"The user's long-term research direction now prioritizes topic {index}.",
            evidence,
            locator=f"user:{index:04d}",
            signal_type="research_change",
            kind="goal",
            category="research",
        )
        for index, evidence in enumerate(research_evidence)
    )
    verified = _draft(
        "The user demonstrated ability to run deterministic verification.",
        verified_evidence,
        locator="final:9999",
        signal_type="verified_outcome",
        kind="capability",
        category="work",
        mode="behavior_observed",
    )

    gated = persistence_gate((*research, verified), capsule)

    assert len(gated.accepted) == 8
    assert any(item.statement == verified["statement"] for item in gated.accepted)
    assert gated.over_limit_count == 1


def test_ranking_deduplicates_evidence_before_stable_locator_tie_break():
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    result, evidence = _safe_result()
    second_evidence = "I prefer deterministic privacy-safe review workflows."
    capsule = replace(result.capsule, user_signals=(evidence, second_evidence))
    first = _draft(
        "The user prefers deterministic privacy-safe workflows.",
        evidence,
        locator="user:0001",
    )
    second = _draft(
        "The user prefers deterministic privacy-safe review workflows.",
        second_evidence,
        locator="user:0002",
    )
    second["evidence"] = [second_evidence, second_evidence]

    gated = persistence_gate((second, first), capsule)

    assert len(gated.accepted) == 2
    assert gated.accepted[0].locator == "user:0001"
    assert gated.accepted[1].evidence == (second_evidence,)


def test_ranking_keeps_explicitly_marked_inference_in_the_lowest_tier():
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    result, _evidence = _safe_result()
    inferred_evidence = tuple(
        f"I prefer tentative workflow topic {index}." for index in range(8)
    )
    research_evidence = "My research direction now prioritizes deterministic verification."
    capsule = replace(
        result.capsule,
        user_signals=(*inferred_evidence, research_evidence),
        decisions_results=(),
        reusable_methods=(),
        next_steps=(),
    )
    inferred = tuple(
        _draft(
            f"The user prefers tentative workflow topic {index}.",
            evidence,
            locator=f"user:{index:04d}",
            mode="agent_inferred",
        )
        for index, evidence in enumerate(inferred_evidence)
    )
    research = _draft(
        "The user's research direction now prioritizes deterministic verification.",
        research_evidence,
        locator="user:9999",
        signal_type="research_change",
        kind="interest",
        category="research",
    )

    gated = persistence_gate((*inferred, research), capsule)

    assert len(gated.accepted) == 8
    assert any(item.statement == research["statement"] for item in gated.accepted)
    assert gated.over_limit_count == 1


@pytest.mark.parametrize(
    ("left_value", "right_value"),
    (
        (
            '{"Private-Note":"LABEL_SECRET_ALPHA"}',
            '{"Private-Note":"LABEL_SECRET_BRAVO"}',
        ),
        (
            '"Private-Note": LABEL_SECRET_ALPHA',
            '"Private-Note": LABEL_SECRET_BRAVO',
        ),
        (
            "<Private-Note>LABEL_SECRET_ALPHA</Private-Note>",
            "<Private-Note>LABEL_SECRET_BRAVO</Private-Note>",
        ),
    ),
)
def test_configured_sensitive_label_structures_have_content_independent_hashes(
    left_value: str,
    right_value: str,
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    policy = CapsulePolicy(
        project_scope="project:stable",
        sensitive_labels=("Private-Note",),
    )
    left = build_capsule(
        (_record("user", f"I prefer safe workflows with {left_value}."),),
        _ref(),
        policy,
    )
    right = build_capsule(
        (_record("user", f"I prefer safe workflows with {right_value}."),),
        _ref(),
        policy,
    )

    assert left.source_fingerprint == right.source_fingerprint
    assert left.capsule_hash == right.capsule_hash
    assert left.counts == right.counts
    assert left.counts.scrubbed_secret_count == 1
    assert "LABEL_SECRET" not in repr((left.capsule.to_mapping(), right.capsule.to_mapping()))


def test_configured_sensitive_label_in_title_has_content_independent_hashes():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    policy = CapsulePolicy(
        project_scope="project:stable",
        sensitive_labels=("Private-Note",),
    )

    def result(secret: str):
        return build_capsule(
            (
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "rollout-main",
                        "session_id": "task-main",
                        "title": f'Capture {{"Private-Note":"{secret}"}}',
                    },
                },
            ),
            _ref(),
            policy,
        )

    left = result("TITLE_LABEL_ALPHA")
    right = result("TITLE_LABEL_BRAVO")

    assert left.source_fingerprint == right.source_fingerprint
    assert left.capsule_hash == right.capsule_hash
    assert left.counts == right.counts
    assert left.counts.scrubbed_secret_count == 1
    assert "TITLE_LABEL" not in repr((left.capsule.to_mapping(), right.capsule.to_mapping()))


def test_persistence_gate_rejects_capsule_policy_sensitive_labels_without_label_text_leak():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    evidence = "I prefer deterministic privacy-safe workflows."
    result = build_capsule(
        (_record("user", evidence),),
        _ref(),
        CapsulePolicy(
            project_scope="project:stable",
            sensitive_labels=("Private-Note",),
        ),
    )
    gated = persistence_gate(
        (
            _draft("Private-Note: POST_GATE_LABEL_SENTINEL", evidence),
            _draft(
                "The user prefers workflows with Private-Note: INLINE_LABEL_SENTINEL.",
                evidence,
                locator="user:0002",
            ),
        ),
        result.capsule,
    )

    assert gated.accepted == ()
    assert gated.filtered_safety_count == 2
    assert "Private-Note" not in repr(result.capsule)
    assert "POST_GATE_LABEL_SENTINEL" not in repr(gated)


@pytest.mark.parametrize(
    "content",
    (
        ["I prefer UNTYPED_LIST_STRING_SENTINEL workflows."],
        [{"text": "I prefer UNTYPED_LIST_MAPPING_SENTINEL workflows."}],
        [
            {
                "type": "unknown_text",
                "text": "I prefer UNKNOWN_LIST_TYPE_SENTINEL workflows.",
            }
        ],
    ),
)
def test_content_parts_require_an_explicit_supported_text_type(content: list[object]):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    record = _record("user", "placeholder")
    assert isinstance(record["payload"], dict)
    record["payload"]["content"] = content
    result = build_capsule(
        (record,),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()
    assert "SENTINEL" not in repr(result.capsule.to_mapping())


@pytest.mark.parametrize(
    "body",
    (
        "I prefer safe workflows.\n```python\nUNTERMINATED_FENCE_SENTINEL = 1",
        "I prefer safe workflows.\n"
        + "\n".join(
            f'{{"item":{index},"value":"JSON_MAPPING_SENTINEL"}}' for index in range(4)
        ),
        "I prefer safe workflows.\n"
        + "\n".join(f"workflow.process(METHOD_CALL_SENTINEL_{index})" for index in range(6)),
        "I prefer safe workflows.\n2026-08-20T10:00:00Z INFO LOG_CUE_SENTINEL",
    ),
)
def test_structural_payloads_drop_the_whole_cued_record(body: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", body),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()
    assert result.counts.dropped_safety_count == 1
    assert "SENTINEL" not in repr(result.capsule.to_mapping())


def test_interrogative_user_signal_without_question_mark_is_rejected_pre_and_post_gate():
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    question = "Do you prefer deterministic workflows"
    result = build_capsule(
        (_record("user", question),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert result.capsule.user_signals == ()

    adversarial_capsule = replace(result.capsule, user_signals=(question,))
    gated = persistence_gate(
        (_draft("The user prefers deterministic workflows.", question),),
        adversarial_capsule,
    )
    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    ("evidence", "statement"),
    (
        ("I don't prefer remote work.", "The user prefers remote work."),
        ("I hardly ever prefer remote work.", "The user prefers remote work."),
        ("I avoid remote work.", "The user does not prefer remote work."),
        ("I hardly ever avoid remote work.", "The user avoid remote work."),
    ),
)
def test_grounding_preserves_broad_polarity_and_durable_predicate_class(
    evidence: str,
    statement: str,
):
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    result, _base_evidence = _safe_result()
    capsule = replace(result.capsule, user_signals=(evidence,), decisions_results=())
    gated = persistence_gate((_draft(statement, evidence),), capsule)

    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    ("evidence", "statement"),
    (
        (
            "Result: PostgreSQL stores project data.",
            "The user prefers PostgreSQL for project data.",
        ),
        (
            "Result: React supports component hooks.",
            "The user prefers React component hooks.",
        ),
    ),
)
def test_assistant_project_or_third_party_results_cannot_ground_user_preferences(
    evidence: str,
    statement: str,
):
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    result, _base_evidence = _safe_result()
    capsule = replace(
        result.capsule,
        user_signals=(),
        decisions_results=(evidence,),
        reusable_methods=(),
    )
    draft = _draft(
        statement,
        evidence,
        mode="behavior_observed",
        signal_type="verified_outcome",
    )
    gated = persistence_gate((draft,), capsule)

    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    ("evidence", "statement"),
    (
        (
            "I prefer Rust, I prefer remote work.",
            "The user prefers Rust, prefers remote work.",
        ),
        (
            "I prefer Rust: I prefer remote work.",
            "The user prefers Rust: prefers remote work.",
        ),
        (
            "I prefer Rust / I prefer remote work.",
            "The user prefers Rust / prefers remote work.",
        ),
        (
            "I prefer Rust. I prefer remote work.",
            "The user prefers Rust. The user prefers remote work.",
        ),
    ),
)
def test_atomicity_rejects_repeated_durable_predicates_across_separators(
    evidence: str,
    statement: str,
):
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    result, _base_evidence = _safe_result()
    capsule = replace(result.capsule, user_signals=(evidence,), decisions_results=())
    gated = persistence_gate((_draft(statement, evidence),), capsule)

    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize("surface", ("title", "user"))
def test_configured_label_discards_arbitrary_scalar_comma_tails_before_hashing(
    surface: str,
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    policy = CapsulePolicy(
        project_scope="project:stable",
        sensitive_labels=("Private-Note",),
    )

    def result(secret: str, tail: str):
        labeled = f'{{"Private-Note":"{secret}","tail":"{tail}"}}'
        if surface == "title":
            records = (
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "rollout-main",
                        "session_id": "task-main",
                        "title": f"Capture {labeled}",
                    },
                },
            )
        else:
            records = (_record("user", f"I prefer safe workflows with {labeled}."),)
        return build_capsule(records, _ref(), policy)

    left = result("SCALAR_SECRET_ALPHA", "ARBITRARY_TAIL_ALPHA")
    right = result("SCALAR_SECRET_BRAVO", "COMPLETELY_DIFFERENT_TAIL_BRAVO")

    assert left.source_fingerprint == right.source_fingerprint
    assert left.capsule_hash == right.capsule_hash
    assert left.counts == right.counts
    assert left.counts.scrubbed_secret_count == 1
    serialized = repr((left.capsule.to_mapping(), right.capsule.to_mapping()))
    assert "SCALAR_SECRET" not in serialized
    assert "ARBITRARY_TAIL" not in serialized
    assert "COMPLETELY_DIFFERENT_TAIL" not in serialized


@pytest.mark.parametrize(
    "body",
    (
        'Method: reuse {"step":"SINGLE_JSON_SENTINEL"} as the workflow.',
        'Method: reuse ["ARRAY_SENTINEL", {"step": 1}] as the workflow.',
        "Method: await workflow.process(AWAIT_CALL_SENTINEL)",
        "Method: await run(AWAIT_PLAIN_CALL_SENTINEL)",
        'Method: runner["step"](BRACKET_CALL_SENTINEL)',
        "Method: workflow.process(CALL_SENTINEL)",
        "Method: run(PLAIN_CALL_SENTINEL)",
        "Method: private_value = ASSIGNMENT_SENTINEL",
        "Method: ~~~python\nTILDE_FENCE_SENTINEL",
        "Method: ```python\nBALANCED_FENCE_SENTINEL\n```",
    ),
)
def test_single_unit_payload_code_call_assignment_and_fence_markers_fail_closed(body: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("assistant", body, final=True),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.decisions_results == ()
    assert result.capsule.reusable_methods == ()
    assert result.capsule.next_steps == ()
    assert "SENTINEL" not in repr(result.capsule.to_mapping())
    assert result.counts.dropped_safety_count == 1


@pytest.mark.parametrize(
    "question",
    (
        "I wonder whether I prefer Rust",
        "I am unsure whether I prefer Rust",
        "I am not sure whether I prefer Rust",
        "I am curious whether I prefer Rust",
        "I want to ask whether I prefer Rust",
    ),
)
def test_indirect_interrogative_and_uncertainty_cues_fail_pre_and_post_gate(question: str):
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    result = build_capsule(
        (_record("user", question),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert result.capsule.user_signals == ()

    capsule = replace(result.capsule, user_signals=(question,))
    gated = persistence_gate(
        (_draft("The user prefers Rust.", question),),
        capsule,
    )
    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    ("evidence", "statement", "predicate"),
    (
        (
            "Result: React can reliably use component hooks.",
            "The user can reliably use React component hooks.",
            "ability",
        ),
        (
            "Result: PostgreSQL must use deterministic migrations.",
            "The user must use deterministic PostgreSQL migrations.",
            "constraint",
        ),
    ),
)
def test_assistant_non_user_subject_cannot_ground_user_ability_or_constraint(
    evidence: str,
    statement: str,
    predicate: str,
):
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    result, _base_evidence = _safe_result()
    capsule = replace(
        result.capsule,
        user_signals=(),
        decisions_results=(evidence,),
        reusable_methods=(),
    )
    draft = _draft(
        statement,
        evidence,
        mode="behavior_observed",
        kind="capability" if predicate == "ability" else "pattern",
        signal_type="capability_evidence" if predicate == "ability" else "decision_or_constraint",
    )
    gated = persistence_gate((draft,), capsule)

    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    "attribution",
    (
        "According to Alice, I prefer Rust.",
        "Alice says I prefer Rust.",
        "Alice reported that I prefer Rust.",
        "Alice quoted me: I prefer Rust.",
    ),
)
def test_attributed_or_reported_user_claims_fail_pre_and_post_gate(attribution: str):
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    result = build_capsule(
        (_record("user", attribution),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert result.capsule.user_signals == ()

    capsule = replace(result.capsule, user_signals=(attribution,))
    gated = persistence_gate(
        (_draft("The user prefers Rust.", attribution),),
        capsule,
    )
    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    ("evidence", "statement"),
    (
        (
            "I prefer Rust, my office is Berlin.",
            "The user prefers Rust, user's office is Berlin.",
        ),
        (
            "I prefer Rust: my office is Berlin.",
            "The user prefers Rust: user's office is Berlin.",
        ),
        (
            "I prefer Rust / my office is Berlin.",
            "The user prefers Rust / user's office is Berlin.",
        ),
        (
            "I prefer Rust. My office is Berlin.",
            "The user prefers Rust. User's office is Berlin.",
        ),
    ),
)
def test_atomicity_rejects_unknown_second_clauses_across_all_separators(
    evidence: str,
    statement: str,
):
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    result, _base_evidence = _safe_result()
    capsule = replace(result.capsule, user_signals=(evidence,), decisions_results=())
    gated = persistence_gate((_draft(statement, evidence),), capsule)

    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    ("configured_label", "surface_label"),
    (
        ("Private  Note", "PRIVATE NOTE"),
        ("Straße", "STRASSE"),
    ),
)
@pytest.mark.parametrize("surface", ("title", "user"))
def test_sensitive_label_detection_uses_one_unicode_whitespace_canonicalization(
    configured_label: str,
    surface_label: str,
    surface: str,
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    policy = CapsulePolicy(
        project_scope="project:stable",
        sensitive_labels=(configured_label,),
    )

    def result(secret: str, tail: str):
        labeled = f"{surface_label} {secret} {tail}"
        if surface == "title":
            records = (
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "rollout-main",
                        "session_id": "task-main",
                        "title": f"Capture {labeled}",
                    },
                },
            )
        else:
            records = (_record("user", f"I prefer workflows with {labeled}."),)
        return build_capsule(records, _ref(), policy)

    left = result("CANONICAL_SECRET_ALPHA", "ARBITRARY_ALPHA_TAIL")
    right = result("CANONICAL_SECRET_BRAVO", "UNRELATED_BRAVO_TAIL")

    assert left.source_fingerprint == right.source_fingerprint
    assert left.capsule_hash == right.capsule_hash
    assert left.counts == right.counts
    assert left.counts.scrubbed_secret_count == 1
    serialized = repr((left.capsule.to_mapping(), right.capsule.to_mapping()))
    assert "CANONICAL_SECRET" not in serialized
    assert "ARBITRARY_ALPHA_TAIL" not in serialized
    assert "UNRELATED_BRAVO_TAIL" not in serialized


@pytest.mark.parametrize(
    ("configured_label", "surface_label"),
    (
        ("Private  Note", "PRIVATE NOTE"),
        ("Straße", "STRASSE"),
    ),
)
def test_persistence_reuses_capsule_sensitive_label_canonicalization(
    configured_label: str,
    surface_label: str,
):
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    clean_evidence = "I prefer deterministic workflows."
    result = build_capsule(
        (_record("user", clean_evidence),),
        _ref(),
        CapsulePolicy(
            project_scope="project:stable",
            sensitive_labels=(configured_label,),
        ),
    )
    adversarial_evidence = f"I prefer {surface_label} workflows."
    capsule = replace(result.capsule, user_signals=(adversarial_evidence,))
    gated = persistence_gate(
        (_draft(f"The user prefers {surface_label} workflows.", adversarial_evidence),),
        capsule,
    )

    assert gated.accepted == ()
    assert gated.filtered_safety_count == 1
    assert configured_label not in repr(capsule)
    assert surface_label not in repr(gated)


@pytest.mark.parametrize(
    "body",
    (
        "Method: reuse [] as the workflow.",
        "Method: reuse {} as the workflow.",
        "Method: reuse [1] as the workflow.",
        "Method: total += 1.",
        "Method: @decorator",
        "Method: lambda value: value",
        "Method: value | transform",
        "Method: value < other",
        "Method: path\\private",
    ),
)
def test_positive_plain_language_grammar_rejects_structural_single_units(body: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("assistant", body, final=True),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.decisions_results == ()
    assert result.capsule.reusable_methods == ()
    assert result.capsule.next_steps == ()
    assert result.counts.dropped_safety_count == 1


@pytest.mark.parametrize(
    "uncertain",
    (
        "I remain undecided about whether I prefer Rust.",
        "I am considering whether I prefer Rust.",
        "I am trying to determine whether I prefer Rust.",
        "I wonder after reviewing many alternatives across several projects and discussing every tradeoff with my team whether I prefer Rust.",
    ),
)
def test_positive_user_grammar_rejects_arbitrary_uncertainty_prefixes(uncertain: str):
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    result = build_capsule(
        (_record("user", uncertain),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert result.capsule.user_signals == ()

    capsule = replace(result.capsule, user_signals=(uncertain,))
    gated = persistence_gate(
        (_draft("The user prefers Rust.", uncertain),),
        capsule,
    )
    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    "arbitrary",
    (
        "Yesterday I realized I prefer Rust.",
        "After the workshop I prefer Rust.",
    ),
)
def test_user_signal_requires_a_declarative_subject_predicate_start(arbitrary: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", arbitrary),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()


def test_positive_user_grammar_preserves_supported_declarative_classes():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    signals = (
        "I prefer deterministic workflows.",
        "My goal is to learn Rust.",
        "We must keep sensitive data in memory.",
        "I can reliably run verification.",
        "We use a reusable workflow.",
        "I learned to validate packages.",
        "My research direction prioritizes privacy.",
    )
    result = build_capsule(
        tuple(_record("user", signal) for signal in signals),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == signals


@pytest.mark.parametrize(
    ("evidence", "statement", "predicate"),
    (
        (
            "Result: This workflow can reliably help you run deterministic verification.",
            "The user can reliably run deterministic verification.",
            "ability",
        ),
        (
            "Result: Deterministic verification can reliably benefit you.",
            "The user can reliably perform deterministic verification.",
            "ability",
        ),
        (
            "Constraint: The workflow requires you to keep data in memory.",
            "The user requires the workflow to keep data in memory.",
            "constraint",
        ),
    ),
)
def test_assistant_object_or_beneficiary_you_is_not_a_grammatical_user_subject(
    evidence: str,
    statement: str,
    predicate: str,
):
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    result, _base_evidence = _safe_result()
    capsule = replace(
        result.capsule,
        user_signals=(),
        decisions_results=(evidence,),
        reusable_methods=(),
    )
    gated = persistence_gate(
        (
            _draft(
                statement,
                evidence,
                mode="behavior_observed",
                kind="capability" if predicate == "ability" else "pattern",
                signal_type=(
                    "capability_evidence" if predicate == "ability" else "decision_or_constraint"
                ),
            ),
        ),
        capsule,
    )

    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    ("evidence", "statement", "predicate", "kind", "signal_type"),
    (
        (
            "Result: You can reliably run deterministic verification.",
            "The user can reliably run deterministic verification.",
            "ability",
            "capability",
            "capability_evidence",
        ),
        (
            "Constraint: The user must keep sensitive data in memory.",
            "The user must keep sensitive data in memory.",
            "constraint",
            "pattern",
            "decision_or_constraint",
        ),
    ),
)
def test_assistant_subject_grammar_allows_matching_user_outcomes(
    evidence: str,
    statement: str,
    predicate: str,
    kind: str,
    signal_type: str,
):
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    result, _base_evidence = _safe_result()
    capsule = replace(
        result.capsule,
        user_signals=(),
        decisions_results=(evidence,),
        reusable_methods=(),
    )
    gated = persistence_gate(
        (
            _draft(
                statement,
                evidence,
                mode="behavior_observed",
                kind=kind,
                signal_type=signal_type,
            ),
        ),
        capsule,
    )

    assert len(gated.accepted) == 1


@pytest.mark.parametrize(
    "attribution",
    (
        "Alice told me I prefer Rust.",
        "Per Alice I prefer Rust.",
        "Alice believes I prefer Rust.",
        "Alice wrote that I prefer Rust.",
        "I was told by Alice that I prefer Rust.",
    ),
)
def test_positive_subject_grammar_rejects_third_party_attribution_variants(
    attribution: str,
):
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    result = build_capsule(
        (_record("user", attribution),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert result.capsule.user_signals == ()

    capsule = replace(result.capsule, user_signals=(attribution,))
    gated = persistence_gate(
        (_draft("The user prefers Rust.", attribution),),
        capsule,
    )
    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize("separator", (" — ", " – "))
def test_atomicity_rejects_unicode_dash_multi_fact_separators(separator: str):
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    evidence = f"I prefer Rust{separator}my office is Berlin."
    statement = f"The user prefers Rust{separator}user's office is Berlin."
    result, _base_evidence = _safe_result()
    capsule = replace(result.capsule, user_signals=(evidence,), decisions_results=())
    gated = persistence_gate((_draft(statement, evidence),), capsule)

    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


def test_atomic_statement_grammar_rejects_a_second_subject_without_punctuation():
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    evidence = "I prefer Rust My office is Berlin."
    statement = "The user prefers Rust The user's office is Berlin."
    result, _base_evidence = _safe_result()
    capsule = replace(result.capsule, user_signals=(evidence,), decisions_results=())
    gated = persistence_gate((_draft(statement, evidence),), capsule)

    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1
