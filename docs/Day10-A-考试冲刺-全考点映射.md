# PlateAgent Day 10-A：犀牛鸟考试全考点映射

> 把 tRPC-Agent 考试大纲的每一个考点，映射到 PlateAgent 项目的具体文件+代码。
> 用途：7.1 犀牛鸟考试最后冲刺。按考纲顺序逐条过。

---

## 一、基础篇

### 1.1 Agent 工程化核心概念

**考点**：理解 Agent、Runner、Model、Tool、Session、Memory、Graph 等基础抽象

| 抽象 | 项目对应 | 关键代码 |
|------|---------|---------|
| **Agent** | `LlmAgent` — 对话入口 | [agent/llm_agent.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/llm_agent.py) — `LlmAgent(name="plate_agent", model=..., instruction=..., tools=[...])` |
| **Runner** | Runner 单例管理 | [server/dependencies.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/server/dependencies.py) — `Runner(app_name=..., agent=root_agent, session_service=..., memory_service=...)` |
| **Model** | DeepSeek via OpenAI 兼容接口 | [agent/config.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/config.py) — `OpenAIModel(model_name="deepseek-chat", api_key=..., base_url=...)` |
| **Tool** | 12 个 FunctionTool | [agent/tools/preprocess.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/tools/preprocess.py) — `FunctionTool(func=tool_gaussian_blur)` 模式 |
| **Session** | InMemory / Redis 切换 | [agent/session_manager.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/session_manager.py) — `create_session_service(use_redis=True/False)` |
| **Memory** | InMemory / Redis 切换 | [agent/session_manager.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/session_manager.py) — `create_memory_service(use_redis=True/False)` |
| **Graph** | GraphAgent 6 节点流水线 | [agent/graph_agent.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/graph_agent.py) — `GraphAgent(name="plate_graph", nodes=[...], edges=[...])` |

**口述框架**：Agent 是大脑（LlmAgent 负责对话和工具调用），Runner 是调度器（管理 Session/Memory/Agent 生命周期），Model 是 LLM 后端，Tool 是 Agent 的手，Session 存短期上下文，Memory 存长期记忆，Graph 编排多步骤流水线。

### 1.2 一次 Agent 调用的完整链路

```
用户输入 "识别车牌 /tmp/car.jpg"
  │
  ▼
Runner.run_async(user_id, session_id, message)
  │
  ├── SessionService.get(session_id) → 恢复历史消息
  ├── MemoryService.search(query) → 召回长期记忆
  │
  ▼
Agent.run_async(ctx)
  │
  ├── LlmAgent: 构造 messages = [system_instruction, history..., user_msg]
  ├── Model.generate(messages, tools) → LLM 返回 tool_calls
  ├── Tool.execute(tool_call) → 调用 FunctionTool
  ├── Model.generate(messages, tool_result) → LLM 返回最终回复
  │
  ▼
Runner 产出事件流:
  ├── TextEvent("预处理完成")
  ├── TextEvent("识别结果: 京A12345")
  └── FinalEvent
  │
  ▼
SessionService.append(session_id, events) → 持久化
```

### 1.3 Quickstart：LlmAgent + Runner 多轮对话 + 流式输出

**项目对应**：[agent/llm_agent.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/llm_agent.py)

```python
# 最小 Agent 三要素：模型 + 指令 + 工具
agent = LlmAgent(
    name="plate_agent",
    model=OpenAIModel(model_name="deepseek-chat", ...),
    instruction="你是一个车牌识别助手...",
    tools=[tool_gaussian_blur, tool_grayscale, ...],
)

# Runner 管理生命周期
runner = Runner(
    app_name="plate_agent",
    agent=agent,
    session_service=InMemorySessionService(),
)

# 流式调用
async for event in runner.run_async(user_id="u1", session_id="s1", new_message=...):
    print(event.content)  # 逐块输出
```

### 1.4 Function Calling 与工具调用

**考点**：FunctionTool 封装、工具 schema、入参/返回值、错误处理、模型触发工具调用过程

**项目对应**：[agent/tools/preprocess.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/tools/preprocess.py)

```python
# 普通函数 → FunctionTool（一行封装）
def tool_gaussian_blur(image_path: str, kernel_size: int = 5) -> dict:
    """对车牌图像应用高斯滤波，减少噪声。  ← docstring 自动生成 schema
    Args:
        image_path: 输入图像路径
        kernel_size: 高斯核大小（奇数）
    Returns:
        {"status": "ok", "output_path": "..."}  ← 结构化返回值
    """
    img = cv2.imread(image_path)
    result = cv2.GaussianBlur(img, (kernel_size, kernel_size), 0)
    output_path = image_path.replace(".jpg", "_blur.jpg")
    cv2.imwrite(output_path, result)
    return {"status": "ok", "output_path": output_path}

# 注册为 FunctionTool
FunctionTool(func=tool_gaussian_blur)
```

