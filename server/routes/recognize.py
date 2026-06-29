"""POST /api/recognize — SSE 流式车牌识别

直接走 GraphAgent 识别流水线，不走闲聊入口。
适合前端直接发起识别请求的场景。

SSE 事件类型：
    node_progress — 每个图节点的进度
    text_delta    — 流式文本片段
    tool_call     — 工具调用
    tool_result   — 工具返回
    final         — 最终识别结果
    error         — 错误
    done          — 流结束
"""

import json
import uuid
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from trpc_agent_sdk.types import Content, Part
from trpc_agent_sdk.dsl.graph import EventUtils
from trpc_agent_sdk.runners import Runner

from server.schemas import RecognizeRequest
from server.dependencies import get_runner, get_app_name
from agent.graph_agent import recognition_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["recognize"])


async def _stream_recognize_events(
    runner,
    app_name: str,
    user_id: str,
    session_id: str,
    image_path: str,
) -> AsyncGenerator[dict, None]:
    """核心：走 GraphAgent 识别流水线，流式推送进度。"""
    message = "请识别这张车牌图片：" + image_path
    user_content = Content(parts=[Part.from_text(text=message)])

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_content,
        ):
            if EventUtils.is_graph_event(event):
                continue

            if not event.content or not event.content.parts:
                continue

            # 流式文本
            if event.partial:
                for part in event.content.parts:
                    if part.text:
                        yield {
                            "event": "text_delta",
                            "data": json.dumps({"content": part.text}, ensure_ascii=False),
                        }
                continue

            # 完整事件
            for part in event.content.parts:
                if part.thought:
                    continue

                if part.function_call:
                    yield {
                        "event": "tool_call",
                        "data": json.dumps({
                            "name": part.function_call.name,
                            "args": part.function_call.args,
                        }, ensure_ascii=False),
                    }

                elif part.function_response:
                    resp = part.function_response.response
                    resp_str = json.dumps(resp, ensure_ascii=False) if isinstance(resp, dict) else str(resp)
                    yield {
                        "event": "tool_result",
                        "data": json.dumps({
                            "name": part.function_response.name,
                            "result": resp_str[:500],
                        }, ensure_ascii=False),
                    }

                elif part.text:
                    yield {
                        "event": "text_delta",
                        "data": json.dumps({"content": part.text}, ensure_ascii=False),
                    }

    except Exception as e:
        logger.exception("识别流水线异常: %s", e)
        yield {
            "event": "error",
            "data": json.dumps({"message": str(e)}, ensure_ascii=False),
        }

    # 读取 session state 获取最终结果
    try:
        session = await runner.session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        final_plate = ""
        blacklist_hit = False
        if session and session.state:
            final_plate = session.state.get("final_plate", "")
            last_response = session.state.get("last_response", "")

            if "黑名单命中" in last_response:
                blacklist_hit = True

            yield {
                "event": "final",
                "data": json.dumps({
                    "plate_number": final_plate,
                    "full_response": last_response,
                    "blacklist_hit": blacklist_hit,
                }, ensure_ascii=False),
            }
    except Exception:
        pass

    yield {
        "event": "done",
        "data": json.dumps({"session_id": session_id}),
    }


@router.post("/recognize")
async def recognize(
    req: RecognizeRequest,
    chat_runner=Depends(get_runner),
):
    """单张车牌识别接口 — SSE 流式返回进度。

    使用 GraphAgent 确定性流水线（预处理→定位→分割→识别）。
    复用 chat Runner 的 Session/Memory 服务以保持跨端点一致性。
    """
    app_name = get_app_name()
    user_id = req.user_id
    session_id = req.session_id or str(uuid.uuid4())

    # 复用 chat Runner 的 session/memory 服务，但用 GraphAgent 做识别
    session_service = chat_runner.session_service
    memory_service = chat_runner.memory_service

    recognize_runner = Runner(
        app_name=app_name,
        agent=recognition_agent,
        session_service=session_service,
        memory_service=memory_service,
    )

    # 创建 session，设置初始 image_path
    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state={"image_path": req.image_path},
    )

    async def event_generator():
        async for sse_dict in _stream_recognize_events(
            runner=recognize_runner,
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            image_path=req.image_path,
        ):
            yield sse_dict

    return EventSourceResponse(event_generator())
