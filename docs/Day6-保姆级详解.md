# PlateAgent Day 6 保姆级详解：FastAPI + SSE 流式服务化

> 用类比理解概念，用项目真实代码验证，用完整链路串联一切。

---

## 零、先回答最可能问的：为什么命令行不够

前五天你一直在命令行跑 Agent。每次运行：

```bash
python -m agent.main          # 启动 → 跑一轮 → 结束
python -m agent.main_graph    # 启动 → 跑一轮 → 结束
```

问题很明显：**不能给前端用，不能给 Postman 用，不能给评审演示**。

Day 6 做的事：把前五天的 Agent 包一层 HTTP 服务。前端发 HTTP 请求，服务端跑 Agent，结果用 SSE 流式推回去。

---

## 一、SSE 是什么——水管类比

### 1.1 普通 HTTP 请求

你打开水龙头（发请求），等水桶接满（等响应），水桶满了才端走（前端渲染）。

**问题**：AI 生成回复可能要 5-10 秒。用户盯着白屏等 10 秒，体验极差。

### 1.2 SSE

水龙头一直开着（HTTP 连接保持），水一滴一滴流出来（逐 token 推送），你边接水边喝（前端逐字渲染）。

**效果**：用户 0.1 秒就看到第一个字，心理等待感几乎为零。

### 1.3 SSE vs WebSocket

| | SSE | WebSocket |
|---|---|---|
| 方向 | 单向：服务端→客户端 | 双向 |
| 协议 | 纯 HTTP | ws:// 升级 |
| 浏览器支持 | EventSource API 原生 | 需要库 |
| 适用场景 | AI 流式输出 / 进度推送 | 聊天室 / 游戏 |

**AI 生成回复是天然的单向推送**——服务端生成，客户端接收。不需要客户端回传任何东西。所以 SSE 是正确选择。

### 1.4 SSE 数据格式

服务端发出的每一帧都长这样：

```event: text_delta
data: {"content": "识"}

event: text_delta
data: {"content": "别"}

event: done
data: {"session_id": "abc-123"}
```

- `event:` 行是事件类型（前端用来分类处理）
- `data:` 行是 JSON 载荷
- 空行分隔两个事件

---

## 二、FastAPI 怎么跑 SSE——EventSourceResponse

### 2.1 核心代码

server/routes/chat.py 的 SSE 返回：

```python
from sse_starlette.sse import EventSourceResponse

@router.post("/api/chat")
async def chat(req: ChatRequest, runner=Depends(get_runner)):
    async def event_generator():
        # runner.run_async() 产生的每个事件 → yield 一个 SSE dict
        async for event in runner.run_async(...):
            ...
            yield {"event": "text_delta", "data": json.dumps({...})}
        yield {"event": "done", "data": json.dumps({...})}

    return EventSourceResponse(event_generator())
```

`EventSourceResponse` 接收一个异步生成器，自动按 SSE 格式输出。你不需要处理 HTTP 分块、Content-Type、连接保持——`sse-starlette` 全封装了。

### 2.2 Runner 事件 → SSE 事件的映射

server/routes/chat.py 的 `_stream_chat_events()` 函数：

```python
async def _stream_chat_events(runner, ...):
    async for event in runner.run_async(...):
        if EventUtils.is_graph_event(event):
            continue                     # ← 跳过图内部事件

        if event.partial:                # ← 流式文本片段
            for part in event.content.parts:
                if part.text:
                    yield {"event": "text_delta", ...}

        for part in event.content.parts: # ← 完整事件
            if part.function_call:
                yield {"event": "tool_call", ...}
            elif part.function_response:
                yield {"event": "tool_result", ...}
```

**映射关系**：

| Runner 事件 | SSE event type |
|------------|----------------|
| `event.partial=True, part.text` | `text_delta` |
| `part.function_call` | `tool_call` |
| `part.function_response` | `tool_result` |
| 流结束 | `done` |
| 异常 | `error` |

---

## 三、双 Agent 架构——什么时候用谁

### 3.1 问题

前五天 `root_agent` 是 GraphAgent。GraphAgent 的特点是**流程固定**——任何输入都走预处理→定位→分割→识别。你发一句"你好"，它也去跑识别流水线。

