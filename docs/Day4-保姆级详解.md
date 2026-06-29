# PlateAgent Day 4 保姆级详解：Session 与 Memory 从零理解

> 用类比理解概念，用项目真实代码验证，用完整链路串联一切。

---

## 零、从一个用户问题出发

打开两个终端窗口，发送同样的消息给同一个 Agent：

```窗口 A（session_id = "abc"）：
  用户: 识别这张车牌
  Agent: 结果：京A12345
  用户: 刚才的结果是什么？   ← 跟上一行在同一 session 里
  Agent: 京A12345            ← 正确回答，因为在同一 Session 中

窗口 B（session_id = "xyz"，同一天，同一用户）：
  用户: 上次识别的那辆京A还在黑名单中吗？
  Agent: 我正在查黑名单...    ← 这里需要 Memory 去搜历史
```

两个看似简单的对话，背后是两个完全不同的存储系统在协作。你作为用户感觉 Agent "有记忆"，但实际上分了两层：

- **Session** 回答了 "刚才的结果"——这是短期上下文，同一轮对话内有效
- **Memory** 回答了 "上次那辆京A"——这是长期记忆，跨对话检索

你打开手机上的任何一个聊天机器人，每次刷新页面它就不记得你说过什么了（Session 丢失），但如果它突然冒出一句 "根据您上次提到的……"——那就是 Memory 在工作了。

---

## 一、Session 到底是什么——用通话录音来理解

### 1.1 类比

你拨打银行客服热线。从接通的瞬间开始：

- 系统生成了一个 **通话编号**（= session_id）
- 你和客服说的每一句话都被 **录音**（= events 列表）
- 客服在纸上 **做的笔记**（= state dict）
- 这次通话结束后，录音保留 24 小时就删除（= TTL）
- 同一时间的每次通话都有独立的录音系统

**Session 就是这个"当前通话的完整记录"**。每次你创建新对话，就是开了一通新电话。

### 1.2 Session 对象里实际存了什么

在 tRPC-Agent 框架中，Session 对象的字段如下（这是框架定义的，不是我们写的）：

| 字段 | 类型 | 存储内容 | 类比 |
|------|------|---------|------|
| id | str | 会话 UUID | 通话编号 |
| app_name | str | 应用名称，如 "plate_agent_day4" | 呼叫中心名称 |
| user_id | str | 用户标识，如 "alice" | 来电号码 |
| events | list[Event] | 所有对话事件（用户消息、模型回复、工具调用） | 通话录音 |
| state | dict | 键值对状态（PlateState 的字段全在这里） | 客服手写笔记 |
| conversation_count | int | 对话轮数 | 通话中说了几轮 |

事件（Event）长什么样？Event 不是我们定义的类——它是框架内部结构。每条 Event 包含：

| 字段 | 含义 |
|------|------|
| author | 谁说的（"user" 或 "model"） |
| content | 说了什么（text、function_call、function_response） |
| timestamp | 什么时候说的 |
| partial | 是不是流式输出的片段 |

### 1.3 关键认知："刚才"是怎么工作的

当你问 "刚才识别结果是什么？"时，框架的运作流程：

```用户发消息 → Runner.run_async()
  → Runner 从 SessionService 加载当前 session 的 events 列表
  → 框架将 events 序列化成模型上下文（类似 ChatGPT 的对话历史）
  → 模型看到之前的所有消息，理解"刚才"指什么
  → 模型生成回复
  → Runner 将新消息追加进 session.events
```

这个流程里，**你没有写任何代码来"加载上下文"**。框架在你调用 runner.run_async() 时自动完成了 Session 加载 → 上下文化 → 新事件写入。

验证代码在 main_graph.py:70：

```python
session = await session_service.get_session(
    app_name="plate_agent_day4", user_id=user_id, session_id=session_id
)
event_count = len(session.events) if session else 0
state_keys = list(session.state.keys()) if session and session.state else []
print(f"
[Session 状态] 事件数: {event_count}, State 字段: {state_keys}")
```

