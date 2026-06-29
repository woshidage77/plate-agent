"""PlateAgent 对话入口 - LlmAgent 定义（含全部 10 FunctionTool）"""

from trpc_agent_sdk.agents import LlmAgent
from trpc_agent_sdk.models import OpenAIModel
from trpc_agent_sdk.tools import FunctionTool

from .config import get_model_config

# 预处理工具
from .tools.preprocess import (
    tool_gaussian_blur,
    tool_grayscale,
    tool_binarize_otsu,
    tool_edge_detect_canny,
    tool_affine_correct,
)
# 定位工具
from .tools.locate import (
    tool_morphology_locate,
    tool_color_locate,
)
# 分割工具
from .tools.segment import tool_vertical_projection
# 识别工具
from .tools.recognize import (
    tool_svm_predict,
    tool_llm_verify,
)
# 知识库工具
from .tools.knowledge import (
    tool_search_blacklist,
    tool_query_history,
)


INSTRUCTION = """你是 PlateAgent，一个基于 OpenCV + DeepSeek 的车牌识别智能体。

你可以调用以下工具完成车牌识别全流程：

**预处理阶段**：
- tool_gaussian_blur: 对图像进行高斯滤波降噪
- tool_grayscale: 将图像转为灰度图
- tool_binarize_otsu: 使用 OTSU 算法二值化
- tool_edge_detect_canny: Canny 算子边缘检测
- tool_affine_correct: 仿射变换倾斜矫正

**定位阶段**：
- tool_morphology_locate: 数学形态学提取候选轮廓
- tool_color_locate: HSV 颜色空间精确定位

**分割阶段**：
- tool_vertical_projection: 垂直投影法字符分割

**识别阶段**：
- tool_svm_predict: SVM 字符识别（返回置信度）
- tool_llm_verify: 对低置信度字符 LLM 二次校验

**查询阶段**：
- tool_search_blacklist: 违章黑名单 RAG 检索
- tool_query_history: 跨会话历史识别记录查询

当用户发送车牌图片时，按顺序调用预处理→定位→分割→识别的完整流水线。
识别完成后，主动调用黑名单查询和写入历史记录。

请用中文回复，保持简洁专业。
"""


def create_plate_agent() -> LlmAgent:
    """创建 PlateAgent，注册全部 10 个 FunctionTool"""
    api_key, base_url, model_name = get_model_config()

    model = OpenAIModel(
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
    )

    tools = [
        # 预处理 (5)
        FunctionTool(tool_gaussian_blur),
        FunctionTool(tool_grayscale),
        FunctionTool(tool_binarize_otsu),
        FunctionTool(tool_edge_detect_canny),
        FunctionTool(tool_affine_correct),
        # 定位 (2)
        FunctionTool(tool_morphology_locate),
        FunctionTool(tool_color_locate),
        # 分割 (1)
        FunctionTool(tool_vertical_projection),
        # 识别 (2)
        FunctionTool(tool_svm_predict),
        FunctionTool(tool_llm_verify),
        # 知识库 (2)
        FunctionTool(tool_search_blacklist),
        FunctionTool(tool_query_history),
    ]

    agent = LlmAgent(
        name="plate_assistant",
        description="车牌识别智能助手，支持 OpenCV 全流程 + LLM 二次校验 + 黑名单 RAG 检索",
        model=model,
        instruction=INSTRUCTION,
        tools=tools,
    )
    return agent


root_agent = create_plate_agent()
