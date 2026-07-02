"""PlateAgent Graph nodes - 6-node pipeline + Tesseract OCR v2"""
import asyncio
import logging
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
from .tools.recognize import tool_tesseract_ocr, tool_svm_predict, tool_llm_verify
from .tools.knowledge import tool_search_blacklist, tool_lookup_confusion

logger = logging.getLogger(__name__)


# Preprocess
@trace_node("preprocess")
async def preprocess_node(state: PlateState, async_writer: AsyncEventWriter) -> Dict[str, Any]:
    img = state.get("image_path", "")
    if not img:
        return {"preprocess_output": "", STATE_KEY_LAST_RESPONSE: "Error: no image path"}

    await async_writer.write_text("[Preprocess] starting...\n")

    steps = [
        ("Gaussian blur", lambda p: tool_gaussian_blur(p)),
        ("Grayscale",     lambda p: tool_grayscale(p)),
        ("Binarize",      lambda p: tool_binarize_otsu(p)),
        ("Canny edges",   lambda p: tool_edge_detect_canny(p)),
        ("Affine correct",lambda p: tool_affine_correct(p)),
    ]

    current_path = img
    for step_name, step_fn in steps:
        await async_writer.write_text(f"  {step_name}... ")
        result = step_fn(current_path)
        if result.get("status") != "ok":
            await async_writer.write_text(f"failed: {result.get('message', '')}\n")
            return {"preprocess_output": current_path}
        current_path = result["output_path"]
        await async_writer.write_text("done\n")

    await async_writer.write_text(f"[Preprocess] done -> {current_path}\n")
    return {"preprocess_output": current_path}


# Locate
@trace_node("locate")
async def locate_node(state: PlateState, async_writer: AsyncEventWriter) -> Dict[str, Any]:
    image_path = state.get("preprocess_output", "")
    if not image_path:
        return {"locate_output": "", STATE_KEY_LAST_RESPONSE: "Error: no preprocess output"}

    await async_writer.write_text("[Locate] starting...\n")
    await async_writer.write_text("  Morphology locate... ")
    morph_result = tool_morphology_locate(image_path)
    if morph_result.get("status") != "ok":
        await async_writer.write_text("failed\n")
        return {"locate_output": image_path}
    candidates = morph_result.get("candidates", [])
    await async_writer.write_text(f"candidates: {len(candidates)}\n")
    if not candidates:
        await async_writer.write_text("[Locate] no candidates found\n")
        return {"locate_output": image_path}

    await async_writer.write_text("  HSV refine... ")
    color_result = tool_color_locate(image_path, candidates)
    if color_result.get("status") != "ok":
        await async_writer.write_text("failed\n")
        return {"locate_output": image_path}

    locate_output = color_result["output_path"]
    plate_color = color_result.get("plate_color", "unknown")
    await async_writer.write_text(f"done (color: {plate_color})\n")
    await async_writer.write_text(f"[Locate] done -> {locate_output}\n")
    return {"locate_output": locate_output}


# Segment
@trace_node("segment")
async def segment_node(state: PlateState, async_writer: AsyncEventWriter) -> Dict[str, Any]:
    image_path = state.get("locate_output", "")
    if not image_path:
        return {"segment_chars": [], STATE_KEY_LAST_RESPONSE: "Error: no locate output"}

    await async_writer.write_text("[Segment] vertical projection... ")
    proj_result = tool_vertical_projection(image_path)
    if proj_result.get("status") != "ok":
        await async_writer.write_text("failed\n")
        return {"segment_chars": []}

    char_images = proj_result.get("char_images", [])
    char_count = proj_result.get("char_count", 0)
    await async_writer.write_text(f"{char_count} characters\n")
    return {"segment_chars": char_images}


# Recognize (v2: Tesseract OCR on ORIGINAL image, not preprocessed plate)
@trace_node("recognize")
async def recognize_node(state: PlateState, async_writer: AsyncEventWriter) -> Dict[str, Any]:
    # Use the ORIGINAL image for OCR, not the preprocessed locate output.
    # The preprocessing chain (especially Canny edge detection) degrades
    # Chinese characters, making Tesseract unable to read them.
    original_image = state.get("image_path", "")
    if not original_image:
        return {"recognize_chars": [], "needs_llm_verify": False,
                STATE_KEY_LAST_RESPONSE: "Error: no image path"}

    await async_writer.write_text("[Recognize] Tesseract OCR on original image...\n")

    ocr_result = tool_tesseract_ocr(original_image)

    if ocr_result.get("status") != "ok":
        await async_writer.write_text(f"[Recognize] OCR failed: {ocr_result.get('message', '')}\n")
        return {"recognize_chars": [], "needs_llm_verify": False,
                "final_plate": ocr_result.get("plate_number", "?")}

    plate_number = ocr_result.get("plate_number", "")
    avg_conf = ocr_result.get("avg_confidence", 0.0)
    ocr_chars = ocr_result.get("chars", [])

    await async_writer.write_text(f"  OCR result: {plate_number} (avg conf: {avg_conf:.2%})\n")

    needs_verify = False
    recognize_chars = []
    for ocr_char in ocr_chars:
        char = ocr_char["char"]
        conf = ocr_char["confidence"]
        char_needs = conf < 0.85
        if char_needs:
            needs_verify = True
        recognize_chars.append({
            "char": char,
            "confidence": conf,
            "needs_verify": char_needs,
        })
        status = " [verify]" if char_needs else ""
        await async_writer.write_text(f"    char {char} (conf: {conf:.2f}){status}\n")

    if needs_verify:
        await async_writer.write_text("[Recognize] low confidence chars found, will verify\n")

    return {
        "recognize_chars": recognize_chars,
        "needs_llm_verify": needs_verify,
        "final_plate": plate_number,
    }


