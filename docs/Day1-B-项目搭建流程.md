# PlateAgent Day 1-B：项目从零搭建流程（搭建向）

> 工作区：`plate-agent/`  
> 目标：让 Agent "开口说话" — DeepSeek 多轮对话跑通  
> 对应的 SDK 知识：`Day1-A-框架核心概念.md`

---

## 搭建前的思考：我们要搭什么？

**一句话**：一个能跟你对话的车牌识别助手，背后接的是 DeepSeek 模型。

但不是一个简单的"发请求→等回复"，而是一个**有状态、有工具、有记忆的 Agent**。

tRPC-Agent 框架帮我们处理了 Agent 生命周期、Session 管理、事件流推送。我们只需要组装零件。

---

## Step 1：环境准备

```bash
# Python 3.12 + venv
python -m venv venv
venv\Scripts\activate

# 核心依赖
pip install trpc-agent-sdk openai python-dotenv opencv-python numpy

# 从 GitHub 克隆 tRPC-Agent（看示例代码用）
git clone https://github.com/trpc-group/trpc-agent-python.git
# git 走代理：git config --global http.proxy http://127.0.0.1:7890
```

---

## Step 2：`.env` — 唯一敏感信息入口

```env
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

**设计决策**：API Key 只出现在 `.env` 一个文件里，所有代码通过 `os.getenv()` 读取。

---

## Step 3：`config.py` — 统一配置入口

```python
# agent/config.py
from dotenv import load_dotenv
load_dotenv()

def get_model_config():
    """返回 (api_key, base_url, model_name) 三元组"""
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY must be set in .env file")
    return DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
```

**设计决策：为什么是三元组而不是 dict 或 namedtuple？**

三个值刚好卡在"元组不混乱"的边界线。校验和返回分离——API Key 为空时在这里就直接报错（fail fast with clear message），而不是等到 `OpenAIModel()` 构造时才暴露（错误堆栈指向框架内部，不好排查）。调用方用解包语法 `api_key, url, name = get_model_config()` 一行拿到三个值。

---

## Step 4：`llm_agent.py` — Agent 定义（组装车间）

```python
# agent/llm_agent.py
from trpc_agent_sdk.agents import LlmAgent
from trpc_agent_sdk.models import OpenAIModel

INSTRUCTION = """你是 PlateAgent，车牌识别智能助手..."""

def create_plate_agent() -> LlmAgent:
    api_key, base_url, model_name = get_model_config()
    model = OpenAIModel(model_name=model_name, api_key=api_key, base_url=base_url)

    agent = LlmAgent(
        name="plate_assistant",
        description="车牌识别智能助手",
        model=model,
        instruction=INSTRUCTION,
        tools=[],  # Day 1 先不装工具
    )
    return agent

root_agent = create_plate_agent()
```

**设计决策**：
- `create_plate_agent()` 是工厂函数 — Day 2 加工具时只改这一个函数
- `INSTRUCTION` 定义 Agent 的"人设" — 后续逐渐丰富
- `root_agent` 是模块级变量 — `main.py` 直接 `from agent.llm_agent import root_agent`

---

## Step 5：`main.py` — Runner 启动入口 + 事件流详解

### 5.1 完整代码

```python
async def run():
    from agent.llm_agent import root_agent

    session_service = InMemorySessionService()         # ① 内存存会话
    runner = Runner(app_name="plate_agent",            # ② Runner 托管 Agent
                    agent=root_agent,
                    session_service=session_service)

    session_id = str(uuid.uuid4())
    await session_service.create_session(...)           # ③ 创建会话

    user_content = Content(parts=[Part.from_text(text="你好")])

    async for event in runner.run_async(...):           # ④ 拉事件流
        if not event.content or not event.content.parts:
            continue

        if event.partial:                               # 流式片段（逐 token）
            for part in event.content.parts:
                if part.text:
                    print(part.text, end="", flush=True)
            continue  # ← 注意：流式片段不进入下面的完整事件处理

        for part in event.content.parts:                # 完整事件
            if part.thought: continue                   # 跳过思考过程
            if part.function_call:
                print(f"\n  [调用工具: {part.function_call.name}]")
            elif part.function_response:
                print(f"  [工具返回: {part.function_response.response}]")
```

### 5.2 事件流核心机制 — AsyncGenerator

`runner.run_async()` 返回类型是 `AsyncGenerator[Event, None]`—— 一个可以 await 的生成器。

```python
async def run_async(...) -> AsyncGenerator[Event, None]:
    # 内部有 yield event 语句
    yield Event(partial=True, text="你")
    yield Event(partial=True, text="好")
    yield Event(partial=False, text="你好")
```

调用方用 `async for` 消费：

```python
async for event in runner.run_async(...):
    # 每次 yield，这里执行一次
    print(event.text)
```

yield 和循环体交替执行——生产者产出一个 Event，消费者立刻处理，然后生产者继续产出下一个。这不是"等全部生成完再一次性返回"，而是**边生产边消费**。

### 5.3 为什么用事件流而不是普通 HTTP 响应？

| 场景 | 普通请求/响应 | 事件流 |
|------|-------------|--------|
| 模型逐 token 生成 | 等 3 秒看到完整回复 | 立刻看到第一个字（打字机效果）|
| 模型中途调工具 | 无法表达"正在调工具" | yield function_call event |
| 工具执行完继续生成 | 需要第二次请求 | 同一个流里继续 yield text event |
| 多 Agent 接力 | 无法表达"子 Agent 介入" | 通过 author 字段区分 |

### 5.4 partial=True vs partial=False

```
一个 event 的生命周期只有两条路之一：

  路 A: partial=True  → 流式文本片段 → 打印 token（不换行）→ 不存 Session
  路 B: partial=False → 完整事件      → 可能是文本/function_call/function_response → 存 Session
```

`partial=True` 只用于推送打字机效果，不存库。`partial=False` 才写入 Session，作为下次对话的历史上下文。如果每个 token 都存 Session，几句话就能撑爆上下文窗口。

### 5.5 一个完整对话的事件时间线

```
用户: "你好，识别 plate.jpg"
    │
[Event 1]  partial=True,  text="好的"     → 终端打印 "好"
[Event 2]  partial=True,  text="，"       → 终端打印 "，"
[Event 3]  partial=True,  text="我来处理"  → 终端打印 "我来处理"
[Event 4]  partial=False, text="好的，我来处理。"  ← 完整句存入 Session
    │
[Event 5]  partial=False, function_call={tool_gaussian_blur, image_path="plate.jpg"}
    │        [框架自动执行工具]
[Event 6]  partial=False, function_response={status:"ok", output_path:"...blurred.jpg"}
    │        [结果送回模型]
    │
[Event 7]  partial=True,  text="接着"     → 继续流式输出
[Event 8]  partial=True,  text="灰度化"   → ...
```

---

## 搭建思路总结：Day 1 做了什么

```
.env → config.py → llm_agent.py → main.py
 ↑        ↑            ↑            ↑
密钥    统一读取    组装Agent    启动对话 + 事件循环
```

**依赖方向永远单向**：`main.py → llm_agent.py → config.py → .env`

Day 1 的 Agent 只是个"会说话的壳"，没有手（Tool）。Day 2 给它装上 12 只手。

---

*关联笔记：Day1-A-框架核心概念.md（考试向）*  
*下一份：Day2-A → FunctionTool 深度知识*
