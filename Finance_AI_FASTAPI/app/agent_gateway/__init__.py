# agent_gateway — Agent 端接口（人员A 负责）
#
# 职责：与外部 LangGraph Agent 服务的 HTTP/SSE 通信
# 文件：
#   client.py   — SSE 流式客户端，调用 /v1/agent/chat
#   registry.py — Agent 注册表（4 个 Agent 的定义）
#   sse.py      — SSE 事件的编码与解析
