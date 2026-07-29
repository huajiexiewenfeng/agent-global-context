import json
from dataclasses import replace
from pathlib import Path

from agc_runtime.models import MemoryItem


def direct_preference_request() -> dict:
    fixture = Path(__file__).parent / "fixtures" / "active-principle.md"
    principle = MemoryItem.from_markdown(fixture.read_text(encoding="utf-8"))
    preference = replace(
        principle,
        id="implementation-plan-first",
        kind="preference",
        subkind="collaboration",
        recall=replace(
            principle.recall,
            decision_impact="medium",
            exposure="scoped_card",
            scopes=("work", "writing"),
            applies_when=("implementation",),
            not_when=("trivial_task",),
        ),
        memory_card="复杂改动先确认实施计划",
        full_meaning="面对复杂改动时，用户偏好先形成清晰计划，再持续推进实现。",
        application_boundary="简单、低风险且可逆的修改无需增加流程。",
        rationale="这会直接改善协作效率。",
    )
    return {
        "action": "observe",
        "observation": {
            "observation_id": "implementation-plan-first-observation",
            "source": {
                "ref": "codex-task:e2e",
                "revision": "r1",
                "content_hash": "a" * 64,
                "observed_at": "2026-07-29T00:00:00Z",
            },
            "assertion": {
                "subject": "user",
                "mode": "direct",
                "modality": "asserted",
            },
            "proposal": {
                "disposition": "new",
                "match_memory_id": None,
                "kind": "preference",
                "scopes": ["work", "writing"],
                "temporal_type": "durable",
                "sensitivity": "normal",
                "rationale": "Changes future collaboration.",
                "requested_confidence": "confirmed",
            },
            "evidence": {
                "count": 1,
                "distinct_sessions": 1,
                "time_span_days": 0,
            },
        },
        "memory_markdown": preference.to_markdown(),
    }


def test_init_write_rebuild_read_forget(tmp_path: Path, cli):
    root = tmp_path / "memory"

    assert cli("admin", root, {"action": "init"})["status"] == "accepted"
    assert cli("write", root, direct_preference_request())["status"] == "accepted"
    assert cli("admin", root, {"action": "rebuild_catalog"})["data"][
        "memory_count"
    ] == 1
    assert cli(
        "read",
        root,
        {"action": "search", "filters": {"kind": ["preference"]}},
    )["data"]["items"][0]["id"] == "implementation-plan-first"
    removed = cli(
        "write",
        root,
        {
            "action": "forget",
            "memory_id": "implementation-plan-first",
            "suppression_scope": "collaboration_preferences",
            "authorization": "explicit_user_request",
            "verification_terms": ["复杂改动先确认实施计划"],
        },
    )

    assert removed["status"] == "accepted"
    assert cli(
        "read",
        root,
        {"action": "search", "filters": {"kind": ["preference"]}},
    )["data"]["items"] == []


def test_policy_rejection_is_a_handled_zero_exit(
    tmp_path: Path, run_cli
):
    request = direct_preference_request()
    request["observation"]["proposal"]["sensitivity"] = "sensitive"

    result = run_cli(
        "write",
        "--root",
        str(tmp_path / "memory"),
        "--input",
        "-",
        stdin=json.dumps(request, ensure_ascii=False),
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "rejected_policy"


def test_malformed_json_is_machine_readable_exit_two(
    tmp_path: Path, run_cli
):
    result = run_cli(
        "read",
        "--root",
        str(tmp_path / "memory"),
        "--input",
        "-",
        stdin="{",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "invalid_json"


def test_io_failure_is_exit_one(tmp_path: Path, run_cli):
    root_file = tmp_path / "not-a-directory"
    root_file.write_text("occupied", encoding="utf-8")

    result = run_cli(
        "admin",
        "--root",
        str(root_file),
        "--input",
        "-",
        stdin='{"action":"init"}',
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "admin_failed"


def test_json_file_input_is_supported(tmp_path: Path, run_cli):
    root = tmp_path / "memory"
    request_file = tmp_path / "request.json"
    request_file.write_text('{"action":"init"}\n', encoding="utf-8")

    result = run_cli(
        "admin",
        "--root",
        str(root),
        "--input",
        str(request_file),
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "accepted"
