# PlateAgent Day 6-B：FastAPI 服务化搭建流程

> 从零搭建 FastAPI + SSE 流式服务的完整步骤

---

## 一、文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | server/schemas.py | Pydantic 请求/响应模型 |
| 新增 | server/dependencies.py | Runner 单例管理 + 依赖注入 |
| 新增 | server/routes/chat.py | POST /api/chat（SSE 流式对话） |
| 新增 | server/routes/recognize.py | POST /api/recognize（SSE 流式识别） |
| 新增 | server/app.py | FastAPI 应用工厂 + lifespan |
| 新增 | server/main.py | uvicorn 启动入口 |
| 修改 | agent/graph_agent.py | 导出双 Agent（root_agent + recognition_agent） |
| 修改 | agent/main_graph.py | import 适配 recognition_agent |

---

## 二、架构总览

```server/
├── __init__.py
├── app.py              # FastAPI 应用工厂 + lifespan
├── main.py             # uvicorn 启动入口
├── schemas.py          # Pydantic 模型
├── dependencies.py     # Runner 单例 + Depends 注入
└── routes/
    ├── __init__.py
    ├── chat.py         # POST /api/chat (LlmAgent)
    └── recognize.py    # POST /api/recognize (GraphAgent)
```

---

## 三、API 接口

### 3.1 POST /api/chat

多轮对话（SSE 流式）。

请求：
```json
{
  "message": "识别这张车牌",
  "user_id": "alice",
  "session_id": "abc-123",
  "image_path": "eval/dataset/test_images/synth_plate.jpg"
}
```

SSE 事件类型：
- `text_delta` — 流式文本片段
- `tool_call` — 工具调用
- `tool_result` — 工具返回
- `done` — 流结束

### 3.2 POST /api/recognize

单张车牌识别（SSE 流式）。

请求：
```json
{
  "image_path": "eval/dataset/test_images/synth_plate.jpg",
  "user_id": "anonymous"
}
```

SSE 事件类型：
- `text_delta` — GraphAgent 节点进度文本
- `tool_call` — 工具调用
- `tool_result` — 工具返回
- `final` — 最终识别结果（plate_number + blacklist_hit）
- `done` — 流结束

### 3.3 GET /api/health

健康检查。

响应：
```json
{"status": "ok", "version": "1.0.0", "agent": "plate_recognition"}
```

---

## 四、启动方式

```bash
cd plate-agent

# 默认端口 8000
python -m server.main

# 指定端口 + 热重载
python -m server.main --port 8080 --reload
```

---

## 五、验证

```bash
# 1. 健康检查
curl http://localhost:8000/api/health

# 2. 流式对话
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}' \
  --no-buffer

# 3. 流式识别
curl -X POST http://localhost:8000/api/recognize \
  -H "Content-Type: application/json" \
  -d '{"image_path": "eval/dataset/test_images/synth_plate.jpg"}' \
  --no-buffer
```
