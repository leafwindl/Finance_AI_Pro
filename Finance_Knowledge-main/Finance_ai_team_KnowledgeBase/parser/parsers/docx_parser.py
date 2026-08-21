"""DOCX 文件解析器（stub）。

部署前需安装: pip install python-docx

提取策略：
  1. 逐段落提取文本
  2. 保留标题样式信息（Heading 1/2/3 → # / ## / ###）
  3. 表格内容转为 Markdown 表格
"""

from pathlib import Path

from parser.parsers.base import BaseParser, ParsedDocument


class DocxParser(BaseParser):
    """解析 .docx 文件。"""

    FORMAT = "docx"
    SUPPORTED_EXTENSIONS = [".docx"]
    SUPPORTED_MIMETYPES = [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]

    def parse(self, file_path: Path) -> ParsedDocument:
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        try:
            from docx import Document

            doc = Document(file_path)
            lines = []

            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    lines.append("")
                    continue

                # 根据样式添加 Markdown 标题标记
                style_name = para.style.name if para.style else ""
                if style_name.startswith("Heading 1"):
                    lines.append(f"# {text}")
                elif style_name.startswith("Heading 2"):
                    lines.append(f"## {text}")
                elif style_name.startswith("Heading 3"):
                    lines.append(f"### {text}")
                else:
                    lines.append(text)

            content = "\n".join(lines)

            # 提取元数据
            metadata = {}
            if doc.core_properties:
                metadata["author"] = str(doc.core_properties.author or "")
                metadata["title"] = str(doc.core_properties.title or "")

            return ParsedDocument(
                content=content,
                source_path=str(file_path),
                source_format="docx",
                content_hash=self._compute_hash(content),
                metadata=metadata,
            )

        except ImportError:
            raise ImportError(
                "解析 DOCX 需要安装 python-docx: pip install python-docx"
            )
        except Exception as e:
            raise RuntimeError(f"DOCX 解析失败 ({file_path.name}): {e}")