运行后输出类似：

```[Session 状态] 事件数: 14, State 字段: ['image_path', 'preprocess_output',
                                         'locate_output', 'segment_chars',
                                         'recognize_chars', 'needs_llm_verify', 'last_response']
```

14 个事件 = 两轮对话（用户消息 ×2 + 模型回复 ×2 + GraphAgent 内部工具调用 ×N）。State 字段 = PlateState 类的所有字段 + 框架内置的 `last_response`。

### 1.4 创建 Session 时设置初始 State

main_graph.py:84 的代码：

```python
await session_service.create_session(
    app_name="plate_agent_day4",
    user_id=user_id,
    session_id=session_id,
    state={"image_path": "eval/dataset/test_images/synth_plate.jpg"},
)
```

这里 `state={"image_path": "..."}` 的值来自 PlateState（graph_state.py:10）的第一个字段：

```python
class PlateState(State):
    image_path: str = ""        # ← 就是这个
    preprocess_output: str = ""
    locate_output: str = ""
    segment_chars: list[str] = []
    recognize_chars: list[dict[str, Any]] = []
    needs_llm_verify: bool = False
    final_plate: str = ""
```

Session 创建时 image_path 被设置为 synth_plate.jpg。随后：

1. GraphAgent 的第一个节点 preprocess_node 从 `state.get("image_path")` 读取这个值
2. 处理完成后返回 `{"preprocess_output": "..."}`
3. 框架自动将返回的 dict 合并到 session.state
4. 下一个节点 locate_node 从 `state.get("preprocess_output")` 读取

这就是为什么节点之间不需要传参——**所有数据都在 session.state 这个共享字典里，由框架自动维护**。

---

## 二、TTL 到底怎么工作——不是简单的一个数字

### 2.1 类比：酒店退房规则

想象你住酒店：

- **你每天续房**：从你最后一次出现开始，往后推 24 小时。如果你第二天又来了，退房时间就往后推
- **房间里的物品逐件过期**：你放在房间里的外卖 1 小时后就得扔掉，但行李箱可以留到退房
- **清洁工定时检查**：每小时来一次，把过期的外卖扔掉

这三个规则分别对应 Session 的三种 TTL 配置。

### 2.2 三层 TTL 对照

config.py:19 的配置：

```python
SESSION_EVENT_TTL_SECONDS = int(os.getenv("SESSION_EVENT_TTL", "3600"))   # 3600秒 = 1小时
SESSION_MAX_EVENTS      = int(os.getenv("SESSION_MAX_EVENTS", "200"))     # 200条
SESSION_TTL_SECONDS     = int(os.getenv("SESSION_TTL", "86400"))          # 86400秒 = 24小时
MEMORY_TTL_SECONDS      = int(os.getenv("MEMORY_TTL", "86400"))           # 86400秒 = 24小时
```

session_manager.py:33 实际使用：

```python
session_config = SessionServiceConfig(
    max_events=SESSION_MAX_EVENTS,                   # ① 数量限制：最多存 200 条事件
    event_ttl_seconds=SESSION_EVENT_TTL_SECONDS,     # ② 事件级别 TTL：单条事件 1h 后过期
    ttl=SessionServiceConfig.create_ttl_config(
        enable=True,
        ttl_seconds=SESSION_TTL_SECONDS,             # ③ 会话级别 TTL：整个会话 24h 后过期
        cleanup_interval_seconds=3600,               #    清理间隔：每小时扫一次
    ),
)
```

三层 TTL 的精妙之处在于——它们是**叠加生效**而非简单覆盖：

| 层级 | 参数 | 默认值 | 判定规则 |
|------|------|--------|---------|
| 事件数量 | max_events | 200 | 超过 200 条 → 删除最旧的事件（FIFO），无论事件多新 |
| 事件时间 | event_ttl_seconds | 3600 | 单条事件的时间戳距今超过 1 小时 → 删除，无论总量多少 |
| 会话时间 | ttl_seconds | 86400 | 整个 session 的最后访问时间距今超过 24 小时 → 整个 session 删除 |

