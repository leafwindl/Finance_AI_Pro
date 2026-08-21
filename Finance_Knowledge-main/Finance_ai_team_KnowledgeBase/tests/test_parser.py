"""文档解析模块测试。

测试覆盖：loader、cleaner、structure_detector、document_dom、
metadata、markdown_builder、端到端流程。
"""

import json
import sys
import tempfile
from pathlib import Path

# 将项目根目录加入路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

pytest.importorskip(
    "parser.structure_detector",
    reason="legacy DOM parser suite; current parser package only provides loader/cleaner/parsers",
)

from parser.loader import load_document, detect_encoding, RawDocument
from parser.cleaner import clean_text
from parser.structure_detector import (
    HeadingScorer,
    detect_list_item,
    is_labeled_line,
)
from parser.document_dom import DocumentNode, build_dom
from parser.metadata import extract_metadata, DocumentMetadata
from parser.markdown_builder import build_markdown


# ═══════════════════════════════════════════════════════
# 测试辅助函数
# ═══════════════════════════════════════════════════════

def _make_temp_txt(content: str, encoding: str = "utf-8") -> Path:
    tmp = tempfile.NamedTemporaryFile(
        mode="wb", suffix=".txt", delete=False,
    )
    tmp.write(content.encode(encoding))
    tmp.close()
    return Path(tmp.name)


# ═══════════════════════════════════════════════════════
# Loader 测试
# ═══════════════════════════════════════════════════════

def test_detect_encoding_utf8():
    data = "第一章 总则".encode("utf-8")
    result = detect_encoding(data, ["utf-8", "gbk", "gb18030"])
    assert result == "utf-8"


def test_detect_encoding_gbk():
    data = "第一章 总则".encode("gbk")
    result = detect_encoding(data, ["utf-8", "gbk"])
    assert result == "gbk"


def test_detect_encoding_fallback():
    data = b"\xff\xfe\x00\x01"
    result = detect_encoding(data, ["utf-8", "gbk"])
    assert result == "utf-8"


def test_load_document_utf8():
    content = "测试内容\n第二行"
    path = _make_temp_txt(content)
    doc = load_document(path)
    assert "测试内容" in doc.content
    assert doc.encoding == "utf-8"
    path.unlink()


def test_load_document_empty():
    path = _make_temp_txt("")
    doc = load_document(path)
    assert doc.content == ""
    path.unlink()


# ═══════════════════════════════════════════════════════
# Cleaner 测试
# ═══════════════════════════════════════════════════════

def test_clean_blank_lines():
    content = "第一行\n\n\n\n\n第二行"
    result = clean_text(content, max_consecutive_blank_lines=2)
    assert "\n\n\n\n" not in result


def test_clean_tabs():
    content = "标题\t内容"
    result = clean_text(content, tab_to_spaces=4)
    assert "\t" not in result
    assert "    " in result


def test_clean_page_numbers():
    content = "正文内容\n第1页\n继续内容"
    result = clean_text(content, remove_page_numbers=True)
    assert "第1页" not in result


def test_clean_page_slash():
    content = "正文\n1/10\n继续"
    result = clean_text(content, remove_page_numbers=True)
    assert "1/10" not in result


def test_clean_bracket_page():
    content = "正文\n[1]\n继续"
    result = clean_text(content, remove_page_numbers=True)
    assert "[1]" not in result


def test_clean_remove_repeated_title():
    title = "上市公司信息披露管理办法"
    lines = [title] * 10 + ["正文内容"] * 30
    content = "\n".join(lines)
    result = clean_text(content, remove_repeated_title=True)
    assert title not in result


# ═══════════════════════════════════════════════════════
# Structure Detector 测试（多特征评分）
# ═══════════════════════════════════════════════════════

def _make_scorer(**kwargs):
    defaults = dict(
        enable_chapter=True,
        enable_article=True,
        h1_keywords=["重要提示", "摘要", "核心观点"],
        h2_keywords=["投资观点", "行业分析", "风险提示"],
        h3_keywords=["前置环境准备", "操作执行步骤", "阶段 1", "阶段 2"],
        min_length=4,
        max_length=40,
    )
    defaults.update(kwargs)
    return HeadingScorer(**defaults)


