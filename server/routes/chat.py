"""POST /api/chat - SSE streaming multi-turn chat"""
import asyncio
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

            if event.partial:
                for part in event.content.parts:
                    if part.text:
                        await asyncio.sleep(0.015)
                        yield {
                            "event": "text_delta",
                            "data": json.dumps({"content": part.text}, ensure_ascii=False),
                        }
                continue

            for part in event.content.parts:
                if part.thought:
                    continue

                if part.function_call:
                    await asyncio.sleep(0.015)
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
                    await asyncio.sleep(0.015)
                    yield {
                        "event": "tool_result",
                        "data": json.dumps({
                            "name": part.function_response.name,
                            "result": resp_str[:500],
                        }, ensure_ascii=False),
                    }

                elif part.text:
                    await asyncio.sleep(0.015)
                    yield {
                        "event": "text_delta",
                        "data": json.dumps({"content": part.text}, ensure_ascii=False),
                    }

    except Exception as e:
        logger.exception("chat stream error: %s", e)
        yield {
            "event": "error",
            "data": json.dumps({"message": str(e)}, ensure_ascii=False),
        }

    yield {
        "event": "done",
        "data": json.dumps({"session_id": session_id}),
    }


@router.post("/chat")
async def chat(
    req: ChatRequest,
    runner=Depends(get_runner),
):
    app_name = get_app_name()
    user_id = req.user_id
    session_id = req.session_id or str(uuid.uuid4())

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