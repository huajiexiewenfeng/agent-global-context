import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agc_runtime import __version__
from agc_runtime.admin_service import dispatch_admin
from agc_runtime.contracts import ToolResponse
from agc_runtime.paths import MemoryPaths
from agc_runtime.read_service import dispatch_read
from agc_runtime.utf8_io import strict_read_text
from agc_runtime.write_service import dispatch_write


def emit(response: ToolResponse, exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(response.to_dict(), ensure_ascii=False) + "\n")
    return exit_code


def _error(
    tool: str,
    action: str,
    code: str,
    message: str,
    *,
    exit_code: int,
) -> int:
    return emit(
        ToolResponse(
            tool=tool,
            action=action,
            status="failed",
            error={"code": code, "message": message},
        ),
        exit_code=exit_code,
    )


def _parse_adapter_arguments(
    arguments: list[str],
) -> tuple[str, Path, str] | None:
    if (
        len(arguments) != 5
        or arguments[0] not in {"read", "write", "admin"}
        or arguments[1] != "--root"
        or not arguments[2]
        or arguments[3] != "--input"
        or not arguments[4]
    ):
        return None
    return arguments[0], Path(arguments[2]).resolve(), arguments[4]


def _read_request(input_value: str) -> Any:
    if input_value == "-":
        source = sys.stdin.read()
    else:
        source = strict_read_text(Path(input_value))
    return json.loads(source)


def _response_exit_code(response: ToolResponse) -> int:
    if response.status != "failed":
        return 0
    code = response.error.get("code", "") if response.error else ""
    if code in {"write_failed", "read_failed", "admin_failed"}:
        return 1
    if code in {
        "invalid_action",
        "invalid_request",
        "id_required",
        "memory_id_required",
        "invalid_verification_terms",
        "forget_authorization_required",
    }:
        return 2
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["version"]:
        return emit(
            ToolResponse(
                tool="agc.admin",
                action="version",
                status="accepted",
                data={"runtime_version": __version__},
            )
        )

    parsed = _parse_adapter_arguments(arguments)
    if parsed is None:
        action = arguments[0] if arguments else ""
        return _error(
            "agc.admin",
            action,
            "invalid_tool",
            "Expected: agc <read|write|admin> --root <path> --input <json-file|->.",
            exit_code=2,
        )
    tool, root, input_value = parsed
    try:
        request = _read_request(input_value)
    except json.JSONDecodeError as error:
        return _error(
            f"agc.{tool}",
            "",
            "invalid_json",
            str(error),
            exit_code=2,
        )
    except (OSError, UnicodeDecodeError) as error:
        return _error(
            f"agc.{tool}",
            "",
            "input_read_failed",
            str(error),
            exit_code=1,
        )
    if not isinstance(request, dict):
        return _error(
            f"agc.{tool}",
            "",
            "invalid_request",
            "input JSON must be an object",
            exit_code=2,
        )

    paths = MemoryPaths.from_root(root)
    dispatchers = {
        "read": dispatch_read,
        "write": dispatch_write,
        "admin": dispatch_admin,
    }
    try:
        response = dispatchers[tool](paths, request)
    except OSError as error:
        return _error(
            f"agc.{tool}",
            str(request.get("action", "")),
            "runtime_io_failed",
            str(error),
            exit_code=1,
        )
    return emit(response, exit_code=_response_exit_code(response))


if __name__ == "__main__":
    raise SystemExit(main())
