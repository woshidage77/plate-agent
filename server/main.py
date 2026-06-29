"""PlateAgent 服务入口 — uvicorn 启动

用法:
    cd plate-agent
    python -m server.main

    # 或指定端口
    python -m server.main --port 8080
"""

import argparse
import uvicorn

from server.app import app
from agent.config import FASTAPI_HOST, FASTAPI_PORT


def main():
    parser = argparse.ArgumentParser(description="PlateAgent API Server")
    parser.add_argument("--host", default=FASTAPI_HOST, help="监听地址")
    parser.add_argument("--port", type=int, default=FASTAPI_PORT, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    uvicorn.run(
        "server.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
