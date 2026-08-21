"""LLM prompt 模板 — 联合分段 + 分类（含子类）。

【改进】Prompt 已分离到配置文件，支持版本管理。
默认 Prompt 仍保留在此模块以保证向后兼容。
"""

import os
import json
from pathlib import Path

# 配置文件路径
_PROMPT_CONFIG_PATH = os.getenv(
    "KB_PROMPT_CONFIG",
    str(Path(__file__).parent.parent / "config" / "prompts.json")
)

def load_prompt(prompt_name: str, default: str) -> str:
    """从配置文件加载 Prompt（支持版本管理、动态修改）。
    
    Args:
        prompt_name: 配置键名（如 "segment_classify"）
        default: 找不到配置时的默认值
    
    Returns:
        Prompt 文本
    """
    if not os.path.exists(_PROMPT_CONFIG_PATH):
        return default
    
    try:
        with open(_PROMPT_CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get(prompt_name, default)
    except Exception:
        return default

# ============================================================================
# 【保留】默认 Prompt（用于向后兼容和离线运行）
# ============================================================================

DEFAULT_SEGMENT_CLASSIFY_PROMPT = """你是 P1 证券知识库专家。你的任务有两步：
1. 将下面这段文本拆分为独立的知识点（chunk），每个 chunk 是一段可以独立理解的知识
2. 将每个 chunk 分类到六个知识库之一，并标注子类

## 六库及子类定义

KB01 系统业务知识库 — 回答"系统怎么工作"：
  KB01-01 系统概览：系统整体定位与边界
  KB01-02 模块说明：ACCOUNT/ORDER_SINGLE/ORDER_BATCH/PERMISSION/RISK 等模块职责
  KB01-03 功能说明：核心功能点详细说明
  KB01-04 业务规则：RULE-GEM-xxx 编号的强制性约束条款
  KB01-05 业务流程：端到端流程、公共校验流程
  KB01-06 接口说明：API-ACCOUNT-001/API-PERM-001/API-RISK-001/API-ORDER-001 等接口
  KB01-07 依赖关系：模块间调用链与降级原则
  KB01-08 错误码：E401/E403/E409/E413/E422/E503/E601/E602 等固定错误码
  KB01-09 版本变化：V1.0→V1.1→V1.2 等版本演变

KB02 法规与合规规则库 — 回答"法规要求了什么"：
  KB02-01 官方法规条款：证监会管理办法、实施办法
  KB02-02 交易所业务规则：交易所业务指南、交易规则
  KB02-03 官方技术规范：技术改造与仿真测试公开依据
  ⚠️ KB02 内容必须 needs_review=true（法规需人工复核版本效力）

KB03 历史需求与评审案例库 — 回答"需求怎样从模糊变完整"：
  KB03-01 完整需求修订案例：初始需求→待确认项→定稿需求→验收标准的完整迭代

KB04 标准测试用例库 — 回答"怎么测"：
  KB04-01 业务场景测试用例：正常/异常/边界/混合场景
  KB04-02 接口测试用例：单个 API 的输入输出验证
  KB04-03 边界与异常测试用例：边界值、重复提交、格式错误

KB05 历史缺陷与测试经验库 — 回答"哪里容易出错"：
  KB05-01 单个缺陷案例：现象复现→根因分析→修复方案→回归测试→漏测复盘

KB06 测试规范与模板库 — 回答"输出什么格式"：
  KB06-01 需求完整性检查规范：需求预评审检查清单
  KB06-02 测试分析输出规范：六维测试分析输出格式
  KB06-03 测试用例设计规范：用例设计标准
  KB06-04 测试用例评审规范：用例质量门禁
  KB06-05 测试步骤书写规范：操作与证据要求
  KB06-06 缺陷书写规范：复现/修复/回归规范

## 分段规则

1. 按主题自然切分，每段 100-500 字
2. 如果原文有编号或标题（如"错误码："、"规则编号："、"用例编号："），优先以此作为分段边界
3. 同一主题的连续内容合并为一段
4. 每段必须包含完整信息，能脱离上下文独立理解

## 分类规则

1. 按核心主题分类，不是按标题关键词机械匹配
2. 一段可能涉及多个 KB，primary_kb 选占比最大的
3. confidence 低于 0.5 时 needs_review=true
4. sub_category 尽量匹配到子类，不确定时可留空

## 输出格式

严格输出 JSON 数组，不要任何其他内容：

[{
  "title": "知识点简短标题（≤20字）",
  "content": "知识点原文（从输入文本中摘取）",
  "primary_kb": "KB01",
  "sub_category": "KB01-04",
  "secondary_kb": [],
  "confidence": 0.95,
  "keywords": ["业务规则", "权限校验"],
  "needs_review": false,
  "legal_ref": ""
}]

sub_category 填写规则：
- KB01 → KB01-01 ~ KB01-09
- KB02 → KB02-01 ~ KB02-03
- KB03 → KB03-01
- KB04 → KB04-01 ~ KB04-03
- KB05 → KB05-01
- KB06 → KB06-01 ~ KB06-06
- 无法确定子类时填空字符串 ""

如果文本中没有可提取的知识点，返回空数组 []。"""


# ============================================================================
# 【动态加载】支持从配置文件覆盖 Prompt
# ============================================================================

SEGMENT_CLASSIFY_PROMPT = load_prompt("segment_classify", DEFAULT_SEGMENT_CLASSIFY_PROMPT)


def build_segment_prompt(text: str, source_name: str = "") -> str:
    """构建分段+分类请求（使用动态加载的 Prompt）。"""
    header = f"文档来源：{source_name}\n\n" if source_name else ""
    # 如果文本太长，截取前 6000 字符（约 3000 tokens）
    truncated = text[:6000]
    suffix = "\n\n（文本较长，已截取前 6000 字符）" if len(text) > 6000 else ""
    return f"{header}请对以下文本进行分段和分类：\n\n{truncated}{suffix}"
