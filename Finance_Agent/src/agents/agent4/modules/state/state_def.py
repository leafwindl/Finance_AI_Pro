from typing import TypedDict, List, Optional, Dict

# 单条知识库检索任务结构
class KbTask(TypedDict):
    kb_codes: List[str]      # Finance KnowledgeBase 编码
    query: str               # 检索query，无匹配则为空字符串
    need_search: bool        # True执行检索 / False跳过检索

# 工作流全局上下文，所有节点共用
class WorkflowState(TypedDict):
    query: str                      # 用户输入/用例标题（供 LLM 生成步骤兜底）
    test_case: Optional[dict]       # 结构化测试用例（唯一输入）
    doc_content: str                # 用户上传文档内容（可选，无文档则为空字符串）
    kb_keywords: Dict[str, List[str]]  # 按知识库分组的关键词，如{"KB01":["考勤"],"KB04":[],...}
    kb_task_list: List[KbTask]      # 知识库路由分发任务列表
    rag_docs: List[str]             # 知识库检索返回文本
    llm_json_raw: str               # LLM输出原始JSON字符串
    parse_data: Optional[list]      # JSON转Python解析后的字典
    is_success: int                 # 状态标识：1成功 / 0失败
    output_text: str                # 最终输出文本
    error_msg: str                  # 错误信息
    progress_msg: str               # 前端进度提示