"""评测报告生成器

将 EvalReport 格式化为可读的文本/Markdown 报告。
Day 8 增强：支持 LLM Judge 评分显示。
"""

from eval.evaluator import EvalReport


def generate_text_report(report: EvalReport) -> str:
    """生成纯文本评测报告。"""
    lines = []
    w = lines.append

    w("=" * 60)
    w("  PlateAgent 车牌识别评测报告")
    w("=" * 60)
    w("")

    w("【整体准确率】")
    w(f"  样本数:     {report.total}")
    w(f"  完全正确:   {report.correct}")
    w(f"  整体准确率: {report.accuracy:.1%}")
    w(f"  字符准确率: {report.char_accuracy:.1%}")
    w(f"  平均耗时:   {report.avg_time_ms:.0f} ms")
    w("")

    w("【按条件分组准确率】")
    for cond_type in ["clear", "blur", "tilt", "noise"]:
        if cond_type in report.by_condition:
            c = report.by_condition[cond_type]
            acc = c["correct"] / c["total"] if c["total"] > 0 else 0
            w(f"  {cond_type:8s}: {c["correct"]:2d}/{c["total"]:2d} = {acc:.1%}")
    w("")

    if report.judge_enabled:
        w("【LLM Judge 评分】（0~1，越高越好）")
        if report.avg_judge_recognition >= 0:
            w(f"  识别质量均值: {report.avg_judge_recognition:.2f}")
        else:
            w("  识别质量均值: N/A")
        if report.avg_judge_blacklist >= 0:
            w(f"  黑名单质量均值: {report.avg_judge_blacklist:.2f}")
        else:
            w("  黑名单质量均值: N/A")
        if report.avg_judge_response >= 0:
            w(f"  回复质量均值: {report.avg_judge_response:.2f}")
        else:
            w("  回复质量均值: N/A")
        w("")

    w("【黑名单命中】")
    if report.blacklist_total > 0:
        w(f"  预期命中: {report.blacklist_total}")
        w(f"  实际命中: {report.blacklist_hits}")
    else:
        w("  （测试集中无黑名单车辆）")
    w("")

    w("【逐张详情】")
    if report.judge_enabled:
        w(f"  {"ID":>3s}  {"标注":<10s} {"预测":<10s} {"结果":>4s} {"字符":>6s} {"耗时":>6s}  {"Judge":>5s}  {"条件"}")
        w(f"  {"---":>3s}  {"----":<10s} {"----":<10s} {"----":>4s} {"----":>6s} {"----":>6s}  {"-----":>5s}  {"----"}")
    else:
        w(f"  {"ID":>3s}  {"标注":<10s} {"预测":<10s} {"结果":>4s} {"字符":>6s} {"耗时":>6s}  {"条件"}")
        w(f"  {"---":>3s}  {"----":<10s} {"----":<10s} {"----":>4s} {"----":>6s} {"----":>6s}  {"----"}")

    for r in report.details:
        char_acc = f"{r.char_correct}/{r.char_total}"
        status = "OK" if r.correct else "MISS"
        cond = r.conditions.get("type", "?")
        if report.judge_enabled and r.judge_recognition >= 0:
            w(f"  {r.image_id:3d}  {r.ground_truth:<10s} {r.predicted:<10s} {status:>4s} {char_acc:>6s} {r.pipeline_time_ms:5.0f}ms  {r.judge_recognition:4.1f}  {cond}")
        else:
            w(f"  {r.image_id:3d}  {r.ground_truth:<10s} {r.predicted:<10s} {status:>4s} {char_acc:>6s} {r.pipeline_time_ms:5.0f}ms  {cond}")

    w("")
    w("=" * 60)

    return "\n".join(lines)


def generate_markdown_report(report: EvalReport) -> str:
    """生成 Markdown 格式评测报告。"""
    lines = []
    w = lines.append

    w("# PlateAgent 车牌识别评测报告")
    w("")
    w("## 整体准确率")
    w("")
    w("| 指标 | 值 |")
    w("|------|----|")
    w(f"| 样本数 | {report.total} |")
    w(f"| 完全正确 | {report.correct} |")
    w(f"| 整体准确率 | {report.accuracy:.1%} |")
    w(f"| 字符准确率 | {report.char_accuracy:.1%} |")
    w(f"| 平均耗时 | {report.avg_time_ms:.0f} ms |")
    w("")

    if report.judge_enabled:
        w("## LLM Judge 评分")
        w("")
        w("| 维度 | 均值 |")
        w("|------|------|")
        rec = f"{report.avg_judge_recognition:.2f}" if report.avg_judge_recognition >= 0 else "N/A"
        bl = f"{report.avg_judge_blacklist:.2f}" if report.avg_judge_blacklist >= 0 else "N/A"
        resp = f"{report.avg_judge_response:.2f}" if report.avg_judge_response >= 0 else "N/A"
        w(f"| 识别质量 | {rec} |")
        w(f"| 黑名单质量 | {bl} |")
        w(f"| 回复质量 | {resp} |")
        w("")

    w("## 按条件分组")
    w("")
    w("| 条件 | 正确 | 总数 | 准确率 |")
    w("|------|------|------|--------|")
    for cond_type in ["clear", "blur", "tilt", "noise"]:
        if cond_type in report.by_condition:
            c = report.by_condition[cond_type]
            acc = c["correct"] / c["total"] if c["total"] > 0 else 0
            w(f"| {cond_type} | {c["correct"]} | {c["total"]} | {acc:.1%} |")
    w("")

    w("## 逐张详情")
    w("")
    if report.judge_enabled:
        w("| ID | 标注 | 预测 | 结果 | 字符 | 耗时 | Judge | 条件 |")
        w("|----|------|------|------|------|------|-------|------|")
    else:
        w("| ID | 标注 | 预测 | 结果 | 字符 | 耗时 | 条件 |")
        w("|----|------|------|------|------|------|------|")

    for r in report.details:
        char_acc = f"{r.char_correct}/{r.char_total}"
        status = "OK" if r.correct else "MISS"
        cond = r.conditions.get("type", "?")
        if report.judge_enabled and r.judge_recognition >= 0:
            w(f"| {r.image_id} | {r.ground_truth} | {r.predicted} | {status} | {char_acc} | {r.pipeline_time_ms:.0f}ms | {r.judge_recognition:.1f} | {cond} |")
        else:
            w(f"| {r.image_id} | {r.ground_truth} | {r.predicted} | {status} | {char_acc} | {r.pipeline_time_ms:.0f}ms | {cond} |")

    return "\n".join(lines)