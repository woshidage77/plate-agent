# PlateAgent Day 3-A：GraphAgent 框架知识（考试向）

> 源：`trpc-agent/examples/graph/` + SDK 源码 `dsl/graph/` + 官方文档 `docs/mkdocs/zh/graph.md`  
> 用途：7.1 犀牛鸟考试知识储备 — Graph 模块

---

## 一、为什么要 GraphAgent？

| 场景 | 用 LlmAgent | 用 GraphAgent |
|------|------------|--------------|
| 自由对话、闲聊 | ✅ | ❌ |
| 需要模型推理决策 | ✅ | 部分（llm_node） |
| **确定性多步骤流水线** | ❌ 模型可能跳步 | ✅ 严格按图执行 |
| 条件分支（if/else） | 依赖 instruction 引导 | ✅ 代码级精确控制 |
| 混合 LLM + 代码 + 子Agent | 被动调用 | ✅ 主动编排 |

**GraphAgent 的本质**：你把流程图（DAG）画好，框架保证按图执行。节点可以是纯函数、LLM调用、子Agent、代码执行器、知识库检索——任意组合。

---

## 二、StateGraph 核心 API

### 2.1 节点类型

| 方法 | 节点类型 | 考试关键词 |
|------|---------|-----------|
| `add_node(name, action)` | 纯函数节点（必须 async def） | 业务逻辑、数据清洗 |
| `add_llm_node(name, model, instruction, tools)` | LLM 节点（内置 tool calling 循环） | 分类、摘要、工具增强 |
| `add_agent_node(node_id, agent)` | 子 Agent 节点（LlmAgent/GraphAgent） | 多 Agent 协作 |
| `add_code_node(name, code_executor, code, language)` | 代码执行节点 | Python/Shell 脚本 |
| `add_knowledge_node(name, query, tool)` | 知识库检索节点 | RAG 问答 |
| `add_mcp_node(name, mcp_toolset, ...)` | MCP 工具节点 | 外部服务调用 |

### 2.2 边的类型

```python
# 固定边 — A 完成后必定走 B
graph.add_edge("node_a", "node_b")

# 条件边 — A 完成后根据 state 决定走 B 还是 C
graph.add_conditional_edges(
    "node_a",              # 源节点
    route_func,            # 路由函数: (state) -> route_key
    {                      # 路由映射: route_key -> 目标节点名
        "high": "node_b",
        "low":  "node_c",
    },
)

# 快捷方式
graph.set_entry_point("first_node")   # START → first_node
graph.set_finish_point("last_node")   # last_node → END
```

### 2.3 compile 与 GraphAgent

```python
graph = StateGraph(MyState)
# ... 添加节点和边 ...

compiled = graph.compile()
agent = GraphAgent(
    name="my_workflow",
    description="我的工作流",
    graph=compiled,
)
# agent 交给 Runner 执行，和 LlmAgent 完全一样
```

---

## 三、State — 节点间共享数据容器

### 3.1 定义 State

```python
from typing import Any
from typing_extensions import Annotated
from trpc_agent_sdk.dsl.graph import State, append_list

class MyState(State):
    """继承框架 State，定义业务字段。"""
    query: str = ""           # 普通字段 — 单节点写入即可
    result: str = ""
    step_count: int = 0

    # Reducer 字段 — 多节点累积写入
    execution_log: Annotated[list[dict[str, Any]], append_list]
```

### 3.2 节点如何读写 State

```python
async def my_node(state: MyState) -> dict[str, Any]:
    # 读 — state.get(key, default)
    query = state.get("query", "")

    # 处理...
    result = process(query)

    # 写 — 返回 dict 增量更新
    return {"result": result, "step_count": 1}
```

**关键规则**：节点返回的是增量 dict，框架自动合并到 State。不会覆盖其他节点写入的字段。

### 3.3 Reducer — 多节点写入同一字段的规则