**关键理解**：模型不"调用"你的函数——模型返回 `tool_calls: [{name: "tool_gaussian_blur", args: {...}}]`，然后 tRPC-Agent 框架执行函数，把结果再发给模型。

### 1.5 Session 会话管理

**考点**：消息/状态/事件/token usage 管理，InMemory/Redis/SQL 适用场景

**项目对应**：[agent/session_manager.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/session_manager.py)

| 后端 | 场景 | 关键代码 |
|------|------|---------|
| InMemorySessionService | 开发/单进程 | `create_session_service(use_redis=False)` |
| RedisSessionService | 生产/多进程 | `create_session_service(use_redis=True)` |

**环境变量切换**：`USE_REDIS=true` → Redis 后端，一行代码完成切换。

---

## 二、进阶篇

### 2.1 Memory 与 Knowledge / RAG

**考点**：长期记忆写入/检索/召回，知识库文档加载/切分/向量化/检索/提示词拼接

**项目对应**：
- **Memory**：[agent/session_manager.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/session_manager.py) — `create_memory_service()`
- **RAG 知识库**：[agent/knowledge/loader.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/knowledge/loader.py) — ChromaDB 三集合
- **检索工具**：[agent/tools/knowledge.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/tools/knowledge.py) — `tool_search_blacklist()`, `tool_lookup_confusion()`

```
RAG 流程 (PlateAgent)：
  文档（黑名单 CSV + 混淆字符表）
    → ChromaDB loader 分块 + 向量化
    → 存入 ChromaDB 三集合（blacklist / plate_specs / confusion_chars）
    → 识别时 tool_search_blacklist(plate) → 向量检索 → 返回命中结果
    → 结果拼入 LLM prompt → 生成最终回复
```

### 2.2 多 Agent 协作与图编排

**考点**：Chain、Parallel、Cycle、TeamAgent、GraphAgent；节点、边、条件路由、状态 reducer、checkpoint、interrupt/resume

**项目对应**：[agent/graph_agent.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/graph_agent.py) + [agent/graph_nodes.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/graph_nodes.py)

| 概念 | PlateAgent 实现 |
|------|---------------|
| **GraphAgent** | 6 节点流水线：preprocess → locate → segment → recognize → llm_verify → format_output |
| **条件路由** | `needs_llm_verify` 字段：True → 走 llm_verify 节点，False → 跳过 |
| **状态传递** | `PlateState`（TypedDict）在节点间传递，每个节点返回 dict 增量 |
| **状态 reducer** | State 字段默认为覆盖策略（graph_state.py 中定义） |

```
GraphAgent 编排 (PlateAgent)：
  preprocess ──→ locate ──→ segment ──→ recognize ──┬── needs_verify=true ──→ llm_verify ──→ format_output
                                                     │
                                                     └── needs_verify=false ──────────────→ format_output
```

**Chain/Parallel/Cycle 概念**（项目暂未实现，但考试需知）：
- Chain：A → B → C，顺序执行
- Parallel：A、B、C 同时执行，等待全部完成
- Cycle：A → B → A → ... ，循环直到条件满足

### 2.3 MCP、A2A 与 AG-UI 协议

**考点**：Agent 接入外部工具服务、Agent 间互通、前端结构化事件、FastAPI/Gateway/Go Server 服务化

**项目对应**：
- **FastAPI 服务化**：[server/app.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/server/app.py) — `FastAPI + lifespan + CORS`
- **SSE 流式**：[server/routes/chat.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/server/routes/chat.py) — `StreamingResponse(event_stream, media_type="text/event-stream")`
- **AG-UI 事件**：`AsyncEventWriter` 在 graph_nodes.py 中写文本事件，AG-UI 定义标准事件类型

| 协议 | 用途 | 项目状态 |
|------|------|---------|
| MCP (Model Context Protocol) | Agent ↔ 外部工具服务 | 概念理解（项目未直接实现） |
| A2A (Agent-to-Agent) | Agent ↔ Agent 互通 | 概念理解 |
| AG-UI | Agent → 前端事件输出 | `AsyncEventWriter` 写事件流 |
| FastAPI | HTTP 服务化 | 完整实现 |

### 2.4 Skills 与 CodeExecutor

**考点**：SKILL.md 技能描述、skill load/run、workspace runtime、本地/容器/Cube/E2B 执行

**项目对应（Day 10 新增）**：
- **SKILL.md**：[skills/plate_recognition/SKILL.md](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/skills/plate_recognition/SKILL.md) — frontmatter + body + Tools 节
- **SkillLoader**：[agent/skill_loader.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/skill_loader.py) — 解析 SKILL.md，提取 name/description/tools

**SKILL.md 核心结构**：
```markdown
---
name: skill-name           # 技能唯一标识
description: One-liner     # 简短描述
---

## Overview                # 功能概述
...

## Tools                   # 该技能暴露的工具列表
- tool_a
- tool_b

## Usage Pattern           # 使用方式
...

## Examples                # 示例
...
```

