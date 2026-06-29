"""PlateAgent LLM Judge — 用 LLM 评估系统输出质量

三个评测维度：
    1. recognition_quality  — 识别结果是否合理（允许 1-2 字符 OCR 误差）
    2. blacklist_quality     — 黑名单查询结果是否恰当
    3. response_quality      — 整体回复是否清晰完整

与 Day 7 的精确匹配评测互补：
    - Day 7 严格比对：完全匹配才算对
    - Day 8 LLM Judge：允许合理误差，关注语义正确性

使用示例：
    judge = LLMJudge(api_key, base_url, model)
    score = await judge.evaluate_recognition("京A12345", "京A1234S")
    print(score)  # {"score": 0.85, "reason": "One char OCR error: S vs 5"}
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


@dataclass
class JudgeScores:
    """LLM Judge 对单次识别的三维评分。"""
    recognition_score: float = 0.0
    recognition_reason: str = ""
    blacklist_score: float = 0.0
    blacklist_reason: str = ""
    response_score: float = 0.0
    response_reason: str = ""
    error: Optional[str] = None


# ── Judge Prompts ──

RECOGNITION_PROMPT = """你是一个车牌识别系统的评测裁判。评估识别结果的质量。

识别目标（ground truth）：{ground_truth}
系统预测（predicted）：{predicted}

评分标准：
- 1.0：完全正确，字符完全匹配
- 0.8：1个字符错误（常见 OCR 混淆，如 B/8、0/O、S/5、京/琼）
- 0.6：2个字符错误
- 0.4：3个字符错误
- 0.2：仅省份或首位正确
- 0.0：完全错误或识别失败

请以 JSON 格式回复，只包含 score 和 reason 两个字段：
{{"score": 0.8, "reason": "第5位字符 S 与标注 5 混淆，属于常见 OCR 错误"}}"""

BLACKLIST_PROMPT = """你是一个黑名单查询系统的评测裁判。评估黑名单查询结果的质量。

查询车牌：{plate_number}
黑名单结果：{blacklist_result}

评分标准：
- 1.0：黑名单命中且信息完整准确
- 0.8：黑名单命中但信息部分缺失
- 0.5：黑名单应命中但未命中，或不应命中但命中了错误的记录
- 0.0：黑名单查询失败或返回完全不相关的结果

请以 JSON 格式回复：
{{"score": 0.8, "reason": "黑名单已命中，但违章描述缺少罚款金额"}}"""

RESPONSE_PROMPT = """你是一个 AI 助手回复质量的评测裁判。评估系统最终回复的质量。

用户请求：识别车牌图片
系统完整回复：{full_response}

评分标准：
- 1.0：回复清晰完整，包含识别结果和必要的补充信息
- 0.8：回复基本完整，有小瑕疵
- 0.5：回复不完整或表述不清
- 0.0：回复无意义或完全错误

请以 JSON 格式回复：
{{"score": 0.8, "reason": "回复包含了识别结果，但缺少置信度说明"}}"""


class LLMJudge:
    """LLM 评测裁判。

    使用 DeepSeek Chat API 对系统输出进行三维质量评估。
    """

    def __init__(self, api_key: str, base_url: str, model: str = "deepseek-chat"):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def _call_llm(self, prompt: str) -> dict:
        """调用 LLM 获取 JSON 评分。"""
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "你是一个客观的评测裁判。只输出 JSON，不要输出其他内容。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,  # 评测用 0 温度确保一致性
                max_tokens=200,
            )
            text = response.choices[0].message.content.strip()
            # 提取 JSON（处理 LLM 可能包裹的 markdown 代码块）
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()
            return json.loads(text)
        except Exception as e:
            logger.error("LLM Judge 调用失败: %s", e)
            return {"score": -1.0, "reason": f"Judge error: {str(e)}"}

    async def evaluate_recognition(
        self, ground_truth: str, predicted: str
    ) -> dict:
        """评估识别结果质量。

        Args:
            ground_truth: 真实车牌号
            predicted: 系统预测车牌号

        Returns:
            {"score": float, "reason": str}
        """
        prompt = RECOGNITION_PROMPT.format(
            ground_truth=ground_truth,
            predicted=predicted,
        )
        return await self._call_llm(prompt)

    async def evaluate_blacklist(
        self, plate_number: str, blacklist_result: dict
    ) -> dict:
        """评估黑名单查询质量。

        Args:
            plate_number: 查询的车牌号
            blacklist_result: 黑名单查询返回的完整 dict

        Returns:
            {"score": float, "reason": str}
        """
        prompt = BLACKLIST_PROMPT.format(
            plate_number=plate_number,
            blacklist_result=json.dumps(blacklist_result, ensure_ascii=False, indent=2),
        )
        return await self._call_llm(prompt)

    async def evaluate_response(self, full_response: str) -> dict:
        """评估整体回复质量。

        Args:
            full_response: 系统完整回复文本

        Returns:
            {"score": float, "reason": str}
        """
        prompt = RESPONSE_PROMPT.format(full_response=full_response)
        return await self._call_llm(prompt)

    async def evaluate_all(
        self,
        ground_truth: str,
        predicted: str,
        blacklist_result: Optional[dict] = None,
        full_response: str = "",
    ) -> JudgeScores:
        """三维综合评测。

        Args:
            ground_truth: 真实车牌号
            predicted: 预测车牌号
            blacklist_result: 黑名单查询结果（可选）
            full_response: 系统完整回复

        Returns:
            JudgeScores: 三维评分汇总
        """
        scores = JudgeScores()

        # 1. 识别质量
        rec_result = await self.evaluate_recognition(ground_truth, predicted)
        scores.recognition_score = rec_result.get("score", -1.0)
        scores.recognition_reason = rec_result.get("reason", "")

        # 2. 黑名单质量
        if blacklist_result:
            bl_result = await self.evaluate_blacklist(predicted or ground_truth, blacklist_result)
            scores.blacklist_score = bl_result.get("score", -1.0)
            scores.blacklist_reason = bl_result.get("reason", "")

        # 3. 回复质量
        if full_response:
            resp_result = await self.evaluate_response(full_response)
            scores.response_score = resp_result.get("score", -1.0)
            scores.response_reason = resp_result.get("reason", "")

        return scores
