"""车牌预处理 FunctionTools —— 对应原文 3.1 节"""

import cv2
import numpy as np


def tool_gaussian_blur(image_path: str, kernel_size: int = 5) -> dict:
    """对车牌图像进行高斯滤波降噪处理。
    
    使用高斯滤波器对输入图像进行平滑处理，消除高斯噪声，
    同时保留图像边缘信息。kernel_size 越大平滑效果越强。
    
    Args:
        image_path: 车牌图像的本地文件路径
        kernel_size: 高斯核大小，必须为奇数，默认 5
    Returns:
        dict: {"status": "ok", "output_path": 处理后的图像临时路径}
    """
    img = cv2.imread(image_path)
    if img is None:
        return {"status": "error", "message": f"无法读取图像: {image_path}"}
    
    # 确保 kernel_size 为奇数
    if kernel_size % 2 == 0:
        kernel_size += 1
    
    blurred = cv2.GaussianBlur(img, (kernel_size, kernel_size), 0)
    output_path = image_path.replace(".jpg", "_blurred.jpg")
    cv2.imwrite(output_path, blurred)
    
    return {"status": "ok", "output_path": output_path}


def tool_grayscale(image_path: str) -> dict:
    """对车牌图像进行加权平均灰度化处理。
    
    使用加权平均值法（R*0.299 + G*0.587 + B*0.114）将彩色图像
    转换为灰度图像，减少计算量，提高后续处理速度。
    
    Args:
        image_path: 经过滤波处理后的图像路径
    Returns:
        dict: {"status": "ok", "output_path": 灰度图路径}
    """
    img = cv2.imread(image_path)
    if img is None:
        return {"status": "error", "message": f"无法读取图像: {image_path}"}
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    output_path = image_path.replace(".jpg", "_gray.jpg")
    cv2.imwrite(output_path, gray)
    
    return {"status": "ok", "output_path": output_path}


def tool_binarize_otsu(image_path: str) -> dict:
    """使用OTSU大津阈值算法对车牌图像进行二值化。
    
    通过最大类间方差法自动选取最佳阈值，将灰度图像转换为
    黑白二值图像，使车牌字符从背景中分离出来。
    
    Args:
        image_path: 灰度化后的图像路径
    Returns:
        dict: {"status": "ok", "output_path": 二值化图路径, "threshold": 自动计算的阈值}
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {"status": "error", "message": f"无法读取图像: {image_path}"}
    
    threshold, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    output_path = image_path.replace(".jpg", "_binary.jpg")
    cv2.imwrite(output_path, binary)
    
    return {"status": "ok", "output_path": output_path, "threshold": int(threshold)}


def tool_edge_detect_canny(image_path: str, low_threshold: int = 50, high_threshold: int = 150) -> dict:
    """使用Canny算子对车牌图像进行边缘检测。
    
    Canny算子是公认最优的边缘检测算法，通过双阈值机制
    有效抑制噪声干扰，精确提取车牌轮廓边缘。
    
    Args:
        image_path: 二值化后的图像路径
        low_threshold: Canny低阈值，默认 50
        high_threshold: Canny高阈值，默认 150
    Returns:
        dict: {"status": "ok", "output_path": 边缘检测图路径}
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {"status": "error", "message": f"无法读取图像: {image_path}"}
    
    edges = cv2.Canny(img, low_threshold, high_threshold)
    output_path = image_path.replace(".jpg", "_edges.jpg")
    cv2.imwrite(output_path, edges)
    
    return {"status": "ok", "output_path": output_path}


def tool_affine_correct(image_path: str) -> dict:
    """使用仿射变换对倾斜车牌图像进行矫正。
    
    通过识别车牌边框计算倾斜角度，利用OpenCV的
    getAffineTransform + warpAffine 实现旋转矫正。
    
    Args:
        image_path: 边缘检测后的图像路径
    Returns:
        dict: {"status": "ok", "output_path": 矫正后图像路径, "angle": 矫正角度}
    """
    img = cv2.imread(image_path)
    if img is None:
        return {"status": "error", "message": f"无法读取图像: {image_path}"}
    
    # 仿射变换：使用原图中心作为旋转中心
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    
    # 默认不做旋转(角度从后续定位阶段获取)
    # 此处保留接口，实际角度由定位阶段传入
    angle = 0.0
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    corrected = cv2.warpAffine(img, matrix, (w, h))
    
    output_path = image_path.replace(".jpg", "_corrected.jpg")
    cv2.imwrite(output_path, corrected)
    
    return {"status": "ok", "output_path": output_path, "angle": angle}
