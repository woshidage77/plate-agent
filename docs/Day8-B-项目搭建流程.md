# PlateAgent Day 8-B：LLM Judge 搭建流程

> 从零搭建 LLM-as-Judge 评测体系的完整步骤

---

## 一、文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | eval/judge.py | LLM Judge 核心 |
| 修改 | eval/evaluator.py | 增加 judge 字段 + run() 集成 |
| 修改 | eval/main.py | 增加 --judge 开关 |
| 修改 | eval/report.py | 报告增加 Judge 列 |

## 二、使用方式

```bash
# 普通评测
python -m eval.main --limit 5

# LLM Judge 评测
python -m eval.main --limit 5 --judge --output judge_report.md
```

## 三、Judge 调用流程

```
python -m eval.main --judge
  evaluator.run(judge=judge):
    1. 跑完所有识别流水线
    2. 对每个结果调用 judge.evaluate_all()
       - evaluate_recognition(gt, predicted)
       - evaluate_blacklist(plate, result)
       - evaluate_response(full_response)
    3. 汇总 Judge 评分到 EvalReport
```

## 四、验证结果

```
整体准确率: 0.0%  (SVM 占位)
LLM Judge:
  识别质量均值: 0.00  (识别失败)
  黑名单质量均值: 0.00
  回复质量均值: 0.50  (至少跑了流水线)
```
