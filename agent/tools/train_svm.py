"""PlateAgent SVM 字符识别模型训练

从零训练一个车牌字符分类器：
    1. 合成训练数据：用系统字体渲染 65 类字符
    2. 数据增强：噪声、模糊、旋转、缩放
    3. 特征提取：HOG（方向梯度直方图）— 使用 OpenCV 实现
    4. 训练 SVM：sklearn.svm.SVC(probability=True)
    5. 保存模型 + label 映射

输出文件：
    - agent/tools/svm_model.pkl    (SVM 模型)
    - agent/tools/svm_labels.json  (class_id → char 映射)

用法：
    python -m agent.tools.train_svm

字符集（中国蓝牌车牌）：
    省份缩写: 31 个汉字
    字母:    24 个 (A-Z 不含 I,O)
    数字:    10 个 (0-9)
    总计:    65 类
"""

import json
import logging
import os
import pickle
import random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── 输出路径 ──
OUTPUT_DIR = Path(__file__).parent
MODEL_PATH = OUTPUT_DIR / "svm_model.pkl"
LABELS_PATH = OUTPUT_DIR / "svm_labels.json"

# ── 可用字体 ──
FONTS = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simkai.ttf",
    "C:/Windows/Fonts/simsun.ttc",
]

# ── 车牌字符集 ──
PROVINCES = list("京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤川青藏琼宁")
LETTERS   = [c for c in "ABCDEFGHIJKLMNPQRSTUVWXYZ"]
DIGITS    = list("0123456789")
ALL_CHARS = PROVINCES + LETTERS + DIGITS

TARGET_SIZE = (32, 32)

# ── OpenCV HOG 参数 ──
HOG_WIN_SIZE = (32, 32)
HOG_BLOCK_SIZE = (16, 16)
HOG_BLOCK_STRIDE = (8, 8)
HOG_CELL_SIZE = (8, 8)
HOG_NBINS = 9

# 创建全局 HOG 实例
_hog = cv2.HOGDescriptor(
    _winSize=HOG_WIN_SIZE,
    _blockSize=HOG_BLOCK_SIZE,
    _blockStride=HOG_BLOCK_STRIDE,
    _cellSize=HOG_CELL_SIZE,
    _nbins=HOG_NBINS,
)


def render_char(char: str, font_path: str, font_size: int,
                noise_level: float = 0.0, rotation: float = 0.0,
                scale: float = 1.0) -> np.ndarray:
    """用指定字体渲染单个字符为 32×32 灰度图。"""
    font = ImageFont.truetype(font_path, font_size)
    img = Image.new("L", (64, 64), color=255)
    draw = ImageDraw.Draw(img)

    bbox = draw.textbbox((0, 0), char, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (64 - text_w) // 2
    y = (64 - text_h) // 2
    draw.text((x, y), char, font=font, fill=0)

    arr = np.array(img, dtype=np.uint8)

    if rotation != 0:
        center = (32, 32)
        M = cv2.getRotationMatrix2D(center, rotation, 1.0)
        arr = cv2.warpAffine(arr, M, (64, 64),
                             borderMode=cv2.BORDER_CONSTANT, borderValue=255)

    arr = cv2.resize(arr, TARGET_SIZE)

    if noise_level > 0:
        noise = np.random.normal(0, noise_level, TARGET_SIZE).astype(np.int16)
        arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    if random.random() < 0.5:
        arr = cv2.GaussianBlur(arr, (3, 3), 0)

    return arr


def extract_hog_features(image: np.ndarray) -> np.ndarray:
    """从 32×32 灰度图提取 HOG 特征向量（OpenCV 实现）。"""
    return _hog.compute(image).flatten().astype(np.float32)


def generate_samples() -> tuple[np.ndarray, np.ndarray]:
    """合成全部 65 类的训练样本。"""
    X_list, y_list = [], []

    for class_id, char in enumerate(ALL_CHARS):
        logger.info("生成 %s (class %d/64)...", char, class_id)
        for font_path in FONTS:
            if not os.path.exists(font_path):
                continue
            for font_size in [28, 32, 36]:
                # 基础样本
                img = render_char(char, font_path, font_size)
                features = extract_hog_features(img)
                X_list.append(features)
                y_list.append(class_id)

                # 增强样本
                for _ in range(6):
                    noise = random.uniform(0, 8)
                    rot = random.uniform(-5, 5)
                    img_aug = render_char(char, font_path, font_size,
                                          noise_level=noise, rotation=rot)
                    features = extract_hog_features(img_aug)
                    X_list.append(features)
                    y_list.append(class_id)

    X = np.array(X_list, dtype=np.float32)
    y = np.array(y_list, dtype=np.int32)
    logger.info("总计 %d 个样本, %d 维特征", X.shape[0], X.shape[1])
    return X, y


def train_and_save():
    """训练 SVM 并保存模型。"""
    from sklearn.svm import SVC
    from sklearn.model_selection import train_test_split

    logger.info("=== 第 1 步：合成训练数据 ===")
    X, y = generate_samples()

    logger.info("=== 第 2 步：划分训练/测试集 ===")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42, stratify=y
    )
    logger.info("训练集 %d, 测试集 %d", X_train.shape[0], X_test.shape[0])

    logger.info("=== 第 3 步：训练 SVM (RBF kernel, probability=True) ===")
    model = SVC(
        kernel="rbf", C=10.0, gamma="scale",
        probability=True, random_state=42,
    )
    model.fit(X_train, y_train)

    logger.info("=== 第 4 步：评估 ===")
    train_acc = model.score(X_train, y_train)
    test_acc = model.score(X_test, y_test)
    logger.info("训练准确率: %.2f%%", train_acc * 100)
    logger.info("测试准确率: %.2f%%", test_acc * 100)

    logger.info("=== 第 5 步：保存模型 ===")
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    logger.info("模型已保存: %s (%.1f KB)", MODEL_PATH,
                MODEL_PATH.stat().st_size / 1024)

    label_map = {str(i): char for i, char in enumerate(ALL_CHARS)}
    with open(LABELS_PATH, "w", encoding="utf-8") as f:
        json.dump(label_map, f, ensure_ascii=False, indent=2)
    logger.info("Label 映射已保存: %s", LABELS_PATH)

    logger.info("=== 第 6 步：抽样验证 ===")
    samples_to_check = [
        (PROVINCES.index("粤"), "粤"),
        (PROVINCES.index("京"), "京"),
        (31 + LETTERS.index("A"), "A"),
        (31 + LETTERS.index("Z"), "Z"),
        (31 + 24 + DIGITS.index("5"), "5"),
        (31 + 24 + DIGITS.index("0"), "0"),
    ]
    for class_id, expected in samples_to_check:
        mask = y_test == class_id
        if not mask.any():
            continue
        probs = model.predict_proba([X_test[mask][0]])
        top_idx = np.argmax(probs[0])
        top_char = ALL_CHARS[top_idx]
        top_conf = probs[0][top_idx]
        correct = "OK" if top_char == expected else f"MISMATCH (expected {expected})"
        logger.info("  class %d (%s): predicted=%s, confidence=%.3f → %s",
                    class_id, expected, top_char, top_conf, correct)

    logger.info("=== 训练完成 ===")
    return test_acc


if __name__ == "__main__":
    acc = train_and_save()
    print(f"\nFinal test accuracy: {acc:.2%}")
    if acc >= 0.85:
        print("PASS: accuracy >= 85%, model ready for tool_svm_predict")
    else:
        print("WARN: accuracy below 85%, consider more samples or tuning")