### 2.3 TTL 刷新时机——这是一个高频考点

TTL 的计数器不是创建时算死的。每次 get_session()（读取会话）或 run_async()（追加新事件）时，TTL 都会**从当前时间重新计算**。

用一个例子解释：

```
13:00  用户创建 session，对话一轮        → TTL 过期时间：明天 13:00
22:00  同一用户回来，继续这个 session    → TTL 过期时间刷新为：明天 22:00
第二天 21:00  用户又来了                  → TTL 过期时间刷新为：第三天 21:00
第三天 22:00  用户没来                     → session 被清理
```

这就解释了为什么 SESSION_TTL_SECONDS=86400（24小时）不是 "只能活 24 小时"，而是 **"24 小时不碰就死"**。每次访问都会续命。

### 2.4 InMemory 下的清理是怎么发生的

cleanup_interval_seconds=3600 只在 InMemory 模式下生效（Redis 模式由 Redis 自己管理）。它意味着：

```
InMemorySessionService 内部有一个后台任务：
  - 每小时醒来一次
  - 扫描所有 session
  - 对每个 session：
      ① 先清理 session.events 中 timestamp 超过 event_ttl_seconds 的单条事件
      ② 如果 events 总数超过 max_events，删除最旧的
      ③ 如果 session 的最后访问时间距今 > ttl_seconds，删除整个 session
  - 扫描完成后继续睡一小时
```

这个设计有个重要推论：**过期的 session 不是立即消失的**。如果 25 小时前用户离开了，清理间隔 1 小时意味着 session 在 24h~25h 之间的某个时间点被删除——精确到小时级别，但不是秒级。

Redis 模式下没有这个问题——Redis 用 EXPIRE 命令，过期键在下一次访问时立即返回 nil，精确到秒。

### 2.5 Memory 的 TTL 独立于 Session

session_manager.py:78：

```python
memory_config = MemoryServiceConfig(
    enabled=MEMORY_ENABLED,
    ttl=MemoryServiceConfig.create_ttl_config(
        enable=True,
        ttl_seconds=MEMORY_TTL_SECONDS,              # 默认 86400，也是 24h
        cleanup_interval_seconds=3600,
    ),
)
```

Session 和 Memory 的 TTL 是**独立计算**的。一个场景可以证明：

```
Session A 已过期被清理（24h 没访问）
→ Session A 的 events 不复存在
→ 但 Memory 中复制的那份事件还在（它的 TTL 从自己最后一次被访问算起）
→ 用户 25 小时后通过新 Session B 调用 tool_query_history
→ 因为 tool_query_history 访问了 Memory → Memory 的 TTL 刷新
→ Session A 的内容被检索到
```

Session 死了 Memory 还活着的状态，就是"你打新电话还能查到历史工单"——两者独立运行。

---

## 三、InMemory vs Redis —— 底层差在哪

### 3.1 类比

**InMemory** = 你在草稿纸上做笔记。能写能看，速度快。但是一阵风吹过来（进程重启），笔记全没了。别人（另一个进程）也看不到你的草稿纸。

**Redis** = 你在云笔记上做记录。能写能看，速度也快（因为 Redis 主要在内存工作）。手机重启（进程重启）不会丢，因为数据落地到硬盘（RDB/AOF）。别人（其他微服务实例）有权限也能看，因为存在共享的服务端。

### 3.2 代码层面的差异——只有一行

session_manager.py:11 的工厂函数设计：

```python
def create_session_service(use_redis: bool = False):
    session_config = SessionServiceConfig(...)  # 同样的配置对象

    if use_redis:
        from trpc_agent_sdk.sessions import RedisSessionService
        return RedisSessionService(
            is_async=True,
            db_url=get_redis_url(),           # redis://localhost:6379/0
            session_config=session_config,    # 同样的配置
        )
    else:
        return InMemorySessionService(session_config=session_config)
```

