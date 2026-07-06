"""美育AI MCP 服务器启动脚本 - MCP SDK 1.28.1 兼容版本

使用方式:
    python run_server.py          # stdio 模式
    python run_server.py --sse    # SSE 模式
"""

import sys


def run_stdio():
    import anyio
    from mcp.server.stdio import stdio_server
    from mcp_server.server import create_server

    server = create_server()
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream,
                server.create_initialization_options()
            )
    anyio.run(run)


def run_sse():
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    from mcp.server.sse import SseServerTransport
    from mcp_server.server import create_server

    server = create_server()
    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream,
                server.create_initialization_options()
            )

    async def handle_messages(request):
        await sse.handle_post_message(
            request.scope, request.receive, request._send
        )

    async def health(request):
        return JSONResponse({"status": "ok", "server": "美育AI-MCP-Server"})

    app = Starlette(
        debug=True,
        routes=[
            Route("/health", health),
            Route("/sse", handle_sse),
            Route("/messages", handle_messages, methods=["POST"]),
        ]
    )

    print("美育AI MCP 服务器已启动 (SSE 模式)")
    print("  - 健康检查: http://localhost:8000/health")
    print("  - SSE 端点:  http://localhost:8000/sse")
    print("  - 消息端点:  http://localhost:8000/messages")
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    if "--sse" in sys.argv:
        try:
            run_sse()
        except KeyboardInterrupt:
            print("\n服务器已停止")
    else:
        run_stdio()
