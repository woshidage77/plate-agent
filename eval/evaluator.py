"""PlateAgent 评测引擎

批量运行 GraphAgent 识别流水线，对比 ground truth 计算准确率。

评测指标：
    - 整体准确率（完全匹配）
    - 字符级准确率（每个位置）
    - 按条件分组准确率（clear / blur / tilt / noise）
    - 黑名单命中率
    - 平均置信度
"""

import asyncio
import json
import os
import time
import logging
from typing import Optional
from dataclasses import dataclass, field

from trpc_agent_sdk.runners import Runner
from trpc_agent_sdk.types import Content, Part

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


@dataclass
class SingleResult:
    """单张图像的评测结果。"""
    image_id: int
    image_path: str
    ground_truth: str
    predicted: str = ""
    correct: bool = False
    char_correct: int = 0
    char_total: int = 0
    blacklist_hit: bool = False
    blacklist_result: dict = field(default_factory=dict)
    full_response: str = ""
    pipeline_time_ms: float = 0.0
    error: Optional[str] = None
    conditions: dict = field(default_factory=dict)
    # LLM Judge 评分（仅 --judge 模式填充）
    judge_recognition: float = -1.0
    judge_blacklist: float = -1.0
    judge_response: float = -1.0
    judge_reasons: dict = field(default_factory=dict)


@dataclass
class EvalReport:
    """评测汇总报告。"""
    total: int = 0
    correct: int = 0
    accuracy: float = 0.0
    char_accuracy: float = 0.0
    avg_time_ms: float = 0.0
    by_condition: dict = field(default_factory=dict)
    blacklist_hits: int = 0
    blacklist_total: int = 0
    details: list[SingleResult] = field(default_factory=list)
    # LLM Judge 汇总
    avg_judge_recognition: float = -1.0
    avg_judge_blacklist: float = -1.0
    avg_judge_response: float = -1.0
    judge_enabled: bool = False