两个 SessionService 的**接口完全相同**（都实现了 create_session / get_session / list_sessions），区别只在实现层：

| 维度 | InMemorySessionService | RedisSessionService |
|------|----------------------|-------------------|
| 存储位置 | Python dict，堆内存 | Redis 服务端（内存 + 持久化文件） |
| 并发安全 | asyncio.Lock（单进程内） | Redis 单线程模型（天然原子操作） |
| 进程重启 | 全部丢失 | 不丢（如果有 RDB/AOF 持久化策略） |
| TTL 实现 | Python 后台 asyncio.Task 定时扫描 | Redis EXPIRE 命令，键自动过期 |
| 多实例共享 | 不可能（数据在进程内存中） | 天然支持（多个服务连同一个 Redis） |
| 启动速度 | 极快（无网络连接） | 需要建立 TCP 连接 + 认证 |
| 适用场景 | 本地开发、单元测试、原型验证 | 部署、多副本、生产环境 |

### 3.3 TTL 在 Redis 中的实现差异

InMemory 的 TTL 靠 Python 代码定时扫描实现（cleanup_interval_seconds）。Redis 完全不同：

```
RedisSessionService 在存储 session 时：
  SET session:plate_agent_day4:alice:session_abc {...}
  EXPIRE session:plate_agent_day4:alice:session_abc 86400

Redis 内部：
  键过期后，Redis 有两种删除策略：
    惰性删除：下次有人访问这个键时，发现过期，返回 nil 并删除
    定期删除：每秒随机抽 20 个键检查，过期的删除
```

cleanup_interval_seconds=3600 在 Redis 模式下**完全不生效**——这是框架文档没明说但代码能验证的设计细节。

### 3.4 为什么开发用 InMemory，生产用 Redis

回到项目代码 main_graph.py:70：

```python
session_service = create_session_service(use_redis=False)  # 开发：不依赖 Redis 也能跑
memory_service = create_memory_service(use_redis=False)    # 开发：不依赖 Redis 也能跑
```

写 Demo 时不希望必须先装 Redis 才能跑项目——这就是工厂函数的设计价值。

上线时，改一行：

```python
session_service = create_session_service(use_redis=True)
memory_service = create_memory_service(use_redis=True)
```

你不需要理解 Session 和 Memory 的内部实现，不需要学习 Redis 的 SET/GET/EXPIRE 命令，不需要管理连接池。工厂函数封装了一切。

---

## 四、Memory 自动存储——Runner 在背后做了什么

### 4.1 你写的代码只有一行

main_graph.py:76：

```python
runner = Runner(
    app_name="plate_agent_day4",
    agent=root_agent,
    session_service=session_service,
    memory_service=memory_service,   # ← Day 4 只加了这一行
)
```

加了这一行之后，Runner 内部的行为变了。我们来看 Runner 在你调用 run_async() 时到底做了什么。

### 4.2 完整链路——从用户消息到 Memory 存储

以场景 2 的 Session A 为例（main_graph.py:107）：

```python
# Session A: 第一次识别
await session_service.create_session(
    app_name="plate_agent_day4", user_id=user_id,
    session_id=session_a_id,
    state={"image_path": "eval/dataset/test_images/synth_plate.jpg"},
)

print("
[Session A] 用户 Alice: 识别这张车牌")
await _run_one_turn(runner, user_id, session_a_id, "识别这张车牌")
```

`_run_one_turn` 执行时，整个过程如下：

