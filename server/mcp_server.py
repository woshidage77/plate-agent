"""PlateAgent MCP Server — Day 12

将 PlateAgent 的 RAG 知识库工具暴露为标准 MCP (Model Context Protocol) 服务。
外部 Agent 可通过 MCP 协议调用黑名单查询和混淆字符检索。

MCP 协议基础：
    - JSON-RPC 2.0 传输
    - tools/list: 列出可用工具及其 schema
    - tools/call: 调用指定工具

考试映射：MCP 协议 → 自己做 MCP Server（双向理解）

用法：
    python -m server.mcp_server
    # MCP Server running at http://localhost:8001/mcp
"""

import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

# ── MCP Tool 定义 ──

MCP_TOOLS = [
    {
        "name": "search_blacklist",
        "description": "查询车牌号是否在黑名单中，返回命中记录和详情",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plate_number": {
                    "type": "string",
                    "description": "要查询的车牌号，如 京A12345",
                }
            },
            "required": ["plate_number"],
        },
    },
    {
        "name": "lookup_confusion",
        "description": "查询某个字符的常见混淆字符（OCR 易错映射），如 5↔S, B↔8, 0↔O",
        "inputSchema": {
            "type": "object",
            "properties": {
                "char": {
                    "type": "string",
                    "description": "要查询的字符",
                    "maxLength": 1,
                }
            },
            "required": ["char"],
        },
    },
]

# ── 工具实现 ──

def _call_search_blacklist(args: dict) -> dict:
    """调用黑名单查询工具。"""
    plate = args.get("plate_number", "")
    if not plate:
        return {"content": [{"type": "text", "text": "错误：缺少 plate_number 参数"}]}

    # 直接调用已有的 knowledge 工具
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agent.tools.knowledge import tool_search_blacklist

    result = tool_search_blacklist(plate)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}]}


def _call_lookup_confusion(args: dict) -> dict:
    """调用混淆字符查询工具。"""
    char = args.get("char", "")
    if not char or len(char) > 1:
        return {"content": [{"type": "text", "text": "错误：请提供单个字符"}]}

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agent.tools.knowledge import tool_lookup_confusion

    result = tool_lookup_confusion(char)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}]}


TOOL_HANDLERS = {
    "search_blacklist": _call_search_blacklist,
    "lookup_confusion": _call_lookup_confusion,
}

# ── FastAPI 应用 ──

app = FastAPI(
    title="PlateAgent MCP Server",
    description="MCP protocol server exposing PlateAgent RAG knowledge tools",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """MCP JSON-RPC 端点。

    支持的方法：
        - initialize: 握手，返回服务器能力
        - tools/list: 列出可用工具
        - tools/call: 调用指定工具
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None},
            status_code=400,
        )

    method = body.get("method", "")
    req_id = body.get("id")

    # ── initialize ──
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "plate-agent-mcp",
                    "version": "1.0.0",
                },
            },
        }

    # ── tools/list ──
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS},
        }

    # ── tools/call ──
    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
            }

        try:
            result = handler(tool_args)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as e:
            logger.exception("MCP tool call failed: %s", tool_name)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(e)},
            }

    # ── unknown method ──
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


@app.get("/health")
async def health():
    return {"status": "ok", "tools": [t["name"] for t in MCP_TOOLS]}


# ── 入口 ──

if __name__ == "__main__":
    import uvicorn
    logger.info("PlateAgent MCP Server starting at http://localhost:8001/mcp")
    logger.info("Tools: %s", [t["name"] for t in MCP_TOOLS])
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")