class PlateEvaluator:
    """批量评测器。

    使用示例：
        evaluator = PlateEvaluator(
            gt_path="eval/dataset/ground_truth.json",
            session_service=session_service,
            memory_service=memory_service,
        )
        report = await evaluator.run()
        print(f"Accuracy: {report.accuracy:.1%}")
    """

    def __init__(
        self,
        gt_path: str,
        session_service,
        memory_service,
        app_name: str = "plate_eval",
    ):
        self.gt_path = gt_path
        self.session_service = session_service
        self.memory_service = memory_service
        self.app_name = app_name

        with open(gt_path, "r", encoding="utf-8") as f:
            self.ground_truth = json.load(f)

    async def run_single(self, item: dict) -> SingleResult:
        """对单张图像运行识别流水线。"""
        from agent.graph_agent import recognition_agent

        runner = Runner(
            app_name=self.app_name,
            agent=recognition_agent,
            session_service=self.session_service,
            memory_service=self.memory_service,
        )

        image_path = item["image"]
        ground_truth = item["plate_number"]
        session_id = f"eval_{item['id']}"

        # 确保绝对路径：ground truth 中的相对路径基于项目根目录
        if not os.path.isabs(image_path):
            project_root = os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)
            ))
            image_path = os.path.join(project_root, image_path)

        await self.session_service.create_session(
            app_name=self.app_name,
            user_id="eval_user",
            session_id=session_id,
            state={"image_path": image_path},
        )

        message = f"请识别这张车牌图片"
        user_content = Content(parts=[Part.from_text(text=message)])

        predicted = ""
        start = time.perf_counter()

        try:
            async for event in runner.run_async(
                user_id="eval_user",
                session_id=session_id,
                new_message=user_content,
            ):
                pass  # 遍历到流结束

            # 读取最终状态
            session = await self.session_service.get_session(
                app_name=self.app_name,
                user_id="eval_user",
                session_id=session_id,
            )
            if session and session.state:
                predicted = session.state.get("final_plate", "")
                if not predicted:
                    last_resp = session.state.get("last_response", "")
                    # 尝试从 last_response 提取
                    if "识别结果：" in last_resp:
                        parts = last_resp.split("识别结果：")
                        if len(parts) > 1:
                            predicted = parts[1].split("\n")[0].strip()

        except Exception as e:
            logger.exception("识别失败: %s", image_path)
            pass

        elapsed_ms = (time.perf_counter() - start) * 1000

        # 计算正确性
        correct = (predicted == ground_truth)
        char_correct = sum(
            1 for i, c in enumerate(predicted)
            if i < len(ground_truth) and c == ground_truth[i]
        )
        char_total = len(ground_truth)

        # 获取完整回复和黑名单结果
        full_response = ""
        blacklist_result = {}
        blacklist_hit = False
        try:
            session = await self.session_service.get_session(
                app_name=self.app_name,
                user_id="eval_user",
                session_id=session_id,
            )
            if session and session.state:
                full_response = session.state.get("last_response", "")
                if "黑名单命中" in full_response:
                    blacklist_hit = True
                # 尝试获取黑名单结构化结果
                final_plate = session.state.get("final_plate", "")
                if final_plate:
                    from agent.tools.knowledge import tool_search_blacklist
                    blacklist_result = tool_search_blacklist(final_plate)
        except Exception:
            pass

        await runner.close()

        return SingleResult(
            image_id=item["id"],
            image_path=item["image"],
            ground_truth=ground_truth,
            predicted=predicted,
            correct=correct,
            char_correct=char_correct,
            char_total=char_total,
            blacklist_hit=blacklist_hit,
            blacklist_result=blacklist_result,
            full_response=full_response,
            pipeline_time_ms=elapsed_ms,
            conditions=item.get("conditions", {}),
        )

    async def run(
        self,
        limit: Optional[int] = None,
        verbose: bool = True,
        judge: Optional["LLMJudge"] = None,
    ) -> EvalReport:
        """批量运行评测。

        Args:
            limit: 限制评测数量（None=全部）
            verbose: 是否打印进度

        Returns:
            EvalReport: 完整评测报告
        """
        items = self.ground_truth[:limit] if limit else self.ground_truth
        report = EvalReport(total=len(items))

        for item in items:
            if verbose:
                print(f"  [{item['id']:02d}/{len(items)}] {item['plate_number']} ... ", end="", flush=True)

            result = await self.run_single(item)
            report.details.append(result)

            if verbose:
                status = "OK" if result.correct else f"MISS (got: {result.predicted})"
                print(f"{status}  {result.pipeline_time_ms:.0f}ms")

        # 汇总
        report.correct = sum(1 for r in report.details if r.correct)
        report.accuracy = report.correct / report.total if report.total > 0 else 0.0

        total_char_correct = sum(r.char_correct for r in report.details)
        total_char = sum(r.char_total for r in report.details)
        report.char_accuracy = total_char_correct / total_char if total_char > 0 else 0.0

        report.avg_time_ms = (
            sum(r.pipeline_time_ms for r in report.details) / report.total
            if report.total > 0
            else 0.0
        )

        # 按条件分组
        for r in report.details:
            cond_type = r.conditions.get("type", "unknown")
            if cond_type not in report.by_condition:
                report.by_condition[cond_type] = {"total": 0, "correct": 0}
            report.by_condition[cond_type]["total"] += 1
            if r.correct:
                report.by_condition[cond_type]["correct"] += 1

        # ── LLM Judge 评分 ──
        if judge is not None:
            report.judge_enabled = True
            print("\n  [Judge] LLM 评测中...")
            from eval.judge import JudgeScores
            for i, r in enumerate(report.details):
                if verbose:
                    print(f"    [{i+1:02d}/{report.total}] judging {r.ground_truth} ... ", end="", flush=True)
                try:
                    scores = await judge.evaluate_all(
                        ground_truth=r.ground_truth,
                        predicted=r.predicted,
                        blacklist_result=r.blacklist_result if r.blacklist_result else None,
                        full_response=r.full_response,
                    )
                    r.judge_recognition = scores.recognition_score
                    r.judge_blacklist = scores.blacklist_score
                    r.judge_response = scores.response_score
                    r.judge_reasons = {
                        "recognition": scores.recognition_reason,
                        "blacklist": scores.blacklist_reason,
                        "response": scores.response_reason,
                    }
                    if verbose:
                        print(f"rec={scores.recognition_score:.1f}")
                except Exception as e:
                    logger.error("Judge 评测失败: %s", e)
                    if verbose:
                        print(f"error: {e}")

            # 汇总 Judge 评分
            valid_rec = [r.judge_recognition for r in report.details if r.judge_recognition >= 0]
            valid_bl = [r.judge_blacklist for r in report.details if r.judge_blacklist >= 0]
            valid_resp = [r.judge_response for r in report.details if r.judge_response >= 0]
            report.avg_judge_recognition = sum(valid_rec) / len(valid_rec) if valid_rec else -1.0
            report.avg_judge_blacklist = sum(valid_bl) / len(valid_bl) if valid_bl else -1.0
            report.avg_judge_response = sum(valid_resp) / len(valid_resp) if valid_resp else -1.0

        # 黑名单
        report.blacklist_total = sum(
            1 for r in report.details
            if r.ground_truth in ["京A12345", "粤B88888", "浙A66666"]
        )
        report.blacklist_hits = sum(
            1 for r in report.details
            if r.ground_truth in ["京A12345", "粤B88888", "浙A66666"]
            and r.blacklist_hit
        )

        return report