```① 用户消息 "识别这张车牌" → user_content 对象

② runner.run_async(user_id=user_id, session_id=session_a_id, new_message=user_content)
   │
   ├─ [Runner 内部] 从 session_service 加载 session (含 events + state)
   ├─ [Runner 内部] 将 events 序列化为模型上下文
   ├─ [Runner 内部] 模型生成回复（GraphAgent 走完整流水线）
   │   ├─ preprocess_node → 返回 {"preprocess_output": "blurred_...jpg"}
   │   ├─ locate_node → 返回 {"locate_output": "crop_...jpg"}
   │   ├─ segment_node → 返回 {"segment_chars": [...]}
   │   ├─ recognize_node → 返回 {"recognize_chars": [...], "needs_llm_verify": False}
   │   └─ format_output_node → 返回 {"last_response": "识别结果：京A12345"}
   ├─ [Runner 内部] 将用户消息 + 模型回复 + 工具调用 → 追加到 session.events
   ├─ [Runner 内部] 将节点返回的 dict 合并到 session.state
   │
   └─ [Runner 内部] ★ run_async 结束时：
        if memory_service is not None and MEMORY_ENABLED:
            await memory_service.store_session(session)
            # ↑ 将整个 session（含全部 events）复制到 Memory 中
            # key = "plate_agent_day4/alice"
```

**关键点**：你没有调 memory_service.store_session()。Runner 在 run_async() 的 finally（或等价的清理逻辑）中自动执行。你只需要把 memory_service 传给 Runner，其余全自动。

### 4.3 Memory 里存的是什么？和 Session 有什么不同？

store_session(session) 的行为：

```
Memory 存储结构（逻辑视图）：
  key: "plate_agent_day4/alice"
    ├─ event_001: {author: "user", text: "识别这张车牌", timestamp: ...}
    ├─ event_002: {author: "model", function_call: preprocess_node, ...}
    ├─ event_003: {author: "model", function_call: locate_node, ...}
    ├─ ...
    └─ event_007: {author: "model", text: "识别结果：京A12345", ...}
```

Memory 存的是**所有事件的副本**，不是摘要，不是总结，不是压缩。原始对话原文。

这很重要——因为不影响检索质量。如果存的是摘要，关键词可能丢失。存原文，你搜 "京A12345" 就一定能匹配到包含 "京A12345" 的事件。

### 4.4 为什么能跨会话

场景 2 的验证代码 main_graph.py:119：

```python
# Session B: 新会话，同一用户 — 通过 Memory 检索历史
session_b_id = "session_b_demo"
await session_service.create_session(
    app_name="plate_agent_day4", user_id=user_id,
    session_id=session_b_id,
    state={},                                    # ← 空 state，全新会话
)

print("
[Session B] 用户 Alice: 我之前识别过什么车牌？(新会话)")
```

Session B 的 session.events 是空的（刚创建），session.state 也是空的。如果只看 Session，Agent 对 "上次识别" 一无所知。

但用户问 "我之前识别过什么车牌？" 时，Agent 看到的是这样的上下文：

```[System] 你可以使用以下工具：
  - tool_query_history(plate_number, limit) — 查询历史车牌识别记录
  - tool_search_blacklist(plate_number) — 查询黑名单
  - ...

[User] 我之前识别过什么车牌？

[Model 思考] 用户想查历史识别记录，我应该调用 tool_query_history
             → tool_query_history(plate_number="", limit=10)
```

然后进入 Memory 检索流程。

---

## 五、Memory 检索——tool_query_history 逐行拆解

### 5.1 入口：InvocationContext 的神奇注入

agent/tools/knowledge.py:32：

```python
async def tool_query_history(
    plate_number: str = "",
    limit: int = 10,
    tool_context: Optional[InvocationContext] = None,   # ← 框架自动注入
) -> dict:
```

你写这个函数时声明了一个 tool_context 参数。调用时你不传这个参数——**框架在调用工具前自动注入**。InvocationContext 对象包含当前执行的全部上下文：

| 属性 | 含义 | 从哪里来 |
|------|------|---------|
| tool_context.session | 当前 Session 对象 | Runner 持有 |
| tool_context.memory_service | MemoryService 实例 | 你传给 Runner 的 |
| tool_context.agent | 当前 Agent 实例 | Runner 持有 |

