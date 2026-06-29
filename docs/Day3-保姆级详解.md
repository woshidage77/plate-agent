# PlateAgent Day 3 保姆级详解：GraphAgent 从零到一

> 阅读前提：已完成 Day 1-2，理解 LlmAgent + FunctionTool + 事件流  
> 使用方式：跟着代码逐段读，每个概念都有类比 + 代码引用

---

## 零、先回答你最可能问的：SVM 置信度到底是什么

### 类比

你让一个朋友辨认远处的车牌：

- 很确定：**"这是 京，100% 确定"** → 置信度 1.0
- 有点犹豫：**"可能是 京，也可能是 琼"** → 置信度 0.6
- 完全瞎猜：**"？？？"** → 置信度 0.0

SVM 做的事完全一样。它看一张字符图片，输出两个东西：
1. **它认为这是什么字符** → `char: "京"`
2. **它对自己的判断有多确定** → `confidence: 0.92`（0=完全不确定，1=100%确定）

### 在你的代码里

[`agent/tools/recognize.py:41`](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\tools\recognize.py:41)：

```python
confidence = 0.0                     # 当前占位值 0.0（SVM 模型还没训练）
needs_verify = confidence < 0.85     # 0.0 < 0.85 → True → 触发 LLM 复核
```

`0.85` 是一个**阈值（threshold）**——你设定的"信任线"。

| 置信度 | 含义 | 系统行为 |
|--------|------|---------|
| ≥ 0.85 | SVM 很确定 | 直接用 SVM 结果，省一次 LLM 调用 |
| < 0.85 | SVM 不确定 | 触发 DeepSeek 复核，修正可能的错误 |

### 为什么需要这个机制

```
无 LLM 复核：SVM 把"琼"误认成"京" → 车牌识别错误 → 罚单开错人
有 LLM 复核：SVM 说"京, conf=0.6" → 触发 DeepSeek → "不对，这是 琼" → 修正
```

**条件路由的本质就是自动化这个"什么时候找 LLM 帮忙"的决策。**

---

## 一、GraphAgent 是什么——流水线类比

### Day 1-2 的方式（LlmAgent）

想象你让一个助手去处理车牌。助手自己看工具箱，自己决定顺序。你**只能建议**（INSTRUCTION），不能强制执行。

```
你: "识别 plate.jpg"
助手: "好，我先高斯滤波...然后灰度化..."
      ↑ 助手自己决定顺序，理论上可能乱来
```

### Day 3 的方式（GraphAgent）

你把"标准操作流程"画成流程图贴在墙上。助手严格按图走，一步不许跳。

```
预处理 → 定位 → 分割 → 识别 → (置信度够?→输出 | 不够→LLM→输出)
         ↑ 你说了算，不是模型说了算
```

**切换原因**：车牌识别是确定性流水线，顺序不能乱。GraphAgent 保证执行顺序。

---

## 二、State —— 流水线上传递的"传送带"

### 类比

工厂流水线上，每个工位处理完后把东西放在传送带上，下一个工位从传送带上拿。

**State 就是那条传送带。**

### 在代码里

[`agent/graph_state.py`](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\graph_state.py)：

```python
class PlateState(State):
    image_path: str = ""          # 工位0放上去的：原始图片路径
    preprocess_output: str = ""   # 工位1放上去的：预处理后的图片
    locate_output: str = ""       # 工位2放上去的：车牌区域图片
    segment_chars: list = []      # 工位3放上去的：切好的字符图片列表
    recognize_chars: list = []    # 工位4放上去的：SVM 识别结果列表
    needs_llm_verify: bool = False  # 工位4放上去的：要不要叫LLM（条件路由开关！）
    final_plate: str = ""         # 工位5/6放上去的：最终车牌号
```

### 规则

| 操作 | 写法 |
|------|------|
| 读 | `state.get("字段名", 默认值)` |
| 写 | `return {"字段名": 新值}` ← 节点返回 dict，框架自动合并 |
| 删除 | ❌ 不允许 |

**为什么不用全局变量？** 10 个用户同时识别 → 全局变量互相覆盖。State 是每个用户、每个会话独立的。