def test_score_chapter_heading():
    scorer = _make_scorer()
    level, title = scorer.detect("第一章 总则")
    assert level == 2, f"第一章应为 H2，实际 {level}"


def test_score_chapter_arabic():
    scorer = _make_scorer()
    level, _ = scorer.detect("第1章 总则")
    assert level == 2


def test_score_section_heading():
    scorer = _make_scorer()
    level, _ = scorer.detect("第一节 概述")
    assert level == 2


def test_score_cn_numbered():
    scorer = _make_scorer()
    level, _ = scorer.detect("一、管理原则")
    assert level == 2


def test_score_cn_paren():
    scorer = _make_scorer()
    level, _ = scorer.detect("（一）适用范围")
    assert level == 3


def test_score_article():
    scorer = _make_scorer()
    level, _ = scorer.detect("第一条 为规范上市公司信息披露行为")
    assert level == 3


def test_score_keyword_h1():
    scorer = _make_scorer()
    level, _ = scorer.detect("重要提示")
    assert level == 1


def test_score_keyword_h2():
    scorer = _make_scorer()
    level, _ = scorer.detect("投资观点")
    assert level == 2, f"投资观点应为 H2，实际 {level}"


def test_score_not_heading():
    scorer = _make_scorer()
    level, _ = scorer.detect("这是一段普通正文内容")
    assert level == 0


def test_score_delimiter():
    scorer = _make_scorer()
    level, title = scorer.detect("===== KB01 业务规则 =====")
    assert level == 2
    assert "=====" not in title


def test_score_bracket():
    scorer = _make_scorer()
    level, _ = scorer.detect("【基础头部杂项备注】")
    assert level == 3


def test_score_h3_labeled():
    """标签行 + 关键字匹配 → H3"""
    scorer = _make_scorer()
    level, _ = scorer.detect("前置环境准备：")
    assert level == 3, f"前置环境准备：应为 H3，实际 {level}"


def test_detect_bullet_list():
    result = detect_list_item("- 列表项目")
    assert result is not None
    ordered, idx, content = result
    assert not ordered
    assert content == "列表项目"


def test_detect_ordered_list():
    result = detect_list_item("1. 第一步")
    assert result is not None
    ordered, idx, content = result
    assert ordered
    assert idx == "1"


def test_is_labeled_line_positive():
    result = is_labeled_line("文档 ID：BIZ-GEM-014")
    assert result is not None
    _full, label, content = result
    assert label == "文档 ID"


def test_is_labeled_line_with_space():
    result = is_labeled_line("步骤 1：登录测试账户")
    assert result is not None
    _full, label, _ = result
    assert "步骤 1" in label


# ═══════════════════════════════════════════════════════
# Document DOM 测试
# ═══════════════════════════════════════════════════════

def test_dom_build_basic():
    scorer = _make_scorer()
    text = "第一章 总则\n\n第一条 测试条款\n\n这是正文内容。"
    doc = build_dom(text, scorer, detect_list_item, is_labeled_line, scorer.h3_keywords)
    assert isinstance(doc, DocumentNode)
    assert doc.node_type == "document"
    # 应该有一个 H1 section 和一个 H4 section
    sections = list(doc.iter_sections())
    assert len(sections) >= 2


def test_dom_find_by_level():
    scorer = _make_scorer()
    text = "\n\n".join([
        "===== KB01 业务规则 =====",
        "正文A",
        "===== KB02 合规法规 =====",
        "正文B",
        "===== KB03 需求评审 =====",
    ])
    doc = build_dom(text, scorer, detect_list_item, is_labeled_line, scorer.h3_keywords)
    h2s = doc.find_by_level(2)
    assert len(h2s) == 3, f"应找到 3 个 H2，实际 {len(h2s)}"
    assert "KB01" in h2s[0].title
    assert "KB02" in h2s[1].title
    assert "KB03" in h2s[2].title


def test_dom_paragraph_merging():
    scorer = _make_scorer()
    text = "这是第一行正文\n这是同一段的续文\n\n这是第二段"
    doc = build_dom(text, scorer, detect_list_item, is_labeled_line, scorer.h3_keywords)
    # 第一段应该是合并的
    paras = [c for c in doc.children if c.node_type == "paragraph"]
    assert len(paras) == 2
    assert "第一行" in paras[0].content
    assert "续文" in paras[0].content


