import json
import sys
from collections.abc import Sequence

from agc_runtime import __version__
from agc_runtime.contracts import ToolResponse


def emit(response: ToolResponse, exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(response.to_dict(), ensure_ascii=False) + "\n")
    return exit_code


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

    action = arguments[0] if arguments else ""
    return emit(
        ToolResponse(
            tool="agc.admin",
            action=action,
            status="failed",
            error={"code": "invalid_tool", "message": "Unknown AGC tool."},
        ),
        exit_code=2,
    )


if __name__ == "__main__":
    raise SystemExit(main())
