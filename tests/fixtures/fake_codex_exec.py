"""Real fake Codex executable for isolated Capture extractor tests."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


REQUIRED_FLAGS = (
    "--ephemeral",
    "--ignore-user-config",
    "--ignore-rules",
    "--sandbox",
    "--output-schema",
    "--json",
    "-",
)
RAW_SENTINEL = "RAW_PROCESS_SECRET_SENTINEL"


def _emit(value: object) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _fail(code: int = 91) -> "None":
    sys.stderr.write(RAW_SENTINEL)
    sys.stderr.flush()
    raise SystemExit(code)


def _draft(index: int = 0) -> dict[str, object]:
    return {
        "statement": "The user prefers privacy.",
        "assertion": {
            "subject": "user",
            "mode": "direct",
            "modality": "asserted",
        },
        "primary_category": "personal_growth",
        "kind": "preference",
        "scopes": ["global"],
        "project_scope": "project:stable",
        "confidence": "confirmed",
        "sensitivity": "normal",
        "signal_type": "explicit_user_state",
        "evidence": ["I prefer privacy."],
        "priority": 1,
        "locator": f"user:{index + 1:04d}",
    }


def _payload(scenario: str) -> dict[str, object]:
    count = {"zero": 0, "eight": 8, "over-eight": 9}.get(scenario, 1)
    payload: dict[str, object] = {
        "schema_version": "capture-extractor-v1",
        "drafts": [_draft(index) for index in range(count)],
    }
    if scenario == "missing-field":
        payload.pop("schema_version")
    elif scenario == "unknown-field":
        payload["raw_model_output"] = RAW_SENTINEL
    elif scenario.startswith("draft-"):
        draft = payload["drafts"][0]  # type: ignore[index]
        if scenario == "draft-missing":
            draft.pop("kind")  # type: ignore[union-attr]
        elif scenario == "draft-unknown":
            draft["unknown"] = RAW_SENTINEL  # type: ignore[index]
        elif scenario == "draft-enum":
            draft["kind"] = "unknown"  # type: ignore[index]
        elif scenario == "draft-type":
            draft["statement"] = ["not", "text"]  # type: ignore[index]
        elif scenario == "draft-bool":
            draft["priority"] = True  # type: ignore[index]
        elif scenario == "draft-nan":
            draft["priority"] = float("nan")  # type: ignore[index]
        elif scenario == "draft-surrogate":
            draft["statement"] = "private-\ud800-tail"  # type: ignore[index]
    return payload


def _scenario(arguments: list[str]) -> str:
    if "--model" not in arguments:
        return "one"
    position = arguments.index("--model")
    return arguments[position + 1]


def _validate_exec(arguments: list[str]) -> tuple[str, dict[str, object]]:
    if arguments[:1] != ["exec"]:
        _fail()
    expected = [
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox",
        "read-only",
        "--output-schema",
    ]
    if arguments[: len(expected)] != expected:
        _fail()
    schema_index = len(expected)
    if schema_index >= len(arguments) or not Path(arguments[schema_index]).is_file():
        _fail()
    remainder = arguments[schema_index + 1 :]
    if remainder == ["--json", "-"]:
        pass
    elif (
        len(remainder) == 4
        and remainder[0] == "--json"
        and remainder[1] == "--model"
        and remainder[2]
        and remainder[3] == "-"
    ):
        pass
    else:
        _fail()
    if os.listdir("."):
        _fail()
    forbidden = {
        "CODEX_HOME",
        "PYTHONPATH",
        "PYTHONHOME",
        "CLAUDECODE",
        "AGENT_GLOBAL_CONTEXT_ROOT",
    }
    if any(key in forbidden or key.startswith("AGC_") for key in os.environ):
        _fail()
    try:
        capsule = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        _fail()
    if not isinstance(capsule, dict):
        _fail()
    if capsule != {"schema_version": "capture-probe-v1"} and "CAPSULE_ONLY_SENTINEL" not in json.dumps(
        capsule, ensure_ascii=True
    ):
        _fail()
    if "CAPSULE_ONLY_SENTINEL" in " ".join(os.environ.values()):
        _fail()
    return _scenario(arguments), capsule


def main() -> int:
    arguments = sys.argv[1:]
    executable_name = Path(sys.argv[0]).stem.casefold()
    if arguments == ["--version"]:
        if "version_fail" in executable_name:
            return 7
        print("codex-fake 1.2.3")
        return 0
    if arguments == ["exec", "--help"]:
        flags = list(REQUIRED_FLAGS)
        if "missing_flag" in executable_name:
            flags.remove("--ignore-rules")
        if "missing_stdin" in executable_name:
            flags.remove("-")
        print(" ".join(flags) + " read-only")
        return 0

    if _scenario(arguments) == "stdin-block":
        time.sleep(5)
        return 0

    scenario, capsule = _validate_exec(arguments)
    is_probe = capsule == {"schema_version": "capture-probe-v1"}
    if "smoke_fail" in executable_name and is_probe:
        _fail(8)
    if scenario == "timeout":
        time.sleep(5)
        return 0
    if scenario == "nonzero":
        _fail(7)
    if scenario == "huge-stdout":
        sys.stdout.write("X" * (2 * 1024 * 1024))
        sys.stdout.flush()
        return 0
    if scenario == "huge-stderr":
        sys.stderr.write("Y" * (2 * 1024 * 1024))
        sys.stderr.flush()
        return 0
    if scenario == "malformed-jsonl":
        sys.stdout.write("{malformed " + RAW_SENTINEL + "\n")
        sys.stdout.flush()
        return 0
    if scenario == "unknown-event":
        _emit({"type": "private.event", "content": RAW_SENTINEL})

    if scenario == "realistic-events" or (
        is_probe and "missing_metadata" in executable_name
    ):
        _emit({"type": "thread.started", "thread_id": "fake-thread"})
        if scenario == "realistic-events":
            _emit({"type": "turn.started"})
            _emit(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item-reasoning",
                        "type": "reasoning",
                        "text": RAW_SENTINEL,
                    },
                }
            )
    else:
        _emit(
            {
                "type": "thread.started",
                "thread_id": "fake-thread",
                "model": "fake-model",
                "provider": "fake-provider",
                "auth_available": True,
                "sandbox": "read-only",
            }
        )
    payload = {"schema_version": "capture-extractor-v1", "drafts": []} if is_probe else _payload(scenario)
    final_event = {
        "type": "item.completed",
        "item": {
            "id": "item-final",
            "type": "agent_message",
            "text": json.dumps(payload, ensure_ascii=True, allow_nan=True),
        },
    }
    _emit(final_event)
    if scenario == "multiple-final":
        _emit(final_event)
    if scenario != "usage-absent":
        usage: dict[str, object] = {
            "input_tokens": 11,
            "output_tokens": 7,
            "total_tokens": 18,
        }
        if scenario == "realistic-events":
            usage = {
                "input_tokens": 11,
                "cached_input_tokens": 3,
                "output_tokens": 7,
            }
        if scenario == "usage-partial":
            usage.pop("output_tokens")
        _emit({"type": "turn.completed", "usage": usage})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
