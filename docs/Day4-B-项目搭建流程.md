# PlateAgent Day 4-B：Session + Memory 项目搭建（搭建向）

> 工作区：`plate-agent/agent/`  
> 目标：Session 持久化 + 跨会话 Memory 检索  
> 对应的 SDK 知识：`Day4-A-框架核心概念.md`

---

## 搭建前的思考：为什么需要 Session 和 Memory？

Day 1-3 用的 `InMemorySessionService`：进程重启，对话历史全丢。用户关了重开，Agent 像失忆一样。

真实场景：
- 用户识别完车牌，关掉窗口 → 过一会回来问"刚才那辆京A呢？"
- 用户上周识别了一辆黑名单车 → 这周又来一辆，系统应该提醒

这需要两层记忆：
- **Session**（短期）：这次对话的上下文（"刚才"）
- **Memory**（长期）：跨对话的历史记录（"上周"）

---

## Step 1：扩展 config.py

[agent/config.py](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\config.py) 新增：

```python
# Session 配置
SESSION_EVENT_TTL_SECONDS = 3600   # 单条事件 1 小时过期
SESSION_MAX_EVENTS = 200           # 最多 200 条事件
SESSION_TTL_SECONDS = 86400        # 整个会话 24 小时过期

# Memory 配置
MEMORY_ENABLED = True              # 默认开启
MEMORY_TTL_SECONDS = 86400         # 记忆 24 小时过期

def get_redis_url() -> str:
    """构建 Redis URL，支持无密码/有密码/自定义三种模式"""
```

**设计决策**：`get_redis_url()` 返回连接字符串。切换 Redis 时只需确保 Redis 在跑，不用改代码。

---

## Step 2：创建 session_manager.py — 统一工厂

[agent/session_manager.py](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\session_manager.py)：

```python
def create_session_service(use_redis=False):
    if use_redis:
        return RedisSessionService(...)
    else:
        return InMemorySessionService(...)  # 当前使用

def create_memory_service(use_redis=False):
    if use_redis:
        return RedisMemoryService(...)
    else:
        return InMemoryMemoryService(...)  # 当前使用
```

**设计决策**：工厂函数封装了后端切换逻辑。`main.py` 只需 `create_session_service(use_redis=True/False)`，一行切换。所有配置参数从 `config.py` 读取，不在工厂里硬编码。

---

## Step 3：更新 main_graph.py — Runner 接入 Memory

[agent/main_graph.py](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\main_graph.py)：

```python
session_service = create_session_service(use_redis=False)
memory_service = create_memory_service(use_redis=False)

runner = Runner(
    app_name="plate_agent_day4",
    agent=root_agent,
    session_service=session_service,
    memory_service=memory_service,   # ← Day 4 新增
)
```

Runner 拿到 `memory_service` 后，自动在每轮对话结束后调用 `memory_service.store_session()`——不需要手动触发。

---

## Step 4：更新 knowledge.py — tool_query_history 接入真实 Memory

[agent/tools/knowledge.py](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\tools\knowledge.py) 用 `InvocationContext` 获取 MemoryService：

```python
async def tool_query_history(
    plate_number: str = "",
    limit: int = 10,
    tool_context: InvocationContext = None,  # ← 框架自动注入
) -> dict:
    memory_service = tool_context.memory_service
    search_key = f"{app_name}/{user_id}"
    response = await memory_service.search_memory(
        key=search_key, query=plate_number, limit=limit
    )
    # 提取事件文本 → 返回 records
```

**设计决策**：Day 2 的 `tool_query_history` 返回空列表。Day 4 变成真实查询，但函数签名不变——向后兼容。

---

## Step 5：验证结果

```
场景1: Session 持久化
  第1轮: 14 条事件写入 Session
  第2轮: 同一 session，事件追加到 14+ 条
  State 保留 20+ 字段（preprocess_output, locate_output, ...）

场景2: 跨会话 Memory
  Session A: 7 条事件 → 自动存入 Memory
  Session B: 新会话 → Memory 检索到 2 条相关记忆
```

---

## 搭建思路总结

```
新增/修改文件              核心变化
─────────────              ────────
config.py                  新增 SESSION_*/MEMORY_* 配置 + get_redis_url()
session_manager.py ← 新建  工厂函数：一键切换 InMemory ↔ Redis
main_graph.py              接入 MemoryService + 跨会话验证场景
tools/knowledge.py          tool_query_history 从占位 → 真实 Memory 查询

不变文件
─────────
graph_agent.py / nodes.py   不变（Runner 接口兼容）
```

**核心理念**：Session=短期上下文（自动加载），Memory=长期记忆（主动检索）。Runner 同时托管两者，Memory 自动存储无需手动触发。

---

*关联笔记：Day4-A-框架核心概念.md / Day4-保姆级详解.md*
