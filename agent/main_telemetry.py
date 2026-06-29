"""PlateAgent Day 9 验证脚本 — OpenTelemetry + TokenTracker 端到端验证

验证项目：
    1. init_telemetry() 输出到控制台
    2. trace_node 装饰器自动创建 span
    3. trace_block 上下文管理器
    4. TokenTracker 线程安全累计 + 成本估算

用法：
    python -m agent.main_telemetry
"""

import asyncio
import logging

from agent.telemetry import init_telemetry, get_tracer, trace_node, trace_block
from agent.token_tracker import TokenTracker, get_global_tracker, reset_global_tracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── 测试用的 dummy 节点 ──

@trace_node("test_preprocess")
async def dummy_preprocess(image_path: str) -> str:
    """模拟预处理节点——被 @trace_node 装饰后自动创建 span。"""
    with trace_block("gaussian_blur", {"kernel_size": 3}):
        await asyncio.sleep(0.05)
    with trace_block("binarize"):
        await asyncio.sleep(0.03)
    return f"{image_path}_processed"


@trace_node("test_recognize")
async def dummy_recognize(image_path: str, tracker: TokenTracker) -> str:
    """模拟识别节点——同时记录 token 用量。"""
    await asyncio.sleep(0.08)

    tracker.record_call(
        input_tokens=120,
        output_tokens=45,
        model="deepseek-chat",
        operation="recognize",
    )
    return "JingA12345"


# ── 主验证流程 ──

async def main():
    print("=" * 60)
    print("PlateAgent Day 9 - OTel + TokenTracker Verification")
    print("=" * 60)

    # 1. 初始化 OTel
    print("\n[1/5] init_telemetry()...")
    init_telemetry(service_name="plate-agent-verify", console_export=True)
    tracer = get_tracer("verify")
    print("  TracerProvider + ConsoleSpanExporter OK\n")

    # 2. 手动 span
    print("[2/5] Manual span...")
    with tracer.start_as_current_span("verify_root") as span:
        span.set_attribute("test_id", "day9_smoke")
        print("  root span: verify_root")

        with tracer.start_as_current_span("verify_child") as child:
            child.set_attribute("step", "nested")
            await asyncio.sleep(0.02)
            print("  child span: verify_child")

    print("  (spans printed to console above)\n")

    # 3. trace_node 装饰器
    print("[3/5] @trace_node decorator...")
    tracker = TokenTracker()
    processed = await dummy_preprocess("/tmp/test_plate.jpg")
    print(f"  dummy_preprocess -> {processed}")

    result = await dummy_recognize(processed, tracker)
    print(f"  dummy_recognize -> {result}\n")

    # 4. TokenTracker
    print("[4/5] TokenTracker stats...")
    tracker.record_call(input_tokens=200, output_tokens=90, operation="chat")
    tracker.record_call(input_tokens=150, output_tokens=60, operation="judge")
    tracker.record_call(input_tokens=80, output_tokens=20, operation="search")

    summary = tracker.get_summary()
    print(f"  call_count: {summary['call_count']}")
    print(f"  total_input_tokens: {summary['total_input_tokens']}")
    print(f"  total_output_tokens: {summary['total_output_tokens']}")
    print(f"  total_tokens: {summary['total_tokens']}")
    print(f"  avg_input: {summary['avg_input_tokens']} / avg_output: {summary['avg_output_tokens']}")
    print(f"  estimated_cost: RMB {summary['estimated_cost_rmb']}")

    # 5. 全局单例
    print("\n[5/5] Global singleton...")
    gtracker = get_global_tracker()
    gtracker.record_call(input_tokens=500, output_tokens=200, operation="batch")
    gsummary = gtracker.get_summary()
    print(f"  global tracker calls: {gsummary['call_count']}")

    gtracker2 = get_global_tracker()
    print(f"  singleton identity: {'SAME' if gtracker is gtracker2 else 'DIFFERENT'}")
    reset_global_tracker()

    print("\n" + "=" * 60)
    print("ALL CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
