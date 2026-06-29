"""PlateAgent Graph 节点 — 6节点确定性流水线 + 条件路由

Day 11 增强（P0）：
    - llm_verify_node：safe_llm_call 三层容错（重试 + 超时 + 降级）
    - format_output_node：低置信度 [?] 标注

Day 11 增强（P1）：
    - recognize_node：asyncio.gather 并行识别（Parallel 考点）
    - human_review_node：interrupt 人工确认（interrupt/resume 考点）
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

from trpc_agent_sdk.dsl.graph import (
    STATE_KEY_LAST_RESPONSE,
    AsyncEventWriter,
)

from .graph_state import PlateState
from .telemetry import trace_node, trace_block
from .retry import safe_llm_call
from .tools.preprocess import (
    tool_gaussian_blur,
    tool_grayscale,
    tool_binarize_otsu,
    tool_edge_detect_canny,
    tool_affine_correct,
)
from .tools.locate import (
    tool_morphology_locate,
    tool_color_locate,
)
from .tools.segment import tool_vertical_projection
from .tools.recognize import tool_svm_predict, tool_llm_verify
from .tools.knowledge import tool_search_blacklist, tool_lookup_confusion

# ── 线程池（用于将同步 SVM 预测转为异步，实现并行） ──
_svm_executor = ThreadPoolExecutor(max_workers=8)


# ═══════════════════════════════════════════════
# 预处理节点
# ═══════════════════════════════════════════════
@trace_node("preprocess")
async def preprocess_node(state: PlateState, async_writer: AsyncEventWriter) -> Dict[str, Any]:
    img = state.get("image_path", "")
    if not img:
        return {"preprocess_output": "", STATE_KEY_LAST_RESPONSE: "错误：未提供图像路径"}

    await async_writer.write_text("[预处理] 开始...\n")

    steps = [
        ("高斯滤波", lambda p: tool_gaussian_blur(p)),
        ("灰度化",   lambda p: tool_grayscale(p)),
        ("二值化",   lambda p: tool_binarize_otsu(p)),
        ("Canny边缘", lambda p: tool_edge_detect_canny(p)),
        ("仿射矫正", lambda p: tool_affine_correct(p)),
    ]

    current_path = img
    for step_name, step_fn in steps:
        await async_writer.write_text(f"  {step_name}... ")
        result = step_fn(current_path)
        if result.get("status") != "ok":
            await async_writer.write_text(f"失败: {result.get('message', '')}\n")
            return {"preprocess_output": current_path}
        current_path = result["output_path"]
        await async_writer.write_text("完成\n")

    await async_writer.write_text(f"[预处理] 完成 → {current_path}\n")
    return {"preprocess_output": current_path}


# ═══════════════════════════════════════════════
# 定位节点
# ═══════════════════════════════════════════════
@trace_node("locate")
async def locate_node(state: PlateState, async_writer: AsyncEventWriter) -> Dict[str, Any]:
    image_path = state.get("preprocess_output", "")
    if not image_path:
        return {"locate_output": "", STATE_KEY_LAST_RESPONSE: "错误：预处理未产出图像"}

    await async_writer.write_text("[定位] 开始...\n")

    await async_writer.write_text("  形态学定位... ")
    morph_result = tool_morphology_locate(image_path)
    if morph_result.get("status") != "ok":
        await async_writer.write_text(f"失败\n")
        return {"locate_output": image_path}

    candidates = morph_result.get("candidates", [])
    await async_writer.write_text(f"候选 {len(candidates)} 个\n")

    if not candidates:
        await async_writer.write_text("[定位] 未找到候选区域\n")
        return {"locate_output": image_path}

    await async_writer.write_text("  HSV精定位... ")
    color_result = tool_color_locate(image_path, candidates)
    if color_result.get("status") != "ok":
        await async_writer.write_text(f"失败\n")
        return {"locate_output": image_path}

    locate_output = color_result["output_path"]
    plate_color = color_result.get("plate_color", "unknown")
    await async_writer.write_text(f"完成（颜色: {plate_color}）\n")
    await async_writer.write_text(f"[定位] 完成 → {locate_output}\n")
    return {"locate_output": locate_output}


# ═══════════════════════════════════════════════
# 分割节点
# ═══════════════════════════════════════════════
@trace_node("segment")
async def segment_node(state: PlateState, async_writer: AsyncEventWriter) -> Dict[str, Any]:
    image_path = state.get("locate_output", "")
    if not image_path:
        return {"segment_chars": [], STATE_KEY_LAST_RESPONSE: "错误：定位未产出车牌区域"}

    await async_writer.write_text("[分割] 垂直投影... ")
    proj_result = tool_vertical_projection(image_path)
    if proj_result.get("status") != "ok":
        await async_writer.write_text(f"失败\n")
        return {"segment_chars": []}

    char_images = proj_result.get("char_images", [])
    char_count = proj_result.get("char_count", 0)
    await async_writer.write_text(f"分割出 {char_count} 个字符\n")
    return {"segment_chars": char_images}


# ═══════════════════════════════════════════════
# 识别节点 — Day 11 P1: Parallel 并行识别
# ═══════════════════════════════════════════════
@trace_node("recognize")
async def recognize_node(state: PlateState, async_writer: AsyncEventWriter) -> Dict[str, Any]:
    """SVM 字符识别 — 使用 asyncio.gather 并行识别所有字符。

    Day 11 增强：
        之前：for char_path in char_images → 串行，7 字符 = 7x 耗时
        现在：asyncio.gather([predict(c) for c in chars]) → 并行，7 字符 ≈ 1x 耗时

    考试映射：Chain/Parallel/Cycle → Parallel 真实案例
    """
    char_images = state.get("segment_chars", [])
    if not char_images:
        return {"recognize_chars": [], "needs_llm_verify": False,
                STATE_KEY_LAST_RESPONSE: "错误：分割未产出字符图像"}

    await async_writer.write_text(
        f"[识别] Parallel SVM 识别 {len(char_images)} 个字符...\n"
    )

    # ── Day 11: Parallel — asyncio.gather 并发执行 ──
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(_svm_executor, tool_svm_predict, path)
        for path in char_images
    ]
    with trace_block("parallel_svm_predict", {"char_count": len(char_images)}):
        results = await asyncio.gather(*tasks)

    needs_verify = False
    for i, svm_result in enumerate(results):
        char = svm_result.get("char", "?")
        confidence = svm_result.get("confidence", 0.0)
        char_needs = svm_result.get("needs_verify", False)

        await async_writer.write_text(f"  字符{i}: {char} (置信度 {confidence:.2f})")
        if char_needs:
            await async_writer.write_text(" [需复核]")
            needs_verify = True
        await async_writer.write_text("\n")

    if needs_verify:
        await async_writer.write_text("[识别] 有低置信度字符，将触发 LLM 复核\n")

    return {
        "recognize_chars": results,
        "needs_llm_verify": needs_verify,
    }


# ═══════════════════════════════════════════════
# 人工确认节点 — Day 11 P1: interrupt/resume
# ═══════════════════════════════════════════════
@trace_node("human_review")
async def human_review_node(state: PlateState, async_writer: AsyncEventWriter) -> Dict[str, Any]:
    """人工确认节点 —— 对极低置信度字符请求人工介入。

    触发条件：任一字符 SVM 置信度 < 0.5
    行为：
        1. 列出需要确认的字符
        2. 通过 async_writer 向用户发送确认请求
        3. 设置 awaiting_human=True，暂停流水线
        4. 用户在下一轮输入确认/修正 → 继续

    考试映射：GraphAgent 进阶 → interrupt/resume 机制

    注意：完整 interrupt 需使用 tRPC-Agent 的 interrupt() API
          （from trpc_agent_sdk.dsl.graph import interrupt）
          当前实现使用 state flag + async_writer 模式，
          展示 interrupt/resume 的设计思路。
    """
    recognize_chars = state.get("recognize_chars", [])
    if not recognize_chars:
        return {}

    # 检查是否需要人工确认
    low_conf_chars = []
    for i, svm_result in enumerate(recognize_chars):
        confidence = svm_result.get("confidence", 0.0)
        if confidence < 0.5:
            low_conf_chars.append({
                "index": i,
                "svm_char": svm_result.get("char", "?"),
                "confidence": confidence,
            })

    if not low_conf_chars:
        return {}  # 无需人工确认，继续

    await async_writer.write_text("\n" + "=" * 40 + "\n")
    await async_writer.write_text("⚠ 人工确认请求\n")
    await async_writer.write_text("-" * 40 + "\n")
    await async_writer.write_text("以下字符识别置信度极低 (< 0.5)，请确认：\n\n")

    for item in low_conf_chars:
        await async_writer.write_text(
            f"  位置{item['index']}: SVM 识别为 '{item['svm_char']}' "
            f"(置信度 {item['confidence']:.2f})\n"
        )

    await async_writer.write_text("\n请回复修正后的完整车牌号，或输入 'skip' 跳过确认。\n")
    await async_writer.write_text("=" * 40 + "\n")

    # ── interrupt 模式说明 ──
    # 完整实现中，此处调用：
    #   from trpc_agent_sdk.dsl.graph import interrupt
    #   human_response = interrupt({
    #       "type": "human_review",
    #       "low_confidence_chars": low_conf_chars,
    #       "message": "请确认以上字符"
    #   })
    # interrupt() 会暂停图执行，等待用户响应后恢复

    return {
        "awaiting_human": True,
        "low_confidence_chars": low_conf_chars,
        STATE_KEY_LAST_RESPONSE: (
            f"⚠ 人工确认：{len(low_conf_chars)} 个字符需要确认"
        ),
    }


# ═══════════════════════════════════════════════
# LLM 复核节点（Day 5 RAG + Day 11 容错）
# ═══════════════════════════════════════════════
@trace_node("llm_verify")
async def llm_verify_node(state: PlateState, async_writer: AsyncEventWriter) -> Dict[str, Any]:
    """对低置信度字符进行 LLM 二次校验。

    Day 11 增强：safe_llm_call 三层容错（重试 + 超时 + 降级）
    """
    recognize_chars = state.get("recognize_chars", [])
    if not recognize_chars:
        return {"final_plate": ""}

    await async_writer.write_text("[LLM复核] 开始...\n")

    final_chars = []
    for i, svm_result in enumerate(recognize_chars):
        svm_char = svm_result.get("char", "?")
        confidence = svm_result.get("confidence", 0.0)

        if svm_result.get("needs_verify"):
            confusion_info = ""
            try:
                confusion_result = tool_lookup_confusion(svm_char)
                if confusion_result.get("status") == "ok" and confusion_result.get("candidates"):
                    candidates = confusion_result["candidates"]
                    confusion_info = (
                        "可能的混淆字符: "
                        + ", ".join(c["char"] for c in candidates)
                    )
                    await async_writer.write_text(
                        f"  字符{i}: SVM={svm_char} conf={confidence:.2f}"
                        f" → 混淆候选: {confusion_info}\n"
                    )
            except Exception:
                pass

            await async_writer.write_text(f"  LLM 复核中... ")

            # Day 11: safe_llm_call 包装
            verified = await safe_llm_call(
                coro_fn=lambda: _do_llm_verify(svm_result),
                fallback_value=svm_result,
                operation=f"llm_verify_char_{i}",
            )

            final_char = verified.get("final_char", svm_char)
            verify_status = " (降级)" if verified is svm_result else ""
            await async_writer.write_text(f"→ {final_char}{verify_status}\n")
        else:
            final_char = svm_char
        final_chars.append(final_char)

    plate = "".join(final_chars)
    await async_writer.write_text(f"[LLM复核] 完成 → 车牌号: {plate}\n")
    return {"final_plate": plate}


async def _do_llm_verify(svm_result: dict) -> dict:
    """执行单次 LLM 复核调用（供 safe_llm_call 的重试机制包装）。"""
    return tool_llm_verify("", svm_result)


# ═══════════════════════════════════════════════
# 格式化输出节点
# ═══════════════════════════════════════════════
@trace_node("format_output")
async def format_output_node(state: PlateState, async_writer: AsyncEventWriter) -> Dict[str, Any]:
    """将最终车牌号格式化为用户可读的响应。

    Day 11 增强：低置信度字符 [?] 标注
    """
    plate = state.get("final_plate", "")

    if not plate:
        recognize_chars = state.get("recognize_chars", [])
        if recognize_chars:
            plate = "".join(r.get("char", "?") for r in recognize_chars)
        else:
            plate = "识别失败"

    # Day 11: 低置信度标注
    recognize_chars = state.get("recognize_chars", [])
    annotated = ""
    for r in recognize_chars:
        ch = r.get("char", "?")
        conf = r.get("confidence", 0.0)
        if conf < 0.5:
            annotated += f"{ch}[?]"
        else:
            annotated += ch
    plate_display = annotated if annotated else plate

    # 黑名单查询
    blacklist_result = tool_search_blacklist(plate)
    blacklist_msg = ""
    if blacklist_result.get("hit"):
        records = blacklist_result.get("records", [])
        for r in records[:3]:
            blacklist_msg += (
                f"\n  [{r['type']}] {r['plate_number']}"
                f" — {r['description']}（{r['status']}）"
            )
        blacklist_msg = f"\n\n⚠ 黑名单命中（{len(records)}条）：{blacklist_msg}"

    final_output = f"识别结果：{plate_display}{blacklist_msg}"

    await async_writer.write_text(f"\n{'='*40}\n{final_output}\n{'='*40}\n")

    return {STATE_KEY_LAST_RESPONSE: final_output}