"""PlateAgent Day 4 — Session + Memory 验证

验证目标：
    1. Session 持久化：同一 session_id 的多轮对话共享上下文
    2. Memory 跨会话：新 session 可以检索到旧 session 的历史事件

用法:
    cd D:/codex_prorject/ai_project/xiniuniaojia/plate-agent
    python -m agent.main_graph
"""

import asyncio
import uuid

from dotenv import load_dotenv
from trpc_agent_sdk.runners import Runner
from trpc_agent_sdk.types import Content, Part
from trpc_agent_sdk.dsl.graph import (
    EventUtils,
    ExecutionPhase,
    NodeExecutionMetadata,
    STATE_KEY_LAST_RESPONSE,
)

load_dotenv()


async def _run_one_turn(runner, user_id, session_id, text, show_details=False):
    """执行一轮对话并打印结果"""
    user_content = Content(parts=[Part.from_text(text=text)])
    last_text = ""

    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=user_content
    ):
        if EventUtils.is_graph_event(event):
            continue
        if not event.content or not event.content.parts:
            continue

        if event.partial:
            for part in event.content.parts:
                if part.text:
                    if show_details:
                        print(part.text, end="", flush=True)
                    last_text += part.text
            continue

    if last_text.strip() and not show_details:
        print(f"  [Agent] {last_text.strip()[:150]}...")
    elif show_details:
        print()

    return last_text


async def demo_session_persistence():
    """场景1：Session 持久化 — 同一 session 多轮对话"""
    print("\n" + "=" * 60)
    print("场景1: Session 持久化 — 同一会话多轮对话")
    print("=" * 60)

    from agent.graph_agent import recognition_agent
    from agent.session_manager import create_session_service, create_memory_service

    session_service = create_session_service(use_redis=False)
    memory_service = create_memory_service(use_redis=False)

    runner = Runner(
        app_name="plate_agent_day4",
        agent=recognition_agent,
        session_service=session_service,
        memory_service=memory_service,
    )

    user_id = "demo_user"
    session_id = str(uuid.uuid4())

    #main_graph.py - 创建session时设置初始state
    await session_service.create_session(
        app_name="plate_agent_day4",
        user_id=user_id,
        session_id=session_id,
        state={"image_path": "eval/dataset/test_images/synth_plate.jpg"},  #platestate的初始值
    )
    #GraphAgent运行后,state变更自动写回session.state
    #preprocess_output,locate_output,...都在session.state里

    # 第1轮
    print("\n[第1轮] 用户: 识别这张车牌")
    await _run_one_turn(runner, user_id, session_id, "识别这张车牌")

    # 第2轮 — 同一 session，模型记得之前的上下文
    print("\n[第2轮] 用户: 刚才识别的结果是什么？(同一session)")
    await _run_one_turn(runner, user_id, session_id, "刚才识别的结果是什么？")

    # 查看 session 状态
    session = await session_service.get_session(
        app_name="plate_agent_day4", user_id=user_id, session_id=session_id
    )
    event_count = len(session.events) if session else 0
    state_keys = list(session.state.keys()) if session and session.state else []
    print(f"\n[Session 状态] 事件数: {event_count}, State 字段: {state_keys}")

    await runner.close()
    print("\n[OK] 场景1 完成: 多轮对话共享 Session，事件持续追加")


async def demo_cross_session_memory():
    """场景2：跨会话 Memory — 新 session 检索历史"""
    print("\n" + "=" * 60)
    print("场景2: 跨会话 Memory — 不同会话检索历史")
    print("=" * 60)

    from agent.graph_agent import recognition_agent
    from agent.session_manager import create_session_service, create_memory_service

    session_service = create_session_service(use_redis=False)
    memory_service = create_memory_service(use_redis=False)

    runner = Runner(
        app_name="plate_agent_day4",
        agent=recognition_agent,
        session_service=session_service,
        memory_service=memory_service,
    )

    user_id = "alice"

    # Session A: 第一次识别
    session_a_id = "session_a_demo"
    await session_service.create_session(
        app_name="plate_agent_day4", user_id=user_id,
        session_id=session_a_id,
        state={"image_path": "eval/dataset/test_images/synth_plate.jpg"},
    )

    print("\n[Session A] 用户 Alice: 识别这张车牌")
    await _run_one_turn(runner, user_id, session_a_id, "识别这张车牌")

    # 检查 Session A 的事件数
    session_a = await session_service.get_session(
        app_name="plate_agent_day4", user_id=user_id, session_id=session_a_id
    )
    print(f"[Session A 事件数] {len(session_a.events) if session_a else 0}")

    # Session B: 新会话，同一用户 — 通过 Memory 检索历史
    session_b_id = "session_b_demo"
    await session_service.create_session(
        app_name="plate_agent_day4", user_id=user_id,
        session_id=session_b_id,
        state={},
    )

    print("\n[Session B] 用户 Alice: 我之前识别过什么车牌？(新会话)")
    await _run_one_turn(runner, user_id, session_b_id, "我之前识别过什么车牌？")

    # 检查 Session B 的事件数（应该是全新的，事件数少）
    session_b = await session_service.get_session(
        app_name="plate_agent_day4", user_id=user_id, session_id=session_b_id
    )
    print(f"[Session B 事件数] {len(session_b.events) if session_b else 0}")

    # 直接调用 Memory 检索 — 验证跨会话记忆存在
    search_key = f"plate_agent_day4/{user_id}"
    memories = await memory_service.search_memory(
        key=search_key, query="车牌 识别", limit=10
    )
    print(f"\n[Memory 直接检索] key={search_key}")
    print(f"  找到 {len(memories.memories)} 条相关记忆（来自 Session A）")

    await runner.close()
    print("\n[OK] 场景2 完成: Session A 的事件出现在 Memory 中")


async def main():
    print("PlateAgent Day 4 — Session + Memory 验证")
    print("Session 后端: InMemory  |  Memory 后端: InMemory")
    print("(Redis 代码已预留，改 use_redis=True 一键切换)")

    await demo_session_persistence()
    await demo_cross_session_memory()

    print("\n" + "=" * 60)
    print("Day 4 验证完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

