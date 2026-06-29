# PlateAgent Day 3-B：GraphAgent 4节点流水线搭建（搭建向）

> 工作区：`plate-agent/agent/`  
> 目标：从 LlmAgent 切换到 GraphAgent — 确定性流水线 + 条件路由  
> 对应的 SDK 知识：`Day3-A-框架核心概念.md`

---

## 搭建前的思考：为什么要从 LlmAgent 切换到 GraphAgent？

Day 1-2 的 LlmAgent：模型看 instruction + tool schema，自己决定每一步调什么。

```
LlmAgent: "嘿 DeepSeek，你自己看着办"      ← 自由但不可控
```

问题：车牌识别是**确定性流水线**——必须按 预处理→定位→分割→识别 的顺序。LlmAgent 虽然测试中没出过错，但理论上可能跳步或调错顺序。

```
GraphAgent: "按这个流程图，一步不许跳"    ← 你说了算
```

GraphAgent 把"模型自主编排"换成"你画图，框架执行"。节点间通过 State 传递数据，比 tool 之间靠模型推理串链更可靠。

---

## Step 1：新增文件结构

```
agent/
├── config.py           (不变)
├── llm_agent.py        (保留 — 对话入口)
├── graph_state.py      ← 新建：4节点共享数据容器
├── graph_nodes.py      ← 新建：6个节点函数
├── graph_agent.py      ← 新建：GraphAgent 组装
├── main.py             (保留 — LlmAgent 入口)
└── main_graph.py       ← 新建：GraphAgent 验证入口
```

---

## Step 2：graph_state.py — 定义共享黑板

```python
class PlateState(State):
    image_path: str = ""        # 用户输入
    preprocess_output: str = "" # 预处理产出
    locate_output: str = ""     # 定位产出
    segment_chars: list = []    # 分割字符路径列表
    recognize_chars: list = []  # SVM 识别结果
    needs_llm_verify: bool = False  # 条件路由标志
    final_plate: str = ""       # 最终车牌号
```

**设计决策**：State 是节点间**唯一的通信方式**。没有全局变量、没有共享内存。每个字段代表流水线中一个阶段的产出，由对应节点写入，下游节点读取。

`needs_llm_verify` 是关键字段——它不存数据，而是**控制条件路由的分流方向**。

---

## Step 3：graph_nodes.py — 6个节点函数

### 3.1 节点设计模式

每个节点遵循相同的模式：

```python
async def xxx_node(state: PlateState, async_writer: AsyncEventWriter) -> dict:
    """节点描述"""
    # ① 从 State 读取输入
    input_data = state.get("field_name", default)

    # ② 推送进度给用户
    await async_writer.write_text("[阶段名] 开始...\n")

    # ③ 执行处理（直接调用 tools/ 函数，非 FunctionTool）
    result = some_tool(input_data)

    # ④ 推送结果
    await async_writer.write_text(f"[阶段名] 完成\n")

    # ⑤ 返回增量 dict → 合并到 State
    return {"field_name": result["output_path"]}
```

**设计决策**：节点**直接调用** `tools/preprocess.py` 中的函数，不通过 `FunctionTool`。因为 GraphAgent 不需要模型推理——节点函数自己就是执行者。`FunctionTool` 是给 LlmAgent 用的，让模型能"看到"工具箱；GraphAgent 的节点直接用函数即可。

### 3.2 四个核心节点

| 节点 | 调用工具 | 产出 |
|------|---------|------|
| `preprocess_node` | 5个预处理工具链式调用 | `preprocess_output` |
| `locate_node` | morphology_locate → color_locate | `locate_output` |
| `segment_node` | vertical_projection | `segment_chars` |
| `recognize_node` | svm_predict 逐个识别 | `recognize_chars` + `needs_llm_verify` |

### 3.3 条件路由的关键：recognize_node

```python
async def recognize_node(state, async_writer):
    needs_verify = False
    results = []
    for char_path in state["segment_chars"]:
        svm_result = tool_svm_predict(char_path)
        if svm_result["needs_verify"]:
            needs_verify = True  # ← 任一字符低置信度就设标志
        results.append(svm_result)

    return {
        "recognize_chars": results,
        "needs_llm_verify": needs_verify,  # ← 条件路由的判定依据
    }
```

---

## Step 4：graph_agent.py — 把节点拼成图

### 4.1 路由函数

```python
def _route_after_recognize(state: PlateState) -> str:
    """条件路由：有低置信度字符 → LLM复核，否则 → 直接输出"""
    if state.get("needs_llm_verify", False):
        return "verify"     # → llm_verify_node
    return "output"         # → format_output_node
```

