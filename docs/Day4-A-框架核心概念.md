# PlateAgent Day 4-A：Session + Memory 框架知识（考试向）

> 源：`trpc-agent/examples/session_service_with_redis/` + `memory_service_with_redis/` + 官方文档  
> 用途：7.1 犀牛鸟考试知识储备

---

## 一、Session vs Memory — 考试必考

| 特性 | Session | Memory |
|------|---------|--------|
| **作用域** | 单个会话 (session_id) | 跨会话（同一 user_id 共享） |
| **生命周期** | 随会话创建，TTL 过期后销毁 | 独立于会话，TTL 控制 |
| **存储内容** | 当前会话的完整对话事件 | 所有会话的事件（关键词匹配检索） |
| **访问方式** | 自动加载到 Agent 上下文 | 通过 `load_memory_tool` 主动检索 |
| **典型用途** | "刚才识别的是什么？"（同会话追问） | "上次那辆京A还在黑名单吗？"（跨会话追问） |

**类比**：
- Session = 你这次打电话的通话录音
- Memory = 你所有历史通话的文字摘要，按关键词搜索

---

## 二、Session 类

```python
from trpc_agent_sdk.sessions import Session

# 关键字段
session.id                # 会话 UUID
session.app_name          # 所属应用
session.user_id           # 所属用户
session.events            # Event 列表（对话历史）
session.state             # dict 状态（GraphAgent 的 State 存在这里）
session.conversation_count # 对话轮数
```

**事件过滤**：`SessionServiceConfig` 控制
- `max_events=200`：最多保留 200 条事件，旧的自动删除
- `event_ttl_seconds=3600`：单条事件 1 小时后过期

---

## 三、三种 Session 后端

| 后端 | 持久化 | 分布式 | TTL 机制 |
|------|--------|--------|---------|
| `InMemorySessionService` | ❌ 进程重启丢失 | ❌ 单进程 | 后台定时清理 |
| `RedisSessionService` | ✅ Redis | ✅ 多进程 | Redis EXPIRE 自动 |
| `SqlSessionService` | ✅ MySQL/PG | ✅ | SQL DELETE 批量 |

**构造方式**：

```python
from trpc_agent_sdk.sessions import RedisSessionService, SessionServiceConfig

config = SessionServiceConfig(
    max_events=200,
    event_ttl_seconds=3600,
    ttl=SessionServiceConfig.create_ttl_config(enable=True, ttl_seconds=86400),
)

session_service = RedisSessionService(
    is_async=True,
    db_url="redis://localhost:6379/0",
    session_config=config,
)
```

---

## 四、三种 Memory 后端

| 后端 | 搜索方式 | 持久化 |
|------|---------|--------|
| `InMemoryMemoryService` | 关键词匹配 | ❌ |
| `RedisMemoryService` | 关键词匹配 | ✅ |
| `SqlMemoryService` | 关键词匹配 + SQL | ✅ |

**构造方式**：

```python
from trpc_agent_sdk.memory import RedisMemoryService, MemoryServiceConfig

config = MemoryServiceConfig(
    enabled=True,
    ttl=MemoryServiceConfig.create_ttl_config(enable=True, ttl_seconds=86400),
)

memory_service = RedisMemoryService(
    is_async=True,
    db_url="redis://localhost:6379/0",
    memory_service_config=config,
)
```

**关键点**：`enabled=True` 时，Runner 自动在每轮对话结束后调用 `store_session()`。不需要手动触发。

---

## 五、Memory 搜索方式 — 关键词匹配

MemoryService 使用**关键词（词元）匹配**，而非语义搜索。

```python
# 内部逻辑
def extract_words_lower(text):
    words = set()
    words.update(re.findall(r'[A-Za-z]+', text))   # 英文单词
    words.update(re.findall(r'[\u4e00-\u9fff]', text)) # 中文字符
    return words

# 搜索时：任意查询词元命中即返回
memories = await memory_service.search_memory(
    key=f"{app_name}/{user_id}",
    query="京A12345",     # 会被拆成 {"京","A","12345"}
    limit=10,
)
```

---

## 六、State 作用域 — Session/User/App/Temp

| 前缀 | 作用域 | 生命周期 | 示例 |
|------|--------|---------|------|
| 无前缀 | 当前 Session | 随会话 | `current_step: "processing"` |
| `user:` | 同一用户所有 Session | 跨会话 | `user:language: "zh"` |
| `app:` | 整个应用 | 全局 | `app:version: "1.0"` |
| `temp:` | 单次 run_async | 不持久化 | `temp:cache: "..."` |

---

## 七、load_memory_tool — Agent 如何检索记忆

```python
from trpc_agent_sdk.tools import load_memory_tool

agent = LlmAgent(
    name="assistant",
    tools=[load_memory_tool],   # ← 注册这个工具
    instruction="Use load_memory to recall past conversations.",
)
```

Agent 调用 `load_memory_tool` 时，框架自动：读取当前 session 的 user_id/app_name → 构建 search_key → 调用 `memory_service.search_memory()`。

---

## 八、考试速记卡

| 考点 | 答案 |
|------|------|
| Session vs Memory 区别？ | Session=单会话上下文，Memory=跨会话关键词检索 |
| Memory 搜索方式？ | 关键词（词元）匹配，非语义搜索 |
| Memory 如何启用？ | `MemoryServiceConfig(enabled=True)` + 传入 Runner |
| Session 事件过滤？ | `max_events` 限数量，`event_ttl_seconds` 限时间 |
| 三种 Session 后端？ | InMemory / Redis / SQL |
| 三种 Memory 后端？ | InMemory / Redis / SQL |
| State 四种作用域？ | Session(无前缀) / `user:` / `app:` / `temp:` |
| `load_memory_tool` 做什么？ | Agent 调用此工具主动检索跨会话记忆 |
| Memory 自动存储？ | `enabled=True` 时 Runner 自动调 `store_session()` |
| TTL 刷新时机？ | 访问时刷新（`get_session` / `search_memory`） |

---

*关联笔记：Day4-B-项目搭建流程.md / Day4-保姆级详解.md*
