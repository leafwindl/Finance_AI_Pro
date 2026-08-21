const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

const getErrorMessage = async (response) => {
  try {
    const data = await response.json()
    if (typeof data?.error?.message === 'string') return data.error.message
    if (typeof data?.detail?.message === 'string') return data.detail.message
    if (typeof data?.detail === 'string') return data.detail
  } catch { /* response body is not JSON */ }
  return `HTTP ${response.status}`
}

// GET /api/v1/conversations — 拉取会话列表
export async function listConversations({ agentId, limit = 20 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (agentId) params.set('agent_id', agentId)
  const response = await fetch(`${apiBaseUrl}/conversations?${params}`, {
    credentials: 'include'
  })
  if (!response.ok) throw new Error(await getErrorMessage(response))
  return response.json()
}

// GET /api/v1/conversations/{id}/messages — 加载历史消息
export async function getConversationMessages(conversationId) {
  const response = await fetch(`${apiBaseUrl}/conversations/${conversationId}/messages`, {
    credentials: 'include'
  })
  if (!response.ok) throw new Error(await getErrorMessage(response))
  return response.json()
}

// DELETE /api/v1/conversations/{id} — 删除会话及消息
export async function deleteConversation(conversationId) {
  const response = await fetch(`${apiBaseUrl}/conversations/${conversationId}`, {
    method: 'DELETE',
    credentials: 'include'
  })
  if (!response.ok) throw new Error(await getErrorMessage(response))
  return response.json()
}
