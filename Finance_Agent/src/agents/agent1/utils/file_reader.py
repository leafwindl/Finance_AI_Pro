"""
文件内容提取工具

支持格式:
    .txt / .md     → 直接读取 (无需额外依赖)
    .pdf           → pip install PyPDF2 后才能用
    .docx          → pip install python-docx 后才能用
    .xlsx / .xls   → pip install openpyxl 后才能用

使用示例:
    from utils.file_reader import extract_text
    content = extract_text(file_bytes, filename)
"""

import importlib.util
from io import BytesIO
from typing import Optional


# ================================================================
# 启动时检查可选依赖是否已安装
# ================================================================
_PYPDF2_OK = importlib.util.find_spec("PyPDF2") is not None
_DOCX_OK   = importlib.util.find_spec("docx") is not None
_OPENPYXL_OK = importlib.util.find_spec("openpyxl") is not None


# ================================================================
# 主入口
# ================================================================

def extract_text(file_bytes: bytes, filename: str) -> str:
    """
    根据文件扩展名, 提取文本内容。

    Args:
        file_bytes: 文件的二进制内容
        filename:   原始文件名 (用于判断扩展名)

    Returns:
        提取的文本内容。如果格式不支持或解析失败, 返回空字符串。
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    handlers = {
        "txt":  _read_txt,
        "md":   _read_txt,
        "pdf":  _read_pdf,
        "docx": _read_docx,
        "xlsx": _read_xlsx,
        "xls":  _read_xlsx,
    }

    handler = handlers.get(ext)
    if handler is None:
        return ""  # 不支持的格式, 静默跳过

    try:
        return handler(file_bytes, filename)
    except Exception as e:
        print(f"[文件读取] 解析失败 ({filename}): {e}")
        return ""


# ================================================================
# 各格式处理函数
# ================================================================

def _read_txt(file_bytes: bytes, filename: str) -> str:
    """读取纯文本文件"""
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("gbk", errors="replace")


def _read_pdf(file_bytes: bytes, _filename: str = "") -> str:
    """读取 PDF (需要 pip install PyPDF2)"""
    if not _PYPDF2_OK:
        return "[提示: 需要安装 PyPDF2 才能读取 PDF 文件。pip install PyPDF2]"

    PdfReader = importlib.import_module("PyPDF2").PdfReader
    reader = PdfReader(BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n".join(pages)


def _read_docx(file_bytes: bytes, _filename: str = "") -> str:
    """读取 Word 文档 (需要 pip install python-docx)"""
    if not _DOCX_OK:
        return "[提示: 需要安装 python-docx 才能读取 Word 文件。pip install python-docx]"

    Document = importlib.import_module("docx").Document
    doc = Document(BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def _read_xlsx(file_bytes: bytes, _filename: str = "") -> str:
    """读取 Excel 文件 (需要 pip install openpyxl)"""
    if not _OPENPYXL_OK:
        return "[提示: 需要安装 openpyxl 才能读取 Excel 文件。pip install openpyxl]"

    load_workbook = importlib.import_module("openpyxl").load_workbook
    wb = load_workbook(BytesIO(file_bytes), data_only=True)
    rows = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows.append(f"--- 工作表: {sheet_name} ---")
        for row in ws.iter_rows(values_only=True):
            row_text = "\t".join(str(cell or "") for cell in row)
            if row_text.strip():
                rows.append(row_text)
    return "\n".join(rows)
