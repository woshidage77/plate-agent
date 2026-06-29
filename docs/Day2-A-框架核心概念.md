# PlateAgent Day 2-A：FunctionTool 深度（考试向）

> 源：`trpc-agent/examples/function_tools/` + `trpc-agent/examples/quickstart/agent/tools.py`  
> 用途：7.1 犀牛鸟考试知识储备 — Tool 模块

---

## 前置基础：三个 Python 概念

### 类型注解（Type Annotation）

```python
def tool(image_path: str, kernel_size: int = 5) -> dict:
#            ^^^^^^^^       ^^^^^^^^                ^^^^
#           参数类型注解     参数类型注解              返回值类型注解
```

`image_path: str` 声明"这个参数应该是字符串类型"。Python 运行时**不强制检查**——你传个 int 也不会报错。但 IDE 和框架会读取注解：IDE 用来智能补全，**tRPC-Agent 框架用 `inspect` 模块提取后生成 JSON Schema 给 DeepSeek**。

### docstring

```python
def tool(...):
    """对车牌图像进行高斯滤波降噪处理。    ← 这就是 docstring
    ...
    """
```

`"""..."""` 包裹的文字是函数的说明书。第一行会被 tRPC-Agent 框架提取，作为 **tool description** 传给 DeepSeek——模型就是靠这一行知道工具能干什么的。

### Schema

Schema = 数据结构的说明书。它不包含实际数据，只定义"字段叫什么、什么类型、必填还是选填"。

tRPC-Agent 框架自动从你的函数签名 + docstring 生成 JSON Schema：

```
你的函数                                  框架生成的 JSON Schema
─────────────────────────────────       ───────────────────────────
def tool_gaussian_blur(         →        {
    image_path: str,            →          "parameters": {
    kernel_size: int = 5        →            "image_path": {"type": "string"},
) -> dict:                     →            "kernel_size": {"type": "integer", "default": 5}
                                 →          }
"""对车牌进行高斯滤波"""          →        "description": "对车牌图像进行高斯滤波降噪处理。"
```

DeepSeek 收到这个 Schema 后，才知道"哦，有个 tool_gaussian_blur 可以调，它需要 image_path (string, 必填) 和 kernel_size (integer, 选填)"。

---

## 一、FunctionTool 的两种创建方式

### 方式 1：直接包装（PlateAgent 采用）

```python
from trpc_agent_sdk.tools import FunctionTool

def get_weather(city: str) -> dict:
    """获取指定城市天气"""
    return {"city": city, "temp": "25°C"}

tool = FunctionTool(get_weather)
```

### 方式 2：装饰器注册 + 查找

```python
from trpc_agent_sdk.tools import register_tool, get_tool

@register_tool("get_session_info")
async def get_session_info(tool_context: InvocationContext) -> dict:
    """获取当前会话信息 — tool_context 由框架自动注入"""
    session = tool_context.session
    return {"session_id": session.id, "user_id": session.user_id}

tool = get_tool("get_session_info")  # 按名字取回
```

---

## 二、FunctionTool 的四条铁律（逐条详解）

### 铁律 1：类型注解必须有

```python
# ❌ 错误 —— 没有类型注解
def tool_gaussian_blur(image_path, kernel_size=5): ...

# ✅ 正确
def tool_gaussian_blur(image_path: str, kernel_size: int = 5) -> dict: ...
```

**为什么？** 框架用 `inspect` 提取参数类型，自动生成 JSON Schema。没有注解 → 参数类型未知 → DeepSeek 可能传错类型（比如给 image_path 传数字）→ cv2.imread(123) 崩溃。

支持的 Python 基础类型：`str, int, float, bool, list, dict`

### 铁律 2：docstring 必须有

```python
# ❌ 错误 —— 空 docstring
def tool_gaussian_blur(...) -> dict:
    img = cv2.imread(image_path)
    ...

# ✅ 正确 —— 第一行是工具描述
def tool_gaussian_blur(...) -> dict:
    """对车牌图像进行高斯滤波降噪处理。
    Args:
        image_path: 车牌图像的本地文件路径
        kernel_size: 高斯核大小，奇数，默认 5
    Returns:
        dict: {"status": "ok", "output_path": 处理后的路径}
    """
```

**为什么？** 框架提取 docstring **第一行**作为 tool description 传给 DeepSeek。没有这行 → Schema 里 `description` 为空 → 模型不知道工具干嘛的 → 不会调用。

Google 风格格式：第一行概述 + `Args:` 块 + `Returns:` 块。

### 铁律 3：返回值建议统一 `dict`，带 `status` 字段

```python
# ❌ 不好 —— 返回字符串，模型无法判断成功/失败
return "处理完成: plate_blurred.jpg"

# ❌ 不好 —— 有 dict 但无 status，模型需要推理
return {"output_path": "plate_blurred.jpg"}

# ✅ 正确
return {"status": "ok", "output_path": "plate_blurred.jpg"}
return {"status": "error", "message": "无法读取图像: bad.jpg"}
```

**注意**：`status` / `message` / `output_path` 这些字段名**不是框架规定的**，而是开发者自行约定的。目的只有一个：让 DeepSeek 能稳定解析——一眼看成功/失败 (`status`)，一眼看产出数据 (`output_path`)。不同工具的产出字段可以不同（定位工具返回 `candidates`，识别工具返回 `char` + `confidence`）。

