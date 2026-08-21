"""
测试步骤生成智能体 — 工作流状态 (v2: 支持结构化 test_case 输入)
"""
from typing import TypedDict, List, Optional, Dict


class KbTask(TypedDict):
    kb_codes: List[str]
    query: str
    need_search: bool


class WorkflowState(TypedDict):
    query: str                          # 用户原始输入（兼容旧接口）
    test_case: Optional[dict]           # 结构化测试用例（新接口主输入）
    doc_content: str                    # 用户上传文档内容
    keywords: List[str]                 # 提取的扁平关键词列表
    kb_keywords: Dict[str, List[str]]   # 按知识库分组关键词 {"KB01":["考勤"], "KB04":[], ...}
    kb_task_list: List[KbTask]          # 知识库路由分发任务列表
    rag_docs: List[str]                 # 知识库检索返回文本
    llm_json_raw: str                   # LLM 输出原始 JSON 字符串
    parse_data: Optional[list]          # JSON 解析后的步骤数组
    is_success: int                     # 1=成功 / 0=失败
    output_text: str                    # 最终输出文本（Markdown 表格）
    error_msg: str                      # 错误信息
    progress_msg: str                   # 前端进度提示
