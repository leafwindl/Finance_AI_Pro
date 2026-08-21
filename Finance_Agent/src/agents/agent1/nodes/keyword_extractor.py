"""
关键词提取节点

对应 Dify 节点: 1784683782106 (关键词提取llm)
功能: 从用户需求中提取多领域关键词, 用于智能路由到不同的知识库

核心能力:
    - 识别核心业务操作
    - 联想关联的合规/风险/测试/历史领域关键词
    - 生成 kb_code_list 用于知识库路由

结构化输出:
    {
      "biz_keywords": "业务功能关键词 (逗号分隔)",
      "test_keywords": "测试与质量关键词 (逗号分隔)",
      "regulatory_keywords": "合规与监管关键词 (逗号分隔)",
      "history_keywords": "历史经验关键词 (逗号分隔)",
      "kb_code_list": ["business_kb", "regulatory_kb", ...] 或 []
    }
"""

from typing import Optional
from pydantic import BaseModel, Field
from ..state import RequirementState
from .llm_config import llm
from ..prompts import KEYWORD_EXTRACTION_SYSTEM_PROMPT


# ================================================================
# Pydantic 模型: 关键词提取的结构化 Schema
# 对应 Dify 中 1784683782106 的 structured_output.schema
# ================================================================

class KeywordExtractionResult(BaseModel):
    """关键词提取的完整输出"""
    biz_keywords: str = Field(
        default="",
        description="业务功能相关的关键词，如开户、转账、委托下单、撤单、清算、持仓、资金划转等。若无则留空字符串"
    )
    test_keywords: str = Field(
        default="",
        description="测试与质量相关的关键词，如边界值、并发、幂等、超时重试、回归测试、缺陷、性能、异常等。若无则留空字符串"
    )
    regulatory_keywords: str = Field(
        default="",
        description="合规与监管相关的关键词，如反洗钱、KYC、适当性管理、投资者保护、信息披露、涨跌幅限制、T+0/T+1、交收规则等。若无则留空字符串"
    )
    history_keywords: str = Field(
        default="",
        description="历史经验相关的关键词，如历史需求、过往变更、版本迭代、历史故障、线上事故、已知问题、重复缺陷等。若无则留空字符串"
    )
    kb_code_list: list[str] = Field(
        default_factory=list,
        description="根据关键词匹配到的目标知识库代码列表。若所有关键词均为空，则返回空数组[]"
    )


# ================================================================
# 关键词提取节点
# ================================================================

def extract_keywords(state: RequirementState) -> dict:
    """
    从用户输入中提取多领域关键词, 用于后续知识库路由。

    这是 Dify 工作流中知识检索的前置步骤:
        1. 识别用户需求中的核心业务操作
        2. 联想该操作涉及的合规、测试、历史领域关键词
        3. 生成 kb_code_list 决定检索哪些知识库

    Args:
        state: RequirementState, 包含 user_input 和可选的 file_content

    Returns:
        dict: 包含 biz_keywords, test_keywords, regulatory_keywords,
              history_keywords, kb_code_list
    """
    user_input = state.get("requirement_input", state.get("user_input", ""))

    # ---- 文件内容 (如果有上传) ----
    file_content = state.get("file_content", "")
    file_name = state.get("file_name", "")
    if file_content:
        file_context = (
            f"\n\n### 用户上传的文件内容 ({file_name}):\n"
            f"{file_content[:3000]}"
        )
    else:
        file_context = ""

    # 构造 System Prompt
    system_prompt = KEYWORD_EXTRACTION_SYSTEM_PROMPT.format(
        user_input=user_input,
        file_context=file_context,
    )

    from langchain_core.messages import SystemMessage, HumanMessage

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_input),
    ]

    # 使用结构化输出
    structured_llm = llm.with_structured_output(KeywordExtractionResult, method="json_mode")
    try:
        result: KeywordExtractionResult = structured_llm.invoke(messages)
    except Exception as exc:
        # json_mode 解析失败/限流/超时等 → 降级返回空关键词（触发兜底全库检索，不打断流水线）
        print(f"[关键词提取] [警告] 结构化输出异常 ({exc})，降级返回空关键词")
        return {
            "biz_keywords": "",
            "test_keywords": "",
            "regulatory_keywords": "",
            "history_keywords": "",
            "kb_code_list": [],
        }

    print(f"[关键词提取] 已处理用户输入 ({len(user_input)} 字符)")
    print("[关键词提取] 已完成四类关键词提取")
    print(f"[关键词提取] 知识库路由: {result.kb_code_list or '→ 触发兜底全库检索'}")

    return {
        "biz_keywords": result.biz_keywords,
        "test_keywords": result.test_keywords,
        "regulatory_keywords": result.regulatory_keywords,
        "history_keywords": result.history_keywords,
        "kb_code_list": result.kb_code_list,
    }
