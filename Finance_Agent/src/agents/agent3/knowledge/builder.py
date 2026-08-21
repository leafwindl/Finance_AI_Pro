# src/knowledge/builder.py
"""
知识库构建 CLI — 一键构建三维知识库

用法：
  python -m src.knowledge.builder

将扫描 docs/ 下的三个子目录，为每个目录创建 ChromaDB collection：
  docs/history_defects/  →  kb_history_defects
  docs/standard_cases/   →  kb_standard_cases
  docs/test_specs/       →  kb_test_specs
"""
from .store import build_collections

if __name__ == "__main__":
    print("=" * 50)
    print("  三维知识库构建工具")
    print("=" * 50)
    print()
    build_collections()
