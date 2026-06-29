import logging
from typing import Optional

from dotenv import load_dotenv
from trpc_agent_sdk.runners import Runner

from agent.telemetry import init_telemetry

load_dotenv()

logger = logging.getLogger(__name__)

# ── 模块级单例 ──
_runner: Optional[Runner] = None
_app_name = "plate_agent_api"


def get_app_name() -> str:
    return _app_name


async def init_runner() -> Runner:
    global _runner
    if _runner is not None:
        return _runner

    import os
    from agent.graph_agent import root_agent
    from agent.session_manager import create_session_service, create_memory_service

    # ── Day 9: 初始化 OpenTelemetry ──
    init_telemetry(service_name=_app_name, console_export=True)

    use_redis = os.getenv("USE_REDIS", "false").lower() == "true"

    session_service = create_session_service(use_redis=use_redis)
    memory_service = create_memory_service(use_redis=use_redis)

    _runner = Runner(
        app_name=_app_name,
        agent=root_agent,
        session_service=session_service,
        memory_service=memory_service,
    )

    logger.info(
        "Runner 初始化完成: agent=%s, session=%s, memory=%s, redis=%s",
        root_agent.name,
        type(session_service).__name__,
        type(memory_service).__name__,
        use_redis,
    )
    return _runner


async def shutdown_runner() -> None:
    global _runner
    if _runner is not None:
        await _runner.close()
        _runner = None
        logger.info("Runner 已关闭")


def get_runner() -> Runner:
    if _runner is None:
        raise RuntimeError("Runner 未初始化，请先调用 init_runner()")
    return _runner