### 5.2 构建搜索 Key

```python
session = tool_context.session
app_name = session.app_name        # "plate_agent_day4"
user_id = session.user_id          # "alice"

search_key = f"{app_name}/{user_id}"  # "plate_agent_day4/alice"
```

Key 的结构是 `{app_name}/{user_id}`。这就是 Memory 的数据隔离机制——搜索 key 把你限定在当前应用 + 当前用户的命名空间内。你搜不到 Bob 的识别记录，也搜不到其他应用的记录。

### 5.3 执行搜索

```python
query = plate_number if plate_number else "车牌 识别"

response = await memory_service.search_memory(
    key=search_key,       # "plate_agent_day4/alice"
    query=query,          # "京A12345" 或 "车牌 识别"
    limit=limit,          # 10
)
```

search_memory 内部做的是**关键词匹配**，不是语义搜索。它把查询字符串拆成词元（token），然后在 Memory 中匹配：

```
输入 query = "京A12345"
↓
拆词：{"京", "A", "12345"}    ← 中文按字拆，英文/数字按词拆
↓
在 key="plate_agent_day4/alice" 下遍历所有存储的事件：
  事件1: "识别这张车牌"              → ["识","别","这","张","车","牌"]  ∩ {"京","A","12345"} = ∅  → 不匹配
  事件2: (function_call preprocess)  → 跳过（非文本事件）
  ...
  事件7: "识别结果：京A12345"        → ["识","别","结","果","京","A","1","2","3","4","5"]
                                        ∩ {"京","A","12345"} = {"京","A","12345"}  → 命中！
```

这与 ChromaDB 的向量检索是两种完全不同的技术路径。关键词匹配的优点是**确定性**——有没有命中不依赖模型质量，只依赖字符串匹配。

### 5.4 提取文本并返回

```python
records = []
for mem in response.memories:
    text_parts = []
    if mem.content and mem.content.parts:
        for part in mem.content.parts:
            if part.text:
                text_parts.append(part.text)
    text = " ".join(text_parts)[:200]        # 截断 200 字，防止上下文过长

    records.append({
        "text": text,
        "author": mem.author if hasattr(mem, 'author') else "unknown",
        "timestamp": str(mem.timestamp) if hasattr(mem, 'timestamp') else "",
    })

return {"status": "ok", "records": records, "count": len(records)}
```

注意 `[:200]`——这截断了返回给模型的文本长度。不是 Memory 只存了 200 字，而是**返回时截断**，避免这些历史记录吃掉太多上下文窗口，挤占当前推理的空间。

### 5.5 完整数据流回顾

把整个 Memory 链路串起来：

```
用户问："上次那辆京A还在黑名单吗？"
↓
GraphAgent 模型看到工具列表中有 tool_query_history
↓
模型决定：调用 tool_query_history(plate_number="", limit=10)
↓
tool_query_history 执行：
  ① 从 tool_context 拿 session → 得到 app_name + user_id
  ② 从 tool_context 拿 memory_service
  ③ 构建 search_key = "plate_agent_day4/alice"
  ④ 调用 memory_service.search_memory(key, query="车牌 识别")
  ⑤ Memory 返回匹配的事件列表（含 Session A 的识别记录）
  ⑥ 工具返回 {"records": [{"text": "识别结果：京A12345", ...}, ...]}
↓
模型看到工具返回结果：
  "好的，根据历史记录，用户上次识别了京A12345。现在让我查黑名单..."
↓
模型调用 tool_search_blacklist("京A12345")
↓
模型输出最终回复
```

从用户视角，好像是 "Agent 记得上次的事"。从代码视角，是 Session A 的事件被 Runner 自动存储 → Memory 关键词匹配 → 返回给 Session B 的模型上下文。

---

## 六、Session 和 Memory 的本质对比——合在一起看