def test_dom_list_items():
    scorer = _make_scorer()
    text = "前置说明\n- 项目1\n- 项目2\n1. 步骤A\n2. 步骤B"
    doc = build_dom(text, scorer, detect_list_item, is_labeled_line, scorer.h3_keywords)
    items = [c for c in doc.children if c.node_type == "list_item"]
    assert len(items) == 4


def test_dom_labeled_lines_separate():
    """标签行不应被合并（可能在 H1 下）"""
    scorer = _make_scorer()
    text = "文档 ID：BIZ-001\n规则编号：RULE-001\n\n正文"
    doc = build_dom(text, scorer, detect_list_item, is_labeled_line, scorer.h3_keywords)
    # H1 section 下找段落（新 H1 逻辑会把文档包装在 H1 下）
    target = doc.children[0] if doc.children and doc.children[0].node_type == "section" else doc
    paras = [c for c in target.children if c.node_type == "paragraph"]
    assert len(paras) == 3, f"标签行应独立，实际 {len(paras)} 个段落"


def test_dom_to_dict():
    scorer = _make_scorer()
    doc = build_dom("第一章 总则\n\n正文。", scorer, detect_list_item, is_labeled_line, scorer.h3_keywords)
    d = doc.to_dict()
    assert d["node_type"] == "document"
    assert len(d["children"]) > 0
    json_str = json.dumps(d, ensure_ascii=False)
    assert "第一章 总则" in json_str


def test_dom_hierarchy():
    """H2 下挂 H3 形成正确父子关系"""
    scorer = _make_scorer()
    text = "===== KB01 业务规则 =====\n正文A\n阶段 1：需求\n内容1"
    doc = build_dom(text, scorer, detect_list_item, is_labeled_line, scorer.h3_keywords)
    h2s = doc.find_by_level(2)
    assert len(h2s) == 1
    # H2 下应有 H3 子节点
    h3_children = [c for c in h2s[0].children if c.node_type == "section" and c.level == 3]
    assert len(h3_children) >= 1, f"H2 下应有 H3 子节点，实际 {len(h3_children)}"


# ═══════════════════════════════════════════════════════
# Metadata 测试
# ═══════════════════════════════════════════════════════

def test_extract_metadata():
    meta = extract_metadata("test.txt", encoding="utf-8")
    assert meta.filename == "test.txt"
    assert meta.encoding == "utf-8"
    assert meta.parser_version == "1.0"


def test_metadata_yaml():
    meta = extract_metadata("测试文件.txt", encoding="gbk")
    yaml_str = meta.to_yaml_frontmatter()
    assert yaml_str.startswith("---")
    assert "测试文件.txt" in yaml_str
    assert "gbk" in yaml_str


# ═══════════════════════════════════════════════════════
# Markdown Builder 测试（DOM 树渲染）
# ═══════════════════════════════════════════════════════

def test_build_markdown_headings():
    scorer = _make_scorer()
    text = "第一章 总则\n\n第一条 测试\n\n正文内容。"
    doc = build_dom(text, scorer, detect_list_item, is_labeled_line, scorer.h3_keywords)
    meta = extract_metadata("test.txt")
    md = build_markdown(doc, meta)
    assert "## 第一章 总则" in md
    assert "### 第一条 测试" in md
    assert "正文内容。" in md


def test_build_markdown_article_bold():
    scorer = _make_scorer()
    text = "第一条 测试"
    doc = build_dom(text, scorer, detect_list_item, is_labeled_line, scorer.h3_keywords)
    meta = extract_metadata("test.txt")
    md = build_markdown(doc, meta, article_style="bold")
    assert "**第一条 测试**" in md
    assert "#### 第一条 测试" not in md


def test_build_markdown_list():
    scorer = _make_scorer()
    text = "- 项目1\n2. 项目2"
    doc = build_dom(text, scorer, detect_list_item, is_labeled_line, scorer.h3_keywords)
    meta = extract_metadata("test.txt")
    md = build_markdown(doc, meta, list_marker="-")
    assert "- 项目1" in md
    assert "2. 项目2" in md


