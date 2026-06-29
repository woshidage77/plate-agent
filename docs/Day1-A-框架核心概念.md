# PlateAgent Day 1-A：tRPC-Agent 框架核心概念（考试向）

> 源：`trpc-agent/examples/quickstart/` + SDK 源码  
> 用途：7.1 犀牛鸟考试知识储备

## 一、六大基础抽象

| 概念 | 一句话 | 对应类 |
|------|--------|--------|
| **Agent** | 智能体，接收输入→推理→调工具→输出 | `LlmAgent`, `GraphAgent`, `ChainAgent` |
| **Runner** | Agent 的执行引擎，管理事件循环和生命周期 | `Runner(app_name, agent, session_service)` |
| **Model** | 大模型抽象，OpenAI兼容协议 | `OpenAIModel(model_name, api_key, base_url)` |
| **Tool** | Agent 可调用的函数/外部服务 | `FunctionTool`, `MCPToolset` |
| **Session** | 单次会话的消息、状态、事件管理 | `InMemorySessionService`, `RedisSessionService` |
| **Memory** | 跨会话长期记忆，支持写入/检索/召回 | `MemoryService` (InMemory/Redis/SQL/Mem0) |

## 二、一次 Agent 调用的完整链路

```
用户输入 (Content/Part)
    │
    ▼
Runner.run_async(user_id, session_id, new_message)
    │
    ├── 1. Session 加载历史消息 + 状态
    ├── 2. Agent 接收 input + instruction + tools schema
    ├── 3. Model 推理 → 决定 直接回复 or 调用工具?
    │       ├── 直接回复 → 流式 text event (event.partial=True)
    │       └── function_call event → 框架自动执行工具
    │               ├── function_response 送回模型
    │               └── 模型基于工具结果生成最终回复
    ├── 4. Session 写入新消息
    └── 5. 返回事件流 (async generator)
```

## 三、事件流 (Event Stream) 结构

```python
async for event in runner.run_async(...):
    # event.partial=True  → 流式片段 (逐token)
    if event.partial:
        for part in event.content.parts:
            if part.text:  print(part.text, end="", flush=True)

    # event.partial=False → 完整事件
    else:
        for part in event.content.parts:
            if part.function_call:       # {"name": "xxx", "args": {...}}
            if part.function_response:   # {"response": {...}}
            if part.thought:             # 思考过程 (DeepSeek-R1)
            if part.text:                # 完整文本块
```

## 四、最小 LlmAgent 写法

```python
# agent/agent.py
from trpc_agent_sdk.agents import LlmAgent
from trpc_agent_sdk.models import OpenAIModel

model = OpenAIModel(
    model_name="deepseek-chat",
    api_key="sk-xxx",
    base_url="https://api.deepseek.com",
)

agent = LlmAgent(
    name="assistant",
    model=model,
    instruction="你是助手",
    tools=[],  # 空 → 纯对话
)
```

## 五、带工具的 LlmAgent

```python
from trpc_agent_sdk.tools import FunctionTool

def get_weather(city: str) -> dict:
    """获取指定城市天气"""
    return {"city": city, "temp": "25°C"}

agent = LlmAgent(
    name="weather_bot",
    model=model,
    instruction="你是天气助手",
    tools=[FunctionTool(get_weather)],
)
```

**三条铁律：**
1. 函数必须有**类型注解** (`city: str`) → 框架自动生成 JSON Schema
2. 函数必须有**docstring** → 第一行作 tool description 传给模型
3. 返回值可以是 `dict/str/list`，框架自动序列化

## 六、Runner 启动模式

```python
# 标准模式 — 手动管理 Session
session_service = InMemorySessionService()
runner = Runner(app_name="app", agent=agent, session_service=session_service)

await session_service.create_session(app_name, user_id, session_id)
user_content = Content(parts=[Part.from_text(text="你好")])

async for event in runner.run_async(user_id, session_id, user_content):
    ...
```

## 七、Session 三种后端

| 后端 | 适用 | 特点 |
|------|------|------|
| `InMemorySessionService` | 开发测试 | 进程重启丢失 |
| `RedisSessionService` | 生产环境 | 持久化，分布式 |
| `SQLSessionService` | 审计需求 | MySQL/PG，结构化查询 |

## 八、LlmAgent vs GraphAgent 选择

| 场景 | 用 |
|------|-----|
| 需要模型推理、工具调用、自由对话 | `LlmAgent` |
| 确定性多步骤流水线，步骤不可乱 | `GraphAgent` |
| 组合使用 | 外层 LlmAgent 对话 + 内层 GraphAgent 流水线 |

---

*下一份：Day 1-B 笔记 → 项目搭建流程*  
*考试重点：六大抽象、事件流结构、两条铁律（类型注解 + docstring）*