| 维度 | Session | Memory |
|------|---------|--------|
| **存什么** | 当前对话的实时事件流 | 所有历史对话的只读副本 |
| **写操作** | 每条消息追加写入（实时） | Runner 在 run_async 结束时批量复制 |
| **读操作** | Runner 自动加载到模型上下文 | 工具函数主动调用 search_memory |
| **隔离键** | {app_name}/{user_id}/{session_id} | {app_name}/{user_id}（无 session_id） |
| **生命周期** | 随会话创建，TTL 过期后销毁 | 独立 TTL，Session 销毁后 Memory 可能还在 |
| **触达方式** | 用户说 "刚才" → 模型自然理解 | 用户说 "上次" → 工具调用 search_memory |
| **容量控制** | max_events（200条）+ event_ttl（1h） | Memory TTL（24h）单一维度 |
| **代码代价** | 零（框架自动管理） | 写一个工具函数 + 传给 Runner 一行 |

本质区别一句话：**Session 是你正在打电话时的当前通话录音。Memory 是客服系统里的历史工单库**——客服听你的当前通话靠 Session，查你以前工单靠 Memory。

---

## 七、State 的四种作用域——前缀决定了"谁能看到"

框架支持四种 State 前缀，Day 4 的实现虽然没有全部用到，但面试必考。

### 7.1 Session State（无前缀）

```
state["image_path"] = "test.jpg"
state["preprocess_output"] = "blurred_003.jpg"
```

作用域：当前这个 session。你开了 5 个不同 session_id，每个都有独立的 image_path。

对应代码：PlateState 的所有字段（graph_state.py）默认都是 Session State。

### 7.2 User State（user: 前缀）

```
state["user:language"] = "zh"
state["user:preferred_unit"] = "km/h"
```

作用域：同一个 user_id 的所有 Session 共享。你换了个新 session，user:language 还在。

典型场景：用户偏好设置——语言、主题、单位制。跟单次对话无关，跟用户身份有关。

### 7.3 App State（app: 前缀）

```
state["app:version"] = "1.0.0"
state["app:blacklist_threshold"] = "0.85"
```

作用域：整个应用的所有用户、所有 Session 共享。所有连接到同一个 SessionService 的请求都能读到。

典型场景：全局配置项——模型版本、阈值、开关。改一处，所有用户生效。

### 7.4 Temp State（temp: 前缀）

```
state["temp:intermediate_result"] = "48x32"
```

作用域：仅在当前 run_async() 执行期间存在。函数返回后就丢弃，不写入 Session，更不写入 Memory。

典型场景：中间计算结果——你需要在函数 A 和函数 B 之间传数据，但不需要持久化。类似局部变量。

### 7.5 四种作用域对比

| 前缀 | 作用域 | 生命周期 | 持久化 | 典型场景 |
|------|--------|---------|--------|---------|
| 无前缀 | 当前 Session | 随会话 TTL | 是 | 车牌识别流水线状态 |
| user: | 同一用户所有 Session | 跨会话 | 是 | 语言偏好、主题设置 |
| app: | 整个应用所有用户 | 全局 | 是 | 模型版本、阈值配置 |
| temp: | 单次 run_async | 函数返回即丢 | 否 | 中间计算缓存 |

---

## 八、验证场景解读——跑完代码后看什么

### 8.1 场景 1：Session 持久化

```python
session_id = str(uuid.uuid4())      # 固定 session_id

# 第 1 轮
await _run_one_turn(runner, user_id, session_id, "识别这张车牌")
# → 产生 ~7 个 events（用户消息 + 模型回复 + 6 个图节点的事件）

# 第 2 轮（同一 session_id）
await _run_one_turn(runner, user_id, session_id, "刚才识别的结果是什么？")
# → events 追加到 ~14 个
# → 模型能回答"刚才"的问题，因为 session.events 里有完整的对话历史
```

你关注两个数据：
- **事件数从 ~7 → ~14**：证明追加机制正确
- **模型能回答"刚才"**：证明上下文加载正确