# Human review
@trace_node("human_review")
async def human_review_node(state: PlateState, async_writer: AsyncEventWriter) -> Dict[str, Any]:
    recognize_chars = state.get("recognize_chars", [])
    if not recognize_chars:
        return {}

    low_conf_chars = []
    for i, r in enumerate(recognize_chars):
        if r.get("confidence", 0.0) < 0.5:
            low_conf_chars.append({
                "index": i,
                "char": r.get("char", "?"),
                "confidence": r.get("confidence", 0.0),
            })

    if not low_conf_chars:
        return {}

    await async_writer.write_text("\n" + "=" * 40 + "\n")
    await async_writer.write_text("Human review needed\n")
    await async_writer.write_text("-" * 40 + "\n")

    for item in low_conf_chars:
        await async_writer.write_text(
            f"  pos {item['index']}: OCR='{item['char']}' (conf: {item['confidence']:.2f})\n"
        )

    await async_writer.write_text("\nReply with corrected plate number, or 'skip'.\n")
    await async_writer.write_text("=" * 40 + "\n")

    return {
        "awaiting_human": True,
        "low_confidence_chars": low_conf_chars,
        STATE_KEY_LAST_RESPONSE: f"Human review: {len(low_conf_chars)} chars need confirmation",
    }


# LLM verify
@trace_node("llm_verify")
async def llm_verify_node(state: PlateState, async_writer: AsyncEventWriter) -> Dict[str, Any]:
    recognize_chars = state.get("recognize_chars", [])
    final_plate = state.get("final_plate", "")

    if not recognize_chars:
        return {"final_plate": final_plate}

    await async_writer.write_text("[Verify] RAG confusion check...\n")
    final_chars = []
    has_correction = False

    for i, r in enumerate(recognize_chars):
        char = r.get("char", "?")
        confidence = r.get("confidence", 0.0)

        if r.get("needs_verify"):
            try:
                confusion_result = tool_lookup_confusion(char)
                if confusion_result.get("status") == "ok" and confusion_result.get("candidates"):
                    candidates = confusion_result["candidates"]
                    await async_writer.write_text(
                        f"  char[{i}] '{char}' conf={confidence:.2f} -> candidates: "
                        f"{', '.join(c['char'] for c in candidates)}\n"
                    )
                    if candidates and candidates[0].get("char"):
                        corrected = candidates[0]["char"]
                        await async_writer.write_text(f"    corrected: {char} -> {corrected}\n")
                        final_chars.append(corrected)
                        has_correction = True
                        continue
            except Exception as e:
                logger.warning("Confusion lookup failed: %s", e)

        final_chars.append(char)

    plate = "".join(final_chars)
    if has_correction:
        await async_writer.write_text(f"[Verify] corrected plate: {plate}\n")
    else:
        await async_writer.write_text("[Verify] no correction needed\n")

    return {"final_plate": plate}


# Format output
@trace_node("format_output")
async def format_output_node(state: PlateState, async_writer: AsyncEventWriter) -> Dict[str, Any]:
    plate = state.get("final_plate", "")

    if not plate:
        recognize_chars = state.get("recognize_chars", [])
        if recognize_chars:
            plate = "".join(r.get("char", "?") for r in recognize_chars)
        else:
            plate = "recognition failed"

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

    blacklist_msg = ""
    blacklist_result = tool_search_blacklist(plate)
    if blacklist_result.get("hit"):
        records = blacklist_result.get("records", [])
        for rec in records[:3]:
            blacklist_msg += (
                f"\n  [{rec['type']}] {rec['plate_number']}"
                f" - {rec['description']} ({rec['status']})"
            )
        blacklist_msg = f"\n\nBlacklist hit ({len(records)}): {blacklist_msg}"

    final_output = f"Result: {plate_display}{blacklist_msg}"

    await async_writer.write_text(f"\n{'='*40}\n{final_output}\n{'='*40}\n")

    return {STATE_KEY_LAST_RESPONSE: final_output}