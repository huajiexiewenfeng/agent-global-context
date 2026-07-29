import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agc_runtime import __version__

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer


def create_server(memory_root: Path) -> "MCPServer":
    from mcp.server.mcpserver import MCPServer

    from agc_runtime.admin_service import dispatch_admin
    from agc_runtime.paths import MemoryPaths
    from agc_runtime.read_service import dispatch_read
    from agc_runtime.write_service import dispatch_write

    paths = MemoryPaths.from_root(memory_root)
    server = MCPServer("agent-global-context")

    @server.tool(name="agc.read")
    def agc_read(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_read(paths, request).to_dict()

    @server.tool(name="agc.write")
    def agc_write(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_write(paths, request).to_dict()

    @server.tool(name="agc.admin")
    def agc_admin(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_admin(paths, request).to_dict()

    return server


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--version"]:
        sys.stdout.write(f"{__version__}\n")
        return 0
    memory_root = os.environ.get("AGC_MEMORY_ROOT")
    if not memory_root:
        raise RuntimeError("AGC_MEMORY_ROOT is required")
    create_server(Path(memory_root)).run(transport="stdio")
    return 0


if __name__ == "__main__":
    main()
