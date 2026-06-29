# PlateAgent Day 2-B：12 FunctionTool 封装 + 端到端验证（搭建向）

> 工作区：`plate-agent/agent/tools/`  
> 目标：给 Agent "装上双手" — 让 DeepSeek 能调用 OpenCV  
> 对应的 SDK 知识：`Day2-A-框架核心概念.md`

---

## 搭建前的思考：为什么拆成 12 个独立 Tool？

Day 1 的 Agent 只会说话。现在要让它**操作 OpenCV 处理图像**。

两种方案对比：

| 方案 | 写法 | 模型能控制什么 | 问题 |
|------|------|---------------|------|
| A: 一个大函数 | `def full_pipeline(img) → str` | 无 — 全自动 | 中间步骤不可见，无法调试/调整 |
| B: 12 个原子 Tool | `tool_gaussian_blur`, `tool_grayscale`, ... | **每一步都能决定是否调、传什么参数** | ✅ 灵活、可观测 |

**选 B 的原因**：Agent 框架的核心价值就是"模型自主编排"。如果写死 pipeline，传统代码就够了，tRPC-Agent 白用。

---

## Step 1：目录结构

```
agent/tools/
├── __init__.py        # 空文件，让 tools/ 成为 Python 包
├── preprocess.py      # 5 个预处理工具
├── locate.py          # 2 个定位工具
├── segment.py         # 1 个分割工具
├── recognize.py       # 2 个识别工具
└── knowledge.py       # 2 个知识库工具（占位）
```

**设计决策**：按原文的四个模块拆分文件，一个文件管一个阶段。不是"一个文件一个 Tool"，而是"一个文件一组相关 Tool"。

---

## Step 2：Tool 的统一设计契约

每个 Tool 遵循四条铁律（详见 Day2-A），以 `tool_gaussian_blur` 为例：

```python
def tool_gaussian_blur(image_path: str, kernel_size: int = 5) -> dict:
    """对车牌图像进行高斯滤波降噪处理。            ← 铁律2: docstring

    Args:
        image_path: 车牌图像的本地文件路径
        kernel_size: 高斯核大小，奇数，默认 5
    Returns:
        dict: {"status": "ok", "output_path": 处理后的路径}
    """
    img = cv2.imread(image_path)
    if img is None:
        return {"status": "error", "message": f"无法读取: {image_path}"}  # 铁律3+4

    blurred = cv2.GaussianBlur(img, (kernel_size, kernel_size), 0)
    output_path = image_path.replace(".jpg", "_blurred.jpg")
    cv2.imwrite(output_path, blurred)

    return {"status": "ok", "output_path": output_path}  # 铁律3
```

### 关于返回值字段的说明

`status`、`output_path`、`message` 这些字段名**不是框架强制的**——没有任何类、接口、配置文件定义过它们。它们是开发时人为约定的，目的只有一个：让 DeepSeek 能稳定解析工具结果。

| 字段 | 作用 | 出现时机 |
|------|------|---------|
| `status` | 给模型明确的成功/失败信号（`"ok"` / `"error"`） | 每次返回都有 |
| `output_path` | 产出文件的路径，供下一个工具使用 | 成功时 |
| `message` | 错误原因，供模型向用户解释 | 失败时 |

不同工具的产出字段不同，因为它们产出不同的东西：

```python
# 预处理工具 → 产出图片文件
{"status": "ok", "output_path": "plate_blurred.jpg"}

# 定位工具 → 产出候选坐标
{"status": "ok", "contours_count": 3, "candidates": [{"x":0,"y":8,"w":401,"h":128}]}

# 识别工具 → 产出字符和置信度
{"status": "ok", "char": "京", "confidence": 0.92, "needs_verify": False}
```

---

## Step 3：工具链式传递的核心机制

关键设计：每个 Tool 的输入是 `image_path`（字符串路径），输出包含 `output_path`（新的文件路径）。模型看到两者的语义关系，自动做参数映射：

```
tool_gaussian_blur(image_path="plate.jpg")
    → return {"output_path": "plate_blurred.jpg"}

tool_grayscale(image_path="plate_blurred.jpg")   ← 模型自动传！
    → return {"output_path": "plate_blurred_gray.jpg"}

tool_binarize_otsu(image_path="plate_blurred_gray.jpg")  ← 模型自动传！
    ...
```

