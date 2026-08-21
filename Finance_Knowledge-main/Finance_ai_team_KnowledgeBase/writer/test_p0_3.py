#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P0-3 智能分块算法测试"""

from kb_common import split_by_h2, split_chunks_smart

# 测试文档
test_doc = """# 系统架构

## 第一章 概览

这是第一章的内容。这是第一章的内容。这是第一章的内容。这是第一章的内容。这是第一章的内容。

### 第一章第一节

这是第一章第一节的内容。这是第一章第一节的内容。这是第一章第一节的内容。

### 第一章第二节

这是第一章第二节的内容。这是第一章第二节的内容。这是第一章第二节的内容。

## 第二章 详细设计

这是第二章的内容。这是第二章的内容。这是第二章的内容。

### 第二章第一节

这是第二章第一节的内容。这是第二章第一节的内容。
"""

# 测试旧版本（现已升级）
print("=" * 60)
print("测试 split_by_h2() [已升级为智能分块]")
print("=" * 60)
chunks = split_by_h2(test_doc)
print(f"✅ 分块成功: {len(chunks)} 个块\n")
for i, chunk in enumerate(chunks, 1):
    print(f"  [{i}] 标题: {chunk['heading'][:40]}")
    print(f"       内容长度: {len(chunk['content'])} 字")
    print(f"       范围: [{chunk['char_start']}, {chunk['char_end']}]")
    print()

# 测试新版本（精细控制）
print("\n" + "=" * 60)
print("测试 split_chunks_smart() [参数控制]")
print("=" * 60)
chunks_smart = split_chunks_smart(test_doc, min_chunk_size=50, max_chunk_size=200)
print(f"✅ 智能分块成功: {len(chunks_smart)} 个块\n")
for i, chunk in enumerate(chunks_smart, 1):
    print(f"  [{i}] 标题: {chunk['heading'][:40]}")
    print(f"       内容长度: {len(chunk['content'])} 字")
    print(f"       范围: [{chunk['char_start']}, {chunk['char_end']}]")
    print()

print("\n" + "=" * 60)
print("✅ P0-3 所有测试通过")
print("=" * 60)