| Reducer | 行为 |
|---------|------|
| `append_list` | 追加到列表（适合日志、执行历史） |
| `merge_dict` | 浅合并 dict |
| `messages_reducer` | 消息列表追加 |
| 无 Reducer（普通字段） | 覆盖写入 |

---

## 四、节点签名 — 依赖注入

节点函数必须 `async def`，框架根据参数名自动注入：

```python
# 最小签名
async def node(state: State) -> dict: ...

# 流式输出（向客户端推送进度文本）
async def node(state: State, async_writer: AsyncEventWriter) -> dict: ...

# 获取会话上下文（user_id, session_id）
async def node(state: State, ctx: InvocationContext) -> dict: ...

# 完整签名
async def node(state: State, async_writer: AsyncEventWriter, ctx: InvocationContext) -> dict: ...
```

**考试重点**：`async_writer.write_text("xxx")` 是推送给用户看的流式文本。被 await 时确保写入顺序。

---

## 五、GraphAgent 事件流 — 比 LlmAgent 多了什么

GraphAgent 的事件流 = LlmAgent 事件流 + 图元数据：

```python
from trpc_agent_sdk.dsl.graph import (
    NodeExecutionMetadata,   # 节点开始/完成/错误
    ExecutionPhase,          # START / COMPLETE / ERROR
    ModelExecutionMetadata,  # 模型调用开始/完成
    ToolExecutionMetadata,   # 工具执行开始/完成
    EventUtils,              # is_graph_event() 判断
)

async for event in runner.run_async(...):
    node_meta = NodeExecutionMetadata.from_event(event)
    if node_meta:
        if node_meta.phase == ExecutionPhase.START:
            print(f"节点 {node_meta.node_id} 开始")
        elif node_meta.phase == ExecutionPhase.COMPLETE:
            print(f"节点 {node_meta.node_id} 完成")

    # 非图内部事件（文本、工具调用等）
    if not EventUtils.is_graph_event(event) and event.content:
        # 和 LlmAgent 一样处理
```

---

## 六、内置 State Key 常量

| 常量 | 实际 Key | 含义 |
|------|---------|------|
| `STATE_KEY_USER_INPUT` | `user_input` | 当前轮用户输入 |
| `STATE_KEY_LAST_RESPONSE` | `last_response` | 最终输出文本 |
| `STATE_KEY_LAST_TOOL_RESPONSE` | `last_tool_response` | 最近工具执行结果 |
| `STATE_KEY_NODE_RESPONSES` | `node_responses` | 按节点聚合的响应 |
| `STATE_KEY_MESSAGES` | `messages` | 会话消息列表 |

---

## 七、考试速记卡

| 考点 | 答案 |
|------|------|
| GraphAgent vs LlmAgent 选择？ | LlmAgent=自由决策，GraphAgent=确定性流水线 |
| 节点函数必须什么签名？ | `async def` |
| 节点间如何传数据？ | 返回 dict → State 自动合并 |
| 条件路由怎么写？ | `add_conditional_edges(source, router, path_map)` |
| 路由函数签名？ | `(state: State) -> str`（返回 path_map 的 key） |
| State 定义方式？ | 继承 `State` 类，声明字段 |
| Reducer 作用？ | 控制多节点写入同一字段的行为 |
| `append_list` 做什么？ | 追加到列表，不覆盖 |
| `add_llm_node` 能调 tool 吗？ | 能，内置 function_call → execute → 回填循环 |
| `add_agent_node` 能传什么？ | 任意 BaseAgent（LlmAgent/GraphAgent/TeamAgent） |
| compile 后怎么执行？ | 包进 `GraphAgent(graph=compiled)`，交 Runner |
| 如何向客户端推送进度？ | `async_writer.write_text("xxx")` |
| 事件流多了什么？ | `NodeExecutionMetadata`（节点开始/完成/错误） |
| `EventUtils.is_graph_event()` 作用？ | 判断事件是否是图内部事件，过滤掉避免干扰 |

---

*关联笔记：Day3-B-项目搭建流程.md → 4节点编排 + 条件路由实战*  
*下一份：Day4-A → Session + Memory 深度*
