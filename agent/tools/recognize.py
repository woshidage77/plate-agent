"""车牌字符识别 — Tesseract OCR 版，替换破损的 SVM 模型"""
import logging
import os
from pathlib import Path
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

_TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_TESSDATA_DIR = Path(__file__).parent.parent.parent / "tessdata"

_PROVINCES = set("\u4eac\u6d25\u6caa\u6e1d\u5180\u8c6b\u4e91\u8fbd\u9ed1\u6e58\u7696\u9c81\u65b0\u82cf\u6d59\u8d63\u9102\u6842\u7518\u664b\u8499\u9655\u5409\u95fd\u8d35\u7ca4\u5ddd\u9752\u85cf\u743c\u5b81")
_LETTERS = set("ABCDEFGHJKLMNPQRSTUVWXYZ")
_DIGITS = set("0123456789")
_VALID_CHARS = _PROVINCES | _LETTERS | _DIGITS


def _init_tesseract():
    if os.path.exists(_TESSERACT_CMD):
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD
    if _TESSDATA_DIR.exists():
        os.environ["TESSDATA_PREFIX"] = str(_TESSDATA_DIR.resolve())


_init_tesseract()


def tool_tesseract_ocr(image_path: str) -> dict:
    _debug = []
    _debug.append(f"TESSDATA_PREFIX={os.environ.get('TESSDATA_PREFIX', 'NOT SET')}")
    _debug.append(f"TESSDATA_DIR={_TESSDATA_DIR.resolve()}")
    _debug.append(f"TESSDATA exists={_TESSDATA_DIR.exists()}")
    _debug.append(f"TESSERACT_CMD exists={os.path.exists(_TESSERACT_CMD)}")

    if not os.path.exists(image_path):
        return {"status": "error", "message": f"图像不存在: {image_path}"}

    try:
        img = Image.open(image_path)
        config = "--psm 7"
        raw_text = pytesseract.image_to_string(img, lang="chi_sim+eng", config=config).strip()

        _debug.append(f"raw_text len={len(raw_text)}")
        _debug.append(f"raw_text codepoints={[hex(ord(c)) for c in raw_text]}")
        _debug.append(f"_PROVINCES len={len(_PROVINCES)}")
        _debug.append(f"_PROVINCES sample codepoints={[hex(ord(c)) for c in list(_PROVINCES)[:3]]}")

        for i, c in enumerate(raw_text):
            _debug.append(f"char[{i}] U+{ord(c):04X} in_valid={c in _VALID_CHARS}")

        filtered = "".join(c for c in raw_text if c in _VALID_CHARS)
        _debug.append(f"filtered={repr(filtered)}")

        data = pytesseract.image_to_data(img, lang="chi_sim+eng", config=config, output_type=pytesseract.Output.DICT)
        chars = []
        for i, text in enumerate(data["text"]):
            t = text.strip()
            conf_val = int(data["conf"][i])
            if t and conf_val > 0:
                filtered_t = "".join(c for c in t if c in _VALID_CHARS)
                if filtered_t:
                    chars.append({"char": filtered_t, "confidence": round(conf_val / 100.0, 4)})

        if chars:
            avg_conf = round(sum(c["confidence"] for c in chars) / len(chars), 4)
        else:
            avg_conf = 0.0

        plate_number = filtered if filtered else raw_text
        plate_number = plate_number.replace(" ", "")

        return {
            "status": "ok",
            "plate_number": plate_number,
            "raw_ocr": raw_text,
            "chars": chars,
            "avg_confidence": avg_conf,
            "char_count": len(chars),
            "_debug": _debug,
        }
    except Exception as e:
        logger.exception("Tesseract OCR failed: %s", e)
        return {"status": "error", "message": str(e), "_debug": _debug}


def tool_svm_predict(image_path):
    logger.warning("tool_svm_predict deprecated, use tool_tesseract_ocr")
    return {"status": "error", "char": "?", "confidence": 0.0, "needs_verify": True}


def tool_llm_verify(char_image_path, svm_result):
    logger.warning("tool_llm_verify deprecated")
    final_char = svm_result.get("char", "?") if isinstance(svm_result, dict) else "?"
    return {"final_char": final_char}