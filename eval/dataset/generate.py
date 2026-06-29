"""PlateAgent 评测数据集生成器

生成 30 张合成车牌图像，用于验证识别流水线的准确率。
每张图像都有已知的 ground truth 车牌号。

生成策略：
    - 10 张 清晰标准图（baseline）
    - 10 张 模糊图（高斯模糊，模拟运动模糊）
    - 5 张  倾斜图（旋转 ±5~15 度）
    - 5 张  噪声图（椒盐噪声）

输出：
    eval/dataset/test_plates/plate_001.jpg ~ plate_030.jpg
    eval/dataset/ground_truth.json
"""

import json
import os
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

# ── 配置 ──
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_plates")
GT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ground_truth.json")

PLATE_WIDTH = 440
PLATE_HEIGHT = 140
TOTAL_IMAGES = 30

# 真实车牌号（覆盖多个省份 + 数字字母组合）
REAL_PLATES = [
    "京A12345", "沪B67890", "粤C24680", "苏D13579", "浙E86420",
    "鲁F97531", "闽G11223", "豫H44556", "川I77889", "渝J99001",
    "黑K22334", "吉L55667", "辽M88990", "冀N00112", "晋P33445",
    "陕Q66778", "甘R99001", "青S11223", "云T44556", "贵U77889",
    "鄂V00112", "湘W33445", "赣X66778", "皖Y99001", "琼Z11223",
    "蒙A33445", "宁B66778", "新C99001", "藏D11223", "桂E44556",
]


def create_plate_image(plate_number: str) -> Image.Image:
    """创建一张标准蓝底白字车牌图像。"""
    img = Image.new("RGB", (PLATE_WIDTH, PLATE_HEIGHT), (0, 51, 153))  # 蓝底
    draw = ImageDraw.Draw(img)

    # 尝试加载中文字体，失败则用默认
    font_paths = [
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
    ]
    font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 80)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    # 绘制文字（居中）
    bbox = draw.textbbox((0, 0), plate_number, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (PLATE_WIDTH - text_w) // 2
    y = (PLATE_HEIGHT - text_h) // 2
    draw.text((x, y), plate_number, fill=(255, 255, 255), font=font)

    # 画白色边框（模拟车牌边框）
    draw.rectangle([5, 5, PLATE_WIDTH - 6, PLATE_HEIGHT - 6], outline=(255, 255, 255), width=3)

    return img


def apply_blur(img: Image.Image, strength: float) -> Image.Image:
    """应用高斯模糊。strength: 0~1，越大越模糊。"""
    radius = strength * 3.0
    return img.filter(ImageFilter.GaussianBlur(radius=radius))


def apply_tilt(img: Image.Image, angle: float) -> Image.Image:
    """旋转图像（模拟倾斜拍摄）。"""
    return img.rotate(angle, expand=True, fillcolor=(0, 51, 153))


def apply_noise(img: Image.Image, strength: float) -> Image.Image:
    """添加椒盐噪声。strength: 0~1，噪声像素占比。"""
    arr = np.array(img)
    mask = np.random.random(arr.shape[:2]) < strength
    arr[mask] = [0, 0, 0]
    mask = np.random.random(arr.shape[:2]) < strength * 0.5
    arr[mask] = [255, 255, 255]
    return Image.fromarray(arr)


def generate_dataset():
    """主生成逻辑。"""
    os.makedirs(OUT_DIR, exist_ok=True)
    random.seed(42)  # 可复现
    np.random.seed(42)

    plates = REAL_PLATES.copy()
    random.shuffle(plates)

    dataset = []

    for i in range(TOTAL_IMAGES):
        plate = plates[i]
        img = create_plate_image(plate)
        conditions = {}

        # 决定这张图的处理方式
        if i < 10:
            # 清晰标准图（不做额外处理）
            conditions["type"] = "clear"
        elif i < 20:
            # 模糊图
            blur_level = round(0.3 + random.random() * 0.7, 2)
            img = apply_blur(img, blur_level)
            conditions["type"] = "blur"
            conditions["blur"] = blur_level
        elif i < 25:
            # 倾斜图
            angle = round(random.uniform(-15, 15), 1)
            img = apply_tilt(img, angle)
            conditions["type"] = "tilt"
            conditions["angle"] = angle
        else:
            # 噪声图
            noise_level = round(0.02 + random.random() * 0.08, 3)
            img = apply_noise(img, noise_level)
            conditions["type"] = "noise"
            conditions["noise"] = noise_level

        # 保存
        filename = f"plate_{i+1:03d}.jpg"
        out_path = os.path.join(OUT_DIR, filename)
        img.save(out_path, "JPEG", quality=95)

        dataset.append({
            "id": i + 1,
            "image": f"eval/dataset/test_plates/{filename}",
            "plate_number": plate,
            "conditions": conditions,
        })

        print(f"  [{i+1:02d}/30] {filename} — {plate} ({conditions['type']})")

    # 写 ground truth
    with open(GT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    print(f"\n生成完成: {TOTAL_IMAGES} 张图像 → {OUT_DIR}")
    print(f"标注文件: {GT_PATH}")


if __name__ == "__main__":
    generate_dataset()
