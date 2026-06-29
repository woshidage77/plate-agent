# PlateAgent Day 9 保姆级详解：从零理解 OpenTelemetry 和 Token 追踪

> 用类比理解概念，用项目真实代码验证。

---

## 零、Day 8 的评测差在哪里——不差，但缺了"运行时视角"

Day 7-8 的评测体系看的是**结果好不好**（准确率、Judge 打分）。

Day 9 的 OTel 看的是**运行怎么样**（哪个节点慢？LLM 花了多少 token？）。

类比：
- Day 7-8 = 考试成绩（结果导向）
- Day 9 = 答题过程录像（过程导向）

---

## 一、把 OpenTelemetry 类比成快递追踪

你去淘宝买了个东西。想知道包裹到哪了，打开物流追踪：

`
物流单号：SF123456789  ← 这就是一个 Trace

2024-01-15 09:00  深圳福田 已揽件     ← 这是一个 Span
2024-01-15 12:00  深圳中转 运输中     ← 这也是一个 Span
2024-01-15 18:00  广州白云 派送中     ← 这也是一个 Span
2024-01-15 20:00  签收成功            ← 这也是一个 Span
`

每个 Span 告诉你：谁、什么时候、做了什么、花了多久。

换成车牌识别：

`
请求: 识别 /tmp/car.jpg          ← Trace

14:31:00  preprocess 节点 83ms   ← Span
14:31:00  locate 节点 45ms       ← Span
14:31:00  segment 节点 30ms      ← Span
14:31:01  recognize 节点 80ms    ← Span
14:31:01  format_output 节点 5ms ← Span
`

如果某天有人投诉"识别太慢了"，你打开追踪一看——
llm_verify 节点花了 2 秒。哦，DeepSeek 那边堵车了。

---

## 二、@trace_node 装饰器——"给函数穿个马甲"

### 2.1 不用装饰器有多痛苦

假设有 6 个节点函数，每个都要手动写 span：

`python
# 节点 1：预处理
async def preprocess_node(state, writer):
    tracer = get_tracer("plate_agent.graph")
    with tracer.start_as_current_span("graph.preprocess") as span:
        span.set_attribute("node.name", "preprocess")
        start = time.perf_counter()
        try:
            # ... 20 行业务逻辑 ...
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR))
            raise
        finally:
            span.set_attribute("duration_ms", ...)
`

6 个节点 × 15 行重复代码 = 90 行。而且每次改逻辑都要 6 个地方同步。

### 2.2 装饰器是怎么省掉这 90 行的

python 的装饰器本质是"用一个函数包住另一个函数"：

`python
# 这个：
@trace_node("preprocess")
async def preprocess_node(state, writer):
    # 业务逻辑

# 等价于：
preprocess_node = trace_node("preprocess")(原始的_preprocess_node)
`

	race_node 内部做的是你刚才手动写的那些事：创建 span、计时、成功/失败标记。

### 2.3 装饰器内部拆解

`python
def trace_node(node_name):
    def decorator(func):
        @wraps(func)  # 保留原函数的名字和文档字符串
        async def wrapper(*args, **kwargs):
            tracer = get_tracer("plate_agent.graph")    # ① 拿到 tracer
            with tracer.start_as_current_span(...) as span:  # ② 创建 span
                start = time.perf_counter()               # ③ 开始计时
                try:
                    result = await func(*args, **kwargs)  # ④ 真正执行
                    span.set_status(Status(StatusCode.OK))  # ⑤ 标记成功
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR))  # ⑥ 标记失败
                    raise
                finally:
                    span.set_attribute("duration_ms", ...)  # ⑦ 记录耗时
        return wrapper
    return decorator
`

七步走：拿 tracer → 建 span → 计时 → 执行 → 成功/失败 → 记耗时。

---

## 三、trace_block——节点内部的子步骤

@trace_node 只管一整层。节点内部有子步骤怎么办？

`python
@trace_node("preprocess")         # 外层 span："graph.preprocess"
async def preprocess_node(state, writer):
    with trace_block("gaussian_blur"):   # 子 span："gaussian_blur"
        result = tool_gaussian_blur(path)
    with trace_block("binarize"):        # 子 span："binarize"
        result = tool_binarize_otsu(path)
`

结果得到一棵 span 树：

`
graph.preprocess (83ms)
  ├── gaussian_blur (51ms)
  └── binarize (31ms)
`

