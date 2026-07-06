"""图像预处理模块 — OpenCV 管线

实现方案要求的四种输入方式：
1. 手机拍照：透视校正 + 白平衡 + 阴影压制
2. 高清扫描：格式校验 + DPI 检查
3. 局部识别反查：DINOv2 特征匹配 (Phase 2)
4. 文字搜索：语义搜索 (Phase 2)
"""

import os
import json
from typing import Optional, Dict, Tuple
from dataclasses import dataclass


@dataclass
class PreprocessResult:
    success: bool
    output_path: str = ""
    width: int = 0
    height: int = 0
    corrections: list[str] = None

    def __post_init__(self):
        if self.corrections is None:
            self.corrections = []


# ============ 格式验证 ============

ALLOWED_FORMATS = {"jpg", "jpeg", "png", "tiff", "tif", "webp"}
MIN_RESOLUTION = (800, 600)  # 最小 800x600
SCAN_MIN_DPI = 300


def validate_image(image_path: str) -> Tuple[bool, str]:
    """验证图片格式和基本质量"""
    if not os.path.exists(image_path):
        return False, "文件不存在"
    ext = image_path.rsplit(".", 1)[-1].lower() if "." in image_path else ""
    if ext not in ALLOWED_FORMATS:
        return False, f"不支持的文件格式: {ext}，支持: {', '.join(ALLOWED_FORMATS)}"
    return True, "ok"


def validate_scan(image_path: str) -> Tuple[bool, str]:
    """验证高清扫描件质量 (DPI >= 300)"""
    valid, msg = validate_image(image_path)
    if not valid:
        return False, msg
    # Note: 真实验证 DPI 需要 PIL 读 EXIF，Phase 0 仅做格式检查
    return True, "格式校验通过"


def get_image_info(image_path: str) -> Dict:
    """获取图片基本信息"""
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            return {
                "width": img.width,
                "height": img.height,
                "format": img.format,
                "mode": img.mode,
                "dpi": img.info.get("dpi", (0, 0)),
            }
    except ImportError:
        return {"error": "PIL not installed", "path": image_path}


# ============ 预处理管线 (Phase 1 骨架) ============

def preprocess_photo(image_path: str, output_dir: str = "./uploads") -> PreprocessResult:
    """手机拍照预处理管线

    完整流程 (Phase 1 通过 OpenCV 实现):
    1. 透视校正 (warpPerspective)
    2. 白平衡校正 (灰度世界 + 完美反射混合)
    3. 阴影压制 (SSR + CLAHE)
    4. 自动裁边 (Canny + 最大轮廓)
    """
    try:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            return PreprocessResult(success=False)

        h, w = img.shape[:2]
        corrections = []

        # Step 1: 透视校正 - 尝试检测纸张四角
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            largest = max(contours, key=cv2.contourArea)
            peri = cv2.arcLength(largest, True)
            approx = cv2.approxPolyDP(largest, 0.02 * peri, True)
            if len(approx) == 4:
                pts = approx.reshape(4, 2).astype(np.float32)
                # 排序四角: 左上 右上 右下 左下
                s = pts.sum(axis=1)
                diff = np.diff(pts, axis=1)
                rect = np.zeros((4, 2), dtype=np.float32)
                rect[0] = pts[np.argmin(s)]
                rect[2] = pts[np.argmax(s)]
                rect[1] = pts[np.argmin(diff)]
                rect[3] = pts[np.argmax(diff)]
                dst_w = max(int(np.linalg.norm(rect[1] - rect[0])), int(np.linalg.norm(rect[3] - rect[2])))
                dst_h = max(int(np.linalg.norm(rect[2] - rect[1])), int(np.linalg.norm(rect[3] - rect[0])))
                dst = np.array([[0, 0], [dst_w-1, 0], [dst_w-1, dst_h-1], [0, dst_h-1]], dtype=np.float32)
                M = cv2.getPerspectiveTransform(rect, dst)
                img = cv2.warpPerspective(img, M, (dst_w, dst_h))
                corrections.append("透视校正")
                h, w = img.shape[:2]

        # Step 2: 白平衡 (灰度世界算法)
        b, g, r = cv2.split(img.astype(np.float32))
        b_avg, g_avg, r_avg = np.mean(b), np.mean(g), np.mean(r)
        k = (b_avg + g_avg + r_avg) / 3
        b = b * k / (b_avg + 1)
        g = g * k / (g_avg + 1)
        r = r * k / (r_avg + 1)
        img = cv2.merge([b, g, r]).clip(0, 255).astype(np.uint8)
        corrections.append("白平衡校正")

        # Step 3: CLAHE 对比度增强
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        img = cv2.cvtColor(cv2.merge([l, a, b_ch]), cv2.COLOR_LAB2BGR)
        corrections.append("阴影压制 (CLAHE)")

        # 保存
        os.makedirs(output_dir, exist_ok=True)
        basename = os.path.splitext(os.path.basename(image_path))[0]
        out_path = os.path.join(output_dir, f"{basename}_processed.jpg")
        cv2.imwrite(out_path, img, [cv2.IMWRITE_JPEG_QUALITY, 95])

        return PreprocessResult(
            success=True, output_path=out_path,
            width=w, height=h, corrections=corrections,
        )

    except ImportError:
        return PreprocessResult(success=False)
    except Exception as e:
        return PreprocessResult(success=False)


# ============ 批处理报告 ============

def batch_preprocess(image_paths: list[str], output_dir: str = "./uploads") -> list[PreprocessResult]:
    """批量预处理"""
    return [preprocess_photo(p, output_dir) for p in image_paths]