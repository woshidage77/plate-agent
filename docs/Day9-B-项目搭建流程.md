# PlateAgent Day 9-B：OpenTelemetry + TokenTracker 搭建流程

> 从零集成 OpenTelemetry 可观测性和 Token 追踪的完整步骤

---

## 一、文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | agent/telemetry.py | OTel 初始化 + tracer + @trace_node 装饰器 + trace_block |
| 新增 | agent/token_tracker.py | TokenRecord + TokenTracker 线程安全计数器 |
| 新增 | agent/main_telemetry.py | 验证脚本（端到端 5 项检查） |
| 修改 | server/dependencies.py | init_runner() 中调用 init_telemetry() |
| 修改 | server/app.py | 添加 FastAPIInstrumentor.instrument_app() |
| 修改 | agent/graph_nodes.py | 6 个节点函数加 @trace_node 装饰器 |

## 二、新增依赖

已在 requirements.txt 中：

`
opentelemetry-api>=1.20.0
opentelemetry-sdk>=1.20.0
opentelemetry-instrumentation-fastapi>=0.41b0
`

## 三、使用方式

### 3.1 验证脚本（独立运行）

`ash
python -m agent.main_telemetry
`

输出 5 项检查：
1. init_telemetry() 初始化
2. 手动 span 创建（verify_root → verify_child）
3. @trace_node 装饰器（test_preprocess, test_recognize）
4. TokenTracker 统计（4 次调用累计）
5. 全局单例验证

### 3.2 服务运行（自动启用）

`ash
python -m server.main
`

FastAPI 启动时 lifespan 自动调用 init_runner() → init_telemetry()。
每个 HTTP 请求的 span 由 FastAPIInstrumentor 自动创建。

## 四、架构设计

`
server/main.py (uvicorn)
  └── server/app.py: create_app()
      ├── lifespan → init_runner() → init_telemetry()  ← Day 9 入口
      ├── FastAPIInstrumentor.instrument_app(app)       ← 自动 HTTP span
      └── routes/chat.py, routes/recognize.py
          └── agent/graph_nodes.py (6 节点)
              ├── @trace_node("preprocess")   ← 每个节点一个 span
              ├── @trace_node("locate")
              ├── @trace_node("segment")
              ├── @trace_node("recognize")
              ├── @trace_node("llm_verify")
              └── @trace_node("format_output")
                  └── trace_block("xxx")      ← 内部子步骤 span

agent/telemetry.py:
  init_telemetry() → TracerProvider
    ├── SimpleSpanProcessor(console_exporter)  ← 开发：stdout JSON
    └── (可选) BatchSpanProcessor(otlp)       ← 生产：Jaeger/Grafana

agent/token_tracker.py:
  TokenTracker (threading.Lock)
    ├── record_call(input, output, model, op)
    ├── get_summary() → {call_count, tokens, cost}
    └── get_global_tracker()  ← 全局单例
`

## 五、关键设计决策

| 决策 | 原因 |
|------|------|
| ConsoleSpanExporter 默认 | 开发阶段不需要额外基础设施 |
| SimpleSpanProcessor | 开发调试需要即时看到 span |
| 生产切 OTLP | 一行代码切换，不改业务逻辑 |
| @trace_node 装饰器 | 消除 6 节点 × 10 行重复代码 |
| trace_block 上下文管理器 | 节点内部子步骤追踪 |
| TokenTracker 全局单例 | 跨模块共享同一计数器 |
| threading.Lock | FastAPI 多 worker 线程安全 |
| DeepSeek 价格硬编码 | 当前只用 DeepSeek，后续可配置化 |

## 六、验证结果

`
============================================================
PlateAgent Day 9 - OTel + TokenTracker Verification
============================================================

[1/5] init_telemetry()...
  TracerProvider + ConsoleSpanExporter OK

[2/5] Manual span...
  root span: verify_root
  child span: verify_child
  (spans printed to console above)

[3/5] @trace_node decorator...
  dummy_preprocess -> /tmp/test_plate.jpg_processed
  dummy_recognize -> JingA12345

[4/5] TokenTracker stats...
  call_count: 4
  total_input_tokens: 550
  total_output_tokens: 215
  total_tokens: 765
  avg_input: 137.5 / avg_output: 53.8
  estimated_cost: RMB 0.00098

[5/5] Global singleton...
  global tracker calls: 1
  singleton identity: SAME

============================================================
ALL CHECKS PASSED
============================================================
`

ConsoleSpanExporter 输出的 JSON span 记录（示例）：

`json
{
    "name": "graph.test_preprocess",
    "context": {
        "trace_id": "0x2543f473aedf2907b0e56e62d7783c8c",
        "span_id": "0x52ac472175783de8"
    },
    "status": {"status_code": "OK"},
    "attributes": {
        "node.name": "test_preprocess",
        "node.type": "graph_agent",
        "duration_ms": 83.11
    }
}
`

## 七、后续扩展方向（Day 10+）

- Metrics：Prometheus 指标（请求数/延迟分位数/错误率）
- Grafana Dashboard：可视化 Trace + Metrics
- 告警规则：LLM 复核耗时 > 2s 触发告警
- TokenTracker 接入 Metrics：token 消耗趋势图