API 服务有两种需求：
- 闲聊聊天天 → 需要灵活的 LlmAgent
- 识别车牌 → 需要确定性的 GraphAgent

### 3.2 解决方案

graph_agent.py 导出两个 Agent：

```python
root_agent = _create_chat_agent()          # LlmAgent → /api/chat
recognition_agent = create_graph_agent()   # GraphAgent → /api/recognize
```

| 端点 | Agent | 决策方式 |
|------|-------|---------|
| /api/chat | LlmAgent | 模型自由选择：闲聊 or 调工具 |
| /api/recognize | GraphAgent | 确定性流水线，4 节点固定执行 |

但两个端点**共享同一个 SessionService 和 MemoryService**。这样 /api/recognize 产生的识别结果，后续 /api/chat 可以通过 Memory 召回。

### 3.3 代码证据

server/routes/recognize.py：

```python
# 复用 chat Runner 的 session/memory 服务
session_service = chat_runner.session_service
memory_service = chat_runner.memory_service

# 但用 GraphAgent 做识别
recognize_runner = Runner(
    app_name=app_name,
    agent=recognition_agent,           # ← GraphAgent
    session_service=session_service,   # ← 共享
    memory_service=memory_service,     # ← 共享
)
```

---

## 四、Runner 的单例管理——lifespan 模式

### 4.1 问题

每个 HTTP 请求都 new 一个 Runner → 每次都重新加载 Agent、工具、Session/Memory 服务 → 极慢。

### 4.2 解决方案

server/dependencies.py 实现 Runner 单例：

```python
_runner: Optional[Runner] = None     # 模块级全局变量

async def init_runner() -> Runner:
    global _runner
    if _runner is not None:
        return _runner                 # 已存在，直接返回

    # 首次创建
    session_service = create_session_service(use_redis=False)
    memory_service = create_memory_service(use_redis=False)
    _runner = Runner(
        app_name=_app_name,
        agent=root_agent,
        session_service=session_service,
        memory_service=memory_service,
    )
    return _runner

def get_runner() -> Runner:           # FastAPI Depends 注入
    if _runner is None:
        raise RuntimeError("Runner 未初始化")
    return _runner
```

FastAPI lifespan 在启动时调用 `init_runner()`：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_runner()       # startup
    yield
    await shutdown_runner()   # shutdown
```

### 4.3 请求隔离

Runner 是共享的，但会话通过 `session_id` 隔离：

```用户 A (session_id="aaa") → Runner → Session A 的 events/state
用户 B (session_id="bbb") → Runner → Session B 的 events/state
```

每个请求可以传已有的 `session_id` 继续对话，也可以不传让服务端自动生成新的。

---

## 五、从零到一的代码流程回顾

```server/schemas.py       ──→ ChatRequest / RecognizeRequest / SSEEvent
                              ↓
server/dependencies.py  ──→ init_runner() → Runner 单例
                              get_runner()  → FastAPI Depends
                              ↓
server/routes/chat.py   ──→ POST /api/chat
                              _stream_chat_events() → Runner 事件 → SSE 事件
                              ↓
server/routes/recognize.py ─→ POST /api/recognize
                              recognize_runner (GraphAgent, 共享 Session/Memory)
                              ↓
server/app.py           ──→ lifespan(Runner 启停) + CORS + 路由注册
                              ↓
server/main.py          ──→ uvicorn.run("server.app:app", port=8000)
```

---

## 六、考试速记卡

| 考点 | 答案 |
|------|------|
| SSE 全称？ | Server-Sent Events |
| SSE 和 WebSocket 核心区别？ | SSE 单向推送，WebSocket 双向 |
| FastAPI 怎么返回 SSE？ | EventSourceResponse(async_generator) |
| Runner 为什么做单例？ | 避免每个请求重新加载 Agent/工具/Session 服务 |
| 双 Agent 架构？ | /api/chat→LlmAgent(灵活对话), /api/recognize→GraphAgent(确定流水线) |
| 两个端点共享什么？ | SessionService + MemoryService（保证跨端点数据一致） |
| lifespan 做什么？ | startup 初始化 Runner，shutdown 关闭 Runner |
| SSE 事件类型有哪些？ | text_delta / tool_call / tool_result / final / error / done |
| 请求级隔离靠什么？ | session_id |
| 启动命令？ | python -m server.main --port 8000 |
