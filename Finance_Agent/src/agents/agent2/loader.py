"""加载器 — 环境初始化 (bootstrap) + 知识库加载 (KnowledgeBaseLoader)"""

import os, re, sys
from pathlib import Path
from typing import List

from langchain_core.documents import Document

_modular_agent_dir = Path(__file__).resolve().parent
_project_root = _modular_agent_dir.parent.parent   # Finance_Agent/（原为 .parent 指向 src/agents，.env 加载不到）
_DEFAULT_KB_DIR = _modular_agent_dir / "knowledge_base" / "example"
_bootstrap_done = False


# ================================================================
# 环境初始化（独立函数，不涉及知识库）
# ================================================================
def bootstrap() -> None:
    """一次性环境初始化：编码、路径、.env、API Key 校验。"""
    global _bootstrap_done
    if _bootstrap_done:
        return
    _bootstrap_done = True

    sys.stdout.reconfigure(encoding="utf-8")

    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

    from dotenv import load_dotenv
    load_dotenv(_project_root / ".env")

    if not os.environ.get("DEEPSEEK_API_KEY") and not os.environ.get("OLLAMA_BASE_URL"):
        print("[错误] 请在 .env 文件中设置 DEEPSEEK_API_KEY（或 OLLAMA_BASE_URL）")
        sys.exit(1)


# ================================================================
# 知识库加载器
# ================================================================
class KnowledgeBaseLoader:
    """知识库加载器：切分 .md 文件 → 写入 HybridRetriever 文档存储。"""

    def __init__(self, kb_dir: Path | None = None) -> None:
        self.kb_dir = kb_dir or _DEFAULT_KB_DIR
        self._init_done: bool = False

    # ---- 文本切分 ----
    @staticmethod
    def _split_by_headers(content: str, max_chars: int = 800) -> list[str]:
        parts = re.split(r'\n(?=## )', content)
        chunks: list[str] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(part) <= max_chars:
                chunks.append(part)
            else:
                paragraphs = part.split('\n\n')
                buf = ""
                for p in paragraphs:
                    p = p.strip()
                    if not p:
                        continue
                    if len(p) > max_chars:
                        if buf.strip():
                            chunks.append(buf.strip())
                            buf = ""
                        for i in range(0, len(p), max_chars):
                            chunks.append(p[i : i + max_chars].strip())
                    elif len(buf) + len(p) + 2 > max_chars:
                        chunks.append(buf.strip())
                        buf = p
                    else:
                        buf = buf + "\n\n" + p if buf else p
                if buf.strip():
                    chunks.append(buf.strip())
        return chunks

    # ---- 文件读取 ----
    def _load_files(self) -> list[Document]:
        docs: list[Document] = []
        md_files = sorted(self.kb_dir.rglob("*.md"))
        if not md_files:
            print(f"  [警告] 在 {self.kb_dir} 下未找到任何 .md 文件")
            return docs
        for filepath in md_files:
            try:
                content = filepath.read_text(encoding="utf-8")
            except Exception as e:
                print(f"  [跳过] {filepath.name}: {e}")
                continue
            if not content.strip():
                continue
            kb_folder = (
                filepath.parent.name if filepath.parent != self.kb_dir else ""
            )
            kb_code = kb_folder[:4] if kb_folder.startswith("KB") else ""
            meta = {
                "source": str(filepath.relative_to(self.kb_dir)),
                "filename": filepath.name,
                "kb_code": kb_code,
            }
            for chunk in self._split_by_headers(content):
                docs.append(Document(page_content=chunk, metadata=meta))
        return docs

    # ---- 公开入口 ----
    def load(self) -> None:
        """加载知识库到默认检索器中（幂等）。

        KB_BASE_URL 有值时跳过本地加载，检索走下游 REST API。
        """
        if self._init_done:
            return
        self._init_done = True

        if os.environ.get("KB_BASE_URL", ""):
            print("[初始化] KB_BASE_URL 已配置，使用下游 REST API，跳过本地知识库加载\n")
            return
        if os.environ.get("ALLOW_LOCAL_KB_FALLBACK", "false").lower() != "true":
            print("[初始化] 未启用本地知识库降级，跳过示例知识加载\n")
            return

        from .handlers.retriever import default_retriever

        print("[初始化] 正在加载知识库...")
        if not self.kb_dir.exists():
            print(f"  [警告] 知识库文件夹不存在: {self.kb_dir}")
            return
        docs = self._load_files()
        print(f"  读取到 {len(docs)} 个文本块")
        store = default_retriever.get_store("default")
        store.extend(docs)
        print(
            f"  [加载完成] 共 {len(store)} 块"
            "（首次问答会计算 embedding 并缓存，后续秒加载）\n"
        )


# 模块级默认实例
default_loader = KnowledgeBaseLoader()
