import json
import re
import zipfile
from datetime import datetime, timezone
from typing import Any

from agc_runtime.contracts import ToolResponse
from agc_runtime.forget_transaction import (
    ForgetOperation,
    ForgetPlanError,
    _apply_forget_operation,
    _journal_path,
    _load_journal,
    _prepare_forget_plan,
    _request_digest,
    _rollback_forget_operations,
    _tombstone_path,
    _verify_forget_plan,
)
from agc_runtime.locking import root_write_lock
from agc_runtime.migration_manifest import MigrationManifestError
from agc_runtime.paths import MemoryPaths
from agc_runtime.utf8_io import atomic_write_text, strict_read_text


_SCOPE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
_AMBIGUOUS_SCOPES = {"all", "global", "everything", "*"}


def _failed(code: str, message: str) -> ToolResponse:
    return ToolResponse(
        tool="agc.write",
        action="forget",
        status="failed",
        error={"code": code, "message": message},
    )


def _validate_request(request: Any) -> tuple[
    dict[str, Any], str, str, tuple[str, ...]
]:
    if not isinstance(request, dict):
        raise ForgetPlanError(
            "invalid_request", "request must be a mapping"
        )
    if request.get("authorization") != "explicit_user_request":
        raise ForgetPlanError(
            "forget_authorization_required",
            "hard forget requires explicit_user_request authorization",
        )
    memory_id = request.get("memory_id")
    if not isinstance(memory_id, str) or not memory_id:
        raise ForgetPlanError(
            "memory_id_required", "exact memory_id is required"
        )
    suppression_scope = request.get("suppression_scope")
    if (
        not isinstance(suppression_scope, str)
        or not _SCOPE_PATTERN.fullmatch(suppression_scope)
        or suppression_scope in _AMBIGUOUS_SCOPES
    ):
        raise ForgetPlanError(
            "ambiguous_suppression_scope",
            "suppression_scope must be precise",
        )
    raw_terms = request.get("verification_terms", [])
    if (
        not isinstance(raw_terms, list)
        or not raw_terms
        or any(not isinstance(term, str) or not term for term in raw_terms)
    ):
        raise ForgetPlanError(
            "invalid_verification_terms",
            "verification_terms must be a non-empty list of non-empty strings",
        )
    return request, memory_id, suppression_scope, tuple(raw_terms)


def forget(paths: MemoryPaths, request: Any) -> ToolResponse:
    try:
        (
            request_mapping,
            memory_id,
            suppression_scope,
            verification_terms,
        ) = _validate_request(request)
    except ForgetPlanError as error:
        if error.code == "ambiguous_suppression_scope":
            return ToolResponse(
                tool="agc.write",
                action="forget",
                status="needs_adjudication",
                data={"code": error.code},
            )
        return _failed(error.code, str(error))

    digest = _request_digest(request_mapping)
    journal_path = _journal_path(paths, memory_id)
    tombstone_file = _tombstone_path(paths, memory_id)
    forgotten_at = datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    tombstone = {
        "memory_id": memory_id,
        "status": "forgotten",
        "forgotten_at": forgotten_at,
        "suppression_scope": suppression_scope,
    }

    with root_write_lock(paths):
        try:
            journal = _load_journal(
                paths, journal_path, memory_id, digest
            )
            existing_memories = list(
                paths.memories.glob(f"*/{memory_id}.md")
            )
            if journal is None and not existing_memories:
                if tombstone_file.exists():
                    existing = json.loads(
                        strict_read_text(tombstone_file)
                    )
                    return ToolResponse(
                        tool="agc.write",
                        action="forget",
                        status="accepted",
                        data={
                            "code": "already_forgotten",
                            "tombstone": existing,
                            "managed_agc_copies_deleted": True,
                            "source_task_deleted": False,
                        },
                    )
                return _failed(
                    "memory_not_found", f"memory not found: {memory_id}"
                )
            if journal is None and len(existing_memories) > 1:
                return ToolResponse(
                    tool="agc.write",
                    action="forget",
                    status="needs_adjudication",
                    data={"code": "ambiguous_memory_id"},
                )

            plan = _prepare_forget_plan(
                paths,
                memory_id,
                verification_terms,
                digest,
                tombstone,
                journal_path,
                journal,
            )
            if journal is None:
                atomic_write_text(
                    journal_path,
                    json.dumps(
                        plan.journal,
                        ensure_ascii=False,
                        sort_keys=True,
                        indent=2,
                    )
                    + "\n",
                )

            originals: list[
                tuple[ForgetOperation, bool, bytes | None]
            ] = []
            for operation in (*plan.operations, plan.tombstone):
                existed = operation.path.exists()
                originals.append(
                    (
                        operation,
                        existed,
                        operation.path.read_bytes() if existed else None,
                    )
                )
            applied: list[
                tuple[ForgetOperation, bool, bytes | None]
            ] = []
            try:
                for original in originals[:-1]:
                    _apply_forget_operation(original[0])
                    applied.append(original)
                _verify_forget_plan(
                    paths, plan, memory_id, verification_terms
                )
                _apply_forget_operation(originals[-1][0])
                applied.append(originals[-1])
            except Exception as error:
                _rollback_forget_operations(applied)
                return _failed("forget_failed", str(error))

            journal_path.unlink(missing_ok=True)
        except ForgetPlanError as error:
            return _failed(error.code, str(error))
        except (
            MigrationManifestError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
            zipfile.BadZipFile,
        ) as error:
            return _failed("forget_failed", str(error))

    return ToolResponse(
        tool="agc.write",
        action="forget",
        status="accepted",
        data={
            "code": "memory_forgotten",
            "tombstone": tombstone,
            "managed_agc_copies_deleted": True,
            "source_task_deleted": False,
        },
    )