def test_build_markdown_hierarchy():
    """验证 DOM 层级正确渲染为 Markdown 缩进"""
    scorer = _make_scorer()
    text = "===== KB01 业务规则 =====\n正文A"
    doc = build_dom(text, scorer, detect_list_item, is_labeled_line, scorer.h3_keywords)
    meta = extract_metadata("test.txt")
    md = build_markdown(doc, meta)
    assert "## KB01 业务规则" in md


# ═══════════════════════════════════════════════════════
# 端到端测试
# ═══════════════════════════════════════════════════════

def _get_project_root():
    return Path(__file__).parent.parent


def _load_project_config():
    import yaml
    config_path = _get_project_root() / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_e2e_regulation():
    """端到端：监管文件（章节识别）"""
    from main import parse_single_file
    config = _load_project_config()
    input_file = _get_project_root() / "input" / "test_regulation.txt"
    output_dir = _get_project_root() / "output"
    result = parse_single_file(input_file, config, output_dir)
    assert result
    assert "## 第一章 总则" in result
    assert "## 第二章 信息披露要求" in result
    assert "### 第一条" in result
    assert "### 第十条" in result
    assert "filename:" in result
    assert "为规范上市公司信息披露行为" in result


def test_e2e_research():
    """端到端：研究报告（非标准标题）"""
    from main import parse_single_file
    config = _load_project_config()
    input_file = _get_project_root() / "input" / "test_research.txt"
    output_dir = _get_project_root() / "output"
    result = parse_single_file(input_file, config, output_dir)
    assert result
    assert "# 重要提示" in result
    assert "# 摘要" in result
    assert "## 投资观点" in result
    assert "## 行业分析" in result
    assert "## 风险提示" in result
    assert "第1页" not in result
    assert "第2页" not in result


def test_e2e_complex_list():
    """端到端：复杂列表（嵌套结构）"""
    from main import parse_single_file
    config = _load_project_config()
    input_file = _get_project_root() / "input" / "test_complex_list.txt"
    output_dir = _get_project_root() / "output"
    result = parse_single_file(input_file, config, output_dir)
    assert result
    assert "## 一、管理原则" in result
    assert "### （一）适用范围" in result
    assert "## 二、操作流程" in result
    assert "- 业务申请表" in result
    assert "1. 部门初审" in result
    assert "4. 终审批复" in result


def test_e2e_dom_split_by_h2():
    """端到端：test6 DOM 按 H2 切分对应 KB01-KB06"""
    from main import parse_document_from_file
    config = _load_project_config()
    result = parse_document_from_file(
        _get_project_root() / "input" / "test6.txt", config,
    )
    assert result.success
    h2s = result.dom.find_by_level(2)
    assert len(h2s) == 6, f"test6 应有 6 个 H2，实际 {len(h2s)}"
    # 验证六库对应关系
    keywords = ["KB01", "KB02", "KB03", "KB04", "KB05", "KB06"]
    for kw in keywords:
        found = any(kw in h2.title for h2 in h2s)
        assert found, f"未找到 {kw} 对应的 H2 段落"


# ═══════════════════════════════════════════════════════
# parse_document() 纯函数接口测试
# ═══════════════════════════════════════════════════════

def test_parse_document_basic():
    from main import parse_document, ParseResult
    content = "第一章 总则\n\n第一条 测试内容\n\n这是一段正文。"
    result = parse_document(content, filename="test.txt")
    assert isinstance(result, ParseResult)
    assert result.success
    assert result.markdown
    assert result.dom is not None
    assert result.metadata.filename == "test.txt"
    assert "## 第一章 总则" in result.markdown


def test_parse_document_empty():
    from main import parse_document
    result = parse_document("", filename="empty.txt")
    assert result.success
    assert result.markdown == ""


def test_parse_document_dom_export():
    """ParseResult.dom 可 JSON 序列化"""
    from main import parse_document
    content = "第一章 总则\n\n第一条 测试条款\n\n正文内容。"
    result = parse_document(content, filename="test.txt")
    d = result.dom.to_dict()
    json_str = json.dumps(d, ensure_ascii=False)
    assert "第一章 总则" in json_str


