"""共享工具函数"""

import uuid


def generate_uuid() -> str:
    """生成 UUID"""
    return uuid.uuid4().hex


def validate_image_format(filename: str) -> bool:
    """验证图片文件格式是否支持"""
    ALLOWED = {"jpg", "jpeg", "png", "tiff", "tif", "webp"}
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED
