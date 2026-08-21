const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

// randomUUID is unavailable in some browsers on plain HTTP public origins.
// Keep client message IDs available until the public site is moved to HTTPS.
const createClientMessageId = () => {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 12)}`
}

const getErrorMessage = async (response) => {
  try {
    const data = await response.json()

    if (typeof data?.error?.message === 'string') {
      return data.error.message
    }

    if (typeof data?.detail === 'string') {
      return data.detail
    }

    if (typeof data?.detail?.message === 'string') {
      return data.detail.message
    }
  } catch {
    // Fall back to the HTTP status when the response is not JSON.
  }

  return `HTTP ${response.status}`
}

/**
 * Upload a single file via multipart form data.
 * POST /api/v1/files/upload
 */
export async function uploadFile(file, agentId = '', signal) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('agent_id', agentId)

  const response = await fetch(`${apiBaseUrl}/files/upload`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
    signal
  })

  if (!response.ok) {
    throw new Error(await getErrorMessage(response))
  }

  return response.json()
}

/**
 * Send a chat message with streaming SSE response.
 * POST /api/v1/chat
 * Returns an async iterable yielding { event, data } objects.
 */
export async function sendChatMessage({
  query,
  conversation_id = null,
  agent_id,
  file_ids = [],
  client_message_id = createClientMessageId(),
  signal
}) {
  const body = {
    query,
    conversation_id: conversation_id || null,
    agent_id,
    file_ids,
    client_message_id
  }

  const response = await fetch(`${apiBaseUrl}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream'
    },
    credentials: 'include',
    body: JSON.stringify(body),
    signal
  })

  if (!response.ok) {
    throw new Error(await getErrorMessage(response))
  }

  return parseSseStream(response.body)
}

async function* parseSseStream(body) {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const parseBlock = (block) => {
    let event = 'message'
    const dataLines = []
    for (const rawLine of block.split(/\r?\n/)) {
      if (rawLine.startsWith('event:')) event = rawLine.slice(6).trim() || 'message'
      if (rawLine.startsWith('data:')) dataLines.push(rawLine.slice(5).trimStart())
    }
    if (dataLines.length === 0) return null
    try {
      return { event, data: JSON.parse(dataLines.join('\n')) }
    } catch {
      return null
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })

    while (true) {
      const match = buffer.match(/\r?\n\r?\n/)
      if (!match || match.index == null) break
      const block = buffer.slice(0, match.index)
      buffer = buffer.slice(match.index + match[0].length)
      const parsed = parseBlock(block)
      if (parsed) yield parsed
    }

    if (done) break
  }

  if (buffer.trim()) {
    const parsed = parseBlock(buffer)
    if (parsed) yield parsed
  }
}

export async function fetchAgentCapabilities() {
  const response = await fetch(`${apiBaseUrl}/agents`, { credentials: 'include' })
  if (!response.ok) throw new Error(await getErrorMessage(response))
  return response.json()
}

/**
 * 审批决策
 * POST /api/v1/chat/approve
 */
export async function sendApproval({ conversation_id, approval_id, decision, reason = '' }) {
  const body = { conversation_id, approval_id, decision, reason }

  const response = await fetch(`${apiBaseUrl}/chat/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(body)
  })

  if (!response.ok) {
    throw new Error(await getErrorMessage(response))
  }

  return response.json()
}

/**
 * Health check endpoint.
 * GET /api/v1/health
 */
export async function healthCheck() {
  const response = await fetch(`${apiBaseUrl}/health`, {
    credentials: 'include'
  })

  if (!response.ok) {
    throw new Error(await getErrorMessage(response))
  }

  return response.json()
}