---

## 三、节点 —— 流水线上的工位

### 3.1 节点统一模式

```python
async def xxx_node(state: PlateState, async_writer: AsyncEventWriter) -> dict:
    # ① 读传送带
    input_data = state.get("field_name", default)

    # ② 推送进度给用户（打字机效果）
    await async_writer.write_text("[阶段名] 开始...\n")

    # ③ 执行处理（直接调用 tools/ 里的函数，不通过 FunctionTool）
    result = some_tool(input_data)

    # ④ 写回传送带
    return {"field_name": result["output_path"]}
```

**与 Day 2 的关键区别**：节点直接调用 `tools/` 里的函数，而不是通过 `FunctionTool` 包装。因为这里不需要模型推理——节点自己就是执行者。

### 3.2 预处理节点

[`agent/graph_nodes.py:10`](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\graph_nodes.py:10)

```python
current_path = img                           # 从原始图片开始
for step_name, step_fn in steps:             # 遍历5个处理步骤
    result = step_fn(current_path)            # 执行当前步骤
    current_path = result["output_path"]      # 产出作为下一步的输入
# 最后 current_path = 仿射矫正后的图片
return {"preprocess_output": current_path}
```

**与 Day 2 的关键区别**：Day 2 是模型自己推理"上一个 tool 的 output_path 应该传给下一个 tool 的 image_path"。这里是代码显式传递 `current_path`——不需要模型推理，100% 确定。

### 3.3 识别节点（最关键—条件路由的开关）

[`agent/graph_nodes.py:107`](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\graph_nodes.py:107)

```python
needs_verify = False                            # 初始：不需要帮忙

for i, char_path in enumerate(char_images):     # 遍历每个字符图片
    svm_result = tool_svm_predict(char_path)     # SVM 识别这个字符
    char_needs = svm_result["needs_verify"]     # 这个字符需要帮忙吗？
    if char_needs:
        needs_verify = True                      # 只要有一个不确定 → 找 LLM

return {
    "recognize_chars": results,                 # 所有 SVM 结果
    "needs_llm_verify": needs_verify,            # ← 这个 bool 控制下一步走向
}
```

`needs_llm_verify` 是条件路由的"开关"：`False` → 流水线直通输出，`True` → 先走 LLM 复核。

---

## 四、条件路由 —— 流程图的"分叉路口"

### 4.1 路由函数

[`agent/graph_agent.py:97`](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\graph_agent.py:97)

```python
def _route_after_recognize(state: PlateState) -> str:
    """读 State → 决定方向 → 返回方向标识字符串"""
    if state.get("needs_llm_verify", False):
        return "verify"      # → 去 LLM 复核分支
    return "output"          # → 直接输出
```

| 输入 | 判断 | 返回 | 去向 |
|------|------|------|------|
| 所有字符置信度 ≥ 0.85 | `False` | `"output"` | `format_output_node` |
| 任一字符置信度 < 0.85 | `True` | `"verify"` | `llm_verify_node` |

### 4.2 注册分叉路口

[`agent/graph_agent.py:138`](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\graph_agent.py:138)

```python
graph.add_conditional_edges(
    "recognize",                    # 从哪个节点出发
    _route_after_recognize,         # 用哪个函数判断方向
    {
        "verify": "llm_verify",     # 函数返回"verify" → 去 llm_verify 节点
        "output": "format_output",  # 函数返回"output" → 去 format_output 节点
    },
)
```

**映射关系**：路由函数返回的字符串（左列 key）→ 框架找到对应的节点名（右列 value）→ 执行该节点。

### 4.3 完整流程图

```
START
  │
  ▼
preprocess_node     ← 5步预处理（链式调用，不依赖模型）
  │
  ▼
locate_node         ← 形态学粗定位 + HSV 颜色精定位
  │
  ▼
segment_node        ← 垂直投影法切出单个字符
  │
  ▼
recognize_node      ← SVM 逐个识别 + 设 needs_llm_verify 标志
  │
  ├── needs_llm_verify=False ──→ format_output_node  ← 拼接结果+查黑名单
  │
  └── needs_llm_verify=True
          │
          ▼
     llm_verify_node   ← DeepSeek 复核低置信度字符
          │
          ▼
     format_output_node  ← 拼接最终结果 + 查黑名单
          │
          ▼
         END
```

