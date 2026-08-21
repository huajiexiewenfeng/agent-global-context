"""Explicit, one-shot, census-only Capture command."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import sys
from typing import Any

from agc_runtime.capture_status_service import bind_capture_status, capture_status
from agc_runtime.capture_store import CaptureStore, root_fingerprint
from agc_runtime.contracts import ToolResponse
from agc_runtime.paths import MemoryPaths
from agc_runtime.runtime_config import load_runtime_config


_TOOL = "agc.capture"


def _emit(response: ToolResponse, *, exit_code: int) -> int:
    sys.stdout.write(
        json.dumps(response.to_dict(), ensure_ascii=True, sort_keys=True) + "\n"
    )
    return exit_code


def _failed(action: str, code: str, message: str, *, exit_code: int = 2) -> int:
    return _emit(
        ToolResponse(
            tool=_TOOL,
            action=action,
            status="failed",
            error={"code": code, "message": message},
        ),
        exit_code=exit_code,
    )


def _parse(arguments: list[str]) -> tuple[str, Path, Any] | None:
    if (
        len(arguments) in {5, 7}
        and arguments[0] == "activation"
        and arguments[1] == "--root"
        and arguments[2]
        and arguments[3] == "--evidence"
        and arguments[4]
        and (
            len(arguments) == 5
            or (
                arguments[5] == "--consent-digest"
                and len(arguments[6]) == 64
                and all(item in "0123456789abcdef" for item in arguments[6])
            )
        )
    ):
        return (
            "activation",
            Path(arguments[2]),
            (Path(arguments[4]), arguments[6] if len(arguments) == 7 else None),
        )
    if (
        len(arguments) == 5
        and arguments[0] == "run"
        and arguments[1] == "--root"
        and arguments[2]
        and arguments[3] == "--max-items"
        and arguments[4].isdigit()
        and 1 <= int(arguments[4]) <= 100
    ):
        return "run", Path(arguments[2]), arguments[4]
    if (
        len(arguments) == 6
        and arguments[0] == "cycle"
        and arguments[1] == "--root"
        and arguments[2]
        and arguments[3] == "--once"
        and arguments[4] == "--max-items"
        and arguments[5].isdigit()
        and 1 <= int(arguments[5]) <= 100
    ):
        return "runner-cycle", Path(arguments[2]), arguments[5]
    if (
        len(arguments) == 5
        and arguments[0] == "retry"
        and arguments[1] == "--root"
        and arguments[2]
        and arguments[3] == "--revision-key"
        and len(arguments[4]) == 67
        and arguments[4].startswith("cr_")
        and all(item in "0123456789abcdef" for item in arguments[4][3:])
    ):
        return "retry", Path(arguments[2]), arguments[4]
    if (
        len(arguments) == 8
        and arguments[0] == "backfill"
        and arguments[1] == "--root"
        and arguments[2]
        and arguments[3] == "--authorization-digest"
        and len(arguments[4]) == 64
        and all(item in "0123456789abcdef" for item in arguments[4])
        and arguments[5] == "--max-items"
        and arguments[6].isdigit()
        and 1 <= int(arguments[6]) <= 100
        and arguments[7] == "--once"
    ):
        return "backfill", Path(arguments[2]), f"{arguments[4]}:{arguments[6]}"
    if (
        len(arguments) == 3
        and arguments[0] == "prepare-backfill"
        and arguments[1] == "--root"
        and arguments[2]
    ):
        return "prepare-backfill", Path(arguments[2]), None
    if (
        len(arguments) == 3
        and arguments[0] == "probe"
        and arguments[1] == "--root"
        and arguments[2]
    ):
        return "probe", Path(arguments[2]), None
    if (
        len(arguments) == 6
        and arguments[0] == "scan"
        and arguments[1] == "--root"
        and arguments[2]
        and arguments[3] == "--mode"
        and arguments[4] in {"census", "incremental"}
        and arguments[5] == "--once"
    ):
        return "scan", Path(arguments[2]), arguments[4]
    if (
        len(arguments) == 4
        and arguments[0] == "cycle"
        and arguments[1] == "--root"
        and arguments[2]
        and arguments[3] == "--once"
    ):
        return "cycle", Path(arguments[2]), "incremental"
    return None


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _activation(
    paths: MemoryPaths, evidence_path: Path, consent_digest: str | None
) -> int:
    from agc_runtime.capture_activation import (
        ActivationEvidence,
        activation_digest_for,
        diagnose_activation,
    )

    try:
        if evidence_path.is_symlink() or not evidence_path.is_file():
            raise ValueError
        if evidence_path.stat().st_size > 8192:
            raise ValueError

        def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result

        mapping = json.loads(
            evidence_path.read_text(encoding="utf-8"),
            object_pairs_hook=no_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
        evidence = ActivationEvidence.from_mapping(mapping)
        status = bind_capture_status(
            capture_status(paths), evidence_kind="capture_cli_root"
        )
        report = diagnose_activation(
            status, evidence, consent_digest=consent_digest
        )
    except (
        OSError,
        RuntimeError,
        UnicodeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return _failed(
            "activation",
            "invalid_activation_evidence",
            "Activation evidence is invalid",
        )
    data = report.to_mapping()
    data["activation_digest"] = activation_digest_for(report)
    return _emit(
        ToolResponse(
            tool=_TOOL,
            action="activation",
            status="accepted",
            data=data,
        ),
        exit_code=0,
    )


def _extractor_command(value: str) -> tuple[str, ...]:
    if value == "codex-app":
        from agc_runtime.codex_app_runtime import resolve_codex_app_command

        return resolve_codex_app_command()
    try:
        command = tuple(shlex.split(value, posix=True))
    except ValueError as error:
        raise ValueError("capture extractor executable is invalid") from error
    if not 1 <= len(command) <= 4:
        raise ValueError("capture extractor executable is invalid")
    return command


def _scan_mapping(report: Any) -> dict[str, Any]:
    return {
        "window": {
            "start_at": report.window.start_at,
            "end_at": report.window.end_at,
        },
        "known_key_count": report.known_key_count,
        "accounted_key_count": report.accounted_key_count,
        "silent_loss_count": report.silent_loss_count,
        "pending_key_count": report.pending_key_count,
        "created_receipt_count": report.created_receipt_count,
        "replay_count": report.replay_count,
        "source_quarantine_count": report.source_quarantine_count,
        "source_health": report.source_health,
        "acknowledged_marker_count": report.acknowledged_marker_count,
        "advanced_hint_count": report.advanced_hint_count,
    }


def _probe(paths: MemoryPaths) -> int:
    try:
        status = bind_capture_status(
            capture_status(paths), evidence_kind="capture_cli_root"
        )
    except (KeyError, OSError, TypeError, UnicodeError, ValueError):
        return _failed(
            "probe",
            "invalid_runtime_config",
            "runtime configuration is invalid",
        )
    except RuntimeError:
        return _failed(
            "probe",
            "capture_busy",
            "Capture state is temporarily unavailable",
            exit_code=1,
        )
    scanner_assessment = status["scanner"]["assessment"]
    if scanner_assessment in {"busy", "corrupt"}:
        code, message = (
            ("capture_busy", "Capture state is temporarily unavailable")
            if scanner_assessment == "busy"
            else (
                "scanner_corrupt",
                "Capture state failed integrity validation",
            )
        )
        return _emit(
            ToolResponse(
                tool=_TOOL,
                action="probe",
                status="failed",
                data=status,
                error={"code": code, "message": message},
            ),
            exit_code=1,
        )
    return _emit(
        ToolResponse(tool=_TOOL, action="probe", status="accepted", data=status),
        exit_code=0,
    )


def _run_scan(paths: MemoryPaths, *, action: str, mode: str) -> int:
    try:
        config = load_runtime_config(paths)
    except (KeyError, OSError, TypeError, UnicodeError, ValueError):
        return _failed(
            action,
            "invalid_runtime_config",
            "runtime configuration is invalid",
        )

    capture = config.capture
    if not capture.enabled:
        return _failed(action, "capture_disabled", "Capture is disabled")
    if capture.mode == "runner":
        return _failed(
            action,
            "capture_runner_unsupported",
            "Capture Runner is not installed",
        )
    if capture.mode != "scanner_only":
        return _failed(
            action,
            "capture_mode_unsupported",
            "Capture mode is not scanner_only",
        )
    if capture.paused:
        return _failed(action, "capture_paused", "Capture is paused")
    if not capture.sources:
        return _failed(
            action,
            "capture_sources_unconfigured",
            "Capture sources are not configured",
        )
    if capture.budgets.backfill_window_days != 7:
        return _failed(
            action,
            "capture_window_unsupported",
            "Capture census window must be seven days",
        )

    try:
        # Deferred imports are an activation boundary: disabled, paused, runner,
        # and invalid configurations never load or instantiate Source adapters.
        from agc_runtime.capture_scanner import CaptureScanner
        from agc_runtime.codex_source_adapter import CodexSourceAdapter

        adapters = tuple(CodexSourceAdapter(Path(item)) for item in capture.sources)
        report = CaptureScanner(
            CaptureStore(paths),
            adapters,
            excluded_task_ids=capture.exclude.task_ids,
        ).scan(run_started_at=_utc_now(), force_full=mode == "census")
    except RuntimeError:
        return _failed(
            action,
            "capture_busy",
            "Capture state is temporarily unavailable",
            exit_code=1,
        )
    except OSError:
        return _failed(
            action,
            "capture_source_failed",
            "Capture source is unavailable",
            exit_code=1,
        )
    except (KeyError, TypeError, UnicodeError, ValueError):
        return _failed(
            action,
            "capture_integrity_failed",
            "Capture state failed integrity validation",
            exit_code=1,
        )
    except Exception:
        return _failed(
            action,
            "capture_operation_failed",
            "Capture operation failed",
            exit_code=1,
        )

    data = {
        "mode": mode,
        "once": True,
        "memory_root": {
            "fingerprint": root_fingerprint(paths),
            "assessment": "verified",
            "matches_host_binding": True,
            "evidence": {"kind": "capture_cli_root"},
        },
        "sources": {"configured_count": len(adapters)},
        "exclusions": {
            "task_id_count": len(capture.exclude.task_ids),
            "project_id_count": len(capture.exclude.project_ids),
            "project_id_assessment": "not_assessed",
        },
        "scan": _scan_mapping(report),
    }
    return _emit(
        ToolResponse(tool=_TOOL, action=action, status="accepted", data=data),
        exit_code=0,
    )


def _run_prepare_backfill(paths: MemoryPaths) -> int:
    action = "prepare-backfill"
    try:
        config = load_runtime_config(paths)
        capture = config.capture
        if not capture.enabled:
            return _failed(action, "capture_disabled", "Capture is disabled")
        if capture.mode != "scanner_only":
            return _failed(
                action,
                "capture_mode_unsupported",
                "Capture mode is not scanner_only",
            )
        if capture.paused:
            return _failed(action, "capture_paused", "Capture is paused")
        if not capture.sources:
            return _failed(
                action,
                "capture_sources_unconfigured",
                "Capture sources are not configured",
            )

        from agc_runtime.capture_backfill import prepare_backfill
        from agc_runtime.codex_extractor import CodexExtractor
        from agc_runtime.codex_source_adapter import CodexSourceAdapter

        adapters = tuple(CodexSourceAdapter(Path(item)) for item in capture.sources)
        extractor = CodexExtractor(
            executable=_extractor_command(capture.extractor.executable),
            explicit_model=capture.extractor.model,
        )
        preparation = prepare_backfill(
            paths=paths,
            adapters=adapters,
            extractor=extractor,
            now=_utc_now(),
        )
    except RuntimeError as error:
        code = (
            "extractor_capability_unavailable"
            if str(error) == "capture_extractor_unavailable"
            else "capture_busy"
        )
        message = (
            "Capture Extractor capability is unavailable"
            if code == "extractor_capability_unavailable"
            else "Capture state is temporarily unavailable"
        )
        return _failed(action, code, message, exit_code=1)
    except OSError:
        return _failed(
            action,
            "capture_source_failed",
            "Capture source is unavailable",
            exit_code=1,
        )
    except (KeyError, TypeError, UnicodeError, ValueError) as error:
        known = {
            "capture_disabled",
            "capture_mode_unsupported",
            "capture_paused",
            "capture_sources_unconfigured",
            "capture_window_unsupported",
            "capture_budget_unavailable",
            "capture_backfill_source_count_unsupported",
        }
        code = str(error) if str(error) in known else "capture_integrity_failed"
        return _failed(
            action,
            code,
            "Capture backfill preparation failed",
            exit_code=1,
        )
    except Exception:
        return _failed(
            action,
            "capture_operation_failed",
            "Capture operation failed",
            exit_code=1,
        )
    return _emit(
        ToolResponse(
            tool=_TOOL,
            action=action,
            status="accepted",
            data=preparation.to_mapping(),
        ),
        exit_code=0,
    )


def _run_backfill(paths: MemoryPaths, encoded: str) -> int:
    action = "backfill"
    digest, maximum = encoded.split(":", 1)
    try:
        config = load_runtime_config(paths)
        capture = config.capture
        from agc_runtime.capture_backfill import load_backfill_preparation
        from agc_runtime.capture_runner import CaptureRunner
        from agc_runtime.codex_extractor import CodexExtractor
        from agc_runtime.codex_source_adapter import CodexSourceAdapter

        preparation = load_backfill_preparation(paths, digest)
        adapters = tuple(CodexSourceAdapter(Path(item)) for item in capture.sources)
        extractor = CodexExtractor(
            executable=_extractor_command(capture.extractor.executable),
            explicit_model=capture.extractor.model,
        )
        report = CaptureRunner(
            paths, adapters, extractor, preparation
        ).run_manual_backfill(
            authorization_digest=digest,
            max_items=int(maximum),
            now=_utc_now(),
        )
    except RuntimeError as error:
        code = (
            str(error)
            if str(error) in {
                "capture_backfill_authorization_stale",
                "capture_extractor_unavailable",
            }
            else "capture_busy"
        )
        return _failed(action, code, "Capture backfill was not started", exit_code=1)
    except OSError:
        return _failed(
            action, "capture_source_failed", "Capture source is unavailable", exit_code=1
        )
    except (KeyError, TypeError, UnicodeError, ValueError) as error:
        code = (
            str(error)
            if str(error).startswith("capture_")
            else "capture_integrity_failed"
        )
        return _failed(action, code, "Capture backfill failed", exit_code=1)
    except Exception:
        return _failed(
            action,
            "capture_operation_failed",
            "Capture backfill failed",
            exit_code=1,
        )
    return _emit(
        ToolResponse(
            tool=_TOOL,
            action=action,
            status="accepted",
            data={"once": True, **report.to_mapping()},
        ),
        exit_code=0,
    )


def _run_retry(paths: MemoryPaths, receipt_id: str) -> int:
    action = "retry"
    try:
        from agc_runtime.capture_runner import retry_capture_receipt

        receipt = retry_capture_receipt(paths, receipt_id, now=_utc_now())
    except RuntimeError:
        return _failed(
            action,
            "capture_retry_busy",
            "Capture retry is temporarily unavailable",
            exit_code=1,
        )
    except (KeyError, OSError, TypeError, UnicodeError, ValueError) as error:
        code = (
            str(error)
            if str(error).startswith("capture_retry_")
            else "capture_integrity_failed"
        )
        return _failed(action, code, "Capture retry was not queued", exit_code=1)
    return _emit(
        ToolResponse(
            tool=_TOOL,
            action=action,
            status="accepted",
            data={
                "receipt_id": receipt.receipt_id,
                "status": receipt.status,
                "attempt_count": receipt.attempt_count,
            },
        ),
        exit_code=0,
    )


def _run_runner(
    paths: MemoryPaths, *, action: str, maximum: int, scan_first: bool
) -> int:
    try:
        config = load_runtime_config(paths)
        capture = config.capture
        if not capture.enabled:
            return _failed(action, "capture_disabled", "Capture is disabled")
        if capture.mode != "runner":
            return _failed(
                action,
                "capture_mode_unsupported",
                "Capture mode is not runner",
            )
        if not capture.sources:
            return _failed(
                action,
                "capture_sources_unconfigured",
                "Capture sources are not configured",
            )

        from agc_runtime.capture_runner import CaptureRunner
        from agc_runtime.capture_scanner import CaptureScanner
        from agc_runtime.codex_extractor import CodexExtractor
        from agc_runtime.codex_source_adapter import CodexSourceAdapter

        adapters = tuple(CodexSourceAdapter(Path(item)) for item in capture.sources)
        now = _utc_now()
        scan = None
        if scan_first and not capture.paused:
            scan = CaptureScanner(
                CaptureStore(paths),
                adapters,
                excluded_task_ids=capture.exclude.task_ids,
            ).scan(run_started_at=now)
        extractor = CodexExtractor(
            executable=_extractor_command(capture.extractor.executable),
            explicit_model=capture.extractor.model,
        )
        report = CaptureRunner(paths, adapters, extractor, None).run_once(
            max_items=maximum,
            now=now,
        )
    except RuntimeError as error:
        code = (
            str(error)
            if str(error) in {"capture_extractor_unavailable"}
            else "capture_busy"
        )
        return _failed(action, code, "Capture Runner did not start", exit_code=1)
    except OSError:
        return _failed(
            action,
            "capture_source_failed",
            "Capture source is unavailable",
            exit_code=1,
        )
    except (KeyError, TypeError, UnicodeError, ValueError):
        return _failed(
            action,
            "capture_integrity_failed",
            "Capture Runner state failed integrity validation",
            exit_code=1,
        )
    data: dict[str, Any] = {"once": True, **report.to_mapping()}
    if scan is not None:
        data["scan"] = _scan_mapping(scan)
    return _emit(
        ToolResponse(tool=_TOOL, action=action, status="accepted", data=data),
        exit_code=0,
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parsed = _parse(arguments)
    if parsed is None:
        return _failed(
            "invoke",
            "invalid_invocation",
            "Expected a supported one-shot Capture operation",
        )
    action, root, mode = parsed
    try:
        paths = MemoryPaths.from_root(root)
    except (OSError, RuntimeError, ValueError):
        return _failed(
            action,
            "invalid_memory_root",
            "Memory Root binding is invalid",
        )
    if action == "probe":
        return _probe(paths)
    if action == "activation":
        evidence_path, consent_digest = mode
        return _activation(paths, evidence_path, consent_digest)
    if action == "prepare-backfill":
        return _run_prepare_backfill(paths)
    if action == "backfill":
        assert mode is not None
        return _run_backfill(paths, mode)
    if action == "retry":
        assert mode is not None
        return _run_retry(paths, mode)
    if action in {"run", "runner-cycle"}:
        assert mode is not None
        return _run_runner(
            paths,
            action="cycle" if action == "runner-cycle" else action,
            maximum=int(mode),
            scan_first=action == "runner-cycle",
        )
    assert mode is not None
    return _run_scan(paths, action=action, mode=mode)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
