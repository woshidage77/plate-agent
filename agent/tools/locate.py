"""车牌定位 FunctionTools —— 对应原文 3.2 节"""

import cv2
import numpy as np


def tool_morphology_locate(image_path: str) -> dict:
    """使用数学形态学方法提取车牌全部候选轮廓。
    
    通过腐蚀+膨胀（开运算/闭运算）处理二值化图像，
    消除小而无意义的区域，填充细小空洞，提取所有候选车牌轮廓。
    
    Args:
        image_path: 预处理后的图像路径
    Returns:
        dict: {"status": "ok", "contours_count": 候选轮廓数量, 
               "candidates": [{"x": int, "y": int, "w": int, "h": int}, ...]}
    """
    img = cv2.imread(image_path)
    if img is None:
        return {"status": "error", "message": f"无法读取图像: {image_path}"}
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    
    # 形态学操作：闭运算连接相邻区域
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (22, 7))
    closed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    
    # 开运算去除小噪点
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)
    
    # 查找轮廓
    contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    candidates = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        # 宽高比在 2~5.5 之间的可能是车牌
        ratio = w / h if h > 0 else 0
        if 2.0 <= ratio <= 5.5 and w > 50 and h > 15:
            candidates.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})
    
    return {
        "status": "ok",
        "contours_count": len(contours),
        "candidates": candidates
    }


def tool_color_locate(image_path: str, candidates: list) -> dict:
    """使用HSV颜色特征从候选轮廓中精确定位车牌区域。
    
    将图像从RGB转换到HSV颜色空间，根据中国车牌颜色范围
    （蓝/绿/黄/白）筛选出最可能的车牌矩形区域。
    
    Args:
        image_path: 原始图像路径
        candidates: 候选轮廓列表 [{"x": int, "y": int, "w": int, "h": int}, ...]
    Returns:
        dict: {"status": "ok", "plate_region": {"x": int, "y": int, "w": int, "h": int}, 
               "plate_color": str, "output_path": 裁剪后的车牌区域路径}
    """
    img = cv2.imread(image_path)
    if img is None:
        return {"status": "error", "message": f"无法读取图像: {image_path}"}
    
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # 蓝色范围 (中国蓝牌最常见)
    lower_blue = np.array([100, 43, 46])
    upper_blue = np.array([124, 255, 255])
    
    best_rect = None
    best_score = 0
    plate_color = "unknown"
    
    for cand in candidates:
        x, y, w, h = cand["x"], cand["y"], cand["w"], cand["h"]
        roi = hsv[y:y+h, x:x+w]
        
        # 统计蓝色像素占比
        mask = cv2.inRange(roi, lower_blue, upper_blue)
        blue_ratio = np.sum(mask > 0) / (w * h) if w * h > 0 else 0
        
        if blue_ratio > best_score:
            best_score = blue_ratio
            best_rect = cand
            plate_color = "blue"
    
    if best_rect is None and candidates:
        best_rect = candidates[0]
    
    # 裁剪车牌区域
    if best_rect:
        x, y, w, h = best_rect["x"], best_rect["y"], best_rect["w"], best_rect["h"]
        # 扩大 10% 边距
        x = max(0, int(x - w * 0.05))
        y = max(0, int(y - h * 0.05))
        w = min(img.shape[1] - x, int(w * 1.1))
        h = min(img.shape[0] - y, int(h * 1.1))
        
        plate = img[y:y+h, x:x+w]
        output_path = image_path.replace(".jpg", "_plate.jpg")
        cv2.imwrite(output_path, plate)
        
        return {
            "status": "ok",
            "plate_region": {"x": x, "y": y, "w": w, "h": h},
            "plate_color": plate_color,
            "output_path": output_path
        }
    
    return {"status": "error", "message": "未找到车牌区域"}
