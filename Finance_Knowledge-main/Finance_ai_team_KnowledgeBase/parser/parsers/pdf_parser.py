"""PDF 文件解析器（stub）。

部署前需安装: pip install pdfplumber

PDF 提取策略：
  1. 优先提取嵌入的文本层（pdfplumber）
  2. 文本为空时降级为 OCR（pytesseract + pdf2image）
  3. 保留页级元数据
"""

from pathlib import Path

from parser.parsers.base import BaseParser, ParsedDocument


class PdfParser(BaseParser):
    """解析 .pdf 文件。"""

    FORMAT = "pdf"
    SUPPORTED_EXTENSIONS = [".pdf"]
    SUPPORTED_MIMETYPES = ["application/pdf"]

    def parse(self, file_path: Path) -> ParsedDocument:
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        try:
            import pdfplumber
            text_parts = []
            total_pages = 0

            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

            content = "\n\n".join(text_parts)

            # 基本清洗：合并多余空行
            import re
            content = re.sub(r"\n{4,}", "\n\n\n", content)

            return ParsedDocument(
                content=content,
                source_path=str(file_path),
                source_format="pdf",
                content_hash=self._compute_hash(content),
                metadata={"pages": total_pages},
            )

        except ImportError:
            raise ImportError(
                "解析 PDF 需要安装 pdfplumber: pip install pdfplumber"
            )
        except Exception as e:
            raise RuntimeError(f"PDF 解析失败 ({file_path.name}): {e}")
