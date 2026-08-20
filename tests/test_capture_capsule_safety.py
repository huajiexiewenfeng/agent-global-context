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

    evidence = "I prefer Rust."
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
        _record("user", "I prefer Rust."),
        _record("user", "OTHER_TURN_SENTINEL", turn_id="turn-other"),
        _record(
            "assistant",
            "Result: tests pass.",
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
    assert capsule.user_signals == ("I prefer Rust.",)
    assert capsule.decisions_results == ("Result: tests pass.",)
    assert capsule.reusable_methods == ()
    assert capsule.next_steps == ()
    assert capsule.file_locators == ()
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
            f"I prefer Topic-{index:03d}-" + ("x" * 180) + ".",
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
        f"I prefer Topic-{index}."
        for index in range(count)
    )
    result = build_capsule(
        tuple(_record("user", evidence) for evidence in evidence_values),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    drafts = tuple(
        _draft(
            f"The user prefers Topic-{index}.",
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
    valid = _draft("The user prefers Rust.", evidence)
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
        "The user prefers Rust.",
        evidence,
        locator="user:0002",
        priority=3,
    )
    duplicate_b = _draft(
        "  the USER prefers Rust.  ",
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
    assert len(gated.accepted) == 1
    assert gated.accepted[0].locator == "user:0001"
    assert gated.filtered_policy_count == 2


def test_persistence_evidence_requires_a_whole_capsule_signal_and_exact_proposition():
    from agc_runtime.capture_safety import persistence_gate

    result, evidence = _safe_result()
    valid = _draft("The user prefers Rust.", evidence)
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
        (_draft("The user prefers Rust.", evidence),),
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
                '"content":"I prefer Rust."}}',
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
        "I prefer Rust.",
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
        _draft("The user prefers Rust.", evidence)
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
    draft = _draft("The user prefers Rust.", evidence)
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
        f"My long-term research direction now prioritizes Topic-{index}."
        for index in range(8)
    )
    verified_evidence = "Result: the user demonstrated ability to run Verification."
    capsule = replace(
        result.capsule,
        user_signals=research_evidence,
        decisions_results=(verified_evidence,),
        reusable_methods=(),
        next_steps=(),
    )
    research = tuple(
        _draft(
            f"The user's long-term research direction now prioritizes Topic-{index}.",
            evidence,
            locator=f"user:{index:04d}",
            signal_type="research_change",
            kind="goal",
            category="research",
        )
        for index, evidence in enumerate(research_evidence)
    )
    verified = _draft(
        "The user demonstrated ability to run Verification.",
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
    second_evidence = "I prefer Go."
    capsule = replace(result.capsule, user_signals=(evidence, second_evidence))
    first = _draft(
        "The user prefers Rust.",
        evidence,
        locator="user:0001",
    )
    second = _draft(
        "The user prefers Go.",
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
        f"I prefer Topic-{index}." for index in range(8)
    )
    research_evidence = "My research direction now prioritizes Privacy."
    capsule = replace(
        result.capsule,
        user_signals=(*inferred_evidence, research_evidence),
        decisions_results=(),
        reusable_methods=(),
        next_steps=(),
    )
    inferred = tuple(
        _draft(
            f"The user prefers Topic-{index}.",
            evidence,
            locator=f"user:{index:04d}",
            mode="agent_inferred",
        )
        for index, evidence in enumerate(inferred_evidence)
    )
    research = _draft(
        "The user's research direction now prioritizes Privacy.",
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

    evidence = "I prefer Rust."
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
        "I prefer Rust.",
        "My goal is to learn Rust.",
        "We must keep Memory.",
        "I can reliably run tests.",
        "We use workflow.",
        "I learned to validate Packages.",
        "My research direction prioritizes Privacy.",
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
            "Result: You can reliably run Verification.",
            "The user can reliably run Verification.",
            "ability",
            "capability",
            "capability_evidence",
        ),
        (
            "Constraint: The user must keep Memory.",
            "The user must keep Memory.",
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


@pytest.mark.parametrize("control", ("\x00", "\x01", "\x08", "\x0b", "\x0c", "\x7f"))
def test_capsule_policy_rejects_sensitive_labels_with_unicode_controls(control: str):
    from agc_runtime.capture_capsule import CapsulePolicy

    with pytest.raises(ValueError, match="capture_capsule_contract_invalid"):
        CapsulePolicy(
            project_scope="project:stable",
            sensitive_labels=(f"Private{control}Note",),
        )


@pytest.mark.parametrize(
    "body",
    (
        "Method: 流程(代码秘密)",
        "Method: raise PRIVATE_CODE_SENTINEL",
        "Method: assert PRIVATE_CODE_SENTINEL",
        "Method: while PRIVATE_CODE_SENTINEL",
        "Method: print PRIVATE_CODE_SENTINEL",
        "Method: python private_script.py",
        "Method: use python private_script.py",
        "Decision: use python private_script.py",
        "Result: Python private_script.py",
        "Constraint: use python private_script.py",
        "Next step: run python private_script.py",
    ),
)
def test_plain_language_shape_rejects_unicode_calls_and_plain_code_commands(body: str):
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
    assert "PRIVATE_CODE_SENTINEL" not in repr(result.capsule.to_mapping())


@pytest.mark.parametrize(
    ("evidence", "statement"),
    (
        ("I prefer maybe Rust.", "The user prefers maybe Rust."),
        ("I prefer Rust or maybe Go.", "The user prefers Rust or maybe Go."),
        ("I prefer Rust per Alice.", "The user prefers Rust per Alice."),
        (
            "I prefer Rust based on Alice's claim.",
            "The user prefers Rust based on Alice's claim.",
        ),
    ),
)
def test_user_proposition_rejects_uncertainty_alternatives_and_attribution_anywhere(
    evidence: str,
    statement: str,
):
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    result = build_capsule(
        (_record("user", evidence),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert result.capsule.user_signals == ()

    capsule = replace(result.capsule, user_signals=(evidence,))
    gated = persistence_gate((_draft(statement, evidence),), capsule)
    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


def test_canonical_proposition_equality_rejects_assistant_ask_object_rewrite():
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    evidence = "Result: You can reliably ask React to render components."
    statement = "The user can reliably render React components."
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
                kind="capability",
                signal_type="capability_evidence",
            ),
        ),
        capsule,
    )

    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    "evidence",
    (
        "Result: You can reliably render React components per Alice.",
        "Result: You can reliably render React components based on Alice's claim.",
    ),
)
def test_assistant_user_subject_with_suffix_attribution_cannot_ground_a_draft(
    evidence: str,
):
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    statement = "The user can reliably render React components."
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
                kind="capability",
                signal_type="capability_evidence",
            ),
        ),
        capsule,
    )

    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