### 铁律 4：错误不要抛异常，返回 `{"status": "error"}`

```python
# ❌ 错误 —— 抛异常会中断事件流
if img is None:
    raise FileNotFoundError(f"图片不存在: {image_path}")

# ✅ 正确 —— 返回 error dict，事件流正常继续
if img is None:
    return {"status": "error", "message": f"无法读取图像: {image_path}"}
```

**为什么？** `runner.run_async()` 是异步生成器。工具里抛异常 → 事件循环崩溃 → `async for` 中断 → 对话断开。返回 `{"status": "error"}` → 框架正常处理 → 送回模型 → 模型给用户解释原因 → 对话继续。

---

## 三、从 Python 函数到 DeepSeek 调用的完整链路

```
你的 Python 函数:
┌──────────────────────────────────────────────────┐
│ def tool_gaussian_blur(                          │
│     image_path: str,         ← 类型注解           │
│     kernel_size: int = 5     ← 类型注解 + 默认值  │
│ ) -> dict:                   ← 返回值类型注解      │
│                                                  │
│     """对车牌图像进行高斯滤波降噪处理。 ← docstring │
│     Args:                                        │
│         image_path: 车牌图像的本地文件路径          │
│         kernel_size: 高斯核大小，必须为奇数         │
│     Returns:                                     │
│         dict: {"status": "ok", ...}              │
│     """                                          │
│                                                  │
│     img = cv2.imread(image_path)                 │
│     if img is None:                              │
│         return {"status": "error", ...} ← 铁律3,4 │
│     ...                                          │
│     return {"status": "ok", ...}     ← 铁律3     │
└──────────────────────────────────────────────────┘
                        │
                        │ inspect 提取
                        ▼
┌──────────────────────────────────────────────────┐
│ JSON Schema（发给 DeepSeek）                       │
│ {                                                │
│   "name": "tool_gaussian_blur",                  │
│   "description": "对车牌图像进行高斯滤波降噪处理。", │
│   "parameters": {                                │
│     "image_path": {"type": "string"},             │
│     "kernel_size": {"type": "integer",            │
│                     "default": 5}                 │
│   }                                              │
│ }                                                │
└──────────────────────────────────────────────────┘
                        │
                        │ 塞进 Function Calling prompt
                        ▼
┌──────────────────────────────────────────────────┐
│ DeepSeek:                                        │
│ "我可以调 tool_gaussian_blur，需要传              │
│  image_path='plate.jpg'..."                      │
│ → 输出 function_call:                            │
│   {"name":"tool_gaussian_blur",                  │
│    "args":{"image_path":"plate.jpg"}}            │
└──────────────────────────────────────────────────┘
                        │
                        │ 框架自动执行你的函数
                        ▼
┌──────────────────────────────────────────────────┐
│ 返回 {"status": "ok", "output_path": "..."}      │
│ → 框架送回 DeepSeek                               │
│ → 模型看到 output_path → 决定下一步调什么工具      │
└──────────────────────────────────────────────────┘
```

---

## 四、同步 vs 异步 Tool

```python
def sync_tool(x: int) -> dict:        # 普通 def — 同步
    return {"result": x * 2}

async def async_tool(url: str) -> dict:  # async def — 异步
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
    return {"data": resp.text}
```

框架两种都支持，事件循环里自动 `await`。

---

## 五、InvocationContext — 工具内获取上下文

```python
from trpc_agent_sdk.context import InvocationContext

async def my_tool(query: str, tool_context: InvocationContext) -> dict:
    """tool_context 参数自动注入，调用方无需传"""
    session = tool_context.session
    return {"session_id": session.id, "user_id": session.user_id}
```

`tool_context` 参数名固定，框架识别后自动注入当前 Session、用户信息。

---

## 六、考试速记卡

| 考点 | 答案 |
|------|------|
| Tool 创建有几种方式？ | 2 种：`FunctionTool(fn)` 和 `@register_tool + get_tool` |
| 类型注解的作用？ | 框架生成 JSON Schema，告诉模型参数类型 |
| 没有类型注解会怎样？ | 模型不知道参数类型，可能传错导致崩溃 |
| docstring 的作用？ | 第一行作为 tool description 传给模型 |
| 没有 docstring 会怎样？ | 模型不知道工具用途，不会调用 |
| Schema 是什么？ | 数据结构的说明书（字段名、类型、必填/选填） |
| Schema 从哪来？ | 框架从函数签名 + docstring 自动生成 |
| 返回值为什么统一 dict？ | 结构化数据比字符串更精准，模型能稳定解析 |
| `status` 字段是框架强制的吗？ | **不是**，是开发者约定，目的是给模型明确的成功/失败信号 |
| 错误怎么处理？ | 返回 `{"status": "error", "message": "..."}`，不抛异常 |
| 抛异常会怎样？ | 事件循环崩溃，对话断开 |
| `InvocationContext` 怎么拿到？ | 参数名写 `tool_context`，框架自动注入 |

---

*关联笔记：Day2-B-项目搭建流程.md*  
*下一份：Day3-A → GraphAgent 框架知识*
