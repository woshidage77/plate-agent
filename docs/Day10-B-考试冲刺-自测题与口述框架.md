# PlateAgent Day 10-B：自测题 + 口述框架

> 7.1 犀牛鸟考试前最后一轮自检。每道题尝试不看答案口述，然后对照检查。
> 用途：考前自测 + 面试口述模板。

---

## 一、基础自测（必答，10 题）

### Q1：说出 tRPC-Agent 的 6 个核心抽象，以及它们在 PlateAgent 项目中分别对应哪个文件

<details>
<summary>口述框架</summary>

- **Agent** — [agent/llm_agent.py] — `LlmAgent(name="plate_agent", model=..., instruction=..., tools=[...])`
- **Runner** — [server/dependencies.py] — `Runner(app_name=..., agent=..., session_service=..., memory_service=...)`
- **Model** — [agent/config.py] — `OpenAIModel(model_name="deepseek-chat", ...)`
- **Tool** — [agent/tools/preprocess.py] 等 — `FunctionTool(func=xxx)`
- **Session** — [agent/session_manager.py] — `create_session_service(use_redis=bool)`
- **Memory** — [agent/session_manager.py] — `create_memory_service(use_redis=bool)`
</details>

### Q2：一次 Agent 调用从用户输入到事件流输出的完整链路是怎样的？

<details>
<summary>口述框架</summary>

```
用户输入 → Runner.run_async()
  → SessionService.get() 恢复历史
  → MemoryService.search() 召回记忆
  → Agent.run_async() 构造 messages
  → Model.generate() → 可能返回 tool_calls
  → Tool.execute() → 执行工具
  → Model.generate() 再次调用 → 最终回复
  → 事件流输出 (TextEvent → FinalEvent)
  → SessionService.append() 持久化
```
</details>

### Q3：FunctionTool 是怎么工作的？模型真的"调用"了你的 Python 函数吗？

<details>
<summary>口述框架</summary>

不，模型不直接调用函数。流程是：
1. 框架把工具的 name + description + parameters schema 发给模型
2. 模型返回 `tool_calls: [{name: "tool_xxx", arguments: {...}}]`
3. 框架根据 name 找到对应的 Python 函数，用 arguments 调用
4. 函数返回值作为 tool_result 发回给模型
5. 模型基于 tool_result 生成最终回复
</details>

### Q4：InMemorySessionService 和 RedisSessionService 有什么区别？什么时候用哪个？

<details>
<summary>口述框架</summary>

- **InMemory**：数据存在内存，进程重启丢失。适合开发/单进程。
- **Redis**：数据存在 Redis，支持多进程共享。适合生产/水平扩展。
- 项目用 `USE_REDIS=true` 环境变量一键切换。
</details>

### Q5：Memory 和 Session 的区别是什么？

<details>
<summary>口述框架</summary>

- **Session**：短期上下文。存当前对话的 messages、state、events。对话结束可丢弃。
- **Memory**：长期记忆。跨会话持久化用户偏好、历史知识。支持检索和召回。
- 类比：Session = 这次聊天的聊天记录，Memory = 你对这个用户的所有了解。
</details>

---

## 二、进阶自测（必答，8 题）

### Q6：RAG 的完整流程是怎样的？PlateAgent 中体现在哪里？

<details>
<summary>口述框架</summary>

```
文档（黑名单CSV + 混淆字符表）
  → ChromaDB loader 加载 → 分块(chunk) → 向量化(embedding)
  → 存入向量数据库（ChromaDB 三集合）
  → 用户查询时 → 向量检索 → 返回 top-k 结果
  → 拼接到 LLM prompt → LLM 基于上下文生成答案
```

项目体现：[agent/knowledge/loader.py] 加载，[agent/tools/knowledge.py] 检索工具。
</details>

### Q7：GraphAgent 的节点、边、条件路由分别是什么？你项目里怎么用的？

<details>
<summary>口述框架</summary>

- **节点(node)**：一个处理函数，接收 state 返回 dict 增量。我的项目有 6 个节点。
- **边(edge)**：定义节点间的流转顺序。preprocess → locate → segment → recognize → ...
- **条件路由(conditional edge)**：根据 state 字段决定下一节点。如 `needs_llm_verify` 为 True 走 llm_verify，否则跳过。
- **状态(state)**：TypedDict，节点间通过 state 传递数据。
</details>

### Q8：MCP、A2A、AG-UI 三个协议分别解决什么问题？

<details>
<summary>口述框架</summary>

| 协议 | 解决什么 | 类比 |
|------|---------|------|
| MCP | Agent 如何调用外部工具服务 | USB 接口——Agent 插上就能用外部工具 |
| A2A | Agent 之间如何通信协作 | 对讲机——Agent A 把任务委托给 Agent B |
| AG-UI | Agent 如何向前端输出结构化事件 | 电视信号——Agent 播事件，前端接收渲染 |
</details>

### Q9：SKILL.md 的结构是怎样的？Skills 系统解决了什么问题？

<details>
<summary>口述框架</summary>

