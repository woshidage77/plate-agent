# PlateAgent Day 2 保姆级详解：12 把工具装进 Agent 手里

> 使用方式：跟着代码逐段读，每个概念都有类比 + 代码引用

---

## 零、先回答你最可能问的：Schema / 类型注解 / docstring 到底是什么

### 类型注解

```python
def tool_gaussian_blur(image_path: str, kernel_size: int = 5) -> dict:
#                      ^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^   ^^^^^^
#                      参数: 类型注解     参数: 类型注解 + 默认值    返回值: 类型注解
```

`image_path: str` = "我声明这个参数应该是字符串"。Python 运行时不强制检查——你传个 int 也不会报错。但 tRPC-Agent 框架用 `inspect` 模块读取注解，自动生成 JSON Schema 给 DeepSeek。

### docstring

```python
def tool_gaussian_blur(...):
    """对车牌图像进行高斯滤波降噪处理。    ← 这就是 docstring
    Args:
        image_path: 车牌图像的本地文件路径
        kernel_size: 高斯核大小，奇数，默认 5
    Returns:
        dict: {"status": "ok", "output_path": 处理后的路径}
    """
```

`"""..."""` 包裹的文字 = 函数的说明书。框架提取**第一行**作为 tool description 传给 DeepSeek。模型就是靠这一行知道工具能干什么的。

### Schema

Schema = 数据结构的说明书。用填表类比：

```
┌──────────────────────────────────┐
│ 姓名：__________  (必填，文字)     │  ← 这就是 Schema
│ 年龄：__________  (必填，数字)     │     不包含你的实际数据
│ 手机：__________  (选填，11位)     │     只定义"字段叫什么、什么类型、必填吗"
└──────────────────────────────────┘
```

框架从你的函数签名 + docstring 自动生成 JSON Schema，发给 DeepSeek：

```
你的函数                                  框架生成的 Schema
─────────────────────────────────       ───────────────────────────
def tool_gaussian_blur(         →        {
    image_path: str,            →          "parameters": {
    kernel_size: int = 5        →            "image_path": {"type": "string"},
) -> dict:                     →            "kernel_size": {"type": "integer", "default": 5}
                                 →          },
"""对车牌进行高斯滤波"""          →          "description": "对车牌图像进行高斯滤波降噪处理。"
                                 →        }
```

---

## 一、四条铁律逐条拆解

### 铁律 1：类型注解必须有

```python
# ❌ 没有注解 → 框架不知道参数类型 → 模型可能传错
def tool_gaussian_blur(image_path, kernel_size=5): ...

# ✅ 框架自动生成 Schema
def tool_gaussian_blur(image_path: str, kernel_size: int = 5) -> dict: ...
```

### 铁律 2：docstring 必须有

```python
# ❌ 没有 docstring → Schema 里 description 为空 → 模型不知道工具干嘛的
def tool_gaussian_blur(image_path: str, ...) -> dict:
    img = cv2.imread(image_path)
    ...

# ✅ 第一行作为 tool description 传给 DeepSeek
def tool_gaussian_blur(image_path: str, ...) -> dict:
    """对车牌图像进行高斯滤波降噪处理。"""
```

### 铁律 3：返回值统一 `dict`，带 `status` 字段

```python
# ❌ 返回裸字符串 → 模型无法判断成功/失败
return "处理完成: plate_blurred.jpg"

# ✅ 模型一眼看 success/error
return {"status": "ok", "output_path": "plate_blurred.jpg"}
return {"status": "error", "message": "无法读取图像: bad.jpg"}
```

**注意**：`status` / `output_path` / `message` 这些字段名**不是框架强制的**——没有任何类或接口定义过它们。它们是我在编写每个 Tool 时人为约定的，目的只有一个：让 DeepSeek 能稳定解析——一眼看成功/失败（`status`），一眼看产出数据（`output_path`）。

不同工具返回不同字段，因为它们产出不同：

```python
# 预处理工具 → 图片文件
{"status": "ok", "output_path": "plate_blurred.jpg"}

# 定位工具 → 候选坐标
{"status": "ok", "candidates": [{"x":0,"y":8,"w":401,"h":128}]}

# 识别工具 → 字符+置信度
{"status": "ok", "char": "京", "confidence": 0.92, "needs_verify": False}
```

### 铁律 4：错误不要抛异常，返回 `{"status": "error"}`

```python
# ❌ 抛异常 → 事件流崩溃 → 对话断开
if img is None:
    raise FileNotFoundError(f"图片不存在: {image_path}")

# ✅ 返回 error dict → 框架正常处理 → 模型给用户解释 → 对话继续
if img is None:
    return {"status": "error", "message": f"无法读取图像: {image_path}"}
```

