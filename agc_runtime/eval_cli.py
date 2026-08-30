"""Explicitly authorized AGC Capture-quality Eval Pilot CLI."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from agc_runtime import __version__
from agc_runtime.capture_eval_adapter import (
    AGCCaptureEvidenceResolver,
    capture_eval_cases,
)
from agc_runtime.capture_eval_evidence import canonical_sha256
from agc_runtime.codex_command import resolve_codex_command
from agc_runtime.contracts import ToolResponse
from agc_runtime.paths import MemoryPaths
from agc_runtime.runtime_config import CaptureConfig, load_runtime_config

_TOOL = "agc.eval"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PROFILE_REF = {"id": "agc.capture-quality", "version": "1"}


def _emit(response: ToolResponse, exit_code: int) -> int:
    sys.stdout.write(
        json.dumps(response.to_dict(), ensure_ascii=True, sort_keys=True) + "\n"
    )
    return exit_code


def _failure(action: str, code: str, message: str, exit_code: int) -> int:
    return _emit(
        ToolResponse(
            tool=_TOOL,
            action=action,
            status="failed",
            error={"code": code, "message": message},
        ),
        exit_code,
    )


def _load_profile() -> dict[str, Any]:
    path = Path(__file__).with_name("eval_profiles") / "agc-capture-quality.v1.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("profile_id") != _PROFILE_REF["id"]
        or value.get("profile_version") != _PROFILE_REF["version"]
    ):
        raise ValueError("capture_eval_profile_invalid")
    return value


def _capture_cases(
    *, paths: MemoryPaths, trace_db: Path, max_items: int
) -> tuple[dict[str, Any], ...]:
    from agent_trace_runtime import EventStore, TraceService, resolve_db_path

    service = TraceService(EventStore(resolve_db_path(trace_db)))
    if not service.preflight("optional").ok:
        raise RuntimeError("capture_eval_trace_unavailable")
    return capture_eval_cases(
        service,
        _PROFILE_REF,
        __version__,
        max_items,
    )


def _judge_binding(capture: CaptureConfig) -> dict[str, object]:
    if capture.extractor.executable != "codex-app" or not capture.extractor.model:
        raise ValueError("capture_eval_runtime_unsupported")
    command = resolve_codex_command(capture.extractor.executable)
    return {
        "provider": "openai",
        "model": capture.extractor.model,
        "executable_identity": canonical_sha256(
            {"command": list(command)}
        ).removeprefix("sha256:"),
        "command": command,
    }


def _authorization_payload(
    cases: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
    binding: Mapping[str, object],
    max_items: int,
) -> dict[str, Any]:
    return {
        "profile_ref": _PROFILE_REF,
        "profile_digest": canonical_sha256(profile),
        "provider": binding["provider"],
        "model": binding["model"],
        "executable_identity": binding["executable_identity"],
        "case_digests": [canonical_sha256(item) for item in cases],
        "evidence_digests": [
            item["evidence_refs"][0]["digest"] for item in cases
        ],
        "max_items": max_items,
    }


def _authorization_digest(
    cases: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
    binding: Mapping[str, object],
    max_items: int,
) -> str:
    return canonical_sha256(
        _authorization_payload(cases, profile, binding, max_items)
    ).removeprefix("sha256:")


def _evaluate_cases(
    *,
    paths: MemoryPaths,
    capture: CaptureConfig,
    cases: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
    binding: Mapping[str, object],
    eval_db: Path,
) -> tuple[dict[str, Any], ...]:
    from agent_eval_codex import CodexJsonJudge
    from agent_eval_runtime import EvalService, EvalStore
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    adapters = tuple(CodexSourceAdapter(Path(item)) for item in capture.sources)
    resolver = AGCCaptureEvidenceResolver(paths=paths, adapters=adapters)
    judge = CodexJsonJudge(
        executable=binding["command"],
        model=binding["model"],
        provider=binding["provider"],
    )
    service = EvalService()
    store = EvalStore(eval_db)
    return tuple(
        service.evaluate(
            case=case,
            profile=profile,
            resolver=resolver,
            judge=judge,
            store=store,
        )
        for case in cases
    )


def _parse(arguments: Sequence[str]) -> dict[str, Any] | None:
    values = list(arguments)
    if (
        len(values) == 7
        and values[0] == "prepare-capture"
        and values[1] == "--root"
        and values[3] == "--trace-db"
        and values[5] == "--max-items"
    ):
        try:
            maximum = int(values[6])
        except ValueError:
            return None
        if values[2] and values[4] and 1 <= maximum <= 100:
            return {
                "action": values[0],
                "root": Path(values[2]),
                "trace_db": Path(values[4]),
                "max_items": maximum,
            }
    if (
        len(values) == 11
        and values[0] == "capture"
        and values[1] == "--root"
        and values[3] == "--trace-db"
        and values[5] == "--eval-db"
        and values[7] == "--max-items"
        and values[9] == "--authorization-digest"
    ):
        try:
            maximum = int(values[8])
        except ValueError:
            return None
        if (
            values[2]
            and values[4]
            and values[6]
            and 1 <= maximum <= 100
            and _DIGEST.fullmatch(values[10]) is not None
        ):
            return {
                "action": values[0],
                "root": Path(values[2]),
                "trace_db": Path(values[4]),
                "eval_db": Path(values[6]),
                "max_items": maximum,
                "authorization_digest": values[10],
            }
    return None


def _summary(
    results: Sequence[Mapping[str, Any]],
    binding: Mapping[str, object],
) -> dict[str, Any]:
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for result in results:
        current = result.get("usage")
        if isinstance(current, Mapping):
            for name in usage:
                value = current.get(name)
                if type(value) is int and value >= 0:
                    usage[name] += value
    return {
        "evaluated_count": len(results),
        "status_counts": dict(sorted(Counter(item["status"] for item in results).items())),
        "result_ids": [item["result_id"] for item in results],
        "profile_ref": _PROFILE_REF,
        "judge": {
            "provider": binding["provider"],
            "model": binding["model"],
            "executable_identity": binding["executable_identity"],
        },
        "usage": usage,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parsed = _parse(sys.argv[1:] if argv is None else argv)
    if parsed is None:
        return _failure("unknown", "invalid_input", "Command arguments are invalid", 2)
    action = parsed["action"]
    try:
        paths = MemoryPaths.from_root(parsed["root"])
        capture = load_runtime_config(paths).capture
        profile = _load_profile()
        cases = _capture_cases(
            paths=paths,
            trace_db=parsed["trace_db"],
            max_items=parsed["max_items"],
        )
        binding = _judge_binding(capture)
        authorization = _authorization_digest(
            cases, profile, binding, parsed["max_items"]
        )
        if action == "prepare-capture":
            data = {
                **_authorization_payload(cases, profile, binding, parsed["max_items"]),
                "authorization_digest": authorization,
                "case_count": len(cases),
            }
            return _emit(
                ToolResponse(tool=_TOOL, action=action, status="accepted", data=data),
                0,
            )
        if parsed["authorization_digest"] != authorization:
            return _failure(
                action,
                "capture_eval_authorization_stale",
                "Capture Eval authorization is stale",
                1,
            )
        results = _evaluate_cases(
            paths=paths,
            capture=capture,
            cases=cases,
            profile=profile,
            binding=binding,
            eval_db=parsed["eval_db"],
        )
        return _emit(
            ToolResponse(
                tool=_TOOL,
                action=action,
                status="accepted",
                data=_summary(results, binding),
            ),
            0,
        )
    except ModuleNotFoundError:
        return _failure(
            action,
            "eval_runtime_unavailable",
            "Eval Runtime is unavailable",
            1,
        )
    except ValueError as error:
        code = str(error)
        if code == "capture_eval_runtime_unsupported":
            return _failure(action, code, "Capture Eval runtime is unsupported", 1)
        return _failure(action, "capture_eval_failed", "Capture Eval failed", 1)
    except (KeyError, OSError, RuntimeError, TypeError, UnicodeError):
        return _failure(action, "capture_eval_failed", "Capture Eval failed", 1)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "_authorization_digest",
    "_capture_cases",
    "_evaluate_cases",
    "_judge_binding",
    "_load_profile",
    "main",
]
