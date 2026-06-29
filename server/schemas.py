"""PlateAgent API Schemas — Pydantic 请求/响应模型"""

from typing import Optional
from pydantic import BaseModel, Field


# ── 请求模型 ──

class ChatRequest(BaseModel):
    """多轮对话请求。

    支持两种模式：
        - 新会话：不传 session_id，服务端自动生成
        - 继续会话：传入已有 session_id，延续上下文
    """
    message: str = Field(..., description="用户消息", min_length=1, max_length=2000)
    user_id: str = Field(default="anonymous", description="用户标识")
    session_id: Optional[str] = Field(default=None, description="会话ID，不传则新建")
    image_path: Optional[str] = Field(default=None, description="可选：图片路径")


class RecognizeRequest(BaseModel):
    """单张车牌识别请求。

    直接走 GraphAgent 识别流水线，不走闲聊入口。
    """
    image_path: str = Field(..., description="车牌图片路径")
    user_id: str = Field(default="anonymous", description="用户标识")
    session_id: Optional[str] = Field(default=None, description="会话ID")


class HistoryRequest(BaseModel):
    """历史查询请求。"""
    user_id: str = Field(..., description="用户标识")
    session_id: Optional[str] = Field(default=None, description="会话ID，不传则列出所有")


# ── SSE 事件模型 ──

class SSEEvent(BaseModel):
    """SSE 流式事件的基础模型。

    所有 SSE 推送都遵循此格式：type 区分事件类型，data 携带载荷。
    """
    type: str = Field(..., description="事件类型")
    data: dict = Field(default_factory=dict, description="事件载荷")


# ── 响应模型 ──

class ChatResponse(BaseModel):
    """非流式响应（兜底用）。"""
    session_id: str
    reply: str
    tool_calls: list[dict] = Field(default_factory=list)


class RecognizeResponse(BaseModel):
    """识别结果响应。"""
    session_id: str
    plate_number: str
    confidence: float = 0.0
    blacklist_hit: bool = False
    blacklist_records: list[dict] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """健康检查响应。"""
    status: str = "ok"
    version: str = "1.0.0"
    agent: str = "plate_recognition"


class ErrorResponse(BaseModel):
    """错误响应。"""
    error: str
    detail: Optional[str] = None