def test_parse_document_getattr():
    from main import parse_document
    content = "测试正文"
    result = parse_document(content, filename="doc.txt", encoding="gbk")
    assert result.markdown is not None
    assert result.dom is not None
    assert result.metadata is not None
    assert result.raw_document is not None
    assert result.cleaned_text is not None
    assert result.success is True
    assert result.error == ""


# ═══════════════════════════════════════════════════════
# 批量解析测试
# ═══════════════════════════════════════════════════════

def test_batch_parse():
    from main import batch_parse
    config = _load_project_config()
    input_dir = _get_project_root() / "input"
    output_dir = _get_project_root() / "output"
    results = batch_parse(input_dir, output_dir, config)
    assert len(results) >= 3
    assert all(ok for _, ok, _ in results), "所有文件应解析成功"
    for name in ["test_regulation", "test_research", "test_complex_list"]:
        output_file = output_dir / f"{name}.md"
        assert output_file.exists()


# ═══════════════════════════════════════════════════════

def run_all_tests():
    tests = [
        # Loader
        ("编码检测-UTF8", test_detect_encoding_utf8),
        ("编码检测-GBK", test_detect_encoding_gbk),
        ("编码检测-兜底", test_detect_encoding_fallback),
        ("加载UTF8文件", test_load_document_utf8),
        ("加载空文件", test_load_document_empty),
        # Cleaner
        ("清洗-空行合并", test_clean_blank_lines),
        ("清洗-制表符替换", test_clean_tabs),
        ("清洗-页码移除", test_clean_page_numbers),
        ("清洗-分页格式", test_clean_page_slash),
        ("清洗-括号页码", test_clean_bracket_page),
        ("清洗-重复标题", test_clean_remove_repeated_title),
        # Structure Detector（多特征评分）
        ("评分-章标题H1", test_score_chapter_heading),
        ("评分-阿拉伯章", test_score_chapter_arabic),
        ("评分-节标题H2", test_score_section_heading),
        ("评分-中文编号H2", test_score_cn_numbered),
        ("评分-括号编号H3", test_score_cn_paren),
        ("评分-条款H4", test_score_article),
        ("评分-关键字H1", test_score_keyword_h1),
        ("评分-关键字H2", test_score_keyword_h2),
        ("评分-非标题", test_score_not_heading),
        ("评分-分隔符H2", test_score_delimiter),
        ("评分-括号标题H3", test_score_bracket),
        ("评分-标签H3", test_score_h3_labeled),
        ("评分-无序列表", test_detect_bullet_list),
        ("评分-有序列表", test_detect_ordered_list),
        ("评分-标签行检测", test_is_labeled_line_positive),
        ("评分-标签含空格", test_is_labeled_line_with_space),
        # Document DOM
        ("DOM-基本构建", test_dom_build_basic),
        ("DOM-按级别查找", test_dom_find_by_level),
        ("DOM-段落合并", test_dom_paragraph_merging),
        ("DOM-列表项", test_dom_list_items),
        ("DOM-标签行独立", test_dom_labeled_lines_separate),
        ("DOM-JSON序列化", test_dom_to_dict),
        ("DOM-层级关系", test_dom_hierarchy),
        # Metadata
        ("元数据生成", test_extract_metadata),
        ("YAML frontmatter", test_metadata_yaml),
        # Markdown Builder（DOM 渲染）
        ("Markdown标题", test_build_markdown_headings),
        ("Markdown条款粗体", test_build_markdown_article_bold),
        ("Markdown列表", test_build_markdown_list),
        ("Markdown层级", test_build_markdown_hierarchy),
        # E2E
        ("E2E-监管文件", test_e2e_regulation),
        ("E2E-研究报告", test_e2e_research),
        ("E2E-复杂列表", test_e2e_complex_list),
        ("E2E-DOM按H2切分", test_e2e_dom_split_by_h2),
        # parse_document API
        ("API-基本调用", test_parse_document_basic),
        ("API-空内容", test_parse_document_empty),
        ("API-DOM可导出", test_parse_document_dom_export),
        ("API-字段可访问", test_parse_document_getattr),
        # 批量
        ("批量解析", test_batch_parse),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
            print(f"  [PASS] {name}")
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {name}: {e}")

    print(f"\n{'='*50}")
    print(f"测试完成: {passed} 通过, {failed} 失败 (共 {len(tests)} 项)")
    print(f"{'='*50}")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
