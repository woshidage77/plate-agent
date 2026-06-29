"""PlateAgent LLM API 重试与容错 — Day 11

三层容错机制：
    1. tenacity 自动重试（指数退避：1s → 2s → 4s）
    2. asyncio.timeout 超时保护（默认 30s）
    3. 降级兜底：重试全部失败 → 使用默认值，不阻塞流水线

使用方式：
    from agent.retry import call_llm_with_retry, LLM_CALL_TIMEOUT

    result = await call_llm_with_retry(
        coro_fn=lambda: model.generate(messages, tools),
        fallback_value="降级结果",
        operation="llm_verify",
    )

考试映射：
    - Agent 工程化鲁棒性（面试级加分项）
    - 错误处理 vs 异常传播（FunctionTool 铁律 4 延伸）
    - 降级策略设计模式
"""

import asyncio
import functools
import logging
from typing import Any, Callable, Coroutine, Optional, TypeVar

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_log,
    after_log,
)

from agent.token_tracker import get_global_tracker

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ── 配置常量 ──
MAX_RETRIES = 3                    # 最多重试 3 次
LLM_CALL_TIMEOUT = 30.0            # 单次调用超时（秒）
RETRY_MIN_WAIT = 1.0               # 首次重试等待（秒）
RETRY_MAX_WAIT = 10.0              # 最大重试等待（秒）

# 可重试的异常类型
RETRYABLE_EXCEPTIONS = (
    asyncio.TimeoutError,
    ConnectionError,
    TimeoutError,
    OSError,  # 网络层错误
)


def _is_retryable(exception: BaseException) -> bool:
    """判断异常是否值得重试。

    网络/超时类异常 → 重试（可能是临时波动）
    其他异常（如 API key 错误）→ 不重试，直接传播
    """
    if isinstance(exception, RETRYABLE_EXCEPTIONS):
        return True
    # HTTP 429 (rate limit) / 503 (service unavailable) — openai 包会抛 APIError
    if hasattr(exception, "http_status"):
        http_status = getattr(exception, "http_status", 0)
        if http_status in (429, 502, 503, 504):
            return True
    # 检查状态码字符串形式（兼容不同 openai 版本）
    status_str = str(exception)
    if any(code in status_str for code in ["429", "502", "503", "504"]):
        return True
    return False


_retry_decorator = retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
    retry=retry_if_exception_type(Exception),  # 在 _is_retryable 中过滤
    before=before_log(logger, logging.WARNING),
    after=after_log(logger, logging.DEBUG),
    reraise=True,
)


async def call_llm_with_retry(
    coro_fn: Callable[[], Coroutine[Any, Any, T]],
    fallback_value: Optional[T] = None,
    operation: str = "llm_call",
    timeout: float = LLM_CALL_TIMEOUT,
) -> T:
    """带重试、超时和降级的 LLM API 调用。

    三层保护：
        1. asyncio.timeout(30s)：防止单次调用无限等待
        2. tenacity retry(3次)：指数退避重试临时故障
        3. fallback_value：全部失败后返回降级值，不抛异常

    Args:
        coro_fn: 异步可调用对象（如 lambda: model.generate(...)）
        fallback_value: 降级兜底值（None 表示不降级，直接抛异常）
        operation: 调用场景标识（用于日志和 TokenTracker）
        timeout: 单次调用超时秒数

    Returns:
        正常：LLM 返回结果
        降级：fallback_value

    Raises:
        最后一次重试的异常（仅在 fallback_value 为 None 时）

    示例：
        result = await call_llm_with_retry(
            coro_fn=lambda: model.generate(messages),
            fallback_value={"char": "?", "confidence": 0.0},
            operation="llm_verify",
        )
    """
    last_exception = None
    tracker = get_global_tracker()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with asyncio.timeout(timeout):
                result = await coro_fn()
                # 成功 — 记录 token 用量（如果结果包含 usage 信息）
                _maybe_track_tokens(result, operation, tracker)
                if attempt > 1:
                    logger.info("[%s] 第 %d 次重试成功", operation, attempt)
                return result

        except asyncio.TimeoutError:
            last_exception = asyncio.TimeoutError(
                f"[{operation}] 调用超时 ({timeout}s)，第 {attempt}/{MAX_RETRIES} 次"
            )
            logger.warning("%s", last_exception)
            if attempt < MAX_RETRIES:
                wait_s = min(RETRY_MIN_WAIT * (2 ** (attempt - 1)), RETRY_MAX_WAIT)
                logger.info("[%s] %ds 后重试...", operation, wait_s)
                await asyncio.sleep(wait_s)

        except Exception as e:
            last_exception = e
            if _is_retryable(e):
                logger.warning(
                    "[%s] 可重试异常 (第 %d/%d 次): %s",
                    operation, attempt, MAX_RETRIES, e,
                )
                if attempt < MAX_RETRIES:
                    wait_s = min(RETRY_MIN_WAIT * (2 ** (attempt - 1)), RETRY_MAX_WAIT)
                    await asyncio.sleep(wait_s)
            else:
                # 不可重试的异常（如 API key 错误）— 不重试
                logger.error("[%s] 不可重试异常: %s", operation, e)
                if fallback_value is not None:
                    logger.warning("[%s] 降级到 fallback_value", operation)
                    return fallback_value
                raise

    # 全部重试失败
    if fallback_value is not None:
        logger.error(
            "[%s] 全部 %d 次重试失败，降级: %s",
            operation, MAX_RETRIES, last_exception,
        )
        return fallback_value

    raise last_exception  # type: ignore[misc]


def _maybe_track_tokens(result: Any, operation: str, tracker) -> None:
    """尝试从 LLM 返回结果中提取 token usage 并记录。"""
    try:
        # 兼容 openai response 对象
        if hasattr(result, "usage"):
            usage = result.usage
            input_tokens = getattr(usage, "prompt_tokens", 0)
            output_tokens = getattr(usage, "completion_tokens", 0)
            if input_tokens or output_tokens:
                tracker.record_call(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    operation=operation,
                )
    except Exception:
        pass  # token 追踪失败不影响主流程


async def safe_llm_call(
    coro_fn: Callable[[], Coroutine[Any, Any, T]],
    fallback_value: T,
    operation: str = "llm_call",
) -> T:
    """最简接口：调用 LLM，失败返回降级值，永不抛异常。

    适用于对可用性要求高于准确性的场景（如 LLM 复核节点）。
    """
    try:
        return await call_llm_with_retry(
            coro_fn=coro_fn,
            fallback_value=fallback_value,
            operation=operation,
        )
    except Exception as e:
        logger.error("[%s] safe_llm_call 最终异常（不应到达）: %s", operation, e)
        return fallback_value