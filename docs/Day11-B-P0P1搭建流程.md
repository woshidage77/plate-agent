# PlateAgent Day 11-B：P0 + P1 搭建流程

> SVM 训练 + 三层容错 + Parallel 并行 + Interrupt 人工确认

---

## 一、文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| **P0-1** | | |
| 新增 | agent/tools/train_svm.py | SVM 训练脚本（合成数据 + HOG + sklearn） |
| 新增 | agent/tools/svm_model.pkl | 训练好的 SVM 模型（11.1 MB） |
| 新增 | agent/tools/svm_labels.json | 65 类 label 映射 |
| 修改 | agent/tools/recognize.py | tool_svm_predict 加载真实模型 |
| **P0-2** | | |
| 新增 | agent/retry.py | call_llm_with_retry + safe_llm_call |
| 修改 | agent/graph_nodes.py | llm_verify_node 集成 safe_llm_call |
| **P1** | | |
| 修改 | agent/graph_nodes.py | recognize_node 改为 Parallel；新增 human_review_node |
| 修改 | agent/graph_agent.py | 注册 human_review_node + 三级条件路由 |
| 修改 | agent/graph_state.py | 新增 awaiting_human + low_confidence_chars |

## 二、使用方式

### 2.1 SVM 模型训练（首次/模型更新时）

```bash
python -m agent.tools.train_svm
```

输出：
```
总计 5544 个样本, 324 维特征
训练准确率: 100.00%
测试准确率: 99.52%
模型已保存: agent/tools/svm_model.pkl (11120.6 KB)
```

### 2.2 SVM 单字符验证

```python
from agent.tools.recognize import tool_svm_predict
result = tool_svm_predict("test_char_A.png")
# {"char": "A", "confidence": 0.6881, "needs_verify": True}
```

### 2.3 重试机制测试

```python
from agent.retry import safe_llm_call
result = await safe_llm_call(
    coro_fn=lambda: some_llm_api_call(),
    fallback_value={"char": "?"},
    operation="test",
)
```

### 2.4 Parallel vs Sequential 对比

```python
# Sequential
results = [tool_svm_predict(p) for p in paths]  # 1130ms

# Parallel (ThreadPoolExecutor)
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=8)
results = list(executor.map(tool_svm_predict, paths))  # 6ms, 185x faster
```

## 三、图结构（Day 11 最终版）

```
preprocess → locate → segment → recognize (Parallel SVM)
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
        conf < 0.5             0.5 ≤ conf < 0.85      conf ≥ 0.85
              │                      │                      │
        "human"                  "verify"               "output"
              │                      │                      │
        human_review            llm_verify            format_output
         (interrupt)          (retry+降级)            ([?]标注)
              │                      │
              └──────────────────────┘
                    format_output
```

## 四、验证清单

- [x] SVM 训练完成 → 99.52% 测试准确率
- [x] 7 字符全对（A/B/5/0/8/Z/S）
- [x] 条件路由三级分派正确（output/verify/human）
- [x] retry 4 场景通过（成功/重试成功/降级/不可重试）
- [x] Parallel 185x 加速
- [x] 7 个节点全部导入成功
- [x] graph 编译成功