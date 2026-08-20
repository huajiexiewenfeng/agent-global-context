"""Explicit, one-shot, census-only Capture command."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
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


def _parse(arguments: list[str]) -> tuple[str, Path, str | None] | None:
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
            executable=(capture.extractor.executable,),
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
    if action == "prepare-backfill":
        return _run_prepare_backfill(paths)
    assert mode is not None
    return _run_scan(paths, action=action, mode=mode)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
