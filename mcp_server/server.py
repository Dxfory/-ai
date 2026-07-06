"""美育AI MCP 服务器主入口 - MCP SDK 1.28.1 兼容版本

使用 MCP SDK 低层级 API 构建，通过 stdio 与客户端通信。
"""

import anyio
from mcp.server.stdio import stdio_server
from mcp.server.lowlevel import Server
from .tools import register_art_tools


def create_server() -> Server:
    server = Server("美育AI-MCP-Server")
    register_art_tools(server)
    return server


def main():
    """以 stdio 模式启动 MCP 服务器"""
    server = create_server()
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream,
                server.create_initialization_options()
            )
    anyio.run(run)


if __name__ == "__main__":
    main()