**关键约定**：路由函数返回的字符串必须匹配 `add_conditional_edges` 的 `path_map` 中的 key。

### 4.2 图构建

```python
def _build_recognition_graph() -> StateGraph:
    graph = StateGraph(PlateState)

    # 添加 6 个节点
    graph.add_node("preprocess", preprocess_node, config=...)
    graph.add_node("locate", locate_node, config=...)
    graph.add_node("segment", segment_node, config=...)
    graph.add_node("recognize", recognize_node, config=...)
    graph.add_node("llm_verify", llm_verify_node, config=...)
    graph.add_node("format_output", format_output_node, config=...)

    # 固定链路：按顺序走
    graph.set_entry_point("preprocess")
    graph.set_finish_point("format_output")
    graph.add_edge("preprocess", "locate")
    graph.add_edge("locate", "segment")
    graph.add_edge("segment", "recognize")

    # 条件路由：recognize → verify 或 output
    graph.add_conditional_edges(
        "recognize",
        _route_after_recognize,
        {"verify": "llm_verify", "output": "format_output"},
    )
    graph.add_edge("llm_verify", "format_output")

    return graph
```

### 4.3 包装为 GraphAgent

```python
def create_graph_agent() -> GraphAgent:
    graph = _build_recognition_graph()
    return GraphAgent(
        name="plate_recognition",
        description="车牌识别确定性流水线",
        graph=graph.compile(),
    )

root_agent = create_graph_agent()
```

**设计决策**：GraphAgent 和 LlmAgent 用同样的 `root_agent` 导出，`main.py` 只需要改一行 import 就能切换。Runner 不关心 Agent 是 LlmAgent 还是 GraphAgent——接口完全一致。

---

## Step 5：main_graph.py — 入口与事件流

与 Day 1 的 `main.py` 相比，GraphAgent 的事件循环**多了节点元数据**：

```python
async for event in runner.run_async(...):
    # 图节点元数据 — GraphAgent 特有
    node_meta = NodeExecutionMetadata.from_event(event)
    if node_meta:
        if node_meta.phase == ExecutionPhase.START:
            print(f"[节点开始] {node_meta.node_id}")
        elif node_meta.phase == ExecutionPhase.COMPLETE:
            print(f"[节点完成] {node_meta.node_id}")

    # 过滤图内部事件
    if EventUtils.is_graph_event(event):
        continue

    # 流式文本（和 LlmAgent 一样）
    if event.partial and part.text:
        print(part.text, end="")
```

**新增概念**：`EventUtils.is_graph_event()` 过滤掉 Graph 内部状态更新事件，避免用户看到"状态变更"等无用日志。

---

## Step 6：端到端验证结果

```
[节点开始] preprocess
  [预处理] 高斯滤波... 完成 → 灰度化... 完成 → ... → 仿射矫正... 完成
[节点完成] preprocess

[节点开始] locate
  [定位] 形态学候选 1 个 → HSV精定位完成
[节点完成] locate

[节点开始] segment
  [分割] 垂直投影 → 分割出 0 个字符
[节点完成] segment

[节点开始] recognize
[节点完成] recognize        ← needs_llm_verify=False, 路由到 format_output

[节点开始] format_output
  识别结果：识别失败
[节点完成] format_output
```

**6 个节点严格按序执行**，条件路由生效（0 字符 → 不触发 LLM 复核），`async_writer` 流式进度正常推送到客户端。

字符分割 0 个是 OpenCV 在合成图上的适配问题。这个 Day 7（评测集 + 真实车牌图）会解决。**架构层面验证通过。**

---

## 搭建思路总结：Day 3 做了什么

```
新增文件                    核心变化
─────────                  ────────
graph_state.py             定义了 State 类 — 节点间唯一的数据通道
graph_nodes.py              6个节点函数 — 每个负责一个阶段
graph_agent.py              组装图 + condition_edges — 确定性流水线
main_graph.py               GraphAgent 版入口 — NodeExecutionMetadata 事件

不变文件
─────────
config.py                   不变
llm_agent.py                保留（对话入口，备用）
tools/                      不变（节点直接调用工具函数，注意：节点调工具时不用 FunctionTool）
```

**核心理念**：LlmAgent → GraphAgent 是把"模型自主编排"换成"你画图、框架执行"。State 替代了 tool 之间的 `image_path→output_path` 推理链，变成显式的字段传递。条件路由让你能用纯 Python 代码写 if/else，而不是在 instruction 里"希望"模型按你的意思走。

---

*关联笔记：Day3-A-框架核心概念.md（考试向）*  
*下一份：Day4-A → Redis Session + 跨会话 Memory*
