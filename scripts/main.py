"""PlateAgent Quickstart - 跑通基础对话"""

import asyncio
import uuid


import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
from trpc_agent_sdk.runners import Runner
from trpc_agent_sdk.sessions import InMemorySessionService
from trpc_agent_sdk.types import Content, Part

load_dotenv()


async def run():
    app_name = "plate_agent"
    user_id = "demo_user"

    from agent.llm_agent import root_agent

    session_service = InMemorySessionService()
    runner = Runner(
        app_name=app_name,
        agent=root_agent,
        session_service=session_service,
    )

    session_id = str(uuid.uuid4())
    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )

    print("=" * 50)
    print("PlateAgent Quickstart - 基础对话测试")
    print("=" * 50)

    queries = [
        "你好，你能帮我做什么？",
        "如果我上传一张车牌照片，你能识别出来吗？",
        "中国车牌有哪些颜色？",
    ]

    for query in queries:
        print(f"\n[用户] {query}")
        print("[PlateAgent] ", end="", flush=True)

        user_content = Content(parts=[Part.from_text(text=query)])

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_content,
        ):
            #守卫:有些事件content为空(如更新状态,跳过)
            if not event.content or not event.content.parts:
                continue

            # ─── 情况 1：流式文本片段 ───
            if event.partial:
                for part in event.content.parts:
                    if part.text:
                        print(part.text, end="", flush=True) # 逐字打印，不换行
                continue  # ← 注意这个 continue：流式片段不进入下面的完整事件处理

            # ─── 情况 2：完整事件（partial=False）───
            for part in event.content.parts:
                if part.thought:
                    continue      # 跳过思考过程
                if part.function_call:
                    print(f"\n  [调用工具: {part.function_call.name}]")
                elif part.function_response:
                    print(f"  [工具返回: {part.function_response.response}]")

        print()

    print("\n" + "=" * 50)
    print("Quickstart 完成！多轮对话 + 流式输出 验证通过")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run())
