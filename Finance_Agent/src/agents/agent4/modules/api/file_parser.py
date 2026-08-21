from pathlib import Path
from fastapi import UploadFile, HTTPException


async def extract_text_from_file(file: UploadFile) -> str:
    """
    从上传的文档中提取纯文本内容。
    支持格式：.txt / .pdf / .docx
    """
    if not file.filename:
        return ""

    ext = Path(file.filename).suffix.lower()

    if ext not in (".txt", ".pdf", ".docx"):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式：{ext}，仅支持 .txt .pdf .docx"
        )

    raw_bytes = await file.read()

    # .txt：直接 UTF-8 解码
    if ext == ".txt":
        return raw_bytes.decode("utf-8", errors="replace")

    # .pdf：用 PyMuPDF 提取文本
    if ext == ".pdf":
        try:
            import fitz
            doc = fitz.open(stream=raw_bytes, filetype="pdf")
            texts = []
            for page in doc:
                texts.append(page.get_text())
            doc.close()
            return "\n".join(texts)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"PDF 解析失败：{str(e)}"
            )

    # .docx：用 python-docx 提取段落文本
    if ext == ".docx":
        try:
            from io import BytesIO
            import docx
            doc = docx.Document(BytesIO(raw_bytes))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"DOCX 解析失败：{str(e)}"
            )

    return ""
