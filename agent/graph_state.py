"""PlateAgent Graph State — 6节点流水线的共享数据容器

GraphAgent 中每个节点都接收 State，返回 dict 增量更新。
State 是节点间唯一的通信方式——没有全局变量、没有共享内存。

Day 11 新增：awaiting_human, low_confidence_chars（interrupt 模式）
"""

from typing import Any

from trpc_agent_sdk.dsl.graph import State


class PlateState(State):
    """车牌识别流水线的完整状态。

    Day 11 最终版字段：
        image_path → preprocess_output → locate_output
        → segment_chars → recognize_chars →
        {human_review | llm_verify} → final_plate
    """

    # 输入
    image_path: str = ""

    # 预处理
    preprocess_output: str = ""

    # 定位
    locate_output: str = ""

    # 分割
    segment_chars: list[str] = []

    # 识别
    recognize_chars: list[dict[str, Any]] = []
    """SVM 识别结果列表
    [{"char": "京", "confidence": 0.92, "needs_verify": False}, ...]"""

    needs_llm_verify: bool = False
    """是否有字符置信度 < 0.85"""

    # Day 11: interrupt 模式字段
    awaiting_human: bool = False
    """是否需要人工确认（置信度 < 0.5 触发）"""

    low_confidence_chars: list[dict[str, Any]] = []
    """极低置信度字符列表
    [{"index": 2, "svm_char": "5", "confidence": 0.32}, ...]"""

    # 最终结果
    final_plate: str = ""