def test_canonical_proposition_equality_rejects_partial_object_coverage():
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    evidence = "I prefer Rust tooling."
    statement = "The user prefers Rust."
    result, _base_evidence = _safe_result()
    capsule = replace(result.capsule, user_signals=(evidence,), decisions_results=())
    gated = persistence_gate((_draft(statement, evidence),), capsule)

    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    ("evidence", "statement", "kind", "signal_type"),
    (
        (
            "I don't prefer Remote.",
            "The user does not prefer Remote.",
            "preference",
            "explicit_user_state",
        ),
        (
            "I can't use Storage.",
            "The user cannot use Storage.",
            "pattern",
            "decision_or_constraint",
        ),
    ),
)
def test_canonical_proposition_normalizes_contractions_without_losing_polarity(
    evidence: str,
    statement: str,
    kind: str,
    signal_type: str,
):
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    result, _base_evidence = _safe_result()
    capsule = replace(result.capsule, user_signals=(evidence,), decisions_results=())
    gated = persistence_gate(
        (_draft(statement, evidence, kind=kind, signal_type=signal_type),),
        capsule,
    )

    assert len(gated.accepted) == 1


@pytest.mark.parametrize(
    ("evidence", "statement"),
    (
        (
            "I prefer Rust office is Berlin.",
            "The user prefers Rust office is Berlin.",
        ),
        (
            "I prefer Rust while office is Berlin.",
            "The user prefers Rust while office is Berlin.",
        ),
        (
            "I prefer Rust whereas office is Berlin.",
            "The user prefers Rust whereas office is Berlin.",
        ),
        (
            "I prefer Rust although office is Berlin.",
            "The user prefers Rust although office is Berlin.",
        ),
    ),
)
def test_atomic_proposition_rejects_independent_object_predicates_and_clause_markers(
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


@pytest.mark.parametrize("label", (" ", "\t", "\u00a0", " \u2003 "))
def test_capsule_policy_rejects_sensitive_labels_empty_after_canonicalization(
    label: str,
):
    from agc_runtime.capture_capsule import CapsulePolicy

    with pytest.raises(ValueError, match="capture_capsule_contract_invalid"):
        CapsulePolicy(project_scope="project:stable", sensitive_labels=(label,))


@pytest.mark.parametrize(
    "body",
    (
        "Result: Raise private error.",
        "Result: Assert private condition.",
        "Decision: use bash private.sh",
        "Method: use node private.js",
        "Constraint: use ruby private.rb",
        "Next step: run pwsh private.ps1",
        "Next step: run cmd private.cmd",
    ),
)
def test_assistant_allowlist_requires_complete_declarative_grammar(body: str):
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
    ("evidence", "statement"),
    (
        ("I prefer possibly Rust.", "The user prefers possibly Rust."),
        ("I prefer Rust if available.", "The user prefers Rust if available."),
        (
            "I prefer Rust unless remote work is required.",
            "The user prefers Rust unless remote work is required.",
        ),
        (
            "I prefer Rust as Alice believes.",
            "The user prefers Rust as Alice believes.",
        ),
        (
            "I prefer Rust in Alice's view.",
            "The user prefers Rust in Alice's view.",
        ),
    ),
)
def test_user_proposition_requires_complete_nominal_object(
    evidence: str,
    statement: str,
):
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    result = build_capsule(
        (_record("user", evidence),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert result.capsule.user_signals == ()

    capsule = replace(result.capsule, user_signals=(evidence,))
    gated = persistence_gate((_draft(statement, evidence),), capsule)
    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    "evidence",
    (
        "Result: You can reliably render React components as Alice believes.",
        "Result: You can reliably render React components in Alice's view.",
    ),
)
def test_assistant_proposition_requires_complete_nominal_object(evidence: str):
    from dataclasses import replace

    from agc_runtime.capture_safety import persistence_gate

    statement = "The user can reliably render React components."
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
                kind="capability",
                signal_type="capability_evidence",
            ),
        ),
        capsule,
    )

    assert gated.accepted == ()
    assert gated.filtered_safety_count + gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    ("evidence", "statement"),
    (
        (
            "I prefer Rust office sits in Berlin.",
            "The user prefers Rust office sits in Berlin.",
        ),
        (
            "I prefer Rust because office sits in Berlin.",
            "The user prefers Rust because office sits in Berlin.",
        ),
        (
            "I prefer Rust when office sits in Berlin.",
            "The user prefers Rust when office sits in Berlin.",
        ),
    ),
)
def test_proposition_parser_rejects_unconsumed_second_clause(
    evidence: str,
    statement: str,
):
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    result = build_capsule(
        (_record("user", evidence),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert result.capsule.user_signals == ()

    capsule = replace(result.capsule, user_signals=(evidence,))
    gated = persistence_gate((_draft(statement, evidence),), capsule)
    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    "tail",
    (
        "office located Berlin",
        "provided Alice agrees",
        "under Alice opinion",
        "whenever Alice approves",
    ),
)
def test_nominal_object_positive_grammar_rejects_arbitrary_residual_clauses(
    tail: str,
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", f"I prefer Rust {tail}."),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()


@pytest.mark.parametrize(
    "tail",
    (
        "maybe",
        "reportedly",
        "safe workflow fails",
        "project fails",
        "breaks",
        "occurs",
        "claims",
        "Because Office Sits Berlin",
        "When Random Capitalized Clause Breaks",
    ),
)
def test_fixed_arity_nominal_ast_rejects_every_unconsumed_tail(tail: str):
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    evidence = f"I prefer Rust {tail}."
    statement = f"The user prefers Rust {tail}."
    result = build_capsule(
        (_record("user", evidence),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert result.capsule.user_signals == ()

    capsule = replace(result.capsule, user_signals=(evidence,))
    gated = persistence_gate((_draft(statement, evidence),), capsule)
    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


def test_fixed_arity_action_ast_rejects_an_arbitrary_tail():
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    evidence = "I can reliably run safe workflow fails."
    statement = "The user can reliably run safe workflow fails."
    result = build_capsule(
        (_record("user", evidence),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert result.capsule.user_signals == ()

    capsule = replace(result.capsule, user_signals=(evidence,))
    gated = persistence_gate(
        (
            _draft(
                statement,
                evidence,
                kind="capability",
                signal_type="capability_evidence",
            ),
        ),
        capsule,
    )
    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


def test_fixed_arity_assistant_ast_rejects_capitalized_attribution_tail():
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    evidence = "Result: You can reliably run React As Alice Believes."
    statement = "The user can reliably run React As Alice Believes."
    result = build_capsule(
        (_record("assistant", evidence, final=True),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert result.capsule.decisions_results == ()

    capsule = replace(result.capsule, decisions_results=(evidence,))
    gated = persistence_gate(
        (
            _draft(
                statement,
                evidence,
                mode="behavior_observed",
                kind="capability",
                signal_type="capability_evidence",
            ),
        ),
        capsule,
    )
    assert gated.accepted == ()
    assert gated.filtered_safety_count + gated.filtered_policy_count == 1


def test_fixed_arity_grammar_keeps_only_atomic_and_bounded_action_objects():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    signals = (
        "I prefer Rust.",
        "I can reliably run tests.",
        "My goal is to learn Rust.",
    )
    result = build_capsule(
        tuple(_record("user", signal) for signal in signals),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == signals


@pytest.mark.parametrize("atom", ("maybe", "reportedly", "fails", "because"))
def test_atomic_nominal_rejects_lowercase_ascii_function_or_predicate_shape(
    atom: str,
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", f"I prefer {atom}."),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()


@pytest.mark.parametrize(
    "atom",
    ("Maybe", "Fails", "Because", "maybé", "Ｍaybe"),
)
def test_security_skeleton_makes_obfuscated_rejected_atoms_equivalent(atom: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", f"I prefer {atom}."),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()


@pytest.mark.parametrize("atom", ("Maybe", "maybé", "Ｍaybe", "Ｆails"))
def test_security_skeleton_rejects_obfuscated_action_complements(atom: str):
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    evidence = f"I can reliably run {atom}."
    statement = f"The user can reliably run {atom}."
    result = build_capsule(
        (_record("user", evidence),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert result.capsule.user_signals == ()

    capsule = replace(result.capsule, user_signals=(evidence,))
    gated = persistence_gate(
        (
            _draft(
                statement,
                evidence,
                kind="capability",
                signal_type="capability_evidence",
            ),
        ),
        capsule,
    )
    assert gated.accepted == ()
    assert gated.filtered_policy_count == 1


def test_security_skeleton_rejects_obfuscated_assistant_attribution():
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    evidence = "Result: You can reliably run React Ａs Alice Believes."
    statement = "The user can reliably run React Ａs Alice Believes."
    result = build_capsule(
        (_record("assistant", evidence, final=True),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    assert result.capsule.decisions_results == ()

    capsule = replace(result.capsule, decisions_results=(evidence,))
    gated = persistence_gate(
        (
            _draft(
                statement,
                evidence,
                mode="behavior_observed",
                kind="capability",
                signal_type="capability_evidence",
            ),
        ),
        capsule,
    )
    assert gated.accepted == ()
    assert gated.filtered_safety_count + gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    "signal",
    (
        "I must keep.",
        "I must store.",
        "I can reliably render.",
        "I can reliably run.",
        "My goal is to learn.",
        "I learned to apply.",
        "I learned to validate.",
    ),
)
def test_transitive_action_grammar_rejects_missing_complements(signal: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", signal),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()


def test_lowercase_user_signals_are_preserved_by_fixed_arity_grammar():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    signals = (
        "I prefer privacy.",
        "I avoid meetings.",
        "My goal is to learn rust.",
        "We must keep data.",
        "I can reliably run tests.",
        "I learned to validate packages.",
        "My principle is privacy.",
        "I identify as engineer.",
    )
    result = build_capsule(
        tuple(_record("user", signal) for signal in signals),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == signals


@pytest.mark.parametrize(
    ("text", "attribute"),
    (
        ("Decision: use privacy gate.", "decisions_results"),
        ("Method: follow review workflow.", "reusable_methods"),
        ("Next step: validate packages.", "next_steps"),
        ("Constraint: keep secrets in memory.", "decisions_results"),
    ),
)
def test_assistant_prefixes_use_closed_fixed_arity_productions(text, attribute):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("assistant", text, final=True),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert getattr(result.capsule, attribute) == (text,)


@pytest.mark.parametrize("surface", ("title", "user"))
def test_fullwidth_configured_label_is_scrubbed_before_both_hashes(surface: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    policy = CapsulePolicy(
        project_scope="project:stable",
        sensitive_labels=("ACME",),
    )

    def result(secret: str):
        if surface == "title":
            records = (
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "rollout-main",
                        "session_id": "task-main",
                        "title": f"Capture ＡＣＭＥ-{secret}",
                    },
                },
            )
        else:
            records = (_record("user", f"I prefer ＡＣＭＥ-{secret}."),)
        return build_capsule(records, _ref(), policy)

    left = result("FULLWIDTH_LABEL_ALPHA")
    right = result("UNRELATED_LABEL_BRAVO")

    assert left.source_fingerprint == right.source_fingerprint
    assert left.capsule_hash == right.capsule_hash
    assert left.counts == right.counts
    assert left.counts.scrubbed_secret_count == 1
    serialized = repr((left.capsule.to_mapping(), right.capsule.to_mapping()))
    assert "ＡＣＭＥ" not in serialized
    assert "FULLWIDTH_LABEL_ALPHA" not in serialized
    assert "UNRELATED_LABEL_BRAVO" not in serialized


def test_fullwidth_known_token_is_scrubbed_as_one_content_independent_unit():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    policy = CapsulePolicy(project_scope="project:stable")

    def result(token_tail: str):
        token = f"ｓｋ－ｐｒｏｊｅｃｔ{token_tail}"
        return build_capsule(
            (_record("user", f"I prefer {token}."),),
            _ref(),
            policy,
        )

    left = result("ＡＡＡＡＡＡＡＡＡＡＡＡＡＡＡＡＡＡＡＡＡＡＡＡ")
    right = result("ＢＢＢＢＢＢＢＢＢＢＢＢＢＢＢＢＢＢＢＢＢＢＢＢ")

    assert left.source_fingerprint == right.source_fingerprint
    assert left.capsule_hash == right.capsule_hash
    assert left.counts == right.counts
    assert left.counts.scrubbed_secret_count == 1
    assert left.capsule.user_signals == ()
    assert right.capsule.user_signals == ()


def test_persistence_rejects_fullwidth_capsule_policy_label():
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    result = build_capsule(
        (_record("user", "I prefer privacy."),),
        _ref(),
        CapsulePolicy(
            project_scope="project:stable",
            sensitive_labels=("ACME",),
        ),
    )
    evidence = "I prefer ＡＣＭＥ."
    capsule = replace(result.capsule, user_signals=(evidence,))
    gated = persistence_gate(
        (_draft("The user prefers ＡＣＭＥ.", evidence),),
        capsule,
    )

    assert gated.accepted == ()
    assert gated.filtered_safety_count == 1


@pytest.mark.parametrize(
    "modifier",
    ("whether", "lest", "until", "after", "whichever", "she", "Alice", "teams"),
)
def test_two_token_nominal_rejects_subject_or_subordinator_modifier(modifier: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", f"I prefer {modifier} workflows."),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()


@pytest.mark.parametrize("atom", ("mаybe", "mαybe", "whеnever", "ｗｈｅｎｅｖｅｒ"))
def test_atom_security_decision_is_stable_across_script_and_width_obfuscation(atom: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", f"I prefer {atom}."),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()


def test_structured_two_token_nominals_preserve_lowercase_user_signals():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    signals = (
        "I prefer concise responses.",
        "I prefer async communication.",
        "I avoid status meetings.",
        "I identify as backend engineer.",
        "My principle is privacy first.",
    )
    result = build_capsule(
        tuple(_record("user", signal) for signal in signals),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == signals


@pytest.mark.parametrize(
    ("text", "attribute"),
    (
        ("Decision: use privacy controls.", "decisions_results"),
        ("Method: follow code review.", "reusable_methods"),
        ("Next step: validate release package.", "next_steps"),
        ("Constraint: keep responses concise.", "decisions_results"),
        ("Constraint: keep credentials secure.", "decisions_results"),
    ),
)
def test_assistant_closed_productions_preserve_safe_two_token_phrases(text, attribute):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("assistant", text, final=True),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert getattr(result.capsule, attribute) == (text,)


@pytest.mark.parametrize(
    ("surface_prefix", "sensitive_labels"),
    (
        ("AСME", ("ACME",)),
        ("sƙ-projecttoken", ()),
    ),
)
def test_mixed_script_title_is_fixed_redaction_before_hashes(
    surface_prefix: str,
    sensitive_labels: tuple[str, ...],
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    policy = CapsulePolicy(
        project_scope="project:stable",
        sensitive_labels=sensitive_labels,
    )

    def result(secret: str):
        return build_capsule(
            (
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "rollout-main",
                        "session_id": "task-main",
                        "title": f"Capture {surface_prefix}-{secret}",
                    },
                },
            ),
            _ref(),
            policy,
        )

    left = result("MIXED_SCRIPT_ALPHA")
    right = result("UNRELATED_BRAVO_TAIL")

    assert left.source_fingerprint == right.source_fingerprint
    assert left.capsule_hash == right.capsule_hash
    assert left.counts == right.counts
    assert left.counts.scrubbed_secret_count == 1
    assert left.capsule.task_title is None
    assert right.capsule.task_title is None


def test_persistence_rejects_unlabelled_mixed_script_claim_as_policy_not_secret():
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    result = build_capsule(
        (_record("user", "I prefer privacy."),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    evidence = "I prefer AСME."
    capsule = replace(result.capsule, user_signals=(evidence,))
    gated = persistence_gate(
        (_draft("The user prefers AСME.", evidence),),
        capsule,
    )

    assert gated.accepted == ()
    assert gated.filtered_safety_count == 0
    assert gated.filtered_policy_count == 1


@pytest.mark.parametrize(
    "object_phrase",
    (
        "Vincent complains",
        "Laurent corrupts",
        "Clement matters",
        "client asserts",
        "component complains",
        "privacy matters",
    ),
)
def test_controlled_english_rejects_name_modifier_or_finite_verb_head(
    object_phrase: str,
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", f"I prefer {object_phrase}."),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()


@pytest.mark.parametrize("modifier", ("Vincent", "VINCENT", "vincent"))
def test_modifier_case_change_cannot_turn_a_rejected_name_into_acceptance(modifier: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", f"I prefer {modifier} responses."),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()


@pytest.mark.parametrize("finite_head", ("improves", "changes", "continues"))
def test_plural_profile_does_not_admit_unknown_third_person_verbs(finite_head: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", f"I prefer privacy {finite_head}."),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()


def test_controlled_english_preserves_representative_lowercase_user_signals():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    signals = (
        "I identify as software engineer.",
        "I identify as product manager.",
        "I prefer direct communication.",
        "I prefer plain language.",
        "I prefer brief answers.",
        "I prefer code review.",
        "We must keep data secure.",
    )
    result = build_capsule(
        tuple(_record("user", signal) for signal in signals),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == signals


@pytest.mark.parametrize(
    ("text", "attribute"),
    (
        ("Decision: use test coverage.", "decisions_results"),
        ("Constraint: keep data secure.", "decisions_results"),
        ("Method: follow team conventions.", "reusable_methods"),
        ("Next step: review error messages.", "next_steps"),
        ("Constraint: keep memory safe.", "decisions_results"),
    ),
)
def test_controlled_english_preserves_representative_assistant_phrases(text, attribute):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("assistant", text, final=True),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert getattr(result.capsule, attribute) == (text,)


@pytest.mark.parametrize(
    ("surface_prefix", "sensitive_labels"),
    (
        ("ѕƙ-ABCDEFGHIJKL", ()),
        ("ACME ТЕАМ", ("ACME TEAM",)),
    ),
)
def test_cross_atom_mixed_script_title_is_content_independent_redaction(
    surface_prefix: str,
    sensitive_labels: tuple[str, ...],
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    policy = CapsulePolicy(
        project_scope="project:stable",
        sensitive_labels=sensitive_labels,
    )

    def result(secret: str):
        return build_capsule(
            (
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "rollout-main",
                        "session_id": "task-main",
                        "title": f"Capture {surface_prefix} {secret}",
                    },
                },
            ),
            _ref(),
            policy,
        )

    left = result("CROSS_ATOM_ALPHA")
    right = result("UNRELATED_BRAVO_TAIL")

    assert left.source_fingerprint == right.source_fingerprint
    assert left.capsule_hash == right.capsule_hash
    assert left.counts == right.counts
    assert left.counts.scrubbed_secret_count == 1
    assert left.capsule.task_title is None
    assert right.capsule.task_title is None


def test_single_script_unicode_title_remains_eligible():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (
            {
                "type": "session_meta",
                "payload": {
                    "id": "rollout-main",
                    "session_id": "task-main",
                    "title": "研究计划",
                },
            },
        ),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.task_title == "研究计划"
    assert result.counts.scrubbed_secret_count == 0


def test_persistence_rejects_cross_atom_mixed_script_at_safety_gate():
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    result = build_capsule(
        (_record("user", "I prefer privacy."),),
        _ref(),
        CapsulePolicy(
            project_scope="project:stable",
            sensitive_labels=("TEAM",),
        ),
    )
    evidence = "I prefer privacy ТЕАМ."
    capsule = replace(result.capsule, user_signals=(evidence,))
    gated = persistence_gate(
        (_draft("The user prefers privacy ТЕАМ.", evidence),),
        capsule,
    )

    assert gated.accepted == ()
    assert gated.filtered_safety_count == 1


def test_all_caps_modifier_cannot_bypass_proper_name_rejection():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", "I prefer DOMINIC responses."),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()


@pytest.mark.parametrize(
    "finite_head",
    (
        "differs", "brings", "exists", "ensures", "manages", "advances",
        "previews", "offers", "clings", "persists", "secures", "damages",
        "enhances", "influences", "balances", "reviews",
    ),
)
def test_controlled_plural_profile_rejects_finite_verb_suffix_variants(
    finite_head: str,
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", f"I prefer privacy {finite_head}."),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()


def test_controlled_profile_preserves_additional_lowercase_user_signals():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    signals = (
        "I identify as frontend engineer.",
        "I identify as data scientist.",
        "I prefer clear explanations.",
        "I prefer short answers.",
        "I prefer written feedback.",
        "I prefer structured responses.",
    )
    result = build_capsule(
        tuple(_record("user", signal) for signal in signals),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == signals


@pytest.mark.parametrize(
    ("text", "attribute"),
    (
        ("Method: follow documented process.", "reusable_methods"),
        ("Next step: review failing tests.", "next_steps"),
        ("Constraint: keep messages short.", "decisions_results"),
        ("Constraint: keep output readable.", "decisions_results"),
    ),
)
def test_controlled_profile_preserves_additional_assistant_phrases(text, attribute):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("assistant", text, final=True),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert getattr(result.capsule, attribute) == (text,)


@pytest.mark.parametrize(
    ("surface_prefix", "sensitive_labels", "left_tail", "right_tail"),
    (
        (
            "ѕƙ-АВСЕНКМОРТХУ",
            (),
            "СЕКРЕТАЛЬФА",
            "ДРУГОЙХВОСТ",
        ),
        ("ТЕАМ", ("TEAM",), "СЕКРЕТАЛЬФА", "ДРУГОЙХВОСТ"),
        ("ΤΕΑΜ", ("TEAM",), "ΑΛΦΑ", "ΒΗΤΑ"),
    ),
)
def test_confusable_secret_title_is_content_independent_redaction(
    surface_prefix: str,
    sensitive_labels: tuple[str, ...],
    left_tail: str,
    right_tail: str,
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    policy = CapsulePolicy(
        project_scope="project:stable",
        sensitive_labels=sensitive_labels,
    )

    def result(secret: str):
        return build_capsule(
            (
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "rollout-main",
                        "session_id": "task-main",
                        "title": f"{surface_prefix} {secret}",
                    },
                },
            ),
            _ref(),
            policy,
        )

    left = result(left_tail)
    right = result(right_tail)

    assert left.source_fingerprint == right.source_fingerprint
    assert left.capsule_hash == right.capsule_hash
    assert left.counts == right.counts
    assert left.counts.scrubbed_secret_count == 1
    assert left.capsule.task_title is None
    assert right.capsule.task_title is None


def test_distinct_single_script_atoms_can_coexist_without_secret_redaction():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (
            {
                "type": "session_meta",
                "payload": {
                    "id": "rollout-main",
                    "session_id": "task-main",
                    "title": "Rust 项目",
                },
            },
        ),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.task_title == "Rust 项目"
    assert result.counts.scrubbed_secret_count == 0


def test_persistence_rejects_confusable_configured_label_at_safety_gate():
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    result = build_capsule(
        (_record("user", "I prefer privacy."),),
        _ref(),
        CapsulePolicy(
            project_scope="project:stable",
            sensitive_labels=("TEAM",),
        ),
    )
    evidence = "I prefer ТЕАМ."
    capsule = replace(result.capsule, user_signals=(evidence,))
    gated = persistence_gate(
        (_draft("The user prefers ТЕАМ.", evidence),),
        capsule,
    )

    assert gated.accepted == ()
    assert gated.filtered_safety_count == 1


@pytest.mark.parametrize("modifier", ("Dominic", "DOMINIC", "DoMiNiC", "dominic"))
def test_unknown_modifier_case_variants_cannot_enter_controlled_vocabulary(modifier: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", f"I prefer {modifier} responses."),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()


@pytest.mark.parametrize(
    "finite_head",
    (
        "functions", "mentions", "comments", "implements", "documents",
        "witnesses", "harnesses", "experiments", "augments", "laments",
        "fragments",
    ),
)
def test_controlled_vocabulary_rejects_generic_suffix_finite_heads(finite_head: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("user", f"I prefer privacy {finite_head}."),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()


def test_versioned_controlled_vocabulary_preserves_reviewed_user_signals():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    signals = (
        "I identify as security engineer.",
        "I identify as software architect.",
        "I prefer concise summaries.",
        "I prefer practical examples.",
        "I prefer detailed explanations.",
    )
    result = build_capsule(
        tuple(_record("user", signal) for signal in signals),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == signals


@pytest.mark.parametrize(
    ("text", "attribute"),
    (
        ("Method: follow established workflow.", "reusable_methods"),
        ("Next step: review generated output.", "next_steps"),
        ("Constraint: keep replies brief.", "decisions_results"),
    ),
)
def test_versioned_controlled_vocabulary_preserves_reviewed_assistant_phrases(
    text: str,
    attribute: str,
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record("assistant", text, final=True),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert getattr(result.capsule, attribute) == (text,)


@pytest.mark.parametrize(
    ("surface_prefix", "sensitive_labels", "left_tail", "right_tail"),
    (
        ("sƙ-ABCDEFGHIJKL", (), "ALPHA_SECRET", "BRAVO_TAIL"),
        ("ɡhp_ABCDEFGHIJKL", (), "ALPHA_SECRET", "BRAVO_TAIL"),
        ("ѕһеӏӏ", ("SHELL",), "АЛЬФА", "БРАВО"),
    ),
)
def test_unresolved_confusable_secret_shape_is_content_independent_redaction(
    surface_prefix: str,
    sensitive_labels: tuple[str, ...],
    left_tail: str,
    right_tail: str,
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    policy = CapsulePolicy(
        project_scope="project:stable",
        sensitive_labels=sensitive_labels,
    )

    def result(secret: str):
        return build_capsule(
            (
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "rollout-main",
                        "session_id": "task-main",
                        "title": f"{surface_prefix}{secret}",
                    },
                },
            ),
            _ref(),
            policy,
        )

    left = result(left_tail)
    right = result(right_tail)

    assert left.source_fingerprint == right.source_fingerprint
    assert left.capsule_hash == right.capsule_hash
    assert left.counts == right.counts
    assert left.counts.scrubbed_secret_count == 1
    assert left.capsule.task_title is None
    assert right.capsule.task_title is None


@pytest.mark.parametrize("label", ("ᴋ", "ѕһеӏӏ", "ɡhp"))
def test_policy_accepts_unicode_confusable_sensitive_label(label: str):
    from agc_runtime.capture_capsule import CapsulePolicy

    policy = CapsulePolicy(
        project_scope="project:stable",
        sensitive_labels=(label,),
    )

    assert 1 <= len(policy.sensitive_labels) <= 8
    assert policy.sensitive_labels == tuple(sorted(set(policy.sensitive_labels)))


@pytest.mark.parametrize("title", ("Rust项目", "C语言", "GPT模型", "Vue组件"))
def test_cjk_script_boundary_without_whitespace_remains_eligible(title: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (
            {
                "type": "session_meta",
                "payload": {
                    "id": "rollout-main",
                    "session_id": "task-main",
                    "title": title,
                },
            },
        ),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.task_title == title
    assert result.counts.scrubbed_secret_count == 0


def test_plain_cyrillic_without_labels_or_identifier_shape_remains_eligible():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    title = "Исследование"
    result = build_capsule(
        (
            {
                "type": "session_meta",
                "payload": {
                    "id": "rollout-main",
                    "session_id": "task-main",
                    "title": title,
                },
            },
        ),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.task_title == title
    assert result.counts.scrubbed_secret_count == 0


def test_user_methods_reuse_the_controlled_nominal_grammar_without_a_second_gate():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    signals = (
        "We use code review.",
        "I use test coverage.",
        "I follow test tooling.",
        "We reuse privacy controls.",
    )
    result = build_capsule(
        tuple(_record("user", signal) for signal in signals),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == signals


@pytest.mark.parametrize(
    ("role", "text"),
    (
        ("user", "I prefer sƙ-ABCDEFGHIJKL."),
        ("assistant", "Result: ɡhp_ABCDEFGHIJKL."),
    ),
)
def test_unresolved_confusable_risk_is_shared_by_user_and_assistant_units(
    role: str,
    text: str,
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (_record(role, text, final=role == "assistant"),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == ()
    assert result.capsule.decisions_results == ()
    assert result.counts.scrubbed_secret_count == 1


def test_persistence_rejects_unresolved_confusable_identifier_shape():
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    result = build_capsule(
        (_record("user", "I prefer privacy."),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )
    evidence = "I prefer sƙ-ABCDEFGHIJKL."
    capsule = replace(result.capsule, user_signals=(evidence,))
    gated = persistence_gate(
        (_draft("The user prefers sƙ-ABCDEFGHIJKL.", evidence),),
        capsule,
    )

    assert gated.accepted == ()
    assert gated.filtered_safety_count == 1


def test_generated_unicode_confusables_provenance_and_key_mappings():
    from agc_runtime._unicode_confusables import (
        GENERATOR_PYTHON_VERSION,
        GENERATOR_UNIDATA_VERSION,
        OFFICIAL_DIRECT_ASCII,
        RAW_CONFUSABLE_CLOSURE,
        SOURCE_SHA256,
        SOURCE_URL,
        UNICODE_SECURITY_VERSION,
    )

    assert UNICODE_SECURITY_VERSION == "17.0.0"
    assert SOURCE_URL == (
        "https://www.unicode.org/Public/17.0.0/security/confusables.txt"
    )
    assert SOURCE_SHA256 == (
        "091c7f82fc39ef208faf8f94d29c244de99254675e09de163160c810d13ef22a"
    )
    assert GENERATOR_PYTHON_VERSION == "3.12.13"
    assert GENERATOR_UNIDATA_VERSION == "15.0.0"
    assert RAW_CONFUSABLE_CLOSURE[ord("Ꮪ")] == "S"
    assert RAW_CONFUSABLE_CLOSURE[ord("Ꮶ")] == "K"
    assert RAW_CONFUSABLE_CLOSURE[ord("ƙ")] == "k\u0314"
    assert RAW_CONFUSABLE_CLOSURE[ord("ɠ")] == "g\u0314"
    assert RAW_CONFUSABLE_CLOSURE[ord("ƥ")] == "p\u0314"
    assert RAW_CONFUSABLE_CLOSURE[ord("ƽ")] == "s"
    assert OFFICIAL_DIRECT_ASCII[ord("ƙ")] == "k"
    assert OFFICIAL_DIRECT_ASCII[ord("ɠ")] == "g"


def test_all_official_direct_ascii_rows_match_runtime_without_exceptions():
    from agc_runtime._unicode_confusables import (
        OFFICIAL_DIRECT_ASCII,
        RAW_CONFUSABLE_CLOSURE,
    )
    from agc_runtime.capture_capsule import _confusable_skeleton
    from scripts.generate_unicode_confusables import _post_mapping_normalize

    assert len(OFFICIAL_DIRECT_ASCII) == 2139
    assert {
        source: expected
        for source, target in RAW_CONFUSABLE_CLOSURE.items()
        if (expected := _post_mapping_normalize(target)).isascii() and expected
    } == dict(OFFICIAL_DIRECT_ASCII)
    mismatches = {
        source: (_confusable_skeleton(chr(source)), expected)
        for source, expected in OFFICIAL_DIRECT_ASCII.items()
        if _confusable_skeleton(chr(source)) != expected
    }
    assert mismatches == {}


def test_unicode_confusable_generator_rejects_cycles():
    from scripts.generate_unicode_confusables import _resolve_raw_closure

    with pytest.raises(ValueError, match="confusable mapping cycle"):
        _resolve_raw_closure({ord("a"): "b", ord("b"): "a"})


def test_unicode_confusable_generator_rejects_duplicate_raw_keys():
    from scripts.generate_unicode_confusables import _raw_mapping_from_rows

    with pytest.raises(ValueError, match="duplicate confusable source"):
        _raw_mapping_from_rows(((0x0199, "k"), (0x0199, "q")))


def test_unicode_confusable_generator_rejects_unpinned_toolchain():
    from scripts.generate_unicode_confusables import _require_pinned_toolchain

    with pytest.raises(
        ValueError,
        match="^unicode_confusables_generator_toolchain_mismatch$",
    ) as caught:
        _require_pinned_toolchain(
            python_version="3.13.0",
            unidata_version="16.0.0",
        )

    assert repr(caught.value) == (
        "ValueError('unicode_confusables_generator_toolchain_mismatch')"
    )


def test_unicode_license_v3_notice_is_complete_and_packaged():
    from importlib.resources import files

    notice = files("agc_runtime").joinpath("UNICODE-LICENSE.txt").read_text("utf-8")

    assert "SPDX-License-Identifier: Unicode-3.0" in notice
    assert "UNICODE LICENSE V3" in notice
    assert "COPYRIGHT AND PERMISSION NOTICE" in notice
    assert "Permission is hereby granted, free of charge" in notice
    assert 'THE DATA FILES AND SOFTWARE ARE PROVIDED "AS IS"' in notice
    assert "IN NO EVENT SHALL THE COPYRIGHT HOLDER" in notice
    assert "without prior written authorization of the copyright holder" in " ".join(
        notice.split()
    )
    assert 'agc_runtime = ["default_config.yaml", "UNICODE-LICENSE.txt"]' in (
        Path("pyproject.toml").read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    ("surface_prefix", "sensitive_labels"),
    (
        ("ᏚᏦ-ABCDEFGHIJKL", ()),
        ("sƙ-ABCDEFGHIJKL", ()),
        ("ɡhp_ABCDEFGHIJKL", ()),
        ("ɠhp_ABCDEFGHIJKL", ()),
        ("ѕƙ-ABCDEFGHIJKL", ()),
        ("ｓｋ-ABCDEFGHIJKL", ()),
        ("ѕһеӏӏ", ("SHELL",)),
    ),
)
def test_unicode_17_confusable_secret_matches_are_content_independent(
    surface_prefix: str,
    sensitive_labels: tuple[str, ...],
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    policy = CapsulePolicy(
        project_scope="project:stable",
        sensitive_labels=sensitive_labels,
    )

    def result(secret: str):
        return build_capsule(
            (
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "rollout-main",
                        "session_id": "task-main",
                        "title": f"{surface_prefix}{secret}",
                    },
                },
            ),
            _ref(),
            policy,
        )

    left = result("ALPHA_SECRET")
    right = result("BRAVO_TAIL")

    assert left.source_fingerprint == right.source_fingerprint
    assert left.capsule_hash == right.capsule_hash
    assert left.counts == right.counts
    assert left.counts.scrubbed_secret_count == 1
    assert left.capsule.task_title is None
    assert right.capsule.task_title is None


@pytest.mark.parametrize(
    "title",
    (
        "Łódź",
        "Æsir",
        "Исследование",
        "Ελληνικά",
        "Rust项目",
        "ᴋA α",
        "AСME notes",
    ),
)
def test_normal_unicode_title_without_secret_match_is_preserved(title: str):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    result = build_capsule(
        (
            {
                "type": "session_meta",
                "payload": {
                    "id": "rollout-main",
                    "session_id": "task-main",
                    "title": title,
                },
            },
        ),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.task_title == title
    assert result.counts.scrubbed_secret_count == 0


@pytest.mark.parametrize("label", ("Łódź", "Æsir", "Команда", "Ομάδα"))
def test_normal_unicode_sensitive_labels_are_valid_policy_inputs(label: str):
    from agc_runtime.capture_capsule import CapsulePolicy

    policy = CapsulePolicy(
        project_scope="project:stable",
        sensitive_labels=(label,),
    )

    assert 1 <= len(policy.sensitive_labels) <= 8
    assert policy.sensitive_labels == tuple(sorted(set(policy.sensitive_labels)))


def test_generated_raw_closure_is_a_fixed_point_for_every_target():
    from agc_runtime._unicode_confusables import RAW_CONFUSABLE_CLOSURE

    assert all(
        "".join(
            RAW_CONFUSABLE_CLOSURE.get(ord(character), character)
            for character in target
        )
        == target
        for target in RAW_CONFUSABLE_CLOSURE.values()
    )


@pytest.mark.parametrize(
    ("surface", "expected"),
    (("ſ", "f"), ("Μ", "m"), ("［", "("), ("］", ")")),
)
def test_runtime_preserves_representative_raw_first_mapping_categories(
    surface: str,
    expected: str,
):
    from agc_runtime.capture_capsule import _confusable_skeleton

    assert _confusable_skeleton(surface) == expected


def test_greek_lunate_sigma_label_scrubs_title_before_both_hashes():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    policy = CapsulePolicy(
        project_scope="project:stable",
        sensitive_labels=("COMPANY",),
    )

    def result(secret: str):
        return build_capsule(
            (
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "rollout-main",
                        "session_id": "task-main",
                        "title": f"ϲOMPANY {secret}",
                    },
                },
            ),
            _ref(),
            policy,
        )

    left = result("ALPHA_SECRET")
    right = result("BRAVO_TAIL")

    assert left.source_fingerprint == right.source_fingerprint
    assert left.capsule_hash == right.capsule_hash
    assert left.counts == right.counts
    assert left.counts.scrubbed_secret_count == 1
    assert left.capsule.task_title is None


def test_greek_lunate_sigma_label_is_rejected_at_persistence_gate():
    from dataclasses import replace

    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    result = build_capsule(
        (_record("user", "I prefer privacy."),),
        _ref(),
        CapsulePolicy(
            project_scope="project:stable",
            sensitive_labels=("C",),
        ),
    )
    evidence = "I prefer ϲ."
    capsule = replace(result.capsule, user_signals=(evidence,))
    gated = persistence_gate(
        (_draft("The user prefers ϲ.", evidence),),
        capsule,
    )

    assert gated.accepted == ()
    assert gated.filtered_safety_count == 1


_CASE_EQUIVALENT_SENSITIVE_FAMILIES = (
    (("m", "M"), ("m", "M", "Μ", "ｍ", "Ｍ")),
    (
        ("team", "TEAM", "Team"),
        ("team", "TEAM", "Team", "ΤΕΑΜ", "ｔｅａｍ", "ＴＥＡＭ"),
    ),
    (
        ("memory", "MEMORY", "Memory"),
        (
            "memory",
            "MEMORY",
            "Memory",
            "ΜΕΜΟRΥ",
            "ｍｅｍｏｒｙ",
            "ＭＥＭＯＲＹ",
        ),
    ),
)


@pytest.mark.parametrize(
    ("label_variants", "text_variants"),
    _CASE_EQUIVALENT_SENSITIVE_FAMILIES,
)
def test_sensitive_label_case_variants_store_each_complete_candidate_union(
    label_variants: tuple[str, ...],
    text_variants: tuple[str, ...],
):
    from agc_runtime.capture_capsule import CapsulePolicy, _sensitive_candidates

    for label in label_variants:
        policy = CapsulePolicy(
            project_scope="project:stable",
            sensitive_labels=(label,),
        )

        assert policy.sensitive_labels == _sensitive_candidates(label)
        assert 1 <= len(policy.sensitive_labels) <= 8


@pytest.mark.parametrize(
    ("label_variants", "text_variants"),
    _CASE_EQUIVALENT_SENSITIVE_FAMILIES,
)
def test_sensitive_label_case_and_unicode_variants_scrub_title_before_both_hashes(
    label_variants: tuple[str, ...],
    text_variants: tuple[str, ...],
):
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    for label in label_variants:
        policy = CapsulePolicy(
            project_scope="project:stable",
            sensitive_labels=(label,),
        )
        for surface in text_variants:
            def result(secret_tail: str):
                return build_capsule(
                    (
                        {
                            "type": "session_meta",
                            "payload": {
                                "id": "rollout-main",
                                "session_id": "task-main",
                                "title": f"{surface} {secret_tail}",
                            },
                        },
                    ),
                    _ref(),
                    policy,
                )

            left = result("ALPHA_SECRET")
            right = result("BRAVO_TAIL")

            assert left.source_fingerprint == right.source_fingerprint
            assert left.capsule_hash == right.capsule_hash
            assert left.counts == right.counts
            assert left.counts.scrubbed_secret_count == 1
            assert left.capsule.task_title is None
            assert right.capsule.task_title is None


@pytest.mark.parametrize(
    ("label_variants", "text_variants"),
    _CASE_EQUIVALENT_SENSITIVE_FAMILIES,
)
def test_sensitive_label_detection_is_symmetric_at_the_persistence_boundary(
    label_variants: tuple[str, ...],
    text_variants: tuple[str, ...],
):
    from agc_runtime.capture_capsule import CapsulePolicy
    from agc_runtime.capture_safety import _contains_sensitive_label

    for label in label_variants:
        stored = CapsulePolicy(
            project_scope="project:stable",
            sensitive_labels=(label,),
        ).sensitive_labels
        for surface in text_variants:
            assert _contains_sensitive_label(surface, stored)


@pytest.mark.parametrize(
    "value",
    tuple(
        variant
        for family in _CASE_EQUIVALENT_SENSITIVE_FAMILIES
        for variants in family
        for variant in variants
    ),
)
def test_sensitive_candidates_are_bounded_sorted_unique_and_deterministic(value: str):
    import agc_runtime.capture_capsule as capture_capsule

    helper = getattr(capture_capsule, "_sensitive_candidates", None)

    assert callable(helper)
    first = helper(value)
    second = helper(value)
    assert first == second
    assert first == tuple(sorted(set(first)))
    assert all(first)
    assert 1 <= len(first) <= 8


_PARTIAL_EMPTY_SINGLE_CODEPOINT_LABELS = (
    "\u00af",  # MACRON
    "\u00b4",  # ACUTE ACCENT
    "\u00b8",  # CEDILLA
    "\u02d8",  # BREVE
    "\u02d9",  # DOT ABOVE
    "\u02da",  # RING ABOVE
    "\u02db",  # OGONEK
    "\u02dc",  # SMALL TILDE
    "\u02dd",  # DOUBLE ACUTE ACCENT
    "\u0345",  # COMBINING GREEK YPOGEGRAMMENI
    "\u037a",  # GREEK YPOGEGRAMMENI
    "\u0384",  # GREEK TONOS
    "\u1fbd",  # GREEK KORONIS
    "\u1fbf",  # GREEK PSILI
    "\u1fc0",  # GREEK PERISPOMENI
    "\u1ffd",  # GREEK OXIA
    "\u1ffe",  # GREEK DASIA
    "\u203e",  # OVERLINE
    "\ufe49",  # DASHED OVERLINE
    "\ufe4a",  # CENTRELINE OVERLINE
    "\ufe4b",  # WAVY OVERLINE
    "\ufe4c",  # DOUBLE WAVY OVERLINE
    "\uffe3",  # FULLWIDTH MACRON
)


def _candidate_view_oracle(value: str) -> tuple[str, ...]:
    import re
    import unicodedata

    from agc_runtime.capture_capsule import _confusable_skeleton

    variants = (value, value.lower(), value.upper(), value.casefold())
    security_inputs = (
        *variants,
        *(unicodedata.normalize("NFKC", variant) for variant in variants),
    )
    return tuple(
        re.sub(r"\s+", " ", _confusable_skeleton(candidate)).strip()
        for candidate in security_inputs
    )


@pytest.mark.parametrize("label", _PARTIAL_EMPTY_SINGLE_CODEPOINT_LABELS)
def test_capsule_policy_rejects_labels_with_any_empty_committed_candidate_view(
    label: str,
):
    from agc_runtime.capture_capsule import CapsulePolicy

    views = _candidate_view_oracle(label)
    assert any(not view for view in views)
    assert any(views)
    with pytest.raises(ValueError, match="capture_capsule_contract_invalid"):
        CapsulePolicy(project_scope="project:stable", sensitive_labels=(label,))


def test_full_unicode_non_control_single_codepoint_partial_empty_boundary_is_closed():
    import sys
    import unicodedata

    from agc_runtime.capture_capsule import CapsulePolicy

    vulnerable: list[str] = []
    for codepoint in range(sys.maxunicode + 1):
        label = chr(codepoint)
        if unicodedata.category(label).startswith("C"):
            continue
        views = _candidate_view_oracle(label)
        if any(not view for view in views) and any(views):
            vulnerable.append(label)

    assert tuple(vulnerable) == _PARTIAL_EMPTY_SINGLE_CODEPOINT_LABELS
    for label in vulnerable:
        with pytest.raises(ValueError, match="capture_capsule_contract_invalid"):
            CapsulePolicy(project_scope="project:stable", sensitive_labels=(label,))


def test_shared_candidate_views_preserve_empty_positions_and_drive_text_candidates():
    import agc_runtime.capture_capsule as capture_capsule

    helper = getattr(capture_capsule, "_sensitive_candidate_views", None)
    assert callable(helper)

    for value in (*_PARTIAL_EMPTY_SINGLE_CODEPOINT_LABELS, "privacy", "TEAM"):
        views = helper(value)
        assert views == _candidate_view_oracle(value)
        assert len(views) == 8
        assert capture_capsule._sensitive_candidates(value) == tuple(
            sorted({candidate for candidate in views if candidate})
        )


@pytest.mark.parametrize("text", _PARTIAL_EMPTY_SINGLE_CODEPOINT_LABELS)
def test_empty_text_candidate_views_never_match_a_nonempty_sensitive_label(text: str):
    from agc_runtime.capture_capsule import CapsulePolicy
    from agc_runtime.capture_safety import _contains_sensitive_label

    labels = CapsulePolicy(
        project_scope="project:stable",
        sensitive_labels=("privacy",),
    ).sensitive_labels

    assert not _contains_sensitive_label(text, labels)