---

## 五、graph_agent.py —— 拼图的地方

[`agent/graph_agent.py`](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\graph_agent.py) 做了五件事：

| 步骤 | 代码 | 作用 |
|------|------|------|
| ① 定义节点 | `graph.add_node("preprocess", preprocess_node, ...)` | 注册每个工位 |
| ② 设起点终点 | `graph.set_entry_point("preprocess")` / `set_finish_point("format_output")` | START→第一个节点，最后一个节点→END |
| ③ 画固定箭头 | `graph.add_edge("preprocess", "locate")` | A 完成必定去 B |
| ④ 画分叉箭头 | `graph.add_conditional_edges("recognize", router, map)` | A 完成后按条件分岔 |
| ⑤ 编译打包 | `GraphAgent(name="...", graph=graph.compile())` | 校验 + 包装，交 Runner |

`graph.compile()` 做校验：图有没有死循环？有没有断头节点？节点名有没有拼错？编译通过 = 图合法。

---

## 六、EventWriter —— 给用户看的进度条

```python
await async_writer.write_text("[预处理] 开始...\n")    # 用户立刻看到
await async_writer.write_text("  高斯滤波... 完成\n")   # 每个小步骤
await async_writer.write_text("[预处理] 完成\n")       # 阶段结束
```

和 Day 1 的流式输出同一个效果，但这里是你**手动控制**输出内容。`await` 确保每条消息按顺序到达客户端，不会后发先至。

---

## 七、当前占位与后续计划

[`agent/tools/recognize.py:34`](D:\codex_prorject\ai_project\xiniuniaojia\plate-agent\agent\tools\recognize.py:34)：

```python
char = "?"
confidence = 0.0                    # ← 永远是 0.0
needs_verify = confidence < 0.85    # ← 0.0 < 0.85，永远是 True
```

当前 SVM 没有真实模型 → 永远是 `"?"` + 置信度 `0.0` → 条件路由永远走 LLM 复核分支。**这不是 bug**——SVM 模型 Day 7 训练，当前是骨架验证阶段。条件路由的架构已经正确。

真实部署时的行为：

| 场景 | SVM 置信度 | 行为 |
|------|-----------|------|
| 清晰字符 "京" | 0.95 | 不走 LLM，直接用 |
| 模糊字符 "0"/"O" | 0.62 | 触发 LLM 复核，修正 |

---

## 八、三个核心概念的串联记忆

```
State             节点              边与路由
─────             ─────             ────────
传送带            工位              传送带上的分岔口
只存数据          只做处理           只决定方向
不执行逻辑        不关心其他节点      不改变数据
```

- **加节点**：只需要在 `graph_agent.py` 加 `add_node` + 改 `add_edge`
- **改顺序**：只改 `add_edge` 的始末点
- **改条件**：只改路由函数的 if 逻辑

所有现有节点的代码一行不用动。

---

## 九、与 Day 1-2 的概念对照表

| 概念 | Day 1-2 (LlmAgent) | Day 3 (GraphAgent) |
|------|-------------------|-------------------|
| 执行控制 | 模型自主决策，instruction 引导 | 你画流程图，框架严格执行 |
| 数据传递 | 工具间靠模型推理串链（output_path → image_path） | State 显式字段传递 |
| 分支逻辑 | INSTRUCTION 里"建议" | `add_conditional_edges` 强制执行 |
| 工具调用 | 通过 FunctionTool 注册，模型决定何时调 | 节点函数直接调用 tools/ 中的函数 |
| 进度推送 | event.partial=True 自动流式 | async_writer.write_text() 手动控制 |
| 确定性 | 低（模型可能跳步） | 高（图保证顺序） |

---

*上一份：Day3-A-框架核心概念.md（考试向）+ Day3-B-项目搭建流程.md（搭建向）*  
*下一份：Day4 → Redis Session + 跨会话 Memory*
