# PlateAgent Day 9-A：OpenTelemetry 可观测性 + Token 追踪（考试向）

> 源：OpenTelemetry 官方规范 + 项目实战
> 用途：7.1 犀牛鸟考试知识储备

---

## 一、为什么需要可观测性

### 1.1 GraphAgent 的黑盒问题

Day 6 的服务化之后，车牌识别是一个 6 节点流水线。问题：

- 哪个节点最慢？（预处理 vs LLM 复核？）
- 一次请求走了哪些节点？（条件路由跳过了 LLM 复核吗？）
- 错误发生在哪里？原因是什么？

没有埋点，这些问题只能靠猜测。

### 1.2 OpenTelemetry 解决什么

OpenTelemetry (OTel) 是 CNCF 孵化的**可观测性标准**，提供三支柱：

| 支柱 | 用途 | PlateAgent 用法 |
|------|------|---------------|
| **Tracing（链路追踪）** | 追踪一次请求的完整路径 | 每个 Graph 节点 = 一个 span |
| **Metrics（指标）** | 数值统计（延迟/吞吐/错误率） | 节点耗时、Token 消耗 |
| **Logging（日志）** | 文本事件记录 | 与 trace_id 关联的异常日志 |

Day 9 只做 Tracing + Token 计数。Metrics 留给 Day 10。

---

## 二、核心概念：Trace / Span / Tracer

### 2.1 类比：快递追踪

- **Trace**：一个快递从发件到签收的全程
- **Span**：全程中的每一站（揽件 → 中转 → 派送 → 签收）
- **Tracer**：快递公司的追踪系统

在 PlateAgent 中：

`
一个车牌识别请求 = 一个 Trace
  ├── preprocess span（预处理）
  │   ├── gaussian_blur span（嵌套子 span）
  │   ├── binarize span
  │   └── ...
  ├── locate span（定位）
  ├── segment span（分割）
  ├── recognize span（识别）
  ├── llm_verify span（LLM 复核，条件性）
  └── format_output span（格式化输出）
`

### 2.2 Span 的生命周期

`
start_span("preprocess")
  ├── set_attribute("node.type", "graph_agent")  # 添加属性
  ├── 执行业务逻辑...
  ├── set_status(StatusCode.OK)                  # 标记成功
  └── end_span()                                 # 结束 → 导出
`

### 2.3 关键类型速查

| 类型 | 说明 |
|------|------|
| TracerProvider | 创建 Tracer 的工厂，持有导出器配置 |
| Tracer | 创建 Span 的工具（get_tracer("name")） |
| Span | 一次操作的记录（名称 + 属性 + 时间戳 + 状态） |
| SpanExporter | 将 Span 发送到后端（Console / OTLP / Jaeger） |
| SpanProcessor | 控制何时导出（Simple=同步，Batch=批量异步） |
| Resource | 标识服务元数据（service.name, service.version） |

---

## 三、@trace_node 装饰器设计

### 3.1 为什么用装饰器

GraphAgent 有 6 个节点函数，每个都要包一层 span。如果不封装：

`python
# 裸写 —— 6 个节点要重复 6 次：
async def preprocess_node(state, writer):
    tracer = get_tracer(...)
    with tracer.start_as_current_span("preprocess") as span:
        # 业务逻辑...
`

6 个节点 = 6 × 10 行重复代码。用装饰器：

`python
@trace_node("preprocess")        # 一行搞定
async def preprocess_node(state, writer):
    ...
`

### 3.2 装饰器自动做了哪些事

1. 创建 span（名称 = "graph.{node_name}"）
2. 设置属性（
ode.name, 
ode.type）
3. 计时（	ime.perf_counter() 前后差值）
4. 成功时设置 StatusCode.OK
5. 异常时设置 StatusCode.ERROR + ecord_exception()
6. 写入 duration_ms 属性

### 3.3 trace_block 上下文管理器

装饰器只适用于整个函数。函数内部的子步骤用 	race_block：

`python
@trace_node("preprocess")
async def preprocess_node(state, writer):
    with trace_block("gaussian_blur", {"kernel_size": 3}):
        result = tool_gaussian_blur(path)
    with trace_block("binarize"):
        result = tool_binarize_otsu(path)
`

---

## 四、Span 导出策略

### 4.1 开发 vs 生产

| 环境 | 导出器 | 特点 |
|------|--------|------|
| 开发 | ConsoleSpanExporter | 打印 JSON 到 stdout，肉眼可读 |
| 生产 | OTLPSpanExporter | 发送到 Jaeger/Grafana Tempo |

### 4.2 SimpleSpanProcessor vs BatchSpanProcessor

| Processor | 行为 | 适用 |
|-----------|------|------|
| SimpleSpanProcessor | Span 结束立即导出（同步阻塞） | 开发/调试 |
| BatchSpanProcessor | 攒一批再发（异步非阻塞） | 生产环境 |

---

## 五、FastAPIInstrumentor 自动注入

### 5.1 作用

一行代码让 FastAPI 的**每个 HTTP 请求**自动创建 span：

`python
FastAPIInstrumentor.instrument_app(app)
`

自动创建的 span 包含：
- HTTP method + path（如 POST /api/chat）
- 状态码
- 请求耗时
- 与内部 span 自动关联（通过 context propagation）

### 5.2 与手动 span 的关系

`
HTTP Request Span (FastAPIInstrumentor 自动创建)
  └── graph.preprocess (手动 @trace_node)
      └── gaussian_blur (手动 trace_block)
      └── binarize (手动 trace_block)
  └── graph.locate (手动 @trace_node)
  └── ...
  └── HTTP Response
`

---

## 六、Token 追踪：TokenTracker

### 6.1 要追踪什么

DeepSeek API 按 token 计费。每次 LLM 调用，需要记录：

- input_tokens：prompt 消耗的 token
- output_tokens：completion 消耗的 token
- model：模型名称
- operation：调用场景（chat / recognize / judge）

### 6.2 成本估算公式

`
cost = (input_tokens / 1_000_000) * 1.0 + (output_tokens / 1_000_000) * 2.0
`

DeepSeek 价格（2024）：input ￥1/M，output ￥2/M。

### 6.3 线程安全

TokenTracker 内部用 	hreading.Lock 保护。
FastAPI 多 worker 场景下保证计数准确。

---

## 七、考点速查

| 考点 | 答案 |
|------|------|
| OTel 三支柱 | Tracing + Metrics + Logging |
| Trace vs Span | Trace = 完整调用链，Span = 链上的一个节点 |
| ConsoleSpanExporter 用途 | 开发阶段调试，输出 JSON 到控制台 |
| FastAPIInstrumentor 作用 | 自动为每个 HTTP 请求创建 span |
| @trace_node 做了什么 | 自动创建 span + 计时 + 状态记录 |
| TokenTracker 成本公式 | input/1M * 1.0 + output/1M * 2.0 (DeepSeek) |
| SimpleSpanProcessor vs BatchSpanProcessor | 同步即时导出 vs 批量异步导出 |
