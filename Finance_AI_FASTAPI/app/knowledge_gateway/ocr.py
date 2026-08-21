"""图片 OCR 识别 — EasyOCR 单例封装

提供线程安全的 EasyOCR 实例管理和图片文字提取能力。
首次调用自动懒加载模型（约 150MB），后续调用复用。
使用 EasyOCR 替代 PaddleOCR，避免 PaddlePaddle 在 Windows 上的 oneDNN/PIR 兼容性问题。

契约 §5.1 引擎开关（Gateway .env）：
- OCR_PROVIDER=easyocr（默认）：本地识别
- OCR_PROVIDER=none：禁用 OCR，图片不提取文本（返回空串）
- OCR_PROVIDER=mineru / paddle：预留的在线/替代引擎，接入后启用；
  当前未实现时抛 RuntimeError，由 extraction.py 按「OCR 失败降级」处理
"""

from __future__ import annotations

import io
import threading

import numpy as np
from PIL import Image

from app.core.config import get_settings

_ocr_lock = threading.Lock()
_ocr_instance = None
_ocr_ready = False


def _get_ocr():
    """线程安全的 EasyOCR 单例。

    首次调用时初始化（加载 ~150MB 模型到 GPU/CPU），后续直接复用。
    支持中英文混合识别。
    """
    global _ocr_instance, _ocr_ready
    if not _ocr_ready:
        with _ocr_lock:
            if not _ocr_ready:
                import easyocr
                _ocr_instance = easyocr.Reader(
                    ["ch_sim", "en"],
                    gpu=False,       # CPU 模式，避免 Windows GPU 兼容问题
                    verbose=False,
                )
                _ocr_ready = True
    return _ocr_instance


def extract_text_from_image(
    raw: bytes, max_side: int = 2048, min_confidence: float = 0.5
) -> str:
    """从图片字节流中提取文字。

    引擎由 .env 的 OCR_PROVIDER 决定（见模块 docstring）；OCR_PROVIDER=none 时
    返回空串（调用方按「未识别出文字」降级，不阻塞聊天）。

    Args:
        raw: 图片原始字节
        max_side: 长边最大像素数，超限自动等比缩放
        min_confidence: 最低置信度阈值，低于此值的识别结果被丢弃

    Returns:
        识别的文字，按从上到下、从左到右排列，用换行分隔
    """
    settings = get_settings()
    provider = (settings.ocr_provider or "easyocr").strip().lower()
    if provider == "none":
        return ""
    if provider not in ("easyocr", "mineru", "paddle"):
        raise RuntimeError(f"未知的 OCR 引擎: {settings.ocr_provider}")
    if provider in ("mineru", "paddle"):
        raise RuntimeError(
            f"OCR 引擎 {provider} 尚未接入，请改用 easyocr 或将 OCR_PROVIDER 设为 none"
        )

    image = Image.open(io.BytesIO(raw))

    # 统一转为 RGB（处理 RGBA / 灰度 / CMYK 等格式）
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    # 缩放大图，避免 OOM
    w, h = image.size
    if max(w, h) > max_side:
        ratio = max_side / max(w, h)
        new_size = (int(w * ratio), int(h * ratio))
        image = image.resize(new_size, Image.LANCZOS)

    ocr = _get_ocr()
    results = ocr.readtext(np.array(image))

    lines: list[str] = []
    for (_bbox, text, confidence) in results:
        if text and confidence >= min_confidence:
            lines.append(text)

    return "\n".join(lines)