### 8.2 场景 2：跨会话 Memory

```python
# Session A — 产生识别结果
session_a_id = "session_a_demo"
await _run_one_turn(runner, user_id, session_a_id, "识别这张车牌")

# Session B — 不同 session_id，空 state
session_b_id = "session_b_demo"
await _run_one_turn(runner, user_id, session_b_id, "我之前识别过什么车牌？")

# 直接检索 Memory 验证
memories = await memory_service.search_memory(
    key="plate_agent_day4/alice", query="车牌 识别", limit=10
)
```

你关注三个数据：
- **Session B 的事件数 < Session A**：证明 Session 独立（新会话事件从零开始）
- **Memory 检索命中 ≥1 条**：证明 Session A 的识别记录被自动存储到 Memory
- **Agent 能回答"之前"**：证明 Memory 检索链路完整

---

## 九、从零到一的代码流程回顾

```config.py                          ──→ SESSION_TTL_SECONDS = 86400
                                       MEMORY_TTL_SECONDS = 86400
                                       MEMORY_ENABLED = True
                                       ↓
session_manager.py                 ──→ create_session_service(use_redis=False)
                                       create_memory_service(use_redis=False)
                                           ↓ 读取 config.py 中的常量
                                           ↓ 构造 SessionServiceConfig / MemoryServiceConfig
                                           ↓ 返回 InMemorySessionService / InMemoryMemoryService
                                       ↓
main_graph.py                      ──→ Runner(..., memory_service=memory_service)
                                           ↓ Runner 拿到 memory_service 引用
                                           ↓
                                       用户调用 runner.run_async()
                                           ↓
                                       ┌─ Runner 加载 session（events + state）
                                       ├─ Runner 调用 GraphAgent（走完整流水线）
                                       ├─ Runner 追加新 events 到 session
                                       ├─ Runner 合并节点返回 dict 到 session.state
                                       └─ Runner 调用 memory_service.store_session(session)
                                           ↓
                                       用户新会话问"上次" →
                                       模型调用 tool_query_history
                                           ↓
tool_query_history                 ──→ tool_context.memory_service.search_memory(
                                           key="plate_agent_day4/alice",
                                           query="车牌 识别"
                                       )
                                           ↓
                                       返回历史事件文本 → 模型知道"上次"是什么
```

---

## 十、考试速记卡

| 考点 | 答案 |
|------|------|
| Session vs Memory 本质区别？ | Session 是当前通话录音（自动加载到上下文），Memory 是历史工单库（工具主动检索） |
| Session 的三层 TTL？ | max_events（数量限制 200）→ event_ttl（单条事件 1h）→ session_ttl（整体 24h），叠加生效 |
| TTL 什么时候刷新？ | 每次访问（get_session / run_async）时重新计时 |
| InMemory vs Redis 的核心差异？ | InMemory 数据在进程堆内存，重启丢失；Redis 在独立服务端，持久化 + 多进程共享 |
| cleanup_interval_seconds 在 Redis 下生效吗？ | 不生效，Redis 用 EXPIRE 自身机制 |
| Memory 是怎么存进去的？ | Runner 在 run_async 结束时自动调用 store_session()，不需要手写代码 |
| Memory 的搜索方式？ | 关键词（词元）匹配，不是语义搜索。中文按字拆，英文按词拆 |
| Memory 的隔离键是什么？ | {app_name}/{user_id}，不包含 session_id |
| tool_query_history 怎么拿到 Memory 服务？ | tool_context: InvocationContext 参数，框架自动注入 |
| State 四种作用域？ | 无前缀=Session，user:=同用户跨会话，app:=全应用，temp:=单次 run_async 不持久化 |
| Session events 包含什么？ | 所有对话事件：用户消息、模型回复、function_call、function_response |
| 怎么从 InMemory 切 Redis？ | create_session_service(use_redis=True)，改一个参数 |