**没有一行胶水代码**。工具之间不需要共享内存、不需要全局变量。模型理解输入输出语义，自己做参数映射。这是 LLM 推理能力在发挥作用——它不是被编程的，是被"引导"的。

---

## Step 4：工具注册 — 在 llm_agent.py 中一次性注册

```python
# agent/llm_agent.py（Day 2 修改部分）

from .tools.preprocess import (
    tool_gaussian_blur, tool_grayscale, tool_binarize_otsu,
    tool_edge_detect_canny, tool_affine_correct,
)
# ... 其他 import

def create_plate_agent() -> LlmAgent:
    tools = [
        FunctionTool(tool_gaussian_blur),
        FunctionTool(tool_grayscale),
        # ... 全部 12 个 ...
    ]
    agent = LlmAgent(..., tools=tools)
```

**设计决策**：所有工具集中注册在一个地方。Day 3 GraphAgent 也需要这些工具，到时候改为按节点分组注册。

---

## Step 5：INSTRUCTION 的设计思路

```python
INSTRUCTION = """你是 PlateAgent...

当你收到车牌图片时，按以下顺序操作：
**预处理阶段** → tool_gaussian_blur, tool_grayscale, ...
**定位阶段**   → tool_morphology_locate, tool_color_locate
**分割阶段**   → tool_vertical_projection
**识别阶段**   → tool_svm_predict, tool_llm_verify
**查询阶段**   → tool_search_blacklist, tool_query_history
"""
```

**设计决策**：INSTRUCTION 里明确告诉模型调用顺序。不是硬编码控制流——模型可以选择跳过某些步骤（比如图像已经够清晰，跳过模糊），但大方向被锁定了。

---

## Step 6：两个占位 Tool 的设计哲学

`tool_svm_predict` 和 `tool_llm_verify` 返回占位数据：

```python
def tool_svm_predict(image_path: str) -> dict:
    # TODO: 加载训练好的 SVM 模型
    return {"status": "ok", "char": "?", "confidence": 0.0, "needs_verify": True}
```

**为什么提前写好但不是完整实现？**
- 让链路先跑通 → 验证模型能自主编排 10 步
- 函数签名和 docstring 是正确的 → 模型能理解工具用途
- Day 3 GraphAgent 实现条件路由时，`confidence < 0.85 → LLM` 这条规则已经定义好

这叫**渐进式开发**：先让骨架跑通，逐步填入真实实现。

---

## Step 7：端到端验证 — 模型自主调用了完整 10 步

```text
[调用工具: tool_gaussian_blur]
[调用工具: tool_grayscale]
[调用工具: tool_binarize_otsu]
[调用工具: tool_edge_detect_canny]
[调用工具: tool_affine_correct]
[调用工具: tool_morphology_locate]
[调用工具: tool_color_locate]
[调用工具: tool_vertical_projection]
[调用工具: tool_svm_predict]
[调用工具: tool_llm_verify]
```

**关键观察**：模型不需要你写 `if/else` 或 `for` 循环。它看 INSTRUCTION 知道顺序，看每个 tool 的 schema 知道参数，自动编排。

---

## 搭建思路总结：Day 2 做了什么

```
Day 1 骨架              Day 2 改造
─────────────           ─────────────────
.env                    .env（不变）
config.py               config.py（不变）
llm_agent.py            llm_agent.py（+12 个 import + tools=[]）
tools/  ← 新建          tools/preprocess.py（5 Tool）
                        tools/locate.py（2 Tool）
                        tools/segment.py（1 Tool）
                        tools/recognize.py（2 Tool，占位）
                        tools/knowledge.py（2 Tool，占位）
main.py                 main.py（不变）
```

**核心理念**：Tool = 独立函数 + 类型注解 + docstring + 统一返回值约定。框架自动生成 Schema，模型靠 Schema 理解和调用工具。

---

*关联笔记：Day2-A-框架核心概念.md（考试向）*  
*下一份：Day3-A → GraphAgent 框架知识，Day3-B → 4节点编排 + 条件路由*
