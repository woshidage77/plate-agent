# PlateAgent Day 1 保姆级详解：从零让 Agent 开口说话

> 使用方式：跟着代码逐段读，每个概念都有类比 + 代码引用

---

## 零、先回答你最可能问的：Agent 到底是什么

### 类比

Agent = 一个带工具箱的助手。

- **没有 Agent**：你给 DeepSeek 发一条消息，它回一条消息。每次对话独立，没有记忆。
- **有 Agent**：助手有自己的工具箱（FunctionTool）、记忆本（Session）、你给的指令手册（INSTRUCTION）。它能连续对话、自主调工具、记住上下文。

tRPC-Agent 框架帮你管理这个助手的"生命支持系统"——你不必自己写事件循环、Session 管理、工具调度。

---

## 一、六大抽象 —— Agent 身体的六个器官

| 概念 | 类比 | 对应类 |
|------|------|--------|
| **Agent** | 助手本人 | `LlmAgent` |
| **Runner** | 助手的管理者（排班、调度） | `Runner(app_name, agent, session_service)` |
| **Model** | 助手的大脑 | `OpenAIModel(model_name, api_key, base_url)` |
| **Tool** | 助手的工具箱 | `FunctionTool(fn)` |
| **Session** | 助手的短期记忆本（单次会话） | `InMemorySessionService` |
| **Memory** | 助手的长期记忆库（跨会话） | `MemoryService` |

---

## 二、一条消息的完整旅程

```
用户输入 "你好"
    │
    ▼
Runner.run_async(user_id, session_id, new_message)
    │
    ├── 1. Session 加载之前的聊天记录
    ├── 2. Agent 收到：你的 instruction + 聊天记录 + 用户新消息 + 工具列表
    ├── 3. Model 推理 → 决定"直接回复"还是"调工具"
    │       ├── 直接回复 → yield Event(partial=True, text="你")
    │       │              yield Event(partial=True, text="好")
    │       │              yield Event(partial=False, text="你好")
    │       └── 调工具    → yield Event(function_call={...})
    │                       → 框架自动执行工具
    │                       → yield Event(function_response={...})
    │                       → 结果送回模型 → 继续生成文本
    ├── 4. Session 写入新消息（只存 partial=False 的事件）
    └── 5. 事件流结束
```

---

## 三、事件流（Event Stream）—— 为什么不是普通请求/响应

### 类比

| 普通 HTTP | 事件流 |
|-----------|--------|
| 写信寄出 → 等3天 → 收到完整回信 | 打电话 → 对方边说边听 → 可以随时插话"等等，你刚才说啥？" |

### 技术本质

`runner.run_async()` 返回 `AsyncGenerator[Event, None]`——一个可以 await 的生成器。

```python
async for event in runner.run_async(...):
    # 每次 runner 内部 yield 一个 Event，这里就收到一个
    if event.partial:
        print(event.text, end="")   # 逐字打印（打字机效果）
```

**yield 和循环体交替执行**：生产者产出一个 Event → 消费者立刻处理 → 生产者继续产出下一个。不是等全部生成完再一次性返回，而是边生产边消费。

### partial=True vs partial=False

```
一个 event 只有两条路之一：

  路 A: partial=True  → 流式文本片段 → 只推给前端 → 不存 Session
  路 B: partial=False → 完整事件    → 可能是文本/function_call/function_response → 存 Session
```

为什么 `partial=True` 不存？如果每个 token 都存 Session，三句话就能撑爆上下文窗口。

---

## 四、文件职责——单向依赖链

```
main.py → llm_agent.py → config.py → .env
  ↑           ↑            ↑          ↑
启动对话    组装Agent    统一配置   唯一敏感信息
```

依赖方向永远单向，绝对不反向引用。每个文件只依赖它的"下一层"。

### config.py — 为什么要用三元组

[`agent/config.py`](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\config.py)：

```python
def get_model_config():
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY must be set")  # fail fast
    return DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
```

返回三元组而非 dict：3 个值刚好不混乱 + 函数体可以提前校验 + 调用方用解包语法 `api_key, url, name = get_model_config()` 一行搞定。

### llm_agent.py — 组装车间

[`agent/llm_agent.py`](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\llm_agent.py)：

```python
model = OpenAIModel(...)     # 大脑
agent = LlmAgent(             # 助手
    name="plate_assistant",
    model=model,
    instruction=INSTRUCTION,  # 指令手册
    tools=[],                 # 工具箱（Day 2 才装）
)
```

`INSTRUCTION` = 系统提示词 = 助手的"人设"。没有它，DeepSeek 就是一个通用聊天模型。

### main.py — 启动钥匙

[`agent/main.py`](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\main.py)：

```python
session_service = InMemorySessionService()     # 内存记忆本
runner = Runner(app_name, agent, session)      # 管理者
async for event in runner.run_async(...):       # 事件循环
    if event.partial:
        print(part.text, end="")               # 打字机效果
```

---

## 五、概念串联记忆

```
.env ──→ config.py ──→ llm_agent.py ──→ main.py
钥匙      读取钥匙     组装助手+大脑     启动对话
```

Day 1 的 Agent 是个"会说话的壳"——有大脑（Model）、有指令（INSTRUCTION）、有记忆（Session），但没有手（Tool）。Day 2 给它装上 12 只手。

---

*上一份：无（第一天）*  
*下一份：Day2-保姆级详解.md*
