"""图片上传 / OCR 契约测试（契约 §5.1 + §4 + §1）。

覆盖：
- 图片格式清单与契约一致（png/jpeg/gif/webp，无 bmp）
- OCR 失败降级：图片解析失败 → ("", True)，不抛异常、不阻塞聊天
- OCR_PROVIDER 引擎开关（none 禁用 / 预留引擎降级）
- 图片 5MB 配置默认值
- ai-assistant stateful 标记（§4）
- X-Agent-Token 请求头构造（§1）
"""

from app.agent_gateway.client import agent_headers
from app.agent_gateway.registry import build_registry
from app.core.config import Settings, get_settings
from app.knowledge_gateway.extraction import (
    IMAGE_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    FileTextError,
    extract_text,
)
from app.knowledge_gateway.ocr import extract_text_from_image


def test_image_extensions_match_contract_5_1():
    # 契约 §5.1：image/png image/jpeg image/gif image/webp（无 bmp）
    assert IMAGE_EXTENSIONS == {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    assert ".gif" in SUPPORTED_EXTENSIONS
    assert ".bmp" not in SUPPORTED_EXTENSIONS


def test_ocr_failure_degrades_to_empty_text(tmp_path):
    # 图片损坏无法识别 → 契约要求返回空文本 + ocr_failed 标记，不抛异常
    fake = tmp_path / "fake.png"
    fake.write_bytes(b"this is not a real image")
    text, ocr_failed = extract_text(str(fake), ".png", 1000)
    assert text == ""
    assert ocr_failed is True


def test_gif_goes_through_ocr_degradation_path(tmp_path):
    # gif 属于契约支持的图片格式，走 OCR 分支；坏字节同样降级而非 400
    fake = tmp_path / "fake.gif"
    fake.write_bytes(b"not a gif")
    text, ocr_failed = extract_text(str(fake), ".gif", 1000)
    assert text == ""
    assert ocr_failed is True


def test_text_file_extraction_returns_text_and_no_flag(tmp_path):
    content = "这是需求文档内容"
    file = tmp_path / "requirement.md"
    file.write_bytes(content.encode("utf-8"))
    text, ocr_failed = extract_text(str(file), ".md", 1000)
    assert text == content
    assert ocr_failed is False


def test_empty_text_file_still_raises(tmp_path):
    # 非图片文件无文本仍按 400 语义处理（契约只要求 OCR 降级）
    file = tmp_path / "empty.txt"
    file.write_bytes(b"   ")
    try:
        extract_text(str(file), ".txt", 1000)
    except FileTextError as exc:
        assert "没有可提取的文本" in str(exc)
    else:
        raise AssertionError("空文本文件应抛 FileTextError")


def test_unsupported_extension_raises(tmp_path):
    file = tmp_path / "malware.exe"
    file.write_bytes(b"x")
    try:
        extract_text(str(file), ".exe", 1000)
    except FileTextError as exc:
        assert "不支持的文件类型" in str(exc)
    else:
        raise AssertionError("不支持的类型应抛 FileTextError")


def test_upload_image_max_bytes_default_5mb():
    # 契约 §5.1：图片单张 ≤5 MB，普通文件 10 MB
    settings = Settings()
    assert settings.upload_image_max_bytes == 5 * 1024 * 1024
    assert settings.upload_max_bytes == 10 * 1024 * 1024


def test_ocr_provider_none_disables_ocr(monkeypatch):
    # 契约 §5.1 引擎开关：OCR_PROVIDER=none → 返回空串，不触发模型加载
    monkeypatch.setenv("OCR_PROVIDER", "none")
    get_settings.cache_clear()
    try:
        assert extract_text_from_image(b"anything") == ""
    finally:
        get_settings.cache_clear()


def test_ocr_provider_reserved_engine_degrades(monkeypatch):
    # mineru/paddle 预留未接入 → 抛 RuntimeError，由 extraction.py 降级为 ("", True)
    monkeypatch.setenv("OCR_PROVIDER", "mineru")
    get_settings.cache_clear()
    try:
        try:
            extract_text_from_image(b"anything")
        except RuntimeError as exc:
            assert "尚未接入" in str(exc)
        else:
            raise AssertionError("预留引擎应抛 RuntimeError")
    finally:
        get_settings.cache_clear()


def test_ai_assistant_is_stateful():
    # 契约 §4：ai-assistant 有状态（多轮记忆，§8）
    registry = build_registry(Settings())
    assert registry["ai-assistant"].stateful is True
    assert registry["requirement-pre-review"].stateful is True
    assert registry["ai-test-analysis"].stateful is False
    assert registry["accounting-expert"].stateful is False
    assert registry["business-analyst"].stateful is False


def test_agent_headers_with_token():
    settings = Settings(agent_api_token="secret-token")
    assert agent_headers(settings) == {"X-Agent-Token": "secret-token"}


def test_agent_headers_without_token_is_empty():
    # 未配置 token 时不发送（向后兼容）
    settings = Settings(agent_api_token="")
    assert agent_headers(settings) == {}


def test_registry_contains_five_stable_agent_ids():
    ids = set(build_registry(Settings()).keys())
    assert ids == {
        "requirement-pre-review",
        "ai-test-analysis",
        "accounting-expert",
        "business-analyst",
        "ai-assistant",
    }