**执行环境对比**：
| 环境 | 特点 | 安全性 |
|------|------|--------|
| 本地执行 | 直接在当前进程运行 Python | 无隔离 |
| 容器执行 (Docker) | 独立的 Docker 容器 | 进程级隔离 |
| Cube 沙箱 | 腾讯内部轻量沙箱 | 强隔离 |
| E2B 沙箱 | 云端安全沙箱 | 最强隔离 |

### 2.5 评测、优化与可观测性

**考点**：Eval set、metric、LLM Judge、rubric evaluator、prompt iteration、AgentOptimizer、OpenTelemetry、Langfuse、token usage、延迟/错误率

**项目对应**：

| 能力 | 项目文件 |
|------|---------|
| Eval set (30 张测试图) | [eval/dataset/generate.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/eval/dataset/generate.py) — clear/blur/tilt/noise 4组 |
| 精确匹配评测 | [eval/evaluator.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/eval/evaluator.py) — 准确率/字符级/分组/黑名单命中 |
| LLM Judge | [eval/judge.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/eval/judge.py) — 三维语义评分 |
| 评测报告 | [eval/report.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/eval/report.py) — Markdown 报告生成 |
| OpenTelemetry | [agent/telemetry.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/telemetry.py) — init_telemetry() + @trace_node + trace_block |
| Token 追踪 | [agent/token_tracker.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/token_tracker.py) — TokenTracker 线程安全 + 成本估算 |

---

## 三、实战篇

### 3.1 工具调用基础助手

**已完成**：Day 1 的 12 个 FunctionTool + LlmAgent 对话入口

```
plate_agent (LlmAgent)
  ├── tool_gaussian_blur()
  ├── tool_grayscale()
  ├── tool_binarize_otsu()
  ├── tool_edge_detect_canny()
  ├── tool_affine_correct()
  ├── tool_morphology_locate()
  ├── tool_color_locate()
  ├── tool_vertical_projection()
  ├── tool_svm_predict()
  ├── tool_llm_verify()
  ├── tool_search_blacklist()
  └── tool_lookup_confusion()
```

### 3.2 RAG 问答 Agent

**已完成**：Day 5 ChromaDB 知识库 + 检索工具

### 3.3 Redis/SQL 持久化 Session

**已完成**：Day 4 `session_manager.py` — `USE_REDIS=true` 一键切换

### 3.4 自定义 Skill

**Day 10 新增**：[skills/plate_recognition/SKILL.md](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/skills/plate_recognition/SKILL.md) + [agent/skill_loader.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/skill_loader.py)

### 3.5 Agent 服务化

**已完成**：Day 6 FastAPI + SSE 流式 + AG-UI EventWriter

---

## 四、进阶挑战

### 4.1 多 Agent 企业知识助手

**概念对应 PlateAgent**：
- 多轮对话 → LlmAgent + Session
- 工具调用 → 12 FunctionTool
- 知识库检索 → ChromaDB RAG
- 长期记忆 → MemoryService
- 流式事件 → AsyncEventWriter
- 运行日志 → OpenTelemetry tracing

### 4.2 GraphAgent 工作流编排

**已完成**：Day 3 GraphAgent + 条件路由 + 状态管理

---

## 五、考试押题速查表

| 必考概率 | 考点 | 一句话答案 |
|---------|------|-----------|
| ★★★★★ | Agent 核心抽象 | Agent(LlmAgent), Runner, Model(OpenAIModel), Tool(FunctionTool), Session, Memory, Graph(GraphAgent) |
| ★★★★★ | FunctionTool 机制 | 普通函数 + docstring = schema，模型返回 tool_calls，框架执行并回传 |
| ★★★★★ | GraphAgent 节点/边/条件路由 | nodes=[A,B,C], edges=[A→B, B→C(条件)], 条件路由根据 state 字段决定下一节点 |
| ★★★★☆ | Session 后端对比 | InMemory(开发), Redis(生产多进程), SQL(持久化+查询) |
| ★★★★☆ | RAG 流程 | 文档→分块→向量化→存储(ChromaDB)→检索→拼prompt→生成 |
| ★★★★☆ | OTel Trace/Span | Trace=完整调用链, Span=链上一个节点, ConsoleSpanExporter(开发), OTLP(生产) |
| ★★★★☆ | SKILL.md 结构 | YAML frontmatter(name/description) + body + Tools 节 |
| ★★★☆☆ | MCP vs A2A vs AG-UI | MCP(工具服务), A2A(Agent互通), AG-UI(前端事件) |
| ★★★☆☆ | Memory vs Session | Session=短对话上下文, Memory=跨会话长期记忆 |
| ★★★☆☆ | FastAPI service 化 | lifespan管理Agent生命周期, SSE流式输出, CORS |