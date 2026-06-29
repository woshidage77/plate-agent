# PlateAgent Day 7 保姆级详解：评测体系从零理解

> 用类比理解概念，用项目真实代码验证，用完整链路串联一切。

---

## 零、为什么前六天缺了这个

前六天你一直在"搭积木"——Agent、工具、流水线、RAG、API。但每次改动后，你只能靠肉眼判断"看起来对不对"。

Day 7 做的事：**给整个系统装一个自动打分器**。每次改代码后跑一遍评测，数字告诉你变好了还是变坏了。

---

## 一、评测是什么——考试类比

- **训练** = 你平时刷题（模型训练，我们不涉及）
- **测试集** = 期末考卷（30 张合成车牌 + 标准答案）
- **评测** = 对答案（跑流水线 → 对比预测和标准答案 → 算分）
- **报告** = 成绩单（准确率、字符正确率、按题型分组）

---

## 二、测试集怎么来的——不能偷看答案

### 2.1 为什么用合成图

真实车牌照片有两个问题：
1. 涉及隐私（别人的车牌不能随便用）
2. 没有 ground truth（你不知道车牌号是什么）

合成图的优势：**你完全知道答案**。车牌号是你自己写的。

### 2.2 生成器做了什么

eval/dataset/generate.py 的核心循环：

```python
for i in range(30):
    plate = REAL_PLATES[i]                    # 京A12345, 沪B67890...
    img = create_plate_image(plate)           # 蓝底白字，PIL 绘制

    if i < 10:      # 清晰图（baseline）
        pass
    elif i < 20:    # 模糊图
        img = apply_blur(img, random_blur)
    elif i < 25:    # 倾斜图
        img = apply_tilt(img, random_angle)
    else:           # 噪声图
        img = apply_noise(img, random_noise)

    img.save(f"plate_{i+1:03d}.jpg")
    dataset.append({"image": "...", "plate_number": plate, "conditions": {...}})
```

关键设计：四种条件**均匀分布**，这样评测报告可以按条件分组看不同干扰下的准确率。

---

## 三、评测引擎怎么工作

### 3.1 单张评测

eval/evaluator.py 的 run_single()：

```python
async def run_single(self, item: dict) -> SingleResult:
    # 1. 创建独立 Runner（GraphAgent）
    runner = Runner(agent=recognition_agent, ...)

    # 2. 设置 session，跑流水线
    await session_service.create_session(state={"image_path": image_path})
    async for event in runner.run_async(...):
        pass  # 遍历到流结束

    # 3. 从 session.state 取最终结果
    session = await session_service.get_session(...)
    predicted = session.state.get("final_plate", "")

    # 4. 对比
    correct = (predicted == ground_truth)
    char_correct = sum(1 for i,c in enumerate(predicted) if c == ground_truth[i])

    return SingleResult(correct=correct, char_correct=char_correct, ...)
```

### 3.2 批量评测 + 汇总

run() 方法循环调用 run_single()，然后汇总：

```python
async def run(self, limit=None, verbose=True) -> EvalReport:
    for item in items:
        result = await self.run_single(item)
        report.details.append(result)

    # 汇总
    report.accuracy = correct_count / total
    report.char_accuracy = total_char_correct / total_chars
    report.avg_time_ms = sum(times) / total

    # 按条件分组
    for r in report.details:
        cond = r.conditions["type"]
        report.by_condition[cond]["total"] += 1
        if r.correct:
            report.by_condition[cond]["correct"] += 1

    return report
```

---

## 四、当前结果解读

SVM 识别模块是占位实现，一直返回"?"，置信度 0.0。所以：

- 整体准确率 = 0%（完全正常——SVM 没训练）
- 字符准确率 = 0%（同上）
- 流水线耗时 ~200ms/张（预处理+定位+分割正常运行）
- 按条件分组：全部 0%（因为 SVM 对所有条件都一样返回"?"）

**这不是 bug，这是评测体系的价值——它如实反映了当前系统的真实能力。**

当 SVM 模型训练完成，替换 tool_svm_predict 里的占位代码：

```python
# 当前（占位）
char = "?"
confidence = 0.0

# 未来（真实 SVM）
model = load_svm_model()
char, confidence = model.predict(hog_features)
```

重新跑一遍评测，数字立即反映改进效果。

---

## 五、考试速记卡

| 考点 | 答案 |
|------|------|
| 评测的三个核心概念？ | 测试集（有标注）→ 运行流水线 → 对比计算指标 |
| 整体准确率 vs 字符准确率？ | 整体=完全匹配才算对，字符=逐位置判断 |
| 四个条件分组？ | clear(10) / blur(10) / tilt(5) / noise(5) |
| 为什么用合成图？ | 可控 ground truth，无隐私问题 |
| 评测结果怎么读？ | 0% 准确率说明 SVM 占位正常，换真实模型后会提升 |
| 报告包含什么？ | 整体准确率、字符准确率、分组准确率、逐张详情、耗时 |
