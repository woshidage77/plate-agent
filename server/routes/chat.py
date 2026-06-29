"""POST /api/chat — SSE 流式多轮对话

支持：
    - 闲聊对话
    - 车牌识别请求（通过 GraphAgent 流水线）
    - 黑名单查询
    - 历史记忆召回

SSE 事件类型：
    text_delta   — 流式文本片段
    tool_call    — 工具调用开始
    tool_result  — 工具返回结果
    node_progress — 图节点进度（AsyncEventWriter 输出）
    final        — 最终完整回复
    error        — 错误
    done         — 流结束
"""

import json
import uuid
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from trpc_agent_sdk.types import Content, Part
from trpc_agent_sdk.dsl.graph import EventUtils

from server.schemas import ChatRequest
from server.dependencies import get_runner, get_app_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


async def _stream_chat_events(
    runner,
    app_name: str,
    user_id: str,
    session_id: str,
    message: str,
    image_path: str | None = None,
) -> AsyncGenerator[dict, None]:
    """核心：将 Runner 事件流转换为 SSE dict 流。"""
    user_content = Content(parts=[Part.from_text(text=message)])

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_content,
        ):
            # ── 跳过图内部事件 ──
            if EventUtils.is_graph_event(event):
                continue

            # ── 跳过空事件 ──
            if not event.content or not event.content.parts:
                continue

            # ── 流式文本片段 ──
            if event.partial:
                for part in event.content.parts:
                    if part.text:
                        yield {
                            "event": "text_delta",
                            "data": json.dumps({"content": part.text}, ensure_ascii=False),
                        }
                continue

            # ── 完整事件 ──
            for part in event.content.parts:
                if part.thought:
                    continue  # 跳过思考过程

                if part.function_call:
                    yield {
                        "event": "tool_call",
                        "data": json.dumps({
                            "name": part.function_call.name,
                            "args": part.function_call.args,
                        }, ensure_ascii=False),
                    }

                elif part.function_response:
                    # 工具返回可能是 dict 或 str
                    resp = part.function_response.response
                    if isinstance(resp, dict):
                        resp_str = json.dumps(resp, ensure_ascii=False)
                    else:
                        resp_str = str(resp)
                    yield {
                        "event": "tool_result",
                        "data": json.dumps({
                            "name": part.function_response.name,
                            "result": resp_str[:500],  # 截断过长返回
                        }, ensure_ascii=False),
                    }

                elif part.text:
                    # 完整文本回复（非流式场景的兜底）
                    yield {
                        "event": "text_delta",
                        "data": json.dumps({"content": part.text}, ensure_ascii=False),
                    }

    except Exception as e:
        logger.exception("对话流异常: %s", e)
        yield {
            "event": "error",
            "data": json.dumps({"message": str(e)}, ensure_ascii=False),
        }

    # 流结束
    yield {
        "event": "done",
        "data": json.dumps({"session_id": session_id}),
    }


@router.post("/chat")
async def chat(
    req: ChatRequest,
    runner=Depends(get_runner),
):
    """多轮对话接口 — SSE 流式返回。

    请求示例：
        curl -X POST http://localhost:8000/api/chat \\
          -H "Content-Type: application/json" \\
          -d '{"message": "识别这张车牌", "image_path": "test.jpg"}' \\
          --no-buffer

    响应格式（SSE）：
        event: text_delta
        data: {"content": "识"}

        event: text_delta
        data: {"content": "别"}

        event: tool_call
        data: {"name": "tool_gaussian_blur", "args": {...}}

        event: done
        data: {"session_id": "abc-123"}
    """
    app_name = get_app_name()
    user_id = req.user_id
    session_id = req.session_id or str(uuid.uuid4())

    # 确保 session 存在
    session_service = runner.session_service
    try:
        existing = await session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
    except Exception:
        existing = None

    if existing is None:
        state = {}
        if req.image_path:
            state["image_path"] = req.image_path
        await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            state=state,
        )

    async def event_generator():
        async for sse_dict in _stream_chat_events(
            runner=runner,
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            message=req.message,
            image_path=req.image_path,
        ):
            yield sse_dict

    return EventSourceResponse(event_generator())
