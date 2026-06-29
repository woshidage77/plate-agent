"""PlateAgent OpenTelemetry 可观测性 — Day 9

提供：
    1. 全链路追踪（tracing）：每个 GraphAgent 节点一个 span
    2. 自动注入：FastAPI 自动为每个 HTTP 请求创建 span
    3. 控制台导出：开发阶段输出到 stdout，生产可切 OTLP/gRPC

使用：
    from agent.telemetry import init_telemetry, get_tracer, trace_node

    init_telemetry()                    # 初始化 SDK
    tracer = get_tracer("plate_agent")  # 获取 tracer

    @trace_node("preprocess")           # 装饰器：自动创建 span
    async def preprocess_node(state, writer):
        ...

架构：
    TracerProvider
      └── ConsoleSpanExporter（开发）/ OTLPSpanExporter（生产）
      └── SimpleSpanProcessor（同步导出）
"""

import os
import time
import logging
from contextlib import contextmanager
from functools import wraps
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.trace import Status, StatusCode, SpanKind

logger = logging.getLogger(__name__)

# 模块级状态
_initialized = False
_tracer_cache: dict[str, trace.Tracer] = {}


def init_telemetry(
    service_name: str = "plate-agent",
    service_version: str = "1.0.0",
    console_export: bool = True,
    otlp_endpoint: Optional[str] = None,
) -> None:
    """初始化 OpenTelemetry SDK。

    在应用启动时调用一次。幂等——重复调用不重复初始化。

    Args:
        service_name: 服务名称（出现在 trace 中）
        service_version: 服务版本
        console_export: 是否输出到控制台
        otlp_endpoint: OTLP collector 地址（如 "http://localhost:4318/v1/traces"）
    """
    global _initialized
    if _initialized:
        return

    # 创建 Resource（标识服务）
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
    })

    # 创建 TracerProvider
    provider = TracerProvider(resource=resource)

    # 控制台导出器（开发用）
    if console_export:
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(console_exporter))

    # OTLP 导出器（生产用）
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info("OTLP exporter 已配置: %s", otlp_endpoint)
        except Exception as e:
            logger.warning("OTLP exporter 配置失败: %s", e)

    # 设置为全局 TracerProvider
    trace.set_tracer_provider(provider)
    _initialized = True
    logger.info(
        "OpenTelemetry 已初始化: service=%s, console=%s, otlp=%s",
        service_name, console_export, bool(otlp_endpoint),
    )


def get_tracer(name: str = "plate_agent") -> trace.Tracer:
    """获取或创建 Tracer 实例。

    Args:
        name: Tracer 名称

    Returns:
        trace.Tracer 实例
    """
    if name not in _tracer_cache:
        _tracer_cache[name] = trace.get_tracer(name)
    return _tracer_cache[name]


def trace_node(node_name: str, attributes: Optional[dict] = None):
    """GraphAgent 节点的 trace 装饰器。

    自动为每个节点函数创建 span，记录：
        - 节点名称
        - 执行耗时
        - 成功/失败状态
        - 自定义属性

    用法：
        @trace_node("preprocess")
        async def preprocess_node(state, writer):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer("plate_agent.graph")
            span_attrs = {
                "node.name": node_name,
                "node.type": "graph_agent",
            }
            if attributes:
                span_attrs.update(attributes)

            with tracer.start_as_current_span(
                f"graph.{node_name}",
                kind=SpanKind.INTERNAL,
                attributes=span_attrs,
            ) as span:
                start = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    span.set_attribute("duration_ms", round(elapsed_ms, 2))
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    span.set_attribute("duration_ms", round(elapsed_ms, 2))
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        return wrapper
    return decorator


@contextmanager
def trace_block(name: str, attributes: Optional[dict] = None):
    """手动创建 trace span 的上下文管理器。

    用于不方便用装饰器的场景（如工具函数内部）。

    用法：
        with trace_block("svm_predict", {"char_index": 3}):
            result = tool_svm_predict(path)
    """
    tracer = get_tracer("plate_agent.graph")
    span_attrs = {"span.name": name}
    if attributes:
        span_attrs.update(attributes)

    with tracer.start_as_current_span(name, attributes=span_attrs) as span:
        start = time.perf_counter()
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            span.set_attribute("duration_ms", round(elapsed_ms, 2))