**结构**：
```markdown
---
name: skill-name
description: ...
---
## Overview
## Tools
- tool_a
- tool_b
## Usage Pattern
```

**解决的问题**：
- 可复用：技能一次定义，多个 Agent 复用
- 延迟加载：不调用 load 时不占 token
- 工具分组：相关工具打包成一个 skill
- 文档内嵌：使用说明和工具定义在一起
</details>

### Q10：OpenTelemetry 中 Trace 和 Span 的关系是什么？ConsoleSpanExporter 和 OTLPSpanExporter 怎么选？

<details>
<summary>口述框架</summary>

- **Trace**：一次完整请求的调用链（如识别一张车牌的全流程）
- **Span**：调用链上的一个节点（如 preprocess 节点耗时 83ms）
- 关系：一个 Trace 包含多个 Span，形成树状结构
- **ConsoleSpanExporter**：打印 JSON 到 stdout，开发调试用
- **OTLPSpanExporter**：发送到 Jaeger/Grafana Tempo，生产环境用
</details>

### Q11：LLM Judge 是什么？和精确匹配评测有什么区别？

<details>
<summary>口述框架</summary>

- **精确匹配**：predicted == ground_truth，对就对错就错。Day 7。
- **LLM Judge**：让 DeepSeek 当裁判，按评分标准打分。Day 8。
- 优势：容忍 OCR 常见混淆（如 5/S、B/8），更符合用户体验。
- 关键设计：评分标准写死在 prompt 里，temperature=0 确保一致性，JSON 输出约束。
</details>

### Q12：TokenTracker 为什么要线程安全？怎么实现的？

<details>
<summary>口述框架</summary>

- **为什么**：FastAPI 多 worker 并发调用 `record_call()`，普通变量会有 race condition（两个线程同时累加导致计数丢失）。
- **怎么实现**：`threading.Lock` 保护。`with self._lock:` 确保同一时刻只有一个线程修改计数器。
- **成本公式**（DeepSeek）：input/1M × 1.0 + output/1M × 2.0（人民币）。
</details>

### Q13：CodeExecutor 有哪些执行环境？安全边界怎么划分？

<details>
<summary>口述框架</summary>

| 环境 | 隔离级别 | 适用场景 |
|------|---------|---------|
| 本地执行 | 无隔离 | 信任的代码/开发调试 |
| Docker 容器 | 进程级隔离 | 一般安全需求 |
| Cube 沙箱 | 强隔离（腾讯内部） | 生产环境 |
| E2B 沙箱 | 最强隔离（云端） | 不可信代码执行 |
</details>

---

## 三、实战场景口述（选答，3 题）

### Q14：如果你的车牌识别 Agent 在生产环境响应变慢，你怎么排查？

<details>
<summary>口述框架</summary>

1. **看 OpenTelemetry trace**：哪个 span 耗时最长？是 preprocess 还是 llm_verify？
2. **看 TokenTracker**：LLM 调用是否异常增多？
3. **看日志**：有没有异常堆栈？
4. **看评测报告**：最近的准确率是否有变化？（可能是模型换了）
5. **定位后**：如果是 DeepSeek 慢 → 加超时+重试；如果是图像处理慢 → 优化算法或加 GPU
</details>

### Q15：如果让你给 PlateAgent 加一个"人工审批"环节（某些车牌需要人工确认），用 GraphAgent 怎么实现？

<details>
<summary>口述框架</summary>

使用 GraphAgent 的 **interrupt / resume** 机制：
1. recognize 节点完成后，检查条件（如置信度 < 0.6）
2. 条件为 True → interrupt（暂停流水线，通知人工）
3. 人工在 UI 确认/修改后 → resume（继续流水线）
4. 用 checkpoint 保存中断时的状态，resume 时恢复
</details>

### Q16：怎么给 PlateAgent 写一个评测体系？

<details>
<summary>口述框架</summary>

1. **构建 Eval set**：30 张测试图，覆盖 clear/blur/tilt/noise 4 种场景
2. **精确匹配**：predicted == ground_truth → 准确率
3. **LLM Judge**：三维评分（识别质量 + 黑名单质量 + 回复质量）
4. **分组统计**：按场景分组，看哪种场景最差
5. **报告生成**：Markdown 报告，含整体指标 + 分组指标 + Judge 评分
6. **持续集成**：每次改代码跑一遍 eval，防止回归
</details>

---

## 四、快速自检清单

考试前 10 分钟快速过一遍：

- [ ] 能说出 6 个核心抽象 + 项目对应文件
- [ ] 能画出一次 Agent 调用的完整链路
- [ ] 能解释 FunctionTool 的工作原理（模型不直接调函数）
- [ ] 能说清 Session vs Memory 区别
- [ ] 能描述 RAG 的 5 步流程
- [ ] 能解释 GraphAgent 节点/边/条件路由
- [ ] 能区分 MCP/A2A/AG-UI
- [ ] 知道 SKILL.md 的结构
- [ ] 能说清 Trace vs Span
- [ ] 能解释 LLM Judge 的评分标准设计
- [ ] 知道 TokenTracker 为什么用 Lock
- [ ] 能说出 4 种 CodeExecutor 环境