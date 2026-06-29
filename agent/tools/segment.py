"""车牌字符分割 FunctionTool —— 对应原文 3.3 节"""

import cv2
import numpy as np


def tool_vertical_projection(image_path: str) -> dict:
    """使用垂直投影法对车牌图像进行字符分割。
    
    计算车牌二值图像在垂直方向上的投影直方图，
    利用波谷-波峰-波谷特征分割出7个独立字符。
    适用于中国标准车牌（GA-36-2007，440mm×140mm）。
    
    Args:
        image_path: 精确定位后的车牌区域图像路径
    Returns:
        dict: {"status": "ok", "char_count": 分割出的字符数,
               "char_images": [字符图像路径列表]}
    """
    img = cv2.imread(image_path)
    if img is None:
        return {"status": "error", "message": f"无法读取图像: {image_path}"}
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    
    # 二值化
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # 垂直投影：统计每列白色像素
    h, w = binary.shape
    projection = np.sum(binary == 255, axis=0)
    
    # 找波谷（白色像素骤减的位置 = 字符间隙）
    threshold = np.max(projection) * 0.2
    in_char = False
    char_regions = []
    start = 0
    
    for i in range(w):
        if projection[i] > threshold and not in_char:
            start = i
            in_char = True
        elif projection[i] <= threshold and in_char:
            char_regions.append((start, i))
            in_char = False
    
    if in_char:
        char_regions.append((start, w - 1))
    
    # 过滤太窄的噪声区域
    char_regions = [(s, e) for s, e in char_regions if (e - s) > 3]
    
    # 裁剪字符
    char_images = []
    base = image_path.rsplit(".", 1)[0]
    
    for idx, (s, e) in enumerate(char_regions):
        char_img = binary[:, s:e]
        char_path = f"{base}_char{idx}.jpg"
        cv2.imwrite(char_path, char_img)
        char_images.append(char_path)
    
    return {
        "status": "ok",
        "char_count": len(char_images),
        "char_images": char_images
    }