**为什么抛异常会崩？** `runner.run_async()` 是异步生成器。工具里抛异常 → 事件循环中断 → `async for` 崩溃。

---

## 二、工具之间如何"串链"——模型推理 vs 代码串链

Day 2 用的是**模型推理串链**（LlmAgent）：

```python
# 工具1 返回
{"status": "ok", "output_path": "plate_blurred.jpg"}

# 工具2 需要的参数叫 image_path
# 模型看到 output_path 和 image_path 的语义关系，自动传：
tool_grayscale(image_path="plate_blurred.jpg")  ← 模型自己推断的！
```

**没有一行胶水代码**。工具间不共享内存、没有全局变量。模型理解输入输出语义，自己做参数映射。

Day 3 切换到 GraphAgent 后改成**代码显式串链**——不再依赖模型推理，100% 确定。

---

## 三、完整链路：从 Python 函数到 DeepSeek 调用

```
你的 Python 函数:
┌──────────────────────────────────────────────────┐
│ def tool_gaussian_blur(                          │
│     image_path: str,         ← 类型注解           │
│     kernel_size: int = 5     ← 类型注解 + 默认值  │
│ ) -> dict:                   ← 返回值类型注解      │
│                                                  │
│     """对车牌图像进行高斯滤波降噪处理。 ← docstring │
│     Args: ...  Returns: ...                      │
│     """                                          │
│                                                  │
│     img = cv2.imread(image_path)                 │
│     if img is None:                              │
│         return {"status": "error", ...} ← 铁律3+4 │
│     ...                                          │
│     return {"status": "ok", ...}     ← 铁律3     │
└──────────────────────────────────────────────────┘
                        │ inspect 提取
                        ▼
┌──────────────────────────────────────────────────┐
│ JSON Schema（发给 DeepSeek）                       │
│ {                                                │
│   "name": "tool_gaussian_blur",                  │
│   "description": "对车牌图像进行高斯滤波降噪处理。", │
│   "parameters": {                                │
│     "image_path": {"type": "string"},             │
│     "kernel_size": {"type": "integer", "default":5}│
│   }                                              │
│ }                                                │
└──────────────────────────────────────────────────┘
                        │ 塞进 Function Calling prompt
                        ▼
┌──────────────────────────────────────────────────┐
│ DeepSeek: "我可以调 tool_gaussian_blur"            │
│ → function_call: {"name":"tool_gaussian_blur",   │
│    "args":{"image_path":"plate.jpg"}}            │
└──────────────────────────────────────────────────┘
                        │ 框架自动执行
                        ▼
┌──────────────────────────────────────────────────┐
│ 返回 {"status": "ok", "output_path": "..."}      │
│ → 送回 DeepSeek → 模型看到 output_path            │
│ → 决定下一步调什么工具                             │
└──────────────────────────────────────────────────┘
```

---

## 四、工具拆分哲学：为什么 12 个而不是 1 个

| 方案 | 写法 | 问题 |
|------|------|------|
| A: 1 个大函数 | `def full_pipeline(img) → str` | 中间步骤不可见、无法调整、不可观测 |
| B: 12 个原子 Tool | `tool_gaussian_blur`, `tool_grayscale`, ... | ✅ 每一步都能控制、可观测、可调试 |

**选 B 的原因**：Agent 框架的核心价值就是"模型自主编排"。写死 pipeline = 传统代码就够了。

---

## 五、文件结构

```
agent/tools/
├── preprocess.py      # 5 个预处理工具（滤波/灰度/二值/Canny/仿射）
├── locate.py          # 2 个定位工具（形态学/HSV）
├── segment.py         # 1 个分割工具（垂直投影）
├── recognize.py       # 2 个识别工具（SVM + LLM）—— 占位
└── knowledge.py       # 2 个知识库工具（黑名单 + 历史）—— 占位
```

**设计决策**：按原文四个模块拆分，每个文件管一个阶段。不是"一个文件一个 Tool"，而是"一个文件一组相关 Tool"。

---

## 六、概念串联记忆

```
类型注解  →  框架生成 JSON Schema  →  DeepSeek 知道参数类型
docstring →  框架提取第一行       →  DeepSeek 知道工具用途
return dict + status →  框架送回模型  →  DeepSeek 知道成功/失败
return error (不抛异常) →  框架不崩溃  →  对话继续
```

**核心理念**：Tool = 独立函数 + 类型注解 + docstring + 统一返回值约定。框架自动生成 Schema，模型靠 Schema 理解并调用工具。

---

*上一份：Day1-保姆级详解.md*  
*下一份：Day3-保姆级详解.md（GraphAgent 从零到一）*
