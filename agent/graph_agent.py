"""PlateAgent GraphAgent — 6节点确定性流水线 + 条件路由

Day 11 增强（P1）：
    - human_review_node：极低置信度 (< 0.5) 触发人工确认（interrupt 模式）
    - recognize_node：Parallel 并行 SVM（asyncio.gather）

图结构（Day 11 最终版）：
    preprocess → locate → segment → recognize
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
              needs_human=true    needs_verify=true    otherwise
                    │                    │                    │
              human_review         llm_verify           format_output
                    │                    │
              format_output         format_output
"""

from typing import Any, Dict

from trpc_agent_sdk.agents import LlmAgent
from trpc_agent_sdk.dsl.graph import (
    GraphAgent,
    NodeConfig,
    STATE_KEY_LAST_RESPONSE,
    STATE_KEY_USER_INPUT,
    StateGraph,
)
from trpc_agent_sdk.models import OpenAIModel
from trpc_agent_sdk.tools import FunctionTool

from .config import get_model_config
from .graph_state import PlateState
from .graph_nodes import (
    preprocess_node,
    locate_node,
    segment_node,
    recognize_node,
    human_review_node,
    llm_verify_node,
    format_output_node,
)
from .tools.preprocess import (
    tool_gaussian_blur,
    tool_grayscale,
    tool_binarize_otsu,
    tool_edge_detect_canny,
    tool_affine_correct,
)
from .tools.locate import tool_morphology_locate, tool_color_locate
from .tools.segment import tool_vertical_projection
from .tools.recognize import tool_svm_predict, tool_llm_verify
from .tools.knowledge import tool_search_blacklist, tool_query_history, tool_lookup_confusion


# ── 聊天对话 Agent ──
def _create_chat_agent() -> LlmAgent:
    """创建对话入口 LlmAgent。"""
    api_key, base_url, model_name = get_model_config()
    model = OpenAIModel(model_name=model_name, api_key=api_key, base_url=base_url)

    tools = [
        FunctionTool(tool_gaussian_blur),
        FunctionTool(tool_grayscale),
        FunctionTool(tool_binarize_otsu),
        FunctionTool(tool_edge_detect_canny),
        FunctionTool(tool_affine_correct),
        FunctionTool(tool_morphology_locate),
        FunctionTool(tool_color_locate),
        FunctionTool(tool_vertical_projection),
        FunctionTool(tool_svm_predict),
        FunctionTool(tool_llm_verify),
        FunctionTool(tool_search_blacklist),
        FunctionTool(tool_lookup_confusion),
        FunctionTool(tool_query_history),
    ]

    return LlmAgent(
        name="plate_chat",
        description="PlateAgent 对话入口，处理车牌识别请求和闲聊",
        model=model,
        instruction="""你是 PlateAgent 对话助手。
如果用户发来车牌图片路径，引导用户使用识别流水线。
对于一般性问题和闲聊，直接简洁回复。""",
        tools=tools,
    )


# ── 条件路由函数 ──

def _route_after_recognize(state: PlateState) -> str:
    """Day 11 三级路由：根据置信度分派到不同路径。

    State 字段：
        recognize_chars[i].confidence < 0.5  → human_review (中断人工确认)
        needs_llm_verify=True                → llm_verify   (LLM 复核)
        otherwise                            → format_output (直接输出)

    这是犀牛鸟考点「条件路由」的完整展示——
    不是简单的 if/else，而是基于 state 的多分支图路由。
    """
    recognize_chars = state.get("recognize_chars", [])

    # 检查是否有极低置信度字符（< 0.5）
    has_very_low = any(
        r.get("confidence", 0.0) < 0.5 for r in recognize_chars
    )
    if has_very_low:
        return "human"

    # 检查是否需要 LLM 复核（0.5 ~ 0.85）
    if state.get("needs_llm_verify", False):
        return "verify"

    return "output"


# ── 图构建 ──
def _build_recognition_graph() -> StateGraph:
    """构建车牌识别 6 节点流水线图（Day 11 最终版）。

    节点：preprocess → locate → segment → recognize
            ├── human_review (极低置信度)
            ├── llm_verify   (低置信度)
            └── format_output (高置信度)
    """
    graph = StateGraph(PlateState)

    # ── 添加节点 ──
    graph.add_node(
        "preprocess", preprocess_node,
        config=NodeConfig(name="preprocess",
                         description="高斯滤波→灰度→二值→Canny→仿射矫正"),
    )
    graph.add_node(
        "locate", locate_node,
        config=NodeConfig(name="locate",
                         description="形态学粗定位 + HSV 精定位"),
    )
    graph.add_node(
        "segment", segment_node,
        config=NodeConfig(name="segment",
                         description="垂直投影字符分割"),
    )
    graph.add_node(
        "recognize", recognize_node,
        config=NodeConfig(name="recognize",
                         description="Parallel SVM 并行识别 + 置信度评估"),
    )
    # Day 11 新增：人工确认节点
    graph.add_node(
        "human_review", human_review_node,
        config=NodeConfig(name="human_review",
                         description="极低置信度 (<0.5) 触发人工确认 — interrupt 模式"),
    )
    graph.add_node(
        "llm_verify", llm_verify_node,
        config=NodeConfig(name="llm_verify",
                         description="LLM 二次校验（含 retry + timeout + 降级）"),
    )
    graph.add_node(
        "format_output", format_output_node,
        config=NodeConfig(name="format_output",
                         description="拼接结果 + 黑名单 + [?]标注"),
    )

    # ── 连接边 ──
    graph.set_entry_point("preprocess")
    graph.set_finish_point("format_output")

    graph.add_edge("preprocess", "locate")
    graph.add_edge("locate", "segment")
    graph.add_edge("segment", "recognize")

    # Day 11: 三级条件路由
    graph.add_conditional_edges(
        "recognize",
        _route_after_recognize,
        {
            "human":  "human_review",   # 极低置信度 → 人工确认
            "verify": "llm_verify",     # 低置信度   → LLM 复核
            "output": "format_output",  # 高置信度   → 直接输出
        },
    )
    graph.add_edge("human_review", "format_output")
    graph.add_edge("llm_verify", "format_output")

    return graph


def create_graph_agent() -> GraphAgent:
    """创建 PlateAgent GraphAgent 完整实例（Day 11 版本）。

    6 节点流水线 + 三级条件路由 + Parallel SVM + 人工确认 + 容错
    """
    graph = _build_recognition_graph()
    return GraphAgent(
        name="plate_recognition",
        description="车牌识别流水线 v2：预处理→定位→分割→Parallel SVM→{人工/LLM}确认→输出",
        graph=graph.compile(),
    )


# 模块级导出
root_agent = _create_chat_agent()
recognition_agent = create_graph_agent()