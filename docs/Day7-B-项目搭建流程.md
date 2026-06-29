# PlateAgent Day 7-B：评测体系搭建流程

> 从零搭建车牌识别评测体系的完整步骤

---

## 一、文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | eval/dataset/generate.py | 合成车牌图生成器 |
| 新增 | eval/dataset/test_plates/ | 30 张测试图像 |
| 新增 | eval/dataset/ground_truth.json | 标注文件 |
| 新增 | eval/evaluator.py | 批量评测引擎 |
| 新增 | eval/report.py | 报告生成器 |
| 新增 | eval/main.py | 评测入口 |

---

## 二、测试集设计

30 张合成车牌图，4 种条件：

| 条件 | 数量 | 干扰 |
|------|------|------|
| clear | 10 | 无干扰 |
| blur | 10 | 高斯模糊 |
| tilt | 5 | 旋转变换 |
| noise | 5 | 椒盐噪声 |

全部覆盖 30 个省份简称，车牌号由字母+5位数字组成。

---

## 三、使用方式

```bash
cd plate-agent

# 生成测试集
python eval/dataset/generate.py

# 全量评测
python -m eval.main

# 快速评测（前10张）
python -m eval.main --limit 10

# 输出 Markdown 报告
python -m eval.main --output eval_report.md
```

---

## 四、评测器架构

```evaluator.py
├── PlateEvaluator
│   ├── __init__: 加载 ground_truth.json
│   ├── run_single(): 单张识别 + 结果比对
│   └── run(): 批量评测 + 汇总统计
│
report.py
├── generate_text_report(): 控制台文本报告
└── generate_markdown_report(): MD 报告（可存档）
```

---

## 五、当前结果说明

SVM 识别模块为占位实现（始终返回 "?"，置信度 0.0），因此评测准确率为 0%。评测体系本身完全正常工作：

- 流水线端到端跑通（预处理→定位→分割→识别→黑名单）
- 平均耗时 ~200ms/张（不含 LLM 调用）
- 报告格式完整（整体/分组/逐张详情/黑名单）

**当 SVM 模型训练完成后，替换 tool_svm_predict 实现即可立即获得有意义的评测数据。**
