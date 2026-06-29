"""PlateAgent Token 用量追踪 — Day 9

追踪每次 LLM API 调用的 token 消耗，用于：
    - 成本估算（DeepSeek 按 token 计费）
    - 性能优化（发现哪些调用消耗最多 token）
    - 评测报告（平均 token 消耗）

使用：
    from agent.token_tracker import TokenTracker, get_global_tracker

    tracker = get_global_tracker()
    tracker.record_call(input_tokens=150, output_tokens=80)
    print(tracker.get_summary())
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TokenRecord:
    """单次 LLM 调用的 token 记录。"""
    timestamp: float = field(default_factory=time.time)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    operation: str = ""  # "chat", "recognize", "judge"


class TokenTracker:
    """Token 用量追踪器（线程安全）。

    累计记录所有 LLM 调用的 token 消耗，
    提供汇总统计和重置功能。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._records: list[TokenRecord] = []
        self._total_input: int = 0
        self._total_output: int = 0
        self._call_count: int = 0

    def record_call(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str = "deepseek-chat",
        operation: str = "",
    ) -> None:
        """记录一次 LLM 调用。

        Args:
            input_tokens: 输入 token 数（prompt）
            output_tokens: 输出 token 数（completion）
            model: 模型名称
            operation: 调用场景标识
        """
        with self._lock:
            record = TokenRecord(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
                operation=operation,
            )
            self._records.append(record)
            self._total_input += input_tokens
            self._total_output += output_tokens
            self._call_count += 1

    def get_summary(self) -> dict:
        """获取累计统计。

        Returns:
            {
                "call_count": int,        # 调用次数
                "total_input_tokens": int,
                "total_output_tokens": int,
                "total_tokens": int,      # input + output
                "avg_input_tokens": float,
                "avg_output_tokens": float,
                "estimated_cost_rmb": float,  # 估算费用（DeepSeek 价格）
            }
        """
        with self._lock:
            avg_in = self._total_input / self._call_count if self._call_count > 0 else 0.0
            avg_out = self._total_output / self._call_count if self._call_count > 0 else 0.0
            total = self._total_input + self._total_output

            # DeepSeek 价格（2024）：￥1/M input tokens, ￥2/M output tokens
            cost = (self._total_input / 1_000_000) * 1.0 + (self._total_output / 1_000_000) * 2.0

            return {
                "call_count": self._call_count,
                "total_input_tokens": self._total_input,
                "total_output_tokens": self._total_output,
                "total_tokens": total,
                "avg_input_tokens": round(avg_in, 1),
                "avg_output_tokens": round(avg_out, 1),
                "estimated_cost_rmb": round(cost, 6),
            }

    def get_records(self) -> list[TokenRecord]:
        """获取所有记录（只读副本）。"""
        with self._lock:
            return list(self._records)

    def reset(self) -> None:
        """重置所有统计。"""
        with self._lock:
            self._records.clear()
            self._total_input = 0
            self._total_output = 0
            self._call_count = 0


# ── 全局单例 ──

_global_tracker: Optional[TokenTracker] = None


def get_global_tracker() -> TokenTracker:
    """获取全局 TokenTracker 单例。"""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = TokenTracker()
    return _global_tracker


def reset_global_tracker() -> None:
    """重置全局 tracker（测试/评测用）。"""
    global _global_tracker
    if _global_tracker is not None:
        _global_tracker.reset()
    _global_tracker = None
