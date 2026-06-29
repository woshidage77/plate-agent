# PlateAgent Day 11-A：防幻觉体系 + Parallel + Interrupt（考试向）

> 源：SVM 训练实战 + 三层容错设计 + Parallel/Interrupt 考点
> 用途：7.1 犀牛鸟考试知识储备 — 这 4 个考点是面试级加分项

---

## 一、SVM 字符识别训练（Tool 模块完整实现）

### 1.1 为什么要自己训 SVM

Day 1-10 的 `tool_svm_predict` 返回 `char="?"` / `confidence=0.0`。
后果：每个字符都触发 `needs_llm_verify=True`，条件路由完全失效。

### 1.2 训练流程

```
合成数据（5544 样本）
  ├── 65 类字符（31 省份 + 24 字母 + 10 数字）
  ├── 4 种字体（微软雅黑/黑体/楷体/宋体）
  ├── 3 种字号（28/32/36）
  └── 增强：噪声 + 旋转(-5°~5°) + 高斯模糊
      │
      ▼
HOG 特征提取（OpenCV）
  ├── winSize=32x32, cellSize=8x8, blockSize=16x16
  └── 输出 324 维特征向量
      │
      ▼
SVM 训练（sklearn.svm.SVC）
  ├── kernel=RBF, C=10.0, probability=True
  ├── 训练集 4712, 测试集 832
  └── 测试准确率 99.52%
```

### 1.3 关键代码

```python
# agent/tools/recognize.py — 真实 SVM 预测
_model = pickle.load(open("svm_model.pkl", "rb"))
_hog = cv2.HOGDescriptor(...)

def tool_svm_predict(image_path):
    img = cv2.resize(cv2.imread(image_path, 0), (32, 32))
    features = _hog.compute(img).flatten().reshape(1, -1)
    char_id = _model.predict(features)[0]
    probs = _model.predict_proba(features)[0]
    confidence = float(np.max(probs))
    char = _label_map[int(char_id)]
    return {"char": char, "confidence": confidence,
            "needs_verify": confidence < 0.85}
```

**考点**：FunctionTool 铁律 3（完整返回值）、铁律 4（docstring 即 schema）的验证。

---

## 二、三层容错体系（Agent 鲁棒性）

### 2.1 设计

```
LLM API 调用
  │
  ├── 第 1 层：asyncio.timeout(30s) — 防止单次调用无限等待
  ├── 第 2 层：tenacity retry(3次) — 指数退避 1s→2s→4s
  └── 第 3 层：fallback_value — 全部失败降级为 SVM 结果
```

### 2.2 可重试 vs 不可重试

| 异常类型 | 是否重试 | 原因 |
|---------|---------|------|
| TimeoutError | ✅ 重试 | 网络波动，下次可能成功 |
| ConnectionError | ✅ 重试 | 临时连接中断 |
| HTTP 429/502/503 | ✅ 重试 | 限流/服务暂不可用 |
| HTTP 401/403 | ❌ 不重试 | API key 错误，重试无意义 |

### 2.3 代码

```python
# agent/retry.py
async def call_llm_with_retry(coro_fn, fallback_value=None, operation="llm_call"):
    for attempt in range(1, 4):
        try:
            async with asyncio.timeout(30):
                return await coro_fn()  # 成功直接返回
        except asyncio.TimeoutError:
            if attempt < 3:
                await asyncio.sleep(2 ** (attempt - 1))  # 指数退避
        except Exception as e:
            if not _is_retryable(e):
                return fallback_value  # 不可重试 → 立即降级
    return fallback_value  # 全部失败 → 降级
```

**考点**：错误处理 vs 异常传播；降级策略（不阻塞流水线）。

---

## 三、Parallel 并行识别（Chain/Parallel/Cycle 考点落地）

### 3.1 问题

车牌识别 7 个字符互不依赖，但原来用 `for` 循环串行处理：

```python
# 改前（串行）
for char_path in char_images:
    result = tool_svm_predict(char_path)  # 每个等待上一个完成
# 7 字符 × 100ms = 700ms
```

### 3.2 并行化

```python
# 改后（并行）— agent/graph_nodes.py
_svm_executor = ThreadPoolExecutor(max_workers=8)

loop = asyncio.get_event_loop()
tasks = [loop.run_in_executor(_svm_executor, tool_svm_predict, p)
         for p in char_images]
results = await asyncio.gather(*tasks)
# 7 字符 × 1ms (并发) ≈ 1ms
```

### 3.3 验证结果

```
Sequential: 1130.5ms
Parallel:     6.1ms
Speedup:    184.8x
```

**考点**：Chain（串行）→ Parallel（并行）的代码级对比；`asyncio.gather` + `ThreadPoolExecutor` 的并发模式。

---

## 四、Interrupt / Resume 人工确认（GraphAgent 进阶考点）

### 4.1 概念

GraphAgent 的 `interrupt()` 允许在流程中暂停执行，等待外部输入后恢复。

```
recognize_node → 置信度 < 0.5
      │
      ▼
human_review_node
      │
      ├── interrupt({chars_to_confirm})  ← 暂停，通知用户
      │
      ▼ （用户输入确认后）
continue → format_output_node
```

### 4.2 tRPC-Agent API

```python
from trpc_agent_sdk.dsl.graph import interrupt

async def human_review_node(state, writer):
    chars_to_confirm = [c for c in state["recognize_chars"]
                        if c["confidence"] < 0.5]
    if chars_to_confirm:
        # 暂停执行，返回确认请求给客户端
        human_response = interrupt({
            "type": "human_review",
            "chars": chars_to_confirm,
        })
        # resume 后 human_response 包含用户的回复
        return {"confirmed_plate": human_response}
    return {}
```

### 4.3 Day 11 实现（state flag 模式）

当前使用 `awaiting_human` state flag + `AsyncEventWriter` 通知用户：

```python
# agent/graph_nodes.py
return {
    "awaiting_human": True,
    "low_confidence_chars": low_conf_chars,  # 携带上下文
    STATE_KEY_LAST_RESPONSE: f"人工确认：{len(low_conf_chars)} 个字符需要确认",
}
```

完整 interrupt 需使用框架的 `interrupt()` API，当前实现展示设计思路。

### 4.4 Checkpoint 机制

LangGraph（底层）的 checkpoint 机制：
- 每次 interrupt 前自动保存当前 state（快照）
- resume 时从快照恢复，继续执行
- 支持任意深度的嵌套 interrupt

**考点**：checkpoint 是中断恢复的数据基础；interrupt 暂停执行，resume 从断点继续。

---

## 五、Day 11 完整图结构

```
preprocess → locate → segment → recognize (Parallel SVM)
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
        conf < 0.5             0.5 ≤ conf < 0.85      conf ≥ 0.85
              │                      │                      │
        human_review            llm_verify            format_output
         (interrupt)          (retry+降级)            ([?]标注)
              │                      │
              └──────────────────────┘
```

防幻觉四道闸门全部就位：
1. SVM 置信度 ≥ 0.85 → 直接通过 ✅
2. 0.5 ≤ conf < 0.85 → LLM 复核（3次重试+降级）✅
3. conf < 0.5 → 人工确认（interrupt）✅
4. format_output [?] 标注 → 用户知情 ✅