---

## 四、ConsoleSpanExporter——"把 span 打印到控制台"

生产环境的追踪数据发到 Jaeger/Grafana，能看到漂亮的瀑布图。

但开发环境没有 Jaeger。ConsoleSpanExporter 把 span 打印成 JSON 到控制台：

`json
{
    "name": "graph.test_preprocess",
    "context": {
        "trace_id": "0x2543f473...",
        "span_id": "0x52ac4721..."
    },
    "status": {"status_code": "OK"},
    "attributes": {
        "node.name": "test_preprocess",
        "duration_ms": 83.11
    }
}
`

每个 span 结束时会自动打印一行 JSON。肉眼可读。

---

## 五、FastAPIInstrumentor——"给 HTTP 请求自动加追踪"

前面说的都是内部节点。那用户的 HTTP 请求本身呢？

不用手动写——一行代码搞定：

`python
FastAPIInstrumentor.instrument_app(app)
`

效果：每次你发 POST /api/chat，自动创建一个 span：

`
POST /api/chat (200, 120ms)       ← FastAPIInstrumentor 自动创建
  └── graph.preprocess (50ms)     ← 内部手动 span，自动关联
  └── graph.recognize (30ms)
  └── ...
`

关键：**自动关联**。HTTP span 和内部 span 有相同的 trace_id，因为这行代码帮你做了 context propagation。

---

## 六、TokenTracker——"给 LLM 打电话记账"

### 6.1 为什么需要

DeepSeek 不是免费的。每次调用都要花钱：

- input token：￥1 / 100 万
- output token：￥2 / 100 万

如果你今天调了 1000 次，花了多少钱？不知道 = 预算失控。

### 6.2 TokenTracker 怎么工作

`python
tracker = get_global_tracker()  # 全局记账本

# 每次 LLM 调用后记一笔
tracker.record_call(
    input_tokens=120,      # prompt 用了 120 token
    output_tokens=45,      # completion 回了 45 token
    model="deepseek-chat",
    operation="recognize", # 识别场景
)

# 想看账单：
summary = tracker.get_summary()
# {
#     "call_count": 4,
#     "total_tokens": 765,
#     "estimated_cost_rmb": 0.00098,  # 不到 1 厘钱
# }
`

### 6.3 线程安全

FastAPI 默认多 worker。多个请求同时调用 ecord_call()。

普通变量在多线程下会丢数据（race condition）。

TokenTracker 用 	hreading.Lock 保护：

`python
def record_call(self, ...):
    with self._lock:        # 上锁——同一时刻只有一个线程能进来
        self._total_input += input_tokens  # 安全累加
`

类比：公共厕所的隔间门锁。一个人进去锁门，完事出来下一个人进。

---

## 七、Day 9 全貌——一图总结

`
用户请求 POST /api/recognize
  │
  ▼
FastAPIInstrumentor → HTTP Span (自动)
  │
  ▼
GraphAgent 流水线
  ├── @trace_node("preprocess")  ── 83ms
  │   ├── trace_block("gaussian_blur")  ── 51ms
  │   ├── trace_block("binarize")       ── 31ms
  │   └── ...
  ├── @trace_node("locate")      ── 45ms
  ├── @trace_node("segment")     ── 30ms
  ├── @trace_node("recognize")   ── 80ms
  │   └── TokenTracker.record_call(input=120, output=45)  ← 记账
  ├── @trace_node("llm_verify")  ── 200ms (条件性)
  │   └── TokenTracker.record_call(input=200, output=30)  ← 记账
  └── @trace_node("format_output") ── 5ms
  │
  ▼
ConsoleSpanExporter → stdout JSON (开发)
  (或) OTLPSpanExporter → Jaeger (生产)
`

---

## 八、常见误区

| 误区 | 正解 |
|------|------|
| "OTel 太复杂，我只要 print" | print 没有 trace_id，无法关联。OTel 标准化的好处是工具链全通用 |
| "ConsoleSpanExporter 就够了" | 生产环境 console JSON 会淹没在日志里。必须接 Jaeger/Grafana |
| "TokenTracker 和 OTel 无关" | 核心归类不同：OTel 是 Tracing，TokenTracker 是成本追踪。Day 10 会统一到 Metrics |
| "装饰器影响性能" | @trace_node 开销 ~0.1ms/span，6 节点 × 0.1ms = 0.6ms，可忽略 |
