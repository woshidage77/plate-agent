# PlateAgent Day 6-A：FastAPI + SSE 流式服务化（考试向）

> 源：FastAPI 官方文档 + sse-starlette + tRPC-Agent Runner 事件流
> 用途：7.1 犀牛鸟考试知识储备

---

## 一、为什么需要服务化

### 1.1 前五天的问题

前五天的代码只能通过命令行脚本运行：

```bash
python -m agent.main          # 手动跑
python -m agent.main_graph    # 手动跑
```

这不能给前端调用，不能给 Postman 测试，不能给评审演示。

### 1.2 Day 6 的答案

把 Agent 包装成 HTTP 服务：

```前端 / Postman / curl
  ↓ HTTP POST
FastAPI (uvicorn)
  ↓ Runner.run_async()
tRPC-Agent (LlmAgent / GraphAgent)
  ↓ SSE 流式事件
前端实时渲染
```

---

## 二、SSE 是什么

### 2.1 SSE vs WebSocket

| | SSE (Server-Sent Events) | WebSocket |
|---|---|---|
| 方向 | 单向：服务端→客户端 | 双向 |
| 协议 | HTTP（标准） | ws://（升级协议） |
| 重连 | 浏览器自动 | 需手动实现 |
| 复杂度 | 极简 | 较复杂 |
| 适用 | 流式文本推送 | 实时双向通信 |

**AI 流式输出天然适合 SSE**——服务端推送，客户端接收，不需要客户端回传。

### 2.2 SSE 协议格式

```event: text_delta
data: {"content": "识"}

event: text_delta
data: {"content": "别"}

event: done
data: {"session_id": "abc-123"}
```

每条消息由 `event:` 行和 `data:` 行组成，空行分隔。

### 2.3 FastAPI 中的 SSE

使用 `sse-starlette` 库：

```python
from sse_starlette.sse import EventSourceResponse

@router.post("/api/chat")
async def chat(req: ChatRequest):
    async def event_generator():
        yield {"event": "text_delta", "data": '{"content": "你好"}'}
        yield {"event": "done", "data": '{"session_id": "..."}'}

    return EventSourceResponse(event_generator())
```

---

## 三、Runner 在服务中的生命周期

### 3.1 核心问题

Runner 包装了 Agent + SessionService + MemoryService。在命令行脚本中，每次运行创建一次。但在 HTTP 服务中：

- 不能每个请求创建一个 Runner（太重，每次都初始化）
- 不能所有请求共享同一个 Session（不同用户/会话需要隔离）

### 3.2 解决方案

**Runner 进程级单例 + Session 请求级隔离**：

```启动时：
  init_runner() → 创建 Runner（含 Agent + SessionService + MemoryService）
  存入模块级 _runner 变量

每个请求：
  get_runner() → 返回同一个 _runner
  通过 session_id 隔离不同用户/会话的数据
```

### 3.3 双 Agent 架构

| 端点 | Agent | 类型 | 用途 |
|------|-------|------|------|
| /api/chat | root_agent | LlmAgent | 对话入口，模型自由决策 |
| /api/recognize | recognition_agent | GraphAgent | 确定性识别流水线 |

两个端点共享同一个 SessionService 和 MemoryService，保证跨端点数据一致。

---

## 四、FastAPI lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await init_runner()     # 初始化 Agent + Session/Memory
    yield
    # shutdown
    await shutdown_runner() # 关闭 Runner
```

lifespan 是 FastAPI 的启动/关闭钩子，替代了旧的 `@app.on_event("startup")`。

---

## 五、考试速记卡

| 考点 | 答案 |
|------|------|
| SSE 全称？ | Server-Sent Events |
| SSE 和 WebSocket 的核心区别？ | SSE 单向（服务端→客户端），WebSocket 双向 |
| SSE 协议格式？ | event: <type> + data: <json> + 空行分隔 |
| FastAPI 怎么返回 SSE？ | EventSourceResponse(async_generator) |
| Runner 在服务中的生命周期？ | lifespan startup 创建单例，所有请求共享 |
| Session 怎么隔离？ | 每个请求独立的 session_id |
| 双 Agent 架构？ | /api/chat 用 LlmAgent，/api/recognize 用 GraphAgent |
| 为什么 Session/Memory 要共享？ | 识别结果能通过 Memory 在后续 chat 中召回 |
