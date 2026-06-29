"""PlateAgent Session & Memory 管理器

核心概念（考试重点）：
    Session  = 短期记忆 — 单个会话的聊天记录，模型自动加载到上下文
    Memory  = 长期记忆 — 跨会话共享，通过 load_memory_tool 检索

工厂函数设计：
    create_services(use_redis=False)
        → use_redis=False: InMemorySessionService + InMemoryMemoryService（开发）
        → use_redis=True:  RedisSessionService + RedisMemoryService（生产）

切换方式：
    改一行代码：create_services(use_redis=True)
"""

from trpc_agent_sdk.memory import (
    InMemoryMemoryService,
    MemoryServiceConfig,
)
from trpc_agent_sdk.sessions import (
    InMemorySessionService,
    SessionServiceConfig,
)

from .config import (
    get_redis_url,
    MEMORY_ENABLED,
    MEMORY_TTL_SECONDS,
    SESSION_EVENT_TTL_SECONDS,
    SESSION_MAX_EVENTS,
    SESSION_TTL_SECONDS,
)


def create_session_service(use_redis: bool = False):
    """创建 SessionService — 管理单个会话的对话历史。

    Session 里存什么：
        - 用户和 Agent 的每条消息（events 列表）
        - 会话状态（state dict，比如 PlateState 的字段）
        - 会话元数据（conversation_count、时间戳）

    Session 的生命周期：
        创建 → 对话中不断追加事件 → TTL 过期后自动清理
    """
    session_config = SessionServiceConfig(
        max_events=SESSION_MAX_EVENTS,                   # 最多保留 200 条事件
        event_ttl_seconds=SESSION_EVENT_TTL_SECONDS,     # 单条事件 1 小时后过期
        ttl=SessionServiceConfig.create_ttl_config(
            enable=True,
            ttl_seconds=SESSION_TTL_SECONDS,             # 整个会话 24 小时后过期
            cleanup_interval_seconds=3600,               # 每小时清理一次
        ),
    )

    if use_redis:
        # 生产环境：Redis 持久化，支持分布式
        from trpc_agent_sdk.sessions import RedisSessionService
        db_url = get_redis_url()
        return RedisSessionService(
            is_async=True,
            db_url=db_url,
            session_config=session_config,
        )
    else:
        # 开发环境：内存存储，进程重启丢失
        return InMemorySessionService(session_config=session_config)


def create_memory_service(use_redis: bool = False):
    """创建 MemoryService — 管理跨会话的长期记忆。

    Memory 里存什么：
        - 每个会话的完整事件（关键词匹配检索）
        - 按 user_id 隔离（用户 A 搜不到用户 B 的记忆）

    Memory 的访问方式：
        自动存储：Runner 在每次对话结束后自动调用 store_session()
        主动检索：Agent 通过 load_memory_tool 搜索历史记忆

    典型场景：
        用户："上次识别的那辆京A12345还在黑名单里吗？"
        Agent 调用 load_memory_tool(query="京A12345")
        → Memory 搜索历史事件 → 找到上次的识别记录 → 返回给模型
    """
    memory_config = MemoryServiceConfig(
        enabled=MEMORY_ENABLED,
        ttl=MemoryServiceConfig.create_ttl_config(
            enable=True,
            ttl_seconds=MEMORY_TTL_SECONDS,              # 记忆 24 小时后过期
            cleanup_interval_seconds=3600,
        ),
    )

    if use_redis:
        # 生产环境：Redis 持久化
        from trpc_agent_sdk.memory import RedisMemoryService
        db_url = get_redis_url()
        return RedisMemoryService(
            is_async=True,
            db_url=db_url,
            memory_service_config=memory_config,
        )
    else:
        # 开发环境：内存存储
        return InMemoryMemoryService(memory_service_config=memory